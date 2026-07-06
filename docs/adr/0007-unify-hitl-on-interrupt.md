# 两套 HITL 统一到 LangGraph interrupt + checkpointer

`deep_research` 现存的两套互不相通的 human-in-the-loop 机制,全部收敛到 LangGraph 的 `interrupt()` + checkpointer 一个原语:

- **大纲确认**:从今天的「进程退出 + 前端带 `confirmed_outline` 重新构造 pipeline」(`pipeline.py:461-505`)升级为——decompose node 后 `interrupt(outline_preview)`,图在 checkpointer 上暂停;用户确认后 `Command(resume=confirmed_outline)` 从断点续跑,Phase 1-2 状态保留不重算。
- **`ask_user` 澄清**:从今天的进程内 `await waiter()`(`pipeline.py:2736`,靠 `StreamBus.wait_for_input`/`submit_input`)改为在 worker 子图内部同样使用 `interrupt()`。

## 为什么

今天同一产品里并存两种暂停范式(「退出重来」vs「协程挂起」),底层管道也不同。要实现 [ADR-0001](./0001-langgraph-as-agent-substrate.md) 承诺的「全仓一致」,HITL 是必须收敛的地方——只统一其一(否决的 B 方案)会让两套范式留到最后,名不副实。

此外 `StreamBus.wait_for_input` 是纯进程内挂起,与 checkpointer 的「可跨进程恢复」语义冲突:`ask_user` 期间进程重启则 `await` 丢失,而 `interrupt` 不会。

大纲确认从 hack 升级为一等公民的暂停恢复,是本次迁移**唯一一处代码明确变简单**的地方——checkpoint 的净收益(核心理由 C)在此兑现得最充分,也才对得起为形态二付出的重写成本。

## 已知代价 / 强制约束

- `interrupt()` 嵌在 mapped subgraph(worker,见 [ADR-0006](./0006-dynamic-queue-as-recursive-supervisor.md))内部时,resume 需路由回正确的 worker 子图。
- 现有 WebSocket 的 `_bus_registry` 用户输入回填机制,需改造为对接 `Command(resume=...)`。
- **正确性链条**:`interrupt` 的恢复依赖 checkpointer 真正持久化了 state,因此本决定与 [ADR-0006](./0006-dynamic-queue-as-recursive-supervisor.md) 的「queue/citations 必须可序列化进 checkpoint」是同一根链条,HITL 正确性直接依赖 State 序列化正确性,两者须一起验证。
