# 03 — 架构方案对比 / Architecture Options

> Stage-1 文档 3/6。**本轮只推荐，不最终决定**——最终选型由人工在 Stage-2 开始前拍板。

---

## 0. 评价标准来自题目本身，不来自「哪个框架更专业」

题目对交付物的要求里有一条决定了整个选型：

> 一份说明：**每条硬约束分别是在代码的哪一层强制的**（不接受「prompt 里让它注意」这种答案）

以及答辩形式：

> 我们会现场追问，包括**直接指着某一段代码问「这行为什么这么写、如果改成 XX 会怎样」**——这段代码不管是不是 AI 生成的，你们都要能讲清楚。

所以本题的架构选型有一个不常见的权重：**可解释性（explainability of the code itself）是一等公民**。一个把控制流藏进框架的方案，即使功能等价，在这道题里也是**减分**的——因为你没法指着一行代码说「就是这里」。

这一点会贯穿下面所有对比。

---

## 1. 方案 A — Raw `google-genai` SDK + Pydantic + 自写状态机 + 自写 policy 层

### 形状

```
CLI (customer)          CLI (operator)
     │                        │
     │  CustomerMessage       │  OperatorCommand
     ▼                        ▼
┌────────────────────────────────────────────┐
│ ① Session / State Store (SQLite)           │  ← 状态在这里，可 sqlite3 直接查
└────────────────┬───────────────────────────┘
                 │  load(customer_id) -> SessionState
                 ▼
┌────────────────────────────────────────────┐
│ ② Pre-gate:  state ∈ {ESCALATED, CLOSED}?  │  ← 是就直接 SILENT，LLM 都不调
└────────────────┬───────────────────────────┘
                 ▼
┌────────────────────────────────────────────┐
│ ③ LLM Perception (唯一一处调用 Gemini)      │
│    输入: 客户消息（作为 data，不拼进指令）   │
│    输出: Perception{intent, dissatisfied,   │
│           suggested_action, draft_reply}    │
│    Pydantic 严格校验；失败 → LLMUnavailable │
└────────────────┬───────────────────────────┘
                 ▼
┌────────────────────────────────────────────┐
│ ④ State Machine (纯函数，无 IO)             │
│    counter 更新 / 强制 escalate 判定        │
└────────────────┬───────────────────────────┘
                 ▼
┌────────────────────────────────────────────┐
│ ⑤ Policy Gate  → Verdict{ALLOW/DENY/...}    │
│    allowlist / state 检查 / rate limit      │
└────────────────┬───────────────────────────┘
                 ▼
┌────────────────────────────────────────────┐
│ ⑥ Executor（唯一出口）                      │
│    入口再查一次 state（choke point）        │
│    显式 dict dispatch，无 getattr           │
│    send() 只在这里存在                      │
└────────────────┬───────────────────────────┘
                 ▼
            Audit Log (JSONL)
```

### 评估

| 维度 | 评价 |
|---|---|
| 架构复杂度 | 低。核心大概 400–600 行 Python |
| 对本题适配度 | **最高**。每条硬约束都能指到具体一行 |
| 两天工作量 | 充裕。半天骨架 + 半天约束 + 半天测试 + 半天文档 |
| debug 难度 | 低。全是自己的栈帧，异常直接指到自己的代码 |
| dependency risk | 最低。`google-genai`（pin `<3.0.0`）+ `pydantic` + 标准库 `sqlite3` |
| Gemini 适配难度 | 低。官方 SDK 直连，structured output 原生支持 |
| state machine 可解释性 | **最高**。`if state is ESCALATED: return SILENT` 就是一行 |
| 确定性约束能否代码层强制 | **能，且能证明**。见 `05` Class A |
| prompt injection 攻击面 | **最小**。只有一处 LLM 调用；ESCALATED 后连这一处都不走 |
| 测试难度 | **最低**。注入 `FakeClock` + `FakeLLM`，全部约束可在无网络下测 |
| 答辩可讲性 | **最高** |

### 缺点（要诚实说）

- 「自己写」听起来不如「用了 LangGraph」显得有技术含量。**但本题的考点恰恰是自己写的那一层**，见第 5 节。
- 如果将来真要扩展成多分支、有循环的复杂 agent 流程，手写编排会开始吃力。本题不会到那一步。

---

## 2. 方案 B — Gemini + LangGraph StateGraph + 自写 policy / executor guard

### 评估

