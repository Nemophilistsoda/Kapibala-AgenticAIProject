# 获客初筛 Agent — KapibalaAI Agent 方向笔试

> 当前状态：确定性 MVP 已完成，`28 passed`；真实 Gemini 调用仍被提供凭证的 `401 UNAUTHENTICATED` 阻塞，详见下文。

一个小而可审计的销售初筛 Agent：LLM 负责意图识别、情绪识别、动作建议和回复草稿；代码负责状态转移、动作收紧、限流、静默锁定和最终副作用。

核心原则是：**模型输出是提案，不是命令。**

## 快速开始

需要 Python 3.11 与 [uv](https://docs.astral.sh/uv/)。

```powershell
uv sync --extra dev
Copy-Item .env.example .env
# 编辑 .env，填入有效 GEMINI_API_KEY

uv run kapibala-agent chat --customer-id demo-customer
```

人工恢复是独立入口，不解析客户文本里的 `/reactivate` 或 `admin:`：

```powershell
uv run kapibala-agent admin reactivate demo-customer
```

运行全部测试：

```powershell
uv run pytest -q
```

当前结果：

```text
28 passed
```

所有测试默认使用 `FakeLLM` 与可注入时钟，不需要网络或 API key。

## 四条硬约束在哪里强制

| 约束 | 强制位置 | 机制 |
|---|---|---|
| 任意滚动 60 秒最多发送 1 条 | `store.py::reserve_send()`，由 `executor.py::_reply()` 调用 | SQLite `BEGIN IMMEDIATE` 原子检查并预留；被拒请求不延长窗口 |
| 连续两次异常强制转人工 | `state_machine.py::transition()` | `irrelevant OR dissatisfied` 共用计数器；一条消息最多 +1；达到 2 强制覆盖模型建议 |
| 只允许四种动作，转人工后静默 | `domain.py` + `service.py` pre-gate + `executor.py` 二次 gate | 严格枚举、无动态 dispatch；ESCALATED/CLOSED 下不调用 LLM，executor 也拒绝状态不匹配动作 |
| 防套取内部信息 | 两次 LLM 调用隔离 + `executor.py` 出站 canary | 模型上下文不含价格底线等秘密；canary 挡完整原样复述；语义改写只能 best-effort |

完整威胁边界见 [`docs/05_THREAT_MODEL.md`](docs/05_THREAT_MODEL.md)，落地后的修正见 [`docs/07_IMPLEMENTATION_NOTES.md`](docs/07_IMPLEMENTATION_NOTES.md)。

## 数据流与权限边界

```text
Customer CLI
    ↓ untrusted text
Gemini classify → Perception (strict schema, still untrusted)
    ↓
policy clamp → deterministic state machine → SQLite
    ↓
Gemini draft (only for reply)
    ↓
Executor state gate → outbound guard → atomic rate reservation → Transport

Operator CLI ───────────────→ reactivate (separate function and event path)
```

模型没有数据库句柄、没有 Python callable、没有工具调用能力，也不能直接触达 transport。

## 已拍板的产品语义

- LLM 可以建议动作；代码用 intent/action 兼容矩阵收紧不一致建议。
- 只有 `reply` 算主动发消息。
- `reply` 被限流后降级为 `schedule_followup`，不等待、不后台排队。
- ESCALATED 与 CLOSED 下不调用 LLM，客户消息严格静默。
- 人工重新激活时 anomaly counter 原子清零。
- 发送额度在发送前原子预留：transport 失败可能损失一个窗口，但不会造成重复发送。这是刻意的 fail-closed 取舍。

## 测试覆盖

- 59.999 / 60.000 秒滚动窗口边界；拒绝尝试不延长窗口。
- 一条消息同时 `irrelevant + dissatisfied` 只计一次。
- 第二次异常覆盖模型的 `reply` 建议并进入 ESCALATED。
- ESCALATED 后的道歉、伪造 system、`admin:`、`/reactivate` 全部静默且不调用 LLM。
- 非法第五动作、大小写/空格变体被 schema 拒绝。
- 模型建议与意图冲突时由 policy clamp。
- LLM 失败不发送、不清零异常计数。
- SQLite 重建后仍保留 ESCALATED 状态。
- 回复包含 canary 时在 transport 前拦截。

显式攻击用例见 [`tests/adversarial/test_attacks.py`](tests/adversarial/test_attacks.py)。

## 关于 AI 的使用

项目使用 AI 做需求分析、仓库搜索、方案 brainstorm 与实现辅助，但不把 AI 报告当作事实。实际核查发现过：推荐仓库无法编译、README 声称 SQLite 而默认实现是内存、`.env.example` 被误放真实 key、以及“发送成功后记录额度”无法与外部发送原子化。

证据与修正记录见 [`COLLAB.md`](COLLAB.md) 和 [`docs/04_AI_DESIGN_REVIEW.md`](docs/04_AI_DESIGN_REVIEW.md)。不会为了展示过程而伪造失败 commit。

## 当前阻塞与已知边界

- 提供的 `AQ.` 凭证经官方 SDK 2.22.0 实测返回 `401 ACCESS_TOKEN_TYPE_UNSUPPORTED`。官方文档说明该格式本身受支持，因此下一步应确认 key 是否仍有效、是否绑定 Gemini API；凭证问题解决前，不能宣称真实 LLM 集成完成。
- 语义层攻击无法 100% 防御：模型可能被诱导误分类，也可能改写而非原样泄漏提示。状态机能保证“给定观测后必然正确转移”，不能保证观测永远正确。
- MVP 不实现真实 IM、Web UI、RAG、multi-agent、流式输出或操作者认证；理由见 `COLLAB.md`。

## 项目结构

```text
src/kapibala_agent/
├── domain.py          # 5 个 intent、4 个 action、状态与 schema
├── llm.py             # Gemini adapter + FakeLLM
├── policy.py          # intent/action 兼容矩阵与 clamp
├── state_machine.py   # 纯函数状态转移
├── store.py           # SQLite 状态与原子限流预留
├── executor.py        # 唯一副作用出口
├── service.py         # customer/operator 两个独立 service
├── audit.py           # JSONL 审计
└── cli.py             # chat / admin CLI
tests/
├── adversarial/
└── test_*.py
```

## 时间投入

`TODO：提交前由本人按真实记录补齐。` 题目明确要求实际用时，这一项不能让 AI 估写。
