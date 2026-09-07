# 06 — 第一阶段技术建议 / Stage-1 Recommendation

> Stage-1 文档 6/6。本文件汇总前五份文档的结论，回答提示词第六、七、八、九节的全部问题，并给出 STAGE-1 VERDICT。

---

# 第一部分：提示词第九节的 12 个问题

## 1. 你认为本题真正考什么？

**不是**「会不会做一个销售聊天机器人」，**是**「你知不知道 LLM 在一个系统里应该拥有多少权力」。

拆开来是三个能力：

**① LLM 与代码的职责边界。** 题目用四条硬约束把这件事问得极其具体：速率限制、强制转人工、转人工后静默、动作白名单——每一条都在问同一个问题：**当 LLM 说「我要做 X」时，谁说了算？** 正确答案是「代码说了算，LLM 只是提建议」。题目甚至预先堵死了错误答案：「不接受『prompt 里让它注意』这种答案」。

**② 能不能区分「可以 100% 保证」和「只能 best-effort」。** 这是我认为区分度最大的一点。约束 3 要求 100% 强制，约束 4 明说不要求 100%——**题目自己把这条分界线画出来了，就是在看你能不能读懂它、并解释为什么这两条的性质不同**。答案是：约束 3 的断言对象是代码执行路径，约束 4 的断言对象是自然语言语义，后者不存在可判定谓词。详见 `05`。

**③ 用 AI 但不被 AI 牵着走。** 「会不会在 AI 给错答案时自己发现并纠正」。这一条不是靠讲故事满足的，是靠**真的去验证**满足的——`python3 -m py_compile` 跑一下就知道 README 推荐的仓库其实 import 不了。

还有一个隐藏考点，藏在答辩形式里：**「直接指着某一段代码问『这行为什么这么写』」**。这句话让**可解释性成为架构选型的硬约束**，而不是软性偏好。它直接决定了我们否掉 LangGraph 和 ADK（见 `03`）。

---

## 2. 推荐 Raw SDK / LangGraph / ADK 中哪一个？为什么？

**推荐方案 A：Raw `google-genai` SDK + Pydantic + 自写状态机 + 自写 policy 层。**

一句话理由：**本题的四条硬约束，没有一条是任何框架能替我们满足的；引框架不会减少要写的安全代码，只会在它外面再套一层需要解释的东西。**

逐条验证：

| 硬约束 | LangGraph 提供吗 | ADK 提供吗 |
|---|---|---|
| rolling 60s rate limit | ❌ | ❌ |
| 连续两次 anomaly 强制 escalate | ❌ | ❌ |
| escalated 后锁定 + 独立入口解锁 | ❌ `interrupt` 是「暂停/恢复」语义，**不匹配** | ❌ |
| 四动作 allowlist（100% 强制） | ❌ | ⚠️ `before_tool_callback` 形状对，但**保证来自框架承诺，我们无法自证** |

**关于「LangGraph 在这道题里解决了什么真实问题」**（提示词特别要求回答）：

LangGraph 的四项核心能力——图式编排、checkpointer、`interrupt` HITL、state reducer——在本题里**一项都用不上**：流程是线性的（感知→转移→策略→执行），没有分支循环要编排；要持久化的只有 4 个标量，20 行 SQLite 更合适且**更好当场展示**；`interrupt` 是「暂停等人回答然后恢复本次执行」，而本题的 escalate 是「锁定 + 未来某时刻由独立入口解锁」——**语义不匹配**；也不需要累积消息历史。

所以按提示词自己给的判据——「如果答案只是『因为它是 Agent 框架，所以显得专业』，则不要采用」——**不采用**。

**关于 ADK**：它的 `before_tool_callback` 确实能返回 dict 来跳过 tool 执行，形状是对的。但题目要求约束 3「**代码层面 100% 强制**」，而把这个 100% 建立在「ADK 一定会在每次 tool 执行前触发回调」这个第三方实现细节上，**我们无法自证**——官方文档说回调在「key stages」触发，没有明文承诺无旁路。方案 A 的答案是：「唯一能发消息的函数是私有的，全仓库只有一处调用点，我可以 grep 给你看」。**这是一个用「框架能力」换「可证明性」的取舍，而这道题的评分标准明确站在可证明性一边。**

