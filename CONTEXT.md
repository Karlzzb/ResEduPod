# DeepTutor Agent 体系

本文件是 DeepTutor 智能体体系的**术语表(glossary)**,只定义概念边界,不含实现细节。
其存在的原因:代码与文档里「智能体 / agent」一词至少指代四个不同层级的东西(专职 `process()` 单元、chat 循环 pipeline、Level-2 capability、外部委派 subagent),必须先钉死每个词的唯一含义,才能把这套系统抽取成标准化、可模板复制的架构。

## Language

**Agent(叶子)**:
单一职责、由一次或几次 LLM 调用构成的最小智能体单元;编译为一个最小 LangGraph 子图(可能仅 1-2 个 node),对外暴露统一契约 `(输入 state) → (输出 state) + 事件流`。
它是「模板复制」的原子对象——「以这个智能体为基础模板做更多智能体」指的就是复制一个 Agent。
_Avoid_: 专职 Agent、worker、node(node 是 Agent 的内部构件,不是 Agent 本身)

**Orchestration(组合)**:
把多个 Agent 子图用 `StateGraph` 连接而成的组合图;负责编排形态(线性 / 并行 `Send` fan-out / 带 `interrupt` 的 human-in-the-loop)。
今天的每个 `pipeline.py` 对应一个 Orchestration。三套多智能体各是一个 Orchestration,但共享同一种 Agent 契约。
_Avoid_: pipeline、flow、workflow(用 Orchestration 统一指代)

**Capability(能力)**:
接管一整个用户回合(turn)的 Level-2 单元,由 `ChatOrchestrator` 路由选中;其内部实现是一个 Orchestration。
Capability 是「面向用户回合」的外壳;Orchestration 是「面向智能体编排」的内核。一个 Capability 恰含一个顶层 Orchestration。
_Avoid_: mode、pipeline

**Tool(工具)**:
由 LLM 按需调用的单次函数(如 `rag`、`web_search`、`exec`),Level 1。
Tool 装点一个回合;Capability 接管一个回合。二者不可混称。
_Avoid_: function、skill(skill 是另一独立概念——system prompt 里给清单、模型按需拉全文)

**Subagent(委派子智能体)**:
把用户本机的外部智能体(Claude Code / Codex)作为「委派对象」拉起并流式监听的机制。
它是「外部进程委派」,与本体系内的 Agent 是**完全不同**的东西,不要因为都叫「agent」而混淆。
_Avoid_: worker、child agent

**AgentDeps(依赖包)**:
一个 Agent 运行所需的、显式类型化的外部服务集合(`llm` / `prompts` / `config` 等接口),经 LangGraph `configurable` 通道注入。
它是「独立可调用」的载体:DeepTutor 侧提供一个包住现有 `services/*` 的实现,独立调用侧可提供一个最小实现。Agent 内部只认这些接口,绝不 import 全局单例。
_Avoid_: services、container、context(context 特指 `UnifiedContext`)

**State(状态)**:
在一个 Orchestration 图中流经各 node 的类型化状态对象(LangGraph `State`)。
取代今天在循环里就地修改的 `messages: list[dict]`。Agent 间传递的结构化契约(如 `ConceptAnalysis`/`SceneDesign`)是 State 的字段,而非自由文本对话。
_Avoid_: context(context 特指 `UnifiedContext` 这个回合级入参 DTO,不是图内状态)

**BaseState(公共状态基类)**:
所有 Orchestration 的 State 共同继承的极薄基类,只含全体 Agent 共有的机制性字段(`messages` / `usage` / `trace_meta` / `language`)。
领域字段由各 Orchestration 在其上扩展。一致性落在此层,而非把所有领域数据拍平进一个大 schema。
_Avoid_: UnifiedState、GlobalState(强行同形的伪一致,已否决)

## 与旧代码抽象的对应

| 本术语 | 今天代码里的对应物 |
| --- | --- |
| Agent | `agents/base_agent.py::BaseAgent` 的 `process()` 单元(如 `ConceptAnalysisAgent`) |
| Orchestration | 各 `pipeline.py`(`math_animator` / `research` / `question`);`run_agentic_loop` + `LoopHost` |
| Capability | `core/capability_protocol.py::BaseCapability` |
| Tool | `core/tool_protocol.py::BaseTool` |
| Subagent | `services/subagent/` + `capabilities/subagent/` |
