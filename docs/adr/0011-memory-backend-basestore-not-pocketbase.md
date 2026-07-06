# 记忆后端:采用 LangGraph Store/Checkpointer 抽象,PocketBase 降为可选

长期记忆与会话存储走 LangGraph `BaseStore` 抽象,checkpointer 走 LangGraph 官方实现:

- 默认零依赖后端:`InMemoryStore` / SQLite(`pip install` 即用)。
- 生产后端:`PostgresStore`(pgvector,提供语义记忆检索)+ `PostgresSaver`(checkpointer)。
- **PocketBase 降级为一个可选 store 后端**,非默认、非唯一;仅当使用方另需其产品能力时才启用。

## 为什么

范畴澄清:PocketBase 是 BaaS(SQLite + REST/realtime + 鉴权 + 文件 + 后台 UI),不是记忆原语;`BaseStore` 是接口 + 一组现成实现(基本无需自写)。真实对比是「跑一个 PocketBase 后端」vs「采用生态现成 Store」,而非「优秀产品 vs 自造轮子」。

作为智能体记忆,PocketBase 同时**过度且不足**:
- 不足:无原生向量/语义检索(智能体长期记忆的核心)、不懂 checkpointer/线程态、在目标生态之外;
- 过度:其强项(鉴权/后台 UI/文件/realtime)正是本次要删的产品层([ADR-0009](./0009-standalone-fork-delete-non-agent.md)),为记忆引入 BaaS 等于把产品包袱搬回来。

`BaseStore`/Checkpointer 为智能体记忆而生,且就是要拥抱的生态本身([ADR-0010](./0010-positioning-stateful-agent-service-two-tier-memory.md)),自写代码反而更少。

## 已知代价

- 需把现有 `services/memory`(PocketBase 逻辑)重写为 `BaseStore` 实现,并搬迁数据模型;i18n/多语言记忆语义保持。
- 语义记忆依赖 embedding provider,并入 [AgentDeps](../../CONTEXT.md)([ADR-0003](./0003-agent-dependency-injection-and-self-contained-prompts.md))。
