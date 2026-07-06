# Agent 依赖注入与自带 prompt

[Agent](../../CONTEXT.md) 通过一个显式类型化的依赖包 `AgentDeps`(`llm` / `prompts` / `config` 等接口)获得运行所需的服务,该依赖包经 LangGraph 的原生 `configurable` 通道传递(`configurable={"deps": AgentDeps(...)}`,node 内 `config["configurable"]["deps"].llm`)。
Agent 内部**永远不 import 全局单例**。
每个 Agent 的 prompt **内聚到 Agent 自身模块**(自带默认 prompt),注入的 `prompts` provider 可覆盖。

## 为什么

这是「独立可调用」能否成立的真正命门,而非 LangGraph 本身。
现状:`BaseAgent` 直接够取三个全局单例(`services.llm`、`services.config.get_agent_params`、`services.prompt.get_prompt_manager()`),其中 prompt 是按 `(module_name, agent_name, language)` 查找的外部 YAML,缺失即抛 `"... prompts are not configured."`。
因此今天单独 import 一个 Agent 跑不起来——它会去够全局单例和磁盘 YAML。

**依赖机制选 C(混合)**:用显式 `AgentDeps` 接口保证类型化与自足(可由独立调用方提供一个最小实现:一个 OpenAI client + 内联 prompt),同时用 `configurable` 通道传递(不自造 DI 容器、天然支持 per-invoke 换后端)。
纯 A(自造注入容器)放弃了 LangGraph 原生机制;纯 B(服务直接塞进 `configurable` dict)让依赖弱类型化、且把基础设施依赖与运行时配置糊在一起。

**prompt 选自带默认(ii)**:只有「开箱即用、自带默认 prompt」的 Agent 才能真正当模板复制(见 [ADR-0001](./0001-langgraph-as-agent-substrate.md) 的可模板化目标)。外部 YAML 方案会让每个复制出来的 Agent 仍依赖一份磁盘配置才能启动。

## 已知代价

- 需定义 `AgentDeps` 及其 `llm`/`prompts`/`config` 子接口,并把现有 `services/*` 适配为其 DeepTutor 侧实现(一次性)。
- prompt 从集中式 YAML 迁为 Agent 内聚,需要一次搬迁;i18n(en/zh)仍由注入的 `prompts` provider 处理覆盖,不能因内聚而丢掉多语言。
