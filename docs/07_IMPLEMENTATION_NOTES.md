# 07 — MVP 实现说明与 Stage-1 偏差

本文件只记录已经落到代码里的事实，不重复 Stage-1 的方案讨论。

## 已实现

- `src/kapibala_agent/`：领域枚举、严格 Pydantic schema、状态机、policy clamp、SQLite store、唯一 executor、审计日志、Gemini/FakeLLM 适配器和两个 CLI 入口。
- `tests/`：无网络确定性测试与显式 adversarial 测试。
- `uv.lock`：锁定完整依赖；`google-genai` 当前解析为 2.22.0，并限制 `<3.0`。

## 对 Stage-1 设计的两处修正

### 1. 限流使用 `last_sent_at`，不使用 deque

题目是 `max_calls=1` 的特例。`last_sent_at` 与长度最多为 1 的 deque 在任意滚动 60 秒窗口内语义等价，但前者可以直接通过 SQLite 事务跨进程原子检查，代码更短、更容易证明。

### 2. 发送前预留额度，不在发送成功后记录

Stage-1 写的是「send 成功后再记录」。但数据库提交和外部发送是两个副作用，没有分布式事务时不可能原子化：如果消息已经发出而数据库提交失败，下一次请求可能再次发送。

MVP 选择更安全的方向：SQLite `BEGIN IMMEDIATE` 内检查并预留发送额度，然后才调用 transport。代价是 transport 失败时仍可能消耗一个 60 秒窗口；收益是不会产生重复发送窗口。对于本地 CLI，这是明确的 fail-closed 取舍。

## 真实 Gemini smoke test

2026-09-07 使用提供的凭证和官方 `google-genai` 2.22.0 调用 `gemini-2.5-flash`：服务端返回 `401 UNAUTHENTICATED / ACCESS_TOKEN_TYPE_UNSUPPORTED`。凭证值未写入新文件、日志或 Git。

这意味着当前阻塞项是凭证有效性/绑定状态，而不是确定性代码。官方文档说明 `AQ.` auth key 是受支持格式，因此不能仅凭前缀判定错误；需要向凭证提供方确认该 key 是否仍有效并绑定 Gemini API。修复凭证后重新执行 live smoke test，才可把真实集成标记为完成。