---

## 3. Top-1 GitHub reference 是哪个？为什么？

**`agent-rails/agent-guard`**（Apache-2.0，pin `ba47d66`）。

但要说清楚它是**哪种意义上的 Top-1**：它是**设计思想**的 Top-1，不是**代码基线**的 Top-1。它 GitHub 上 0 star / 61 commits / 1 fork，README 自称「Early. API will move」。

它教给我们两件具体的、我们自己想不到的事：

1. **滑动窗口里「被拒绝的调用不消耗预算」**——否则会造成自伤型永久静音（`05` T-05）。这是我们从它的 docstring 里学到的，不是自己想到的，已如实记录。
2. **`clock` 作为可注入构造参数**——这是让 60 秒约束能写确定性单测的前提。

加上 `Decision{ALLOW/DENY/REQUIRE_HUMAN}` + `clamp` 单调收紧 + `Verdict.trace()` 审计形状，四样东西几乎一比一映射到本题。

**Top-2**：`googleapis/python-genai` + `google-gemini/cookbook`（官方，Gemini 用法的唯一可信来源）。
**Top-3**：`ntg2208/production-ai-customer-support-langchain`（只取一个点：分类用低温 0.1、生成用高温）。

**降级说明**：前序 AI 上下文推荐的第一候选 `niti007/langgraph-customer-support-agent` **被否掉**——`src/state.py` 有语法错误导致整个包 import 不了，且用的是 OpenAI 不是 Gemini。见 `04` F-3。

---

## 4. 哪些代码值得复用？

**严格来说：一行都不复制。**

这不是洁癖，是三条实际理由：

1. **答辩形式决定的。** 评委会指着代码问「这行为什么这么写」。复制来的代码你答不了，而且这道题的通过条件里明确包含「这段代码不管是不是 AI 生成的，你们都要能讲清楚」。
2. **我们需要的比它们提供的简单得多。** `agent-guard` 的 `VelocityLimiter` 是通用实现（fnmatch 模式匹配、多规则、per-agent-per-tool）。我们只需要 `max_calls=1, window=60, key=customer_id`。**照抄通用实现反而更复杂、更难解释。**
3. **许可证。** `agent-guard` 是 Apache-2.0（另两个是 MIT）。复制需要保留许可证声明 + `NOTICE`。不复制就没这个负担。

**要复用的是「设计决定」，具体是这五条**（会在代码注释里写明出处）：

| 复用的设计 | 出处 |
|---|---|
| 滑动窗口：被拒绝的调用不消耗预算 | `agent-guard/velocity.py` docstring |
| `clock` 可注入（默认 `time.monotonic`） | 同上 |
| 三值 Decision + `clamp` 只能收紧不能放松 | `agent-guard/decision.py` |
| `Verdict` 携带 `module#rule_id@layer :: reason` 的审计形状 | 同上 |
| 分任务用不同温度（分类 0.1 / 生成 0.5） | `ntg2208/config/model_config.py` |

Pydantic `Literal[...]` 约束值域是标准用法，不需要 attribution。

---

## 5. 哪些部分必须我们自己重写？

**全部。** 更有意义的问法是「哪些部分是这道题的核心、必须打磨」：

| 模块 | 为什么必须自己写 |
|---|---|
| **State machine**（ACTIVE / ESCALATED / CLOSED + anomaly counter） | 这是题目考的东西本身。没有任何仓库有这个具体状态机 |
| **Rolling rate limiter** | 需求特殊（1 条/60 秒 + 只有 `reply` 计费 + 被拒不消耗），照抄通用实现反而更复杂 |
| **Policy gate** | 本题的 policy 是「四条硬约束」，与任何通用 guardrails 库的 policy 都不是一回事 |
| **Executor**（唯一出口 + 显式 dispatch + 二次 state 检查） | 100% 保证的落点，必须每一行都能解释 |
| **入口/类型分离**（`CustomerMessage` vs `OperatorCommand`） | 这是我们对 DC-4 的核心答案 |
| **Perception schema + 四步校验链** | fail-closed 的落点 |
| **Adversarial 测试集** | 题目硬性交付物 |

