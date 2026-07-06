# ReActOrchestration 模板与三种 Orchestration 原型

形态一的循环类能力(`chat` / `deep_solve` / `question` / `mastery_path`)统一抽象为一个标准的 `ReActOrchestration` 模板子图,各能力是它的**参数化实例**。
模板是一个通用「LLM node ⇄ tool node」双节点环(条件边:有 tool_call → tool node → 回 LLM;无 tool_call → 结束),把今天的 `LabelProtocol`(标签词表)、`LoopHost`(钩子)、`owned_tools`、system prompt block 作为实例化参数;`solve` 的「计划 / done 闸门 / replan」、`question` 的「explore/plan/quiz 三相」通过参数或叠加额外 node 表达。tool dispatch 的并行(`MAX_PARALLEL_TOOL_CALLS=8`)收进 tool node 一处。

由此,整个体系收敛为**三种 Orchestration 原型** + 统一的 [Agent](../../CONTEXT.md) 叶子契约:

| 原型 | 代表能力 | 图形状 |
| --- | --- | --- |
| 流水线类(线性) | `math_animator` / `visualize` | 线性 node 串联 + 可见的 retry 环([ADR-0005](./0005-loops-as-visible-graph-cycles.md)) |
| 循环类(ReAct) | `chat` / `deep_solve` / `question` / `mastery_path` | LLM ⇄ tool 双节点环(本 ADR) |
| 动态并行类 | `deep_research` | 递归 supervisor + `Send` fan-out([ADR-0006](./0006-dynamic-queue-as-recursive-supervisor.md)) |

## 为什么

`chat`/`question`/`solve`/`mastery` 今天**已经**共享 `run_agentic_loop` + `LoopHost` + `LabelProtocol` + `dispatch_tool_calls`——这是现有代码里唯一已实现的复用。
把它升级为一等公民模板,是「以基础模板派生更多智能体」([ADR-0001](./0001-langgraph-as-agent-substrate.md))最直接的兑现:下一个循环类能力 = 实例化一次 `ReActOrchestration`。
否决 B(各画各的图):会丢掉现有复用,退回「每套各写一遍 ReAct」,比现状更退步。

`question` 归入此原型而非流水线类:探针确认它是绑定 `core.agentic` + tool registry 的 agentic loop(`pipeline.py:356`),与 `chat` 系同类,而非 `math_animator` 系。

## 已知代价

本模板是本次工作量最大的单块:`chat` 循环承载默认流量,并作为 `deep_solve`/`mastery_path`/Partner IM 的底座,且带有大量健壮性设计——多级 provider 降级、`_guard_context_window`、`_forced_finish` 抢救、`InlineThinkFilter`。这些**不得在重写中丢失**,须逐条在新模板里找到落点(单列迁移清单)。
