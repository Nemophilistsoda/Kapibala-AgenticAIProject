# 02 — GitHub 候选仓库调研 / Repository Survey

> Stage-1 文档 2/6。
>
> **调研方法声明**：本文件中标记「✅ 已读源码」的条目，是把仓库 clone 到本地 `references/` 后**实际打开源文件阅读、并对 Python 文件跑过 `py_compile`** 得出的结论；标记「📄 仅读 README/文档」的条目是基于公开页面的二手判断，可信度较低，已在表中注明。
>
> 本文件刻意记录了**README 声明与实际实现不一致**的地方——这既是题目「会不会验证」的直接回应，也是我们否掉部分候选的依据。

---

## 0. 调研目标（不是找「名字最像 sales agent」的项目）

我们要找的是可以复用以下**能力**的项目，而不是同名项目：

1. customer support / sales / lead qualification agent
2. structured LLM classification（Pydantic / JSON schema）
3. sentiment / dissatisfaction 分析
4. 显式状态机（LangGraph 或自写）
5. human escalation / HITL
6. persistence / session state
7. **deterministic policy / guardrails**（本题真正的核心）
8. prompt injection 防御
9. **Gemini API 集成**（我们拿到的是 Gemini key）
10. adversarial / evaluation testing

---

## 1. 已 clone 并读过源码的三个仓库

三个仓库均以 `--depth 1` clone 到 `references/`，pin 的 commit 如下（用于 attribution 与复现）：

| 仓库 | Commit | Clone 时间 | LICENSE |
|---|---|---|---|
| `agent-rails/agent-guard` | `ba47d66739fb8cf87f082da278695a9167f85bc6` | 2026-08-27 | **Apache-2.0** |
| `niti007/langgraph-customer-support-agent` | `fd1148a2cdb919707ddf6d2a260b5090b87826f0` | 2026-08-27 | MIT |
| `ntg2208/production-ai-customer-support-langchain` | `728bedf3eabc2004aa207551caf94202478cc252` | 2026-08-27 | MIT |

---

### 1.1 `niti007/langgraph-customer-support-agent` ✅ 已读源码

前序 AI 对话把它列为**第一候选骨架**。实际读完源码后，我们**否掉了这个判断**。

**发现的三个硬问题：**

**① 仓库当前状态是坏的——`src/state.py` 有真实语法错误，整个包 import 不了。**

文件末尾多出了一段 `}],`：

```
$ python3 -m py_compile src/state.py
  File "src/state.py", line ...
    }],
    ^
SyntaxError: unmatched '}'
```

其余 5 个文件（`config.py` / `graph.py` / `llm_helpers.py` / `models.py` / `nodes.py`）都能编译通过，只有 `state.py` 坏了——而 `graph.py` 和 `nodes.py` 都 `from src.state import SupportState`，所以**这个仓库跑不起来**。README 对此只字未提。

**② 它用的是 OpenAI，不是 Gemini。**

`src/config.py`：

```python
from langchain_openai import ChatOpenAI
...
if not os.environ.get("OPENAI_API_KEY"):
    raise EnvironmentError("OPENAI_API_KEY is not set. ...")
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
```

`requirements.txt` 里是 `langchain-openai`，没有任何 Google/Gemini 依赖。前序 AI 对话把它当成 Gemini 候选是**错的**。

**③ 它是教学 lab 产物，不是工程代码。**

仓库里有 `notebook/Lab_2_Implement_a_LangGraph_customer_support_agent.ipynb`，源码风格是**逐行加注释解释语法**：

```python
import os
# import the operating system library so we can read environment variables
```

这种代码复制进我们的仓库，答辩时「这行为什么这么写」会非常难看。仓库里还提交了 `src/__pycache__/*.pyc`。

**属实的部分**：`graph.py` 里确实有真的 SQLite checkpointer（`SqliteSaver(sqlite3.connect(db_path, check_same_thread=False))`），`nodes.py` 里确实用了 `langgraph.types.interrupt` 做两道 HITL gate。这两条 README 没有吹牛。