---

## 6. 哪些 GitHub 方案看起来高级但其实不适合本题？

| 方案 | 为什么看起来高级 | 为什么不适合 |
|---|---|---|
| **`filip-michalsky/SalesGPT`** | 最有名的开源 AI 销售 agent，名字和题目几乎一样，464 commits | **方向完全相反**——8 个对话阶段的推进由 LLM 决定（`determine_conversation_stage()`），正是本题明令禁止的「LLM 自己决定状态转移」。无 rate limit、无 action allowlist。**名字最像，最不能用。** |
| **`NVIDIA/NeMo-Guardrails`** | 大厂出品，Colang DSL，"dialog rails" 听起来正对口 | 依赖极重；要学一门 DSL；rails 本身部分依赖 LLM 判定；2 天工期 + 「指着代码问为什么」的答辩形式下是负资产 |
| **`acacian/aegis`** | 761 commits，覆盖 12 个框架，"deterministic regex, no LLM calls" 听起来正是我们要的 | 它的 prompt injection 防御核心是 **85+ 条正则模式**。题目原文：「如果你们的防御思路是『把这几句话对应的关键词列表拦下来』，**大概率不够**」。**它恰好是题目点名说不够的那种方案。** |
| **`guardrails-ai/guardrails`** | 成熟的输出校验框架 | 它的 `reask` 机制（校验失败就让模型重试）与本题 fail-closed 要求**方向相反**——校验失败应该是「不执行」，不是「再问一次」 |
| **`pytector` / `llm-guard` 类** | 语义级注入检测，比正则聪明 | **用不可信组件守卫不可信组件**。检测模型自己也会被注入，且永远是概率性的，给不出题目要求的 100% |
| **Google ADK** | Google 自家框架，`before_tool_callback` 形状完全对口 | 100% 保证来自框架承诺，我们无法自证。见问题 2 |
| **LangGraph** | Agent 领域事实标准 | 四项核心能力本题一项都用不上；`interrupt` 语义不匹配。见问题 2 |
| **`statelyai/agent`** | XState 状态机 + LLM，概念最对口 | **TypeScript only**；且它的状态机是「引导 LLM」不是「约束 LLM 的执行权限」 |

**一个可以总结成一句话的规律**：本题的搜索陷阱是——**关键词匹配度和实际适用度呈负相关**。名字最像的（SalesGPT）方向最反，最对口的（agent-guard）名字完全不沾边。

---

## 7. 本轮发现了哪些 AI 初始方案错误或不足？

完整记录见 `04`。摘要：

**过程性发现（实际核查出来的，附证据）**：

| # | 发现 | 严重度 |
|---|---|---|
| F-1 | ZCode 声称完成 Stage-1，**6 份文档一份都没落盘**，spike 源码也不见了（只剩 `.pyc`） | ⛔ |
| F-2 | API key 明文在仓库根目录，无 `.gitignore`，**而本次笔试要求 repo 必须 public** | ⛔ 安全 |
| F-3 | 前序 AI 推荐的第一候选 `niti007` —— **`state.py` 有语法错误 import 不了**，且用 **OpenAI 不是 Gemini** | ❌ |
| F-4 | 前序 AI 称 `ntg2208` 有 SQLite —— 实际 `graph.py` 默认 `MemorySaver()`，是内存 | ❌ |
| F-5 | ZCode 的 spike 设了 `max_output_tokens` 但没基于 `finish_reason` 分支 → 截断时 `parsed` 为 `None` 且无法区分原因 | ⚠️ |

**设计层面被否掉的、看似合理的方案（每一条都是有人真的会这么写的）**：

