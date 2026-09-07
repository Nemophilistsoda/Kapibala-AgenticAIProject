# 01 — 需求矩阵 / Requirement Matrix

> Stage-1 文档 1/6。本文件是对原始笔试题（`kGroup实习生笔试题-候选人版-2026-08-10.md` 题目二）的**独立逆向**，不直接采信任何前序 AI 对话的结论。
>
> 标注规则：
> - `[HARD]` 原题白纸黑字的硬要求，不做就是没做完
> - `[DERIVED]` 为了让某条 `[HARD]` 真正成立而必须做的工程需求
> - `[OPTIONAL]` 题目明说的加分项，或我们认为性价比高的自选动作
> - `[NOT_NEEDED]` 本题不需要，做了是过度工程，要主动砍掉并说明理由

---

## 0. 一句话需求

> 收一条客户消息 → 用 LLM 判断「意图（5 类）」和「是否明显不满（正交布尔）」→ 从 4 个动作里执行 1 个；且**速率限制、强制转人工、转人工后静默、动作白名单**这四条必须由**代码**强制，不能靠 prompt 求模型自觉。

题目自己给出了评分重心（原文）：

> 我们不看你们代码量写了多少，看的是：**边界情况有没有自己想到、有没有验证、AI 给的方案不对的时候有没有发现**。

以及：

> 现场被打穿本身不算失败，**答不出为什么被打穿、你们方案的边界在哪、下一步怎么补，才算没过**。

这两句话决定了本项目的优化目标不是「功能多」，而是**「每个边界都想清楚了、都能证明、都能讲」**。

---

## A. 核心业务能力

| ID | 需求 | 等级 | 说明 / 逆向出的隐含条件 |
|---|---|---|---|
| BC-1 | 模拟客户对话通道 | `[HARD]` | 原文「终端输入、一个最简单的网页聊天框，随便哪种都可以，**越简单越好，重点不在这里**」。→ 明确指示：**不要在 UI 上花时间**。选 CLI。 |
| BC-2 | LLM 意图分类，5 类 | `[HARD]` | 有兴趣 / 需要更多信息 / 明确拒绝 / 答非所问 / 其他。原文：「意图判断**必须真正经过 LLM** 完成」「不能整体用固定关键词/正则规则代替 LLM 分类」。→ 规则只能做**兜底与防御**，不能做**主分类器**。 |
| BC-3 | dissatisfaction 独立判断 | `[HARD]` | 原文：「这是一个**独立于上面 5 类意图的正交信号**，任何意图都可能叠加」。→ 数据结构上必须是 `intent: Enum` + `dissatisfied: bool` 两个字段，**不能**做成第 6 类 intent。这是一个会被现场直接测的点（例：「我挺有兴趣的，但你们服务态度真差」）。 |
| BC-4 | 4 个动作，且只有 4 个 | `[HARD]` | `reply` / `schedule_followup` / `escalate_to_human` / `mark_not_interested`。 |
| BC-5 | `reply` 生成回复草稿 | `[HARD]` | 「生成一条回复草稿」——由 LLM 生成自然语言。 |
| BC-6 | **intent → action 的决定权归属** | `[DERIVED]` **⚠ 需人工拍板** | 原文只说「据此从一个很小的动作集合里选一个动作执行」，**没有明确是 LLM 选还是代码选**。这是本题最大的一个开放设计点，见 `04_AI_DESIGN_REVIEW.md` Q4 / `06` 决策清单 D1。我们的倾向：LLM 输出 `suggested_action`（保留「Agent 感」，也符合题面），但**代码持有最终否决权与改写权**；任何时刻真正执行的 action 由 policy 层决定。 |
| BC-7 | 会话是有状态的，不是无状态函数 | `[DERIVED]` | 由 DC-2/DC-3/DC-5 推出：`agent(message)` 这种纯函数签名无法满足「连续两次」「之后保持静默」「结束会话」。必须有 per-customer 持久会话状态。 |

---

## B. 确定性约束（本题的真正主体）