**结论**：❌ 不作为骨架。它的 `interrupt` HITL 模型（图内暂停 → 等人回答 → 继续）与本题的 escalate 语义（**终止本轮并进入锁定态，人工重新激活是一个独立的外部事件**）不匹配，见 `03`。

---

### 1.2 `ntg2208/production-ai-customer-support-langchain` ✅ 已读源码

**README 与实现不符（明确记录）**：README 宣称有 SQLite persistence，但 `graph.py` 的实际实现是：

```python
from langgraph.checkpoint.memory import MemorySaver
...
def build_graph(checkpointer=None):
    ...
    if checkpointer is None:
        checkpointer = MemorySaver()      # ← 默认是纯内存
    return workflow.compile(checkpointer=checkpointer)
```

`checkpointer` 参数确实可以传 SQLite 进来，但**默认路径是 in-memory**，README 的「SQLite persistence」描述具有误导性。这正好印证了题目提示词里那句「不要因为某仓库 README 写着 production-ready 就相信它」。

**真正有价值的部分**——只有 `config/model_config.py` 那一小段 Gemini 接入：

```python
from langchain_google_genai import ChatGoogleGenerativeAI
model = model_name or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
return ChatGoogleGenerativeAI(model=model, temperature=temperature)
```

注意它用的是 **LangChain 的封装**（`langchain_google_genai`），不是 Google 官方 SDK。它给我们的启发是「router 用低温 0.1、生成用高温」这个分模型温度的做法，而不是这段代码本身。

**不适合的部分**：领域完全无关（英国火车票订票），且体量失衡——`database/database.py` 44KB、`utils/populate_data.py` 58KB、`database/UKConnect_policy.txt` 50KB、`ukconnect_rag_chunks.json` 137KB。这些占了仓库绝大部分体积，对本题零价值。它的「policy_agent」是**RAG 检索退票政策文本**，和本题的「deterministic policy gate」是完全不同的两个东西——**同名不同物，是一个典型的搜索陷阱**。

**结论**：⚠️ 仅作为 Gemini 接入方式的参考点之一（且优先级低于官方 SDK 文档），不作为骨架。

---

### 1.3 `agent-rails/agent-guard` ✅ 已读源码 ⭐

三个里**唯一真正有价值**的，但价值方式和前两个不同：**它的价值是设计思想，不是可依赖的库**。

**为什么不能当依赖**：GitHub 上 **0 star / 61 commits / 1 fork**，README 自称「Early. API will move」。把本题要求「代码层面 100% 强制」的安全边界押在一个零社区验证、API 明说会变的第三方库上，是本末倒置。而且答辩时评委问「escalated 静默在哪一行强制的」，回答「在 agent-guard 的 policy 引擎里」是不可接受的答案。

**它教给我们的两件具体的事：**

**① `agent_guard/velocity.py` — 滑动窗口的正确语义**

```python
@dataclass
class InMemoryVelocityLimiter:
    rules: tuple[VelocityRule, ...]
    clock: Callable[[], float] = time.monotonic          # ← 可注入时钟
    _windows: dict[tuple[str, int], deque[float]] = ...  # ← per-key deque

    def check(self, agent_id: str, tool: str) -> str | None:
        now = self.clock()
        ...
        while stamps and stamps[0] <= cutoff:            # ← prune 过期
            stamps.popleft()
        ...
        if len(stamps) >= rule.max_calls:
            return "velocity limit exceeded ..."          # ← 拒绝，且不记录
        ...
        for index, _rule in matching:                     # ← 只有放行才记录
            self._windows.setdefault(...).append(now)
```

两个关键点直接适用于本题的 DC-1：