| 问题 | 看似合理但错误的写法 | 错在哪 |
|---|---|---|
| 60 秒限制 | 按自然分钟计数 | 12:00:59 + 12:01:00 = 1 秒两条 |
| 60 秒限制 | 把**被拒绝的**发送尝试也记进窗口 | 客户被**永久静音**（自伤型 DoS） |
| anomaly counter | `if 答非所问: +1` / `if 不满: +1` 两行独立 if | 一句「你他妈在说什么」**一次就跳到 2**，违反「连续两次」，且会在答辩开场一分钟被打出来 |
| anomaly counter | LLM 失败时 `counter = 0` | 给攻击者一条**清零计数器**的路径 |
| escalated 静默 | 只在 executor 前检查 | 功能上对，但白烧 quota 且攻击面无谓地敞开 |
| action allowlist | `getattr(executor, f"do_{action}")` | 把**客户可控文本**接到属性解析上。这条边根本不该存在 |
| action allowlist | 用 function calling 声明四个 tool 就算 allowlist | tool schema 限制「模型能提议什么」≠「系统会执行什么」；且**完全不解决「escalated 后不能调用工具」** |
| 结构化输出 | 信任 `response_schema`，不再自校验 | `finish_reason=MAX_TOKENS` / safety filter 都会让 `parsed` 为 `None`；且把安全建立在供应商保证上 |
| 结构化输出 | `data.get("intent", "interested")` | **默认值就是攻击面**——模型不返回时系统自动认为客户有兴趣 |
| API 失败 | 一个大 `try` 包住 llm+policy+executor，`except: pass` | 异常语义不可控，可能跳过 policy |
| 人工重新激活 | 客户发 `/reactivate` 或 `admin:` 前缀 | **把解锁权限交给攻击者**；「逻辑分离」不等于「入口分离」 |
| 人工重新激活 | reactivate 只改 state 不清 counter | counter 仍是 2，客户下一条稍有情绪立刻二次 escalate，人工接管白做 |

共审查 30+ 候选方案，否决 22 个。

---

## 8. 哪些硬约束已经有明确的实现设计？

**四条全部有明确设计，且能说清楚强制点在哪一层：**

| 约束 | 强制层 | 具体位置 | 能否 100% |
|---|---|---|---|
| **① 任意 60 秒 ≤ 1 条** | Policy layer，紧贴 executor | `RateLimiter.try_consume(customer_id)`，deque 滑动窗口，**只在 `send()` 成功后写时间戳**，与 send 同临界区 | ✅ 单进程内 |
| **② 连续两次 anomaly 强制 escalate** | State machine（纯函数） | `transition(state, perception) -> (new_state, forced_action)`；`is_anomaly = irrelevant or dissatisfied`，一条消息最多 +1；counter≥2 → 强制 escalate 且抑制其他动作 | ✅ |
| **③ 四动作 allowlist + escalated 静默** | 三层：schema → policy → executor | Pydantic `Literal` 枚举 → 入口 pre-gate（ESCALATED/CLOSED 直接 SILENT，**不调 LLM**）→ executor 显式 dict dispatch + 第一行二次 state 检查 | ✅ |
| **④ 不泄漏内部信息** | 架构层（最小知识）+ 出站层（canary） | 分类与生成拆两次调用，**两次上下文都不含价格底线/内部规则**；canary UUID 出站检查 | ❌ 只能 best-effort，边界已写清（`05` T-13/T-14） |

---

## 9. 哪些问题目前仍然没有解决？

**A. 5 个需要人工拍板的产品语义决策**（不是技术未知，是选择题，见下面第三部分）。

**B. 3 个真实的技术未知**：

1. **`[未验证]` Gemini 的具体失败模式。** 我们知道要检查 `finish_reason`，但没有实测过 kGroup 给的这个 key 在什么输入下会触发 safety filter、返回什么 `finish_reason`。本轮按人工决定**不调用真实 API**，这条留到 Stage-2 第一步验证。
2. **`[未验证]` 实际可用的模型名。** 官方文档里出现 `gemini-2.5-flash` / `gemini-3.5-flash` / `gemini-3.7-flash` 等多个名字，**实际以 kGroup 的凭证文档为准**。代码必须从环境变量读，不硬编码。
3. **T-15（诱导误分类）没有好的解法。** 这是 `05` 里我们自己判定「最容易被现场打穿」的一条：攻击者不需要越权，只要让 LLM 把明显不满的消息判成正常，counter 就不累加。状态机保证「counter≥2 必然 escalate」，保证不了「LLM 一定判对」。目前只有两条缓解思路（dissatisfied 从宽判定；加纯规则兜底信号），都没验证过效果。