### DC-1 `[HARD]` 任意 60 秒窗口最多主动发出 1 条消息

原文：

> 对同一个客户，agent 在**任意 60 秒窗口**内最多只能主动发出 1 条消息——不管 LLM 内部决定调用几次工具、重试几次，**最终真正「发送」出去的动作必须被这条限制卡住**。注意「任意 60 秒窗口」和「每分钟一个固定窗口」不是一回事。

逆向出的隐含条件：

| ID | 条件 | 等级 |
|---|---|---|
| DC-1.1 | 必须是 **rolling / sliding window**，不能用自然分钟。反例：12:00:59 发一条 + 12:01:00 再发一条 = 1 秒内两条，固定窗口实现会放行 | `[HARD]` |
| DC-1.2 | 限制卡在**真正发送**这一层，不是卡在「LLM 建议 reply」这一层。LLM 重试 5 次、调 5 次工具都不该消耗额度 | `[HARD]` |
| DC-1.3 | 计数单位是 **per-customer**，不是全局 | `[HARD]` |
| DC-1.4 | **「主动发出的消息」的精确定义** ⚠ 需人工拍板 | `[DERIVED]` |
| DC-1.5 | **被限流之后怎么办** ⚠ 需人工拍板 | `[DERIVED]` |
| DC-1.6 | 窗口预算只被**发送成功**消耗；被拒绝的尝试**不得**写入时间戳 | `[DERIVED]` |
| DC-1.7 | check 与 send 必须在同一临界区内完成（避免 TOCTOU） | `[DERIVED]` |

**关于 DC-1.4**：4 个动作里只有 `reply` 明确是「发消息给客户」。`schedule_followup` 原文写着「本轮不回复」，`mark_not_interested` 是打标记，`escalate_to_human` 是内部转交。所以我们的定义是：**只有 `reply` 消耗 60 秒预算**。推论：`escalate_to_human` 触发时**不应该给客户发任何提示语**（比如「正在为您转接人工」），否则它就变成了一次发送，且与 DC-3「严格静默」冲突。这个取舍必须写进 README。

**关于 DC-1.6（这是一个真实的坑）**：如果实现时把「被限流拒绝的 reply 尝试」也 append 进时间戳队列，那么客户每发一条消息就把窗口往后推 60 秒，结果是**客户被永久静音**。我们是在阅读 `agent-guard/agent_guard/velocity.py` 源码时确认这一点的，该实现的 docstring 明确写：

> "a denied call never extends a window (no self-inflicted permanent lockout)"

### DC-2 `[HARD]` 连续两次 anomaly 后强制 escalate

原文：

> 连续两次被判定为「答非所问」或「情绪不满」（**两者共用同一个计数器**，出现其他情况会重置计数）后必须 `escalate_to_human`……这一条应该是**不依赖 LLM 单次输出、任何情况下都会生效**的确定性状态机，**不能是「LLM 觉得该转人工才转」**。

| ID | 条件 | 等级 |
|---|---|---|
| DC-2.1 | `anomaly = (intent == 答非所问) OR (dissatisfied == true)`，共用一个计数器 | `[HARD]` |
| DC-2.2 | 非 anomaly 的一轮 → counter 归零（reset，不是减一） | `[HARD]` |
| DC-2.3 | counter 达到 2 → **强制** escalate，与 LLM 建议什么无关 | `[HARD]` |
| DC-2.4 | 「LLM 不能决定是否 escalate」≠「不能用 LLM 的分类结果做计数」。counter 的**输入**是 LLM 的 `intent`/`dissatisfied`（这是 LLM 的合法职责），counter 的**判定与触发**是代码 | `[DERIVED]` |
| DC-2.5 | 一条消息**同时**满足「答非所问」和「不满」→ counter **+1，不是 +2** | `[DERIVED]` ⚠ |
| DC-2.6 | 触发 escalate 的那一轮**不再执行 reply**；escalate 优先级高于一切 | `[DERIVED]` |
| DC-2.7 | 同一条消息被重复处理不得重复计数（幂等 / message-id 去重） | `[DERIVED]` |
| DC-2.8 | LLM 调用失败时 counter 的语义 ⚠ 需人工拍板 | `[DERIVED]` |