- **被拒绝的调用不消耗窗口预算**。docstring 原话：*"a denied call never extends a window (no self-inflicted permanent lockout)"*。如果把被限流的发送尝试也记进队列，客户每发一条消息就把窗口往后推 60 秒 → **永久静音**。这是朴素实现几乎必然踩的坑。
- **`clock` 是可注入参数（默认 `time.monotonic`）**。这是让 60 秒约束能写确定性单元测试的前提——测「第 59 秒拒绝、第 61 秒放行」不需要真的 `sleep(61)`。

它自己也诚实披露了残留风险：in-memory，进程重启计数器归零。

**② `agent_guard/decision.py` — 三值判定 + 单调收紧**

```python
class Decision(str, Enum):
    ALLOW = "allow"; DENY = "deny"; REQUIRE_HUMAN = "require_human"

PERMISSIVENESS = {Decision.DENY: 0, Decision.REQUIRE_HUMAN: 1, Decision.ALLOW: 2}

def clamp(decision, ceiling):
    return decision if PERMISSIVENESS[decision] <= PERMISSIVENESS[ceiling] else ceiling

@dataclass(frozen=True)
class Verdict:
    decision: Decision; reason: str; rule_id: str | None = None
    module: str | None = None; layer: int | None = None
    def trace(self) -> str:
        return f"{self.decision.value} [{...}] :: {self.reason}"
```

- `ALLOW / DENY / REQUIRE_HUMAN` 三值几乎一比一映射到本题的「放行 / 拒绝 / 强制转人工」。
- **`clamp` 保证任何后续层只能收紧、不能放松**。这是 defense-in-depth 的正确形状：多层防御串起来时，第二层不应该能推翻第一层的 DENY。
- `Verdict.trace()` 每条决策自带 `module#rule_id@layer :: reason`——这正是我们要的 audit log 形状，现场被攻击时能立刻说清「在第几层被拦下的」。

README 里另外两条值得抄的原则：policy 没有 `default` 就在加载时报错（而不是默默给个默认值）；`require_human` 找不到 approver 就 DENY。

**结论**：⭐ **Top-1 参考，但按「读，不依赖」的方式使用**——重写而非复制，见 `06` 第 6 节。注意它是 **Apache-2.0**（另两个是 MIT），若真复制任何片段需要保留许可证声明并在 `THIRD_PARTY.md` 里 attribution。

---

## 2. 通过检索发现的其他候选（📄 主要基于公开文档）