**C. 1 个主动砍掉的**：跨进程并发（`01` PS-5）。要在 README 写明砍掉的理由与补法。

---

## 10. 下一阶段应该只实现什么？

**Stage-2 的唯一目标：一个能跑、四条约束都真的守住、且每条都有测试证明的最小 demo。**

按优先级：

| 优先级 | 内容 |
|---|---|
| **P0（先做，因为不可逆）** | ① `.gitignore` + key 移出仓库 + `.env.example` → ② `git init` → ③ 第一个 commit。**顺序不能反** |
| **P0** | 领域模型（`Intent` / `Action` / `SessionState` 枚举、`Perception` / `Verdict` / `CustomerMessage` / `OperatorCommand` dataclass） |
| **P0** | State machine（纯函数、无 IO、可单测） |
| **P0** | Policy gate + RateLimiter（可注入 clock） |
| **P0** | Executor（唯一出口、显式 dispatch、二次 state 检查） |
| **P0** | SQLite store（显式列） |
| **P1** | Gemini LLM client（Protocol 接口 + 真实实现 + `FakeLLM`），**四步校验链** |
| **P1** | 两个 CLI 入口：`chat`（customer）/ `admin`（operator） |
| **P1** | 确定性单测：60s 边界、counter 序列、双信号 +1、escalated 静默、CLOSED、fail-closed |
| **P1** | Adversarial 测试 ≥3 条（目标 10 条）+ 运行结果存档 |
| **P2** | Audit log（JSONL） |
| **P2** | README + 约束强制点说明文档 + `COLLAB.md` |

**一个建议的时间切分**（2 天参考工作量）：Day-1 上午 P0 全部（骨架 + 状态机 + policy + executor，全部用 FakeLLM 驱动，**先不接真实 API**）；Day-1 下午接 Gemini + 校验链；Day-2 上午测试（确定性 + 对抗）；Day-2 下午文档与打磨。

**为什么先用 FakeLLM**：四条硬约束**没有一条需要真实 LLM 才能测**。先把确定性部分做完做对，接 API 只是最后插上一个实现。这也能保证仓库在没有 key 的机器上仍然 `pytest` 全绿——评委很可能就是这么跑的。

---

## 11. 下一阶段明确不要实现什么？

| 不做 | 理由 |
|---|---|
| Web 前端 / 好看的 UI | 题目：「越简单越好，重点不在这里」 |
| RAG / 向量检索 / 知识库 | 题目没有任何知识问答需求 |
| Multi-agent | 只会扩大攻击面 |
| Redis / Kafka / Postgres | 过度工程，且题目二明确说这个规模用不上 |
| Function calling / tool calling | 不解决任何本题问题，还引入 AFC 版本风险（`04` Q4） |
| LangGraph / ADK / NeMo / 任何 agent 框架 | 见问题 2 |
| 跨进程并发支持 | 主动砍掉，README 写明 |
| Streaming 输出 | 与「发送前拦截」冲突——流式已吐出的字收不回来。这一点值得在 README 提一句 |
| 用户认证 / 多租户 | 不在需求内 |
| 细粒度意图分类（超出 5 类） | 会让 anomaly 判定复杂化，性价比低 |
| 大规模 eval 集 / LLM-as-judge | 超出工作量，不是考点 |

---

## 12. 预计最小 MVP 的模块边界是什么？