**关于 DC-2.5（高危坑）**：如果实现成「答非所问 +1，不满 +1」，那么一句「你他妈到底在说什么鬼东西」（既答非所问又明显不满）会**一次就把 counter 打到 2**，直接 escalate。这违背原文「连续**两次**」。而这恰好是现场攻击者最容易随口说出的一句话——**这个 bug 会在答辩现场第一分钟就被打出来**。正确语义：一条消息 = 一次判定 = 最多 +1。

**关于 DC-2.8**：如果 LLM 超时算「其他情况」从而 reset counter，攻击者理论上可以通过制造超时来清零计数。我们的倾向：LLM 失败**既不加也不重置**，counter 保持不变，本轮不发送。理由：把供应商故障归因到客户身上，两个方向都是错的。

### DC-3 `[HARD]` escalated 之后严格静默

原文：

> 转人工，触发后**不得再自动执行任何动作（含 `reply` / `schedule_followup` / `mark_not_interested`）**，只能保持静默，直到人工重新激活。

| ID | 条件 | 等级 |
|---|---|---|
| DC-3.1 | ESCALATED 是锁定态，4 个动作**一个都不能自动执行**（注意连 `schedule_followup` 都不行） | `[HARD]` |
| DC-3.2 | 客户消息**无论内容如何**都不能解除该状态 | `[HARD]` |
| DC-3.3 | 静默检查必须至少存在于两处：入口（省 quota、缩小攻击面）+ executor 内部（choke point，防将来新增代码路径绕过） | `[DERIVED]` |
| DC-3.4 | ESCALATED 之后**是否还调用 LLM** ⚠ 需人工拍板（我们倾向：不调用） | `[DERIVED]` |

**关于 DC-3.4**：两种做法都能满足题意。但「escalated 后客户消息根本不进入 LLM」这个做法在答辩时更强——可以直接说：**此状态下 prompt injection 的输入面为零，因为没有 prompt**。同时省 quota。

### DC-4 `[HARD]` 人工重新激活

| ID | 条件 | 等级 |
|---|---|---|
| DC-4.1 | 存在一个能把 ESCALATED 解锁回 ACTIVE 的人工入口 | `[HARD]` |
| DC-4.2 | 该入口与 customer channel **完全分离**——不是「同一个输入框里加个前缀判断」，而是**不同的函数入口 / 不同的事件类型**，使得「客户消息构造成 operator 指令」在类型层面就不可能 | `[DERIVED]` ⚠ |
| DC-4.3 | reactivate 后 anomaly counter 是否清零 ⚠ 需人工拍板（我们倾向：清零） | `[DERIVED]` |

**关于 DC-4.3**：若不清零，人工刚接管完放回自动流程，客户下一条稍有情绪就立刻二次 escalate，人工接管等于白做。

### DC-5 `[HARD]` mark_not_interested 后结束会话

| ID | 条件 | 等级 |
|---|---|---|
| DC-5.1 | 该动作使会话进入终态 CLOSED | `[HARD]` |
| DC-5.2 | CLOSED 之后客户再发消息的行为 ⚠ 需人工拍板（我们倾向：静默，不再调用 LLM，不再计数） | `[DERIVED]` |
| DC-5.3 | CLOSED 是否可被人工重开 | `[OPTIONAL]` |

### 状态机（由 B 组约束逆向出的最小状态集）

```
                 ┌──────────────────────────────┐
                 │            ACTIVE            │◄──── operator_reactivate()
                 │  (anomaly_counter: 0 | 1)    │            │
                 └───┬──────────────┬───────────┘            │
      counter 达到 2 │              │ mark_not_interested    │
      或 LLM 建议    │              │                        │
      escalate       ▼              ▼                        │
                 ┌────────────┐  ┌────────────┐              │
                 │ ESCALATED  │  │   CLOSED   │              │
                 │  (锁定)    │──┘   (终态)   │              │
                 └─────┬──────┘  └────────────┘              │
                       └─────────────────────────────────────┘

ESCALATED / CLOSED 状态下：客户消息不产生任何自动动作。
唯一的出边来自 operator channel，永远不来自 customer channel。
```