| # | 仓库 | 一句话 | 与本题的关系 |
|---|---|---|---|
| 4 | `googleapis/python-genai` + `google-gemini/cookbook` | Google 官方 Gen AI SDK 与示例 | ⭐ **Gemini 用法的唯一可信来源**，见第 4 节 |
| 5 | `filip-michalsky/SalesGPT` | 最有名的开源 AI 销售 agent，MIT，464 commits，LangChain + LiteLLM | ❌ **名字最像，方向最反**：8 个对话阶段的推进是**LLM 驱动**的（`determine_conversation_stage()`），正是本题明令禁止的做法。没有 rate limit，没有 action allowlist。可作为「反面教材」写进答辩。 |
| 6 | `lucasboscatti/sales-ai-agent-langgraph` | LangGraph + Gemini Flash 2.0 + SQLite + Streamlit，MIT，~36 commits | ⚠️ 最接近的「同栈同题材」项目。有一个可借鉴点：把 tool 分成 **safe / sensitive** 两类，sensitive 走人工审批。但这只是本题需要的 capability boundary 的**弱化版**——它管的是「哪些工具需要审批」，不管「某状态下所有工具都禁止」。无 rate limit、无 policy 层。demo 级。 |
| 7 | `statelyai/agent` | XState 状态机 + LLM agent | ❌ **TypeScript only**，我们是 Python。且它的状态机是「给 LLM 提供结构化引导」，不是「约束 LLM 的执行权限」——方向也不对。最后 release v1.1.6（2024-09）。 |
| 8 | `acacian/aegis` | LLM guardrails，MIT，761 commits，宣称覆盖 12 个框架 | ⚠️ 看着最强，但**核心是 regex 模式匹配**（自述「10 attack categories, 85+ patterns」的 prompt injection 检测）。题目原文明确说：「如果你们的防御思路是『把这几句话对应的关键词列表拦下来』，**大概率不够**」。它能做补充，**不能做主防线**。 |
| 9 | `protectai/llm-guard` | 输入/输出扫描器集合 | ⚠️ 同上，属于内容层 best-effort 过滤，对 SEC-3 有边际帮助，对 SEC-1/2 无用 |
| 10 | `NVIDIA/NeMo-Guardrails` | Colang DSL 定义 dialog rails | ❌ 依赖极重，需要学一门 DSL，且 rails 本身部分依赖 LLM 判定。2 天工期 + 「必须能指着代码解释」的答辩形式下是负资产 |
| 11 | `guardrails-ai/guardrails` | 输出校验框架（validators + reask） | ⚠️ 它的 `reask` 机制（校验失败就让模型重试）与本题的 fail-closed 要求方向相反——本题里校验失败应该是**不执行**，不是「再问模型一次」 |
| 12 | `MaxMLang/pytector` | prompt injection 检测（本地模型 / API） | ⚠️ 用模型守卫模型，仍是概率性；增加延迟与成本 |
| 13 | `melroyanthony/llm-guardrails` | PII 脱敏 / 注入检测 / 输出校验 | ⚠️ 同类，无差异化价值 |
| 14 | `NirDiamant/GenAI_Agents` | 50+ agent 教程，含 `customer_support_agent_langgraph.ipynb` | 📄 教程集合，可以读那一个 notebook 学 LangGraph 分类节点写法，不作为基线 |

**另外找到一篇直接相关的论文**（不是仓库，但对答辩很有用）：

> Vikas Reddy, Sumanth Reddy Challaram, Abhishek Basu, *"Reason Less, Verify More: Deterministic Gates Recover a Silent Policy-Violation Failure Mode in Tool-Using LLM Agents"*, arXiv:2607.07405, 2026-07-08.

它在 τ²-bench airline 任务上测出：**78% 的失败是「silent wrong-state failure」——最终状态是错的，但没有任何 tool 报错**，因此 agent 收不到任何纠错信号。论文明确对比：

- **prompting** 依赖模型，用户给误导性上下文时失效；
- **reflection（自我反思）对 silent failure 无效**，因为没有 tool error 去触发自纠；
- **LLM judge** 是又一次随机模型调用；
- **deterministic gates**（执行前的只读检查）确定、便宜、可审计。

加上 gate 后 gpt-4o-mini 的 pass₁ 从 29.6% → 42.0%（+12.4pp, P=0.0012），pass_5 从 8.0% → 26.0%。

这篇论文可以直接支撑我们的架构主张：**「不要让 LLM 自己检查自己有没有违规」不是保守，是有实测依据的**。

---

## 3. Scoring Matrix

评分 0–3（3 最好）；`—` 表示不适用。