```
kapibala-agent/
├── app/
│   ├── domain/
│   │   ├── enums.py          # Intent, Action, SessionState  ← 唯一的动作定义源
│   │   └── models.py         # Perception, Verdict, CustomerMessage, OperatorCommand
│   ├── llm/
│   │   ├── protocol.py       # class LLMClient(Protocol): classify() / draft_reply()
│   │   ├── gemini.py         # 真实实现 + 四步校验链
│   │   └── fake.py           # FakeLLM（测试用，可编程返回值/异常）
│   ├── state/
│   │   ├── machine.py        # transition() 纯函数，无 IO
│   │   └── store.py          # SQLite，显式列
│   ├── policy/
│   │   ├── gate.py           # check() -> Verdict，默认 DENY
│   │   └── rate_limit.py     # 滑动窗口，clock 可注入
│   ├── executor/
│   │   └── executor.py       # 唯一出口。_send() 私有，全仓库唯一调用点
│   ├── audit/
│   │   └── log.py            # JSONL
│   └── interface/
│       ├── customer_cli.py   # handle_customer_message(CustomerMessage)
│       └── operator_cli.py   # handle_operator_command(OperatorCommand)
├── tests/
│   ├── unit/                 # 无网络、无 API key、fake clock
│   ├── integration/          # FakeLLM 驱动的端到端
│   └── adversarial/          # ≥3 条（目标 10）攻击对话 + 期望结果
├── docs/                     # 本 6 份 + 约束强制点说明
├── references/               # .gitignore 排除，不入库
├── .env.example
├── .gitignore
├── COLLAB.md
└── README.md
```

**分层与依赖方向（严格单向，不允许反向 import）**：

```
interface → policy → state → domain
              ↓        ↓
           executor  store
              ↓
            audit
llm 只被 interface 调用；domain 不依赖任何其他层
```

---

# 第二部分：提示词第七节的 9 个尖锐问题

| 问题 | 回答 |
|---|---|
| **LLM 到底拥有哪些权力？** | **只有两项：① 对一条客户消息输出 `intent` + `dissatisfied` + `suggested_action`（建议，非命令）；② 生成一段 `draft_reply` 文本。** 除此之外零权力——不能改状态、不能决定是否转人工、不能决定是否发送、不能访问数据库、不能调用任何函数。 |
| **Policy layer 拥有哪些权力？** | 拒绝（DENY）、放行（ALLOW）、把动作**改写**成 `escalate_to_human`（强制转人工）。它**不能**放松 state machine 已经做出的限制——遵循 `clamp` 的单调收紧原则。 |
| **State machine 在哪里？** | `app/state/machine.py`，一个**纯函数** `transition(current, perception) -> (new_state, forced_action)`。无 IO、无网络、无时间依赖，可以完全用单测穷举。它是 counter 与 ESCALATED/CLOSED 的唯一权威。 |
| **Executor 在哪里？** | `app/executor/executor.py`。它是**唯一出口**：第一行重新检查 state，然后用显式 dict 字面量 dispatch。 |
| **真正「send message」的函数在哪里？** | `app/executor/executor.py::_send()`，**私有函数，全仓库唯一调用点在同文件的 `_do_reply()` 里**。可以 `grep -rn "_send(" app/` 证明只有两处（定义 + 调用）。**这是我们对「100% 强制」的最终答案。** |
| **rate limit 最终在哪一层检查？** | Policy layer 的 `RateLimiter`，但**判定与消耗必须紧贴 `_send()`**——check 与 record 在同一临界区，且**record 只在 send 成功后发生**。不是在「LLM 建议 reply」时检查，也不是在入口检查。 |
| **escalated silence 在哪一层检查？** | **两层**：① 入口 pre-gate（`interface`，在调用 LLM **之前**，ESCALATED/CLOSED 直接返回 SILENT）；② executor 第一行（choke point 自守）。第一层是为了省 quota + 把注入攻击面降到零，第二层是为了防未来新增的代码路径绕过第一层。 |
| **customer input 是否可能直接到达 executor？** | **不可能。** 客户文本只以 `CustomerMessage.text` 的形式存在，它唯一的去向是 LLM 的 prompt data 区。executor 的入参是 `Verdict` + `Action` 枚举 + 一个已生成的 `draft_reply` 字符串——**没有任何一条参数是客户原文**。客户文本可以影响 `draft_reply` 的**内容**（这是设计意图），但影响不了**执行哪个动作**。 |
| **human reactivate 是否与 customer channel 完全分离？** | **是，且是类型层面的分离。** `handle_customer_message(msg: CustomerMessage)` 与 `handle_operator_command(cmd: OperatorCommand)` 是两个函数，客户输入被构造成 `CustomerMessage`，而前者的签名根本不接受 `OperatorCommand`。「客户消息能否变成解锁事件」从运行时问题变成了**类型问题**，可以在代码审查里一眼看出。 |

