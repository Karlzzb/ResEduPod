# deep_research 动态队列映射为递归 supervisor + Send fan-out

`deep_research` 的动态自生长队列调度(今 `pipeline.py::_drive_queue` 的手写 batch-`asyncio.gather`)映射为 LangGraph 图里的一个可见环:
`supervisor node`(每轮从 [State](../../CONTEXT.md) 里的 queue 重算 `pending`)→ `Send(当前批 worker,批大小 ≤ max_parallel_topics)` → `aggregate node` → 条件边(仍有 pending?回 `supervisor` : 去 `report`)。
worker 的 `append_child`(经 `APPEND` 标签自主深挖)变为向 State 里的 queue 追加,由 **reducer** 合并;下一轮 supervisor 自然可见。沿用现有 `safety_cap` 防无界生长。

## 为什么

这是唯一既忠实保留 `deep_research` 灵魂(worker 边研究边追加、队列自我扩张)、又满足全部目标(可见拓扑 + checkpoint + 一致)的映射。

- 否决 B(固定 `Send` + 分代 pass 之间才扩队列):它把「实时自生长」偷偷降级为「整批做完才允许扩展」——这是**产品行为回归**,不是纯重构。为贴框架而改语义是本次明确要拒绝的。
- 否决 C(自定义 executor node 内部照旧 `gather`,对图黑盒):直接违反 [ADR-0005](./0005-loops-as-visible-graph-cycles.md),并行与自生长藏进 node,checkpoint 与可视化双双落空。

长研究是 durable execution 的教科书场景:每轮 supervisor 是一个 checkpoint 边界,可断点恢复(见 [ADR-0001](./0001-langgraph-as-agent-substrate.md) 采用 LangGraph 的核心独有价值 C)。

## 已知代价 / 强制约束

- queue 与 citations 进 State 后,多个 worker 并发写入,**必须为它们显式编写 LangGraph reducer** 决定并发追加如何合并——这一层今天由 `asyncio.gather` + 共享对象引用隐式解决,迁移后必须显式化。
- `DynamicTopicQueue` / `CitationManager` 已可 JSON 序列化,满足进 checkpoint 的前提;但需复核其 `asyncio.Lock`(coroutine-only)在 LangGraph 执行模型下的正确性,并修掉 `CitationManager` write-on-every-add 的 O(N²) 全量写盘。