| 维度 | agent-guard | ntg2208 | niti007 | SalesGPT | lucasboscatti | aegis | 官方 SDK/cookbook |
|---|---|---|---|---|---|---|---|
| 与本题需求匹配度 | **3**（安全层） | 1 | 1 | 0（方向反） | 2 | 1 | **3**（SDK 层） |
| 代码规模是否可控 | 3 | 0（>300KB 无关数据） | 3 | 1 | 2 | 1 | — |
| 是否容易理解 | 3 | 1 | 2（但坏的） | 1 | 2 | 1 | 3 |
| 是否用 Gemini | 0 | **3** | 0（用 OpenAI） | 0 | **3** | 1 | **3** |
| 是否有显式状态机 | 1 | 2（StateGraph） | 2（StateGraph） | 0（LLM 驱动） | 2 | 0 | 0 |
| 是否有 structured output | 0 | 1 | **3**（Pydantic Literal） | 1 | 0 | 0 | **3** |
| 是否有人类接管 | 2（require_human） | 0 | **3**（interrupt） | 1 | 2 | 1 | 0 |
| 是否有 persistence | 0（明说 in-memory） | 1（默认 MemorySaver） | 2（SqliteSaver） | 1 | 2 | 1 | 0 |
| 是否有 tests | **3**（21 个测试文件） | 0 | 0 | 2 | 0 | 2 | — |
| 是否有 security / guardrails | **3** | 0 | 0 | 0 | 1 | 2 | 0 |
| LICENSE | Apache-2.0 | MIT | MIT | MIT | MIT | MIT | Apache-2.0 |
| 当前是否跑得起来 | 3 | 2 | **0（语法错误）** | 2 | 2 | 2 | 3 |
| 依赖是否够轻 | **3**（google-re2 + 可选 pyyaml） | 0（LangChain+FAISS+GCP） | 1 | 0 | 1 | 2 | 3 |
| 二次开发成本 | 2 | 0 | 1 | 0 | 1 | 2 | 3 |
| **答辩时能否讲清** | **3** | 1 | 1 | 0 | 1 | 1 | 3 |
| **加权印象** | **⭐ Top-1** | Top-2（局部） | 降级 | 反面教材 | Top-3 | 补充 | ⭐ 必读 |

---

## 4. Gemini SDK 现状核对（对应提示词第八节）

不消耗 API 额度，只核对接口。核对结果与 ZCode 那个已被删除的 spike（我们从残留字节码 `spikes/__pycache__/SPIKE_gemini_interface_check.cpython-313.pyc` 里还原出了它的行为）有出入，记录如下：

| 项 | 结论 |
|---|---|
| 包名 / import | `google-genai`，`from google import genai`。（旧的 `google-generativeai` 是上一代包，不要用） |
| 两条并存的 API | `client.models.generate_content(...)` **和** 更新的 `client.interactions.create(...)` 官方文档目前**都在维护**。结构化输出文档现在主推 `interactions.create` + `response_format={"type":"text","mime_type":"application/json","schema": Model.model_json_schema()}`，读 `interaction.output_text` |
| ZCode spike 用的写法 | `client.models.generate_content` + `config={"response_mime_type":"application/json","response_schema": ProbeSchema, ...}` + 读 `resp.parsed`。**这条路径仍然有效**，且 `resp.parsed` 直接给 Pydantic 对象，比手动 `model_validate_json` 更顺手 |
| ⚠ 版本风险 | 官方 README 提示 **pin `google-genai < 3.0.0`**，3.0 对 AFC（Automatic Function Calling）有 breaking change。我们必须在 `requirements.txt` 里锁版本 |
| 模型名 | 文档中出现 `gemini-2.5-flash` / `gemini-2.5-pro` / `gemini-3.5-flash` / `gemini-3.7-flash` 等。**实际可用的以 kGroup 发的凭证文档为准**，代码里必须从环境变量读，不能硬编码 |
| structured output 限制 | 只支持 JSON Schema 的一个子集；「非常大或深度嵌套的 schema 可能被拒绝」。我们的 schema 只有 4 个扁平字段，安全 |
| 是否需要 function/tool calling | **不需要**。见 `03`/`04` Q4：tool schema 限制的是「模型能提议什么」，不是「系统会执行什么」，对本题的 100% 保证没有贡献，只增加复杂度和 AFC 版本风险 |
| 如何 mock | 把 LLM 封装成一个只有 `classify(message) -> Perception` 的 Protocol/接口，测试注入 `FakeLLM`。所有确定性测试都不碰网络 |