| 维度 | 评价 |
|---|---|
| 架构复杂度 | 中。多一层 graph builder / node / conditional_edges / checkpointer 概念 |
| 对本题适配度 | 中。**能做到，但框架没帮上关键的忙** |
| 两天工作量 | 中。若队友不熟 LangGraph，学习成本会吃掉半天以上 |
| debug 难度 | 中偏高。异常栈会穿过框架内部；state reducer 的合并语义容易踩坑 |
| dependency risk | 中。`langgraph` + `langchain-core` + `langgraph-checkpoint-sqlite`，版本联动 |
| Gemini 适配难度 | 中。走 `langchain-google-genai` 封装，多一层抽象，出问题时要分辨是模型的锅还是封装的锅 |
| state machine 可解释性 | **中偏低**——见下 |
| 确定性约束能否代码层强制 | 能，但**得靠我们自己在 node 里写**，不是框架给的 |
| prompt injection 攻击面 | 与 A 相同（都取决于我们的 gate） |
| 测试难度 | 中。要 mock 图执行或跑整图 |
| 答辩可讲性 | 中 |

### 核心问题：「LangGraph 在这道题里解决了什么真实问题？」

LangGraph 真正提供的能力是四项，逐条对照本题：

| LangGraph 提供 | 本题是否需要 | 结论 |
|---|---|---|
| **图式编排**（分支、循环、并行、多节点路由） | 本题的流程是**线性的**：感知 → 状态转移 → 策略 → 执行。没有需要编排的分支循环 | ❌ 用不上 |
| **Checkpointer 持久化** | 需要持久化，但我们要存的只有 4 个标量字段（state / counter / last_sent_at / updated_at）。用 `SqliteSaver` 存整个 graph state 反而更难当场查看 | ❌ 20 行 SQLite 更合适，且**更可解释** |
| **`interrupt` HITL** | ⚠️ **语义不匹配**——见下 | ❌ |
| **State reducer / 消息累积** | 本题不需要累积消息历史做多轮推理（分类是单条消息级的） | ❌ 用不上 |

**关于 `interrupt` 的语义不匹配（这是否掉方案 B 的关键论证）**：

LangGraph 的 `interrupt` 模型是——图执行到某节点**暂停、等待人类回答、拿到回答后从断点继续本次执行**。这是「审批 gate」的形状（`niti007` 仓库里的两处 `approval_gate` 正是这么用的）。

而本题的 escalate 是完全不同的形状：

```
LangGraph interrupt:   run ──► pause ──► human answers ──► SAME run resumes
本题 escalate:         run ──► 本轮结束，进入 ESCALATED 锁定态
                       （之后每一条客户消息都独立地被静默拒绝，不是「等待」）
                       ──► 人工在某个未来时刻，通过一个完全独立的入口
                           发起 reactivate 事件 ──► 状态解锁
```

把「锁定 + 独立外部事件解锁」硬塞进「暂停 + 恢复本次执行」的模型里，会得到一个别扭且更难解释的实现。而且答辩时评委问「escalated 之后客户又发消息了会怎样」，你得解释 checkpointer 里 pending interrupt 的行为——而不是指着一行 `if state is ESCALATED: return SILENT`。

**结论**：LangGraph 在这道题里唯一的实际收益是「简历上写了 LangGraph」。按提示词里的判据（「如果答案只是『因为它是 Agent 框架，所以显得专业』，则不要采用」），**不采用**。

---

## 3. 方案 C — Google ADK（Agent Development Kit）

### 评估

ADK 确实提供了一个看起来非常对口的机制：`before_tool_callback`。官方文档明确说明，该回调返回一个 `dict` 而不是 `None` 时：

> "Skips the execution of the actual tool function (or sub-agent). The returned `dict` is used as the result of the tool call."

即：**它可以充当一个执行前的确定性 gate**。这在架构形状上和我们要的东西是同构的。

| 维度 | 评价 |
|---|---|
| 架构复杂度 | 高。Agent / Runner / Session / Callback / Tool 一整套概念 |
| 对本题适配度 | 中 |
| 两天工作量 | **风险高**。框架较新，队友大概率没用过 |
| debug 难度 | 高 |
| dependency risk | 高。`google-adk` 版本迭代快 |
| Gemini 适配难度 | 低（这是 Google 自家框架的强项） |
| state machine 可解释性 | 中。状态藏在 ADK Session 里 |
| 确定性约束能否代码层强制 | ⚠️ **能，但保证的性质变了**——见下 |
| 测试难度 | 高 |
| 答辩可讲性 | 低 |

### 否掉方案 C 的关键论证

题目要求约束 3 是 **「代码层面 100% 强制」**。如果我们的 100% 保证依赖于「ADK 一定会在每次 tool 执行前触发 `before_tool_callback`」，那么：

1. 我们查过官方 callbacks 文档，它说回调在「key stages」触发，但**没有明文承诺「每一次 tool 执行前必然触发、无任何旁路」**。
2. 即使它事实上做到了，这个保证也是**第三方框架实现细节**给的，不是我们能证明的。框架升级、某个 code path、某个 sub-agent 分支都可能改变它。
3. 答辩时评委问「你凭什么说 100%」，回答「因为 ADK 文档说 callback 会被调用」是一个明显更弱的答案，且**我们无法当场验证**。

