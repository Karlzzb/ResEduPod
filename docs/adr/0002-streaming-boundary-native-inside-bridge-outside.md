# 流式边界:内部用 LangGraph 原生,StreamBus 桥接只在最外层

[Agent](../../CONTEXT.md) 与 [Orchestration](../../CONTEXT.md) 内部**完全不认识 `StreamBus`**,只使用 LangGraph 原生流式机制(`astream_events` / `StreamWriter` / node 的 `State` 更新)。
`StreamBus` 的桥接收敛到唯一一处——[Capability](../../CONTEXT.md) 外壳层的一个适配器:`astream_events → StreamBus.emit`。

## 为什么

「独立可调用」是本次抽取的核心诉求。只有当 Agent 内部不持有 StreamBus 时,它才能脱离 DeepTutor 被直接 `graph.invoke()` / `graph.astream()` 调用。
本决定把 StreamBus 的耦合面从代码里约 244 处调用点塌缩到 1 处 bridge。

反方案(把 StreamBus 作为 State 字段或注入依赖,node 内部照旧 emit)被否决,因为它有两个致命问题:
1. Agent 仍焊死在 StreamBus 上,「独立可调用」直接落空;
2. StreamBus 是不可 JSON 序列化的活对象,放进 LangGraph `State` 会与 checkpointer(需序列化 state)**直接冲突**,反噬 durable execution(见 [ADR-0001](./0001-langgraph-as-agent-substrate.md))。

## 已知代价

前端 CallTracePanel 依赖一套 trace 元数据(`call_id` / `trace_role` / `trace_kind` / `trace_group` / `call_role` 等,见 `core/trace.py`、`tool_dispatch.py`)。
本决定把「把 LangGraph 事件翻译成这套 trace 元数据」集中成 bridge 里一块独立的、明确的工作——这是整个流式迁移中唯一真正的硬骨头,需单独设计。
