# 定位:有状态的智能体服务,双层记忆映射到 LangGraph checkpointer + Store

新库定位为**有状态的智能体服务**(自带会话与记忆存储),而非无状态引擎。
其持久化明确分为两层,分别映射到 LangGraph 生态原语:

- **短期 / 线程态**:一次 run 的图执行状态,供 `interrupt` 恢复与崩溃续跑,作用域为 thread → **LangGraph Checkpointer**(见 [ADR-0006](./0006-dynamic-queue-as-recursive-supervisor.md)、[ADR-0007](./0007-unify-hitl-on-interrupt.md))。
- **长期 / 跨线程**:跨回合对话历史 + 用户长期(语义)记忆,作用域为 user/session → **LangGraph Store(`BaseStore`)**。今天 `services/session` + `services/memory`(PocketBase 持久化)干的就是这一层。

两层互补,非冗余;「有状态服务」= 两层都要。

## 为什么

- 用户选择「有状态服务」而非「无状态引擎」,即新库自带会话/记忆管理。
- 把两层持久化统一到 LangGraph 的 Checkpointer + Store,是「接入 LangGraph 生态」目前最具体的一个兑现:记忆不再是自造子系统,而是生态一等公民,可换官方/社区后端。
- 这也消除了「checkpointer 与 session 存储各说各话」的不一致风险——二者职责被明确切开。

## 影响后续边界裁决

本定位是纲领:`services/session`(context 构建 + 长期存储)、`services/memory` **保留**并重写为 Store 后端;`services/sandbox`、`multi_user`、`runtime/orchestrator` 等灰色地带的删/留,均按「有状态服务需要什么」来切(后续 ADR 逐项定)。