---

## C. Agent Security

| ID | 需求 | 等级 | 能否 100% 保证 |
|---|---|---|---|
| SEC-1 | 动作白名单，代码层强制 | `[HARD]` | ✅ 可以 |
| SEC-2 | 对话内容不能指挥 agent 越权执行动作 | `[HARD]`（原文要求「代码层面 100% 强制」） | ✅ 可以 |
| SEC-3 | 对话内容不能套出 system prompt / 内部规则 / 价格底线 | `[HARD]`（但原文明确「**不期望做到 100%**，要有清晰防御设计并讲清局限」） | ❌ 只能 best-effort |
| SEC-4 | malformed structured output → fail-closed | `[DERIVED]` | ✅ |
| SEC-5 | LLM 幻觉出第 5 种 action → 必须被拒绝 | `[DERIVED]` | ✅ |
| SEC-6 | LLM timeout / API error → fail-safe，绝不 fail-open | `[DERIVED]` | ✅ |
| SEC-7 | **最小知识原则**：分类用的 LLM context 里不含任何内部规则/价格；生成用的 context 里只含允许对外说的话术 | `[DERIVED]` ⭐ | 把 SEC-3 从「防泄漏」改造成「无物可泄」，是唯一能把这条往结构性保证方向推的手段 |
| SEC-8 | 客户消息作为**数据**而非**指令**传入，结构化定界，不做字符串拼接进 instruction 区 | `[DERIVED]` | 缓解，非保证 |
| SEC-9 | 出站 canary / 内部标记检查 | `[DERIVED]` | 只能 100% 挡「原样复述」，挡不住转述改写 |

**SEC-2 为什么可以做到 100%**：因为它的断言对象是**代码执行路径**，不是模型行为。可形式化为：

```
∀ 客户输入 m:
    executed_action(m) ∈ {reply, schedule_followup, escalate_to_human, mark_not_interested, NONE}
∧   state == ESCALATED  ⇒  executed_action(m) == NONE
∧   state == CLOSED     ⇒  executed_action(m) == NONE
```

这可以靠「executor 是唯一出口 + 显式 dict dispatch + 入口处 state 检查」来保证，并用穷举测试 + 代码审查证明。**它不依赖模型输出任何特定内容。**

**SEC-3 为什么做不到 100%**：因为它的断言对象是**自然语言文本的语义**，而「模型是否泄漏了内部信息」不是一个可判定谓词。任何基于关键词/正则的出站过滤都能被翻译、编码、改写、藏进诗里绕过。原文也明确说了不期望 100%。

---

## D. Persistence / Concurrency / State

| ID | 需求 | 等级 | 理由 |
|---|---|---|---|
| PS-1 | 会话状态持久化到进程外（SQLite 单文件） | `[DERIVED]` | 原题**没有**要求重启存活。但 DC-3 说「任何情况下都会生效」，若状态只在内存，进程重启后 ESCALATED 丢失、客户重新收到自动回复 = 静默被绕过。这是答辩时必然被追问的点，而 SQLite 的成本约等于零。 |
| PS-2 | 状态表用显式列（`state` / `anomaly_counter` / `last_sent_at`），不塞 JSON blob | `[DERIVED]` | 答辩时能当场 `sqlite3` 查出来给评委看，可解释性直接拉满。 |
| PS-3 | 结构化 audit log：每次决策一条记录（LLM 提议了什么 → policy 哪一层判了什么 → 最终执行了什么） | `[DERIVED]` ⭐ | 现场被攻击时可以立刻调出日志说明「模型提议了 X，被第 N 层拒绝」。这是「答得出为什么被打穿」的物证。 |
| PS-4 | 同一客户的并发请求安全（per-customer 锁） | `[DERIVED]` | DC-1.7 的 TOCTOU 需要。**单进程内的锁就够**。 |
| PS-5 | 跨进程 / 分布式并发 | `[NOT_NEEDED]` | 本题是单进程 demo，题目二才考真并发。**主动砍掉，并在 README 写明为什么砍**——题目原文说「明确写清楚你砍掉了什么、为什么砍，比硬撑一个不完整还讲不清楚的版本要加分得多」。 |
| PS-6 | Redis / Kafka / Postgres / 向量数据库 | `[NOT_NEEDED]` | 过度工程。 |

