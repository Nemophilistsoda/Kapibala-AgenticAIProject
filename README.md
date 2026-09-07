# 获客初筛 Agent — KapibalaAI Agent 方向笔试

> 当前里程碑：Stage 1 需求逆向与架构设计完成；运行时代码尚未进入本里程碑。

本项目要实现一个最小销售初筛 Agent：LLM 只负责语言理解和回复生成，状态转移、动作白名单、限流和人工接管由确定性代码掌握最终执行权。

## 为什么先提交设计基线

题目关注的不是代码量，而是边界、验证和发现 AI 错误的能力。第一阶段先固定：

- 原始需求矩阵与产品语义；
- Raw Gemini SDK / LangGraph / Google ADK 的选型比较；
- 对参考仓库的源码核验；
- 10 组 AI 方案审查与 17 条威胁模型；
- 明确的 MVP 范围与主动砍掉项。

Stage-1 结论是使用 Raw `google-genai` SDK + Pydantic + 自写状态机 / policy / executor。完整论证见 `docs/01_REQUIREMENTS.md` 至 `docs/06_STAGE1_RECOMMENDATION.md`。

## 核心边界

```text
customer message (untrusted)
        ↓
LLM perception (untrusted proposal)
        ↓
state machine → policy gate → executor (trusted)
```

四条硬约束的设计与已知局限见 `docs/05_THREAT_MODEL.md`。AI 使用与核查记录见 `COLLAB.md`。

## 下一里程碑

实现可运行 CLI、SQLite 会话状态、Gemini structured output、唯一 executor 出口和无网络可运行的确定性 / 对抗测试，再更新本 README 的启动说明和实测结果。

## 时间投入

待提交前按真实记录补齐，绝不估写。

