# State schema:极薄公共基类 + 每套 Orchestration 独立扩展

每个 [Orchestration](../../CONTEXT.md) 拥有自己的 [State](../../CONTEXT.md) schema,但都继承一个极薄的 `BaseState`。
`BaseState` 只承载所有 Agent 共有的机制性字段(如 `messages` / `usage` / `trace_meta` / `language`);各 Orchestration 在其上扩展自己的领域字段(`math_animator` → `analysis`/`design`/`code`/`render_result`;`deep_research` → `queue`/`citations`;`question` → `plan`/`pairs`)。

## 为什么

一致性应落在**公共机制层**与 Agent 契约层,而非强行拍平领域数据。
三套 Orchestration 的中间产物形状本就迥异(线性 pydantic 传递 vs 自生长的 `DynamicTopicQueue` + `CitationManager` vs quiz dataclass),没有理由同形。

- 否决「全仓一个 `UnifiedState`」(B):字段爆炸、`Optional` 满天飞(`research` 的 `queue` 在 `math_animator` 里永远是 `None`),语义稀释——这是伪一致,更难维护,直接违背 [ADR-0001](./0001-langgraph-as-agent-substrate.md) 的可维护目标。
- 否决「完全各自为政」(C):trace/usage/language 等公共机制会在每套里各写一遍,漂移风险高,退回今天「两套抽象」的病根。

## 已知代价

需维护一个 `BaseState` 基类约定,并约束所有新 Orchestration 从它派生(而非从零起 schema),否则公共机制会重新漂移。