---

# 第三部分：提示词第六节 —— 「复用 GitHub」该怎么做

## 结论：采用方案 2（干净新仓库 + `references/` 只用于阅读）

对比两种做法：

| | 方案 1：fork/clone 某仓库当基线 | 方案 2：干净新仓库 |
|---|---|---|
| Git history 可读性 | ❌ upstream 数百个 commit 淹没我们的协作证据 | ✅ 每个 commit 都是我们的 |
| 「两人都有实质提交」 | ❌ 混在 upstream 历史里，评委难以分辨 | ✅ 一目了然 |
| 「哪些是 upstream / 哪些是我们的」 | ❌ 需要逐文件解释 | ✅ **答案是「全部是我们的」** |
| 代码是否臃肿 | ❌ 继承大量无关代码（`ntg2208` 有 300KB+ 无关数据） | ✅ 只有需要的 |
| LICENSE / attribution | 复杂 | 简单：`docs/02` 记录读过什么、pin 了哪个 commit |
| 答辩风险 | 高——评委可能指到一段我们没读过的 upstream 代码 | 低 |

题目明确说「commit 历史要能看出**两个人都有实质性提交**」，方案 1 会直接污染这个证据。

## 具体操作规范

1. **`references/` 加入 `.gitignore`，不进入我们的仓库。**
   这同时解决了另一个问题：三个 clone 各自带完整 `.git`，如果 `git add .` 会变成嵌套仓库 / gitlink，把仓库搞乱。

2. **在 `docs/02_GITHUB_SURVEY.md` 里记录 pin 的 commit SHA**（已做）。这样「我们读了什么版本」是可复现的，比把代码 vendor 进来更干净。

3. **不复制代码，只复用设计决定**，并在代码注释里注明出处。例如：

   ```python
   # Sliding-window semantics: a DENIED attempt must NOT be recorded,
   # otherwise repeated attempts extend the window forever and permanently
   # mute the customer (self-inflicted lockout).
   # Design credit: agent-rails/agent-guard @ ba47d66, agent_guard/velocity.py
   ```

   **这种注释在答辩时是加分的**——它证明我们读过真代码、知道出处、且做了自己的取舍。

4. **如果 Stage-2 最终决定复制任何 `agent-guard` 片段**（Apache-2.0）：必须保留许可证声明、在 `THIRD_PARTY.md` 里 attribution、并在 README 说明。**当前建议是不复制。**

5. **不删除任何 upstream 的 LICENSE 文件**（`references/` 里的三个 LICENSE 原样保留）。

---

# 第四部分：提示词第八节 —— Gemini 接口验证

本轮按人工决定**不调用真实 API**，只做文档核对。结论见 `02` §4，摘要：

| 项 | 结论 |
|---|---|
| SDK | `google-genai`，`from google import genai`。**必须 pin `<3.0.0`**（官方提示 3.0 对 AFC 有 breaking change） |
| 调用方式 | `client.models.generate_content(...)` 与 `client.interactions.create(...)` 官方都在维护。**建议用前者** + `config={"response_mime_type":"application/json","response_schema": PerceptionSchema}`，因为 `resp.parsed` 直接给 Pydantic 对象 |
| structured output | ✅ 原生支持，但只支持 JSON Schema 的子集，深嵌套 schema 可能被拒。我们的 schema 只有 4 个扁平字段，安全 |
| function/tool calling | **不需要**（`04` Q4）。不用还能避开 AFC 版本风险 |
| 模型名 | 环境变量读取，**不硬编码**。实际可用模型以 kGroup 凭证文档为准 `[未验证]` |
| API key | `GEMINI_API_KEY` 环境变量 / `.env`（不入库），只提交 `.env.example`。**任何路径不 print** |
| 如何 mock | LLM 封装成 `Protocol`，只有 `classify()` / `draft_reply()` 两个方法。测试注入 `FakeLLM`。**所有确定性测试不碰网络** |
| ⚠ 必须处理 | 检查 `finish_reason == STOP`，而不只是看 `parsed` 是否为 `None`——`MAX_TOKENS` / safety filter 都会让 `parsed` 变 `None`，三种失败要分别记 log |