而方案 A 的答案是：**「因为我们的进程里只有一个函数会真的发消息，它在第一行检查 state，而它是私有的，全仓库只有一处调用点，我们可以 grep 给你看」**——这个答案是可当场证伪也可当场证实的。

**这是本题最核心的架构取舍：把 100% 保证建立在自己能证明的东西上，而不是建立在框架承诺上。**

> 顺带一提，这个论证同样适用于方案 B，也适用于任何「用第三方 guardrails 库来满足约束 3」的思路（见 `02` 里的 `aegis` / `NeMo-Guardrails` / `llm-guard`）。

---

## 4. 方案 D（我们补充的）— 混合：Raw SDK 为主 + LangGraph 仅用于画图/文档

「用 LangGraph 定义图但不让它管安全」——听起来两全其美。

**否掉**。理由：混合体是三个方案里**最难解释**的。评委会合理地问「既然安全全在你自己的 gate 里，LangGraph 在这儿干嘛？」，而这个问题没有好答案。如果只是想要一张状态机图，Mermaid 十行就画完了，不需要引一个框架。

---

## 5. 对比总表

| | A：Raw SDK 自写 | B：LangGraph | C：Google ADK | D：混合 |
|---|---|---|---|---|
| 架构复杂度 | ✅ 低 | ⚠️ 中 | ❌ 高 | ❌ 高 |
| 本题适配度 | ✅ 最高 | ⚠️ 中 | ⚠️ 中 | ⚠️ 中 |
| 2 天工作量 | ✅ 充裕 | ⚠️ 紧 | ❌ 有风险 | ❌ 紧 |
| debug 难度 | ✅ 低 | ⚠️ 中高 | ❌ 高 | ❌ 高 |
| 依赖风险 | ✅ 最低 | ⚠️ 中 | ❌ 高 | ❌ 高 |
| 约束能否**被我们证明** | ✅ 能 | ⚠️ 能，但框架没帮忙 | ❌ 依赖框架承诺 | ⚠️ 混乱 |
| 注入攻击面 | ✅ 最小 | = A | ⚠️ 更大（agent loop） | = A |
| 测试难度 | ✅ 最低 | ⚠️ 中 | ❌ 高 | ❌ 中高 |
| **答辩可讲性** | ✅ **最高** | ⚠️ 中 | ❌ 低 | ❌ 最低 |

---

## 6. 本轮推荐（非最终决定）

**推荐方案 A**，理由按重要性排序：

1. **本题的考点就是我们自己写的那一层。** 四条硬约束没有一条是任何框架能替我们满足的——LangGraph 不提供 rolling rate limit，不提供 anomaly counter，不提供「锁定态 + 独立入口解锁」；ADK 的 callback 能当 gate，但它给的保证不是我们能证明的。引框架不会减少我们要写的安全代码，只会在它外面再套一层需要解释的东西。

2. **可解释性在这道题里是评分项，不是附加分。** 答辩形式是「指着代码问为什么」，方案 A 的每条约束都能指到一行。

3. **攻击面最小。** 一处 LLM 调用，一个 executor 出口，一条持久化路径。方案 C 的 agent loop 会引入「模型可以多轮自主调用工具」这个我们并不需要、但必须防的能力。

4. **依赖风险最低。** 三个依赖，全部可 pin。

**但要诚实标注方案 A 的代价**：README 里必须主动回答「你们为什么不用 Agent 框架」，否则会被读成「不会用框架」。正确的表述不是「框架不好」，而是：

> 我们评估过 LangGraph 和 Google ADK。ADK 的 `before_tool_callback` 在形状上确实能充当执行前 gate；LangGraph 的 StateGraph + checkpointer 也能承载状态。我们没有采用，是因为本题要求「约束 3 代码层面 100% 强制」，而把这个 100% 建立在第三方框架的回调触发时机上，我们无法自证。我们选择让「唯一能发消息的函数」在我们自己的进程里、只有一处调用点、可以 grep 给你看。这是一个用「框架能力」换「可证明性」的取舍，如果本题不要求 100% 强制，我们的选择会不一样。

---

## 7. 遗留给 Stage-2 的选型细节

| 问题 | 本轮倾向 | 需要拍板？ |
|---|---|---|
| 一次 LLM 调用还是两次（分类 / 生成回复分开）？ | **两次**——分类调用的 context 里不含任何业务话术与价格信息，从结构上减少可泄漏的内容（对应 `01` SEC-7）。代价是延迟和 quota 翻倍 | ✅ 见 `06` D6 |
| `interactions.create` 还是 `models.generate_content`？ | `models.generate_content` + `response_schema`，因为 `resp.parsed` 直接给 Pydantic 对象 | 否，实现时定 |
| 状态存 SQLite 还是内存？ | SQLite（`01` PS-1） | 否 |
| CLI 还是 Web？ | CLI（题目明说越简单越好） | 否 |

---

*2026-09-02。本轮只推荐，等待人工审查。*