**一个必须在实现时处理的坑**：ZCode 的 spike 里设了 `max_output_tokens`。如果 `draft_reply` 较长而该值偏小，会以 `finish_reason=MAX_TOKENS` 截断，JSON 不完整，`resp.parsed` 变成 `None`。**必须检查 `finish_reason`，不能只看 `parsed` 是否存在**。详见 `04` Q7。

---

## 5. Top 3 与理由

| 排名 | 仓库 | 用途 | 使用方式 |
|---|---|---|---|
| **1** | `agent-rails/agent-guard` | **设计思想**：sliding-window 语义、可注入 clock、三值 Decision、clamp 单调收紧、Verdict/audit 形状、fail-closed 原则 | **读，不依赖。全部重写。** 理由见 `06` |
| **2** | `googleapis/python-genai` + `google-gemini/cookbook` | Gemini SDK 正确用法、structured output、版本 pin | 直接照官方文档写，不信任何二手仓库 |
| **3** | `ntg2208/production-ai-customer-support-langchain` | 仅一个点：分任务用不同温度（分类 0.1 / 生成 0.5+） | 借鉴思路，代码不用 |

**降级说明**：`niti007/langgraph-customer-support-agent` 从前序对话的「第一候选骨架」降为「不采用」，三条理由：仓库当前 import 就崩、用的是 OpenAI 不是 Gemini、代码是教学 lab 风格。它唯一值得留意的是 `models.py` 用 `Literal[...]` 约束 LLM 输出值域的写法——但那是 Pydantic 的标准用法，不需要从这个仓库学。

---

## 6. README 与实际实现不一致的记录（题目要求明确记录）

| 仓库 | README 声明 | 实际代码 | 严重度 |
|---|---|---|---|
| `ntg2208/...` | "SQLite persistence" | `graph.py` 默认 `MemorySaver()`（纯内存） | 中——参数可传，但默认路径误导 |
| `niti007/...` | 完整可运行的 LangGraph 客服 agent | `src/state.py` 语法错误，包 import 不了 | **高——README 完全没提** |
| `niti007/...` | （前序 AI 对话推断它可能适配 Gemini） | 实际是 `ChatOpenAI(model="gpt-4o-mini")` | 高——这是**前序 AI 判断错误**，不是仓库的错，已记入 `04` |
| `agent-rails/agent-guard` | 自称 "Early. API will move" | 属实。代码质量高于 README 的自我评价 | 无——**这是唯一一个不吹牛的** |
| `filip-michalsky/SalesGPT` | "Context-aware AI Sales Agent" | 阶段推进由 LLM 决定，无 policy gate、无 rate limit | 中——不算说谎，但与本题需求正交 |

---

*调研于 2026-09-02，clone 于 2026-08-27。*

## Sources

- [agent-rails/agent-guard](https://github.com/agent-rails/agent-guard)
- [niti007/langgraph-customer-support-agent](https://github.com/niti007/langgraph-customer-support-agent)
- [ntg2208/production-ai-customer-support-langchain](https://github.com/ntg2208/production-ai-customer-support-langchain)
- [googleapis/python-genai](https://github.com/googleapis/python-genai)
- [Gemini API — Structured outputs](https://ai.google.dev/gemini-api/docs/structured-output)
- [filip-michalsky/SalesGPT](https://github.com/filip-michalsky/SalesGPT)
- [lucasboscatti/sales-ai-agent-langgraph](https://github.com/lucasboscatti/sales-ai-agent-langgraph)
- [statelyai/agent](https://github.com/statelyai/agent)
- [acacian/aegis](https://github.com/acacian/aegis)
- [MaxMLang/pytector](https://github.com/MaxMLang/pytector)
- [melroyanthony/llm-guardrails](https://github.com/melroyanthony/llm-guardrails)
- [NirDiamant/GenAI_Agents](https://github.com/NirDiamant/GenAI_Agents)
- [Reason Less, Verify More (arXiv:2607.07405)](https://arxiv.org/html/2607.07405v1)
- [Google ADK — Callbacks](https://adk.dev/callbacks/)