---

## E. Evaluation

| ID | 需求 | 等级 | 说明 |
|---|---|---|---|
| EV-1 | **至少 3 条** 让 agent 犯规的对抗测试 + 运行结果 | `[HARD]` | 原文明确交付物。我们目标做到 ~10 条，覆盖 4 条硬约束各自的攻击面。 |
| EV-2 | 确定性单元测试（注入 fake clock，**不调 LLM**） | `[DERIVED]` | 60 秒边界（59s / 60s / 61s）、counter 序列（异常-正常-异常-异常）、DC-2.5 双信号单条消息、ESCALATED 静默、CLOSED 静默。这些必须能在无网络无 API key 的情况下跑。 |
| EV-3 | LLM 用 mock/stub 的集成测试 | `[DERIVED]` | malformed JSON、第 5 种 action、`finish_reason != STOP`、空响应、timeout、异常。**这是证明 fail-closed 的唯一方式**，因为真实 API 不会按需给你返回坏数据。 |
| EV-4 | 真实 Gemini 少量 smoke test | `[OPTIONAL]` | 证明「意图判断真的经过了 LLM」。 |
| EV-5 | 大规模 eval 集 / LLM-as-judge 评测 | `[NOT_NEEDED]` | 超出 2 天工作量，且不是考点。 |

---

## F. `[NOT_NEEDED]` 完整清单（要主动砍并写明理由）

| 项 | 为什么砍 |
|---|---|
| 真实 IM 平台接入 | 原文：「这道题**不需要接入任何真实 IM 平台**」 |
| 好看的前端 | 原文：「越简单越好，重点不在这里」 |
| RAG / 向量检索 / 知识库 | 题目没有任何知识问答需求 |
| Multi-agent / agent 编排 | 单一职责的单 agent，加 multi-agent 只会扩大攻击面 |
| Redis / Kafka / 消息队列 | 单进程 demo |
| 用户认证 / 多租户 | 不在需求内 |
| Streaming 输出 | CLI demo 不需要，且会让「发送前拦截」变复杂（流式已经吐出去的字收不回来）——这一点值得在 README 里提一句 |
| 细粒度意图分类（超出 5 类） | 题目列的是加分项，但会让 DC-2 的 anomaly 判定变复杂，性价比低 |
| 复杂重试 / 熔断 / 限流中间件 | 自己 20 行写完，引依赖反而讲不清 |

---

## G. 本文件识别出的、必须由人工拍板的开放问题

汇总（详见 `06_STAGE1_RECOMMENDATION.md` 决策清单）：

1. **D1 / BC-6** — action 由 LLM 建议 + 代码否决，还是完全由代码从 intent 映射？
2. **D2 / DC-1.4** — 哪些 action 算「主动发出的消息」？（我们主张只有 `reply`）
3. **D3 / DC-1.5** — reply 被限流后，降级成 `schedule_followup`、丢弃、还是排队补发？
4. **D4 / DC-3.4** — ESCALATED / CLOSED 状态下还调不调 LLM？（我们主张不调）
5. **D5 / DC-4.3 + DC-5.2** — reactivate 后 counter 清零吗？CLOSED 后客户再发消息怎么处理？

这 5 个都**不是技术未知**，是产品语义选择。任选其一都能自圆其说，但**必须选定并写进 README**，因为现场一定会问「为什么这么定」。

---

*本文件基于原始题目独立逆向，2026-09-02。*
