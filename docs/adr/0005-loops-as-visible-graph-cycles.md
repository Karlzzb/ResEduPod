# 循环表达为图里可见的环,不藏进黑盒 node

所有 [Orchestration](../../CONTEXT.md) 里的循环(自愈重试、调度轮次等)一律用 LangGraph 的条件边(conditional edges)画成图拓扑里可见的环,循环计数放进 [State](../../CONTEXT.md) 并在条件边里 gate;**不**把循环埋进单个 node 的内部实现里。

首个应用:`math_animator` 的 `code_retry` 自愈环(今 `retry_manager.py::CodeRetryManager`,回调驱动)重构为——`render` node 后接条件边:成功且过 review → `summary`;失败且未超次数 → 回 `codegen`(带 error 反馈);超次数 / 不可重试错误(如缺 LaTeX)→ 失败收尾。`max_retries=4` 平移为 State 里的重试计数 gate(同时防止撞 `recursion_limit`)。

## 为什么

- 与「显式、可视化、可调试」的架构目标一致(见 [ADR-0001](./0001-langgraph-as-agent-substrate.md));黑盒 node 里藏核心控制流正是本次要消灭的隐式编排。
- checkpoint 精度:循环摊进图拓扑后,每次迭代边界都是一个 checkpoint。`math_animator` 的 render(subprocess 跑 manim)是全链最慢、最易崩的一步,只有把自愈环画进图,断点才能落在「每次 render 之间」,让 durable execution 在形态二也能兑现——黑盒方案只能从整个 retry 块头部重跑。

## 已知代价

图里的显式循环必须有 gate(State 里的计数 + 条件边判断)或 `recursion_limit`,否则无界环会撞递归上限。这是所有循环节点的强制约定。