---

# 第五部分：需要 Jian 本人拍板的决策清单

这 5 条**都不是技术未知**，是产品语义选择。任选其一都能自圆其说，但**必须选定并写进 README**——现场一定会问「为什么这么定」。

| # | 决策 | 我们的倾向 | 反方理由 |
|---|---|---|---|
| **D1** | action 由 LLM 建议 + 代码否决，还是**完全由代码从 intent 映射**？ | LLM 给 `suggested_action`，代码持最终否决与改写权 | 完全代码映射更安全、更好证明，但可能被评委认为「不够 agent」，且题面「据此从动作集合里选一个」略偏向前者 |
| **D2** | 哪些 action 算「主动发出的消息」？ | **只有 `reply`**。推论：escalate 时**不给客户发任何提示语** | 有人会觉得转人工时不说一声体验差。但发提示语就与「严格静默」冲突 |
| **D3** | `reply` 被限流后怎么办？ | 降级为 `schedule_followup`（本轮不发），**不消耗窗口预算** | 也可以「排队 60 秒后补发」，但会引入定时任务和「补发时状态已变」的新问题，不划算 |
| **D4** | ESCALATED / CLOSED 下还调不调 LLM？ | **不调**。攻击输入面为零 + 省 quota | 调用可以给人工准备一份摘要（题目没要求） |
| **D5** | reactivate 后 counter 清零吗？CLOSED 后客户再发消息怎么办？ | counter **清零**（原子事务）；CLOSED 也静默、不调 LLM、不计数 | 不清零 = 人工接管白做（见 `04` Q10） |

**另外两个建议你亲自过一眼的**（不是决策，是风险确认）：

- **R1**：`.gitignore` + key 移出仓库必须在 `git init` **之前**完成。这是唯一一件**做错了就不可逆**的事（key 进了 public repo 的历史只能 rotate）。
- **R2**：`05` T-15（诱导误分类）是我们判定最容易被现场打穿的一条，且**目前没有好解法**。建议在 README 里主动写出来——题目原文说「答不出为什么被打穿、边界在哪、下一步怎么补，才算没过」，**主动承认比被打出来强**。

---

# STAGE-1 VERDICT

## **READY_TO_IMPLEMENT**（附 2 个前置条件）

**理由：**

1. **四条硬约束全部有明确的、可指到具体模块的实现设计**，且每条的「能否 100% 保证」都已论证清楚（`05`：17 条威胁中 12 条属于可 100% 强制的 Class A）。
2. **架构选型已收敛**且有可辩护的理由——不是「因为简单所以选」，而是「因为本题把可证明性列为评分标准，而框架给的保证我们无法自证」。
3. **技术未知已被压到最小**：只剩 Gemini 的具体失败模式与实际模型名，而这两项**不阻塞任何确定性部分的开发**（全部可用 FakeLLM 驱动完成）。
4. **测试策略明确**：所有硬约束都能在无网络、无 API key 的条件下用 fake clock + FakeLLM 测完。这也意味着评委在没有 key 的机器上跑 `pytest` 应该全绿。
5. 剩余的 5 个开放项**是产品语义选择题，不是技术未知**——它们需要的是一次 15 分钟的决策，不是又一轮调研。

**前置条件（必须在写第一行业务代码之前完成）：**

- **P-1 ⛔ 安全**：`.gitignore` + key 移出仓库 + `.env.example`，**然后**才 `git init`。顺序不可逆。
- **P-2**：Jian 对上面 D1–D5 拍板。否则 Stage-2 会在这五个点上返工，而它们都是**贯穿多个模块的语义决定**（比如 D2 会同时影响 rate limiter、executor、state machine 三处）。

**为什么不是 `NEEDS_MORE_DESIGN`**：我们判断继续做设计的边际收益已经很低了。剩下的不确定性有两类——一类要真实 API 才能消除（Gemini 失败模式），继续在纸上讨论没用；另一类是需要人拍板的选择题，继续调研也不会自己收敛。**再多一轮设计只会产生更多文档，不会产生更多确定性。**

---

*2026-09-02，Stage-1 结束。等待人工审查后进入 Stage-2。*
