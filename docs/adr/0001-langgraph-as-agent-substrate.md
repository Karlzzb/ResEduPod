# 采用 LangGraph 作为统一的智能体基座(substrate)

我们决定把 DeepTutor 现有的三套多智能体(`math_animator`/`visualize`/`question` 固定流水线、`deep_research` 动态并行、chat 循环)统一重写到 LangGraph 的底层原语(`StateGraph` / checkpointer / `Send` / `interrupt`)之上,把「[Agent](../../CONTEXT.md)(叶子子图)+ [Orchestration](../../CONTEXT.md)(组合图)」作为所有智能体共享的标准架构模板。

## 背景与权衡

现状是我们**已经**拥有一个自研 agent runtime:`run_agentic_loop`(调度)、`LoopHost` Protocol(节点钩子)、`LabelProtocol`(边/转移)、`dispatch_tool_calls`(并行工具)、`StreamBus`(流式 + HITL)。
因此 LangGraph 在**纯功能**上大多是平替——ReAct + 并行工具我们都有。
真正独有的增量只有两样:**类型化 graph state** 与 **checkpoint / `interrupt` 的 durable execution**(现有 `deep_research` 的大纲确认 HITL 是靠进程退出 + `confirmed_outline` 重构实现的,不是真正的暂停恢复)。

我们**不是**为功能采用它,而是为**架构一致性与可模板化**:今天存在两套互不相通的智能体抽象(`agents/chat/` 的循环 vs `agents/base_agent.py` 的 `process()`),这种不一致本身是维护负担。用一个工业级图运行时把它们收敛成一套,才能「以此为基础模板持续派生更多智能体、接入 LangGraph 生态原语」。

明确区分:我们采用的是 **LangGraph-框架原语**,不是 `create_react_agent` 这类**预制件**——后者不足以支撑工业级项目。

## 已知代价(有意接受)

- 形态二(短、确定性、一分钟跑完的线性流水线)几乎拿不到 durable execution 的好处,却仍要重写——这是为「全仓一致性」主动买单,而非功能需要。
- 抽取的主要成本不在循环框架,而在解耦共享服务:`services/{llm,config,prompt}`、外部 YAML prompt 包、`path_service`/sandbox/render service。这部分与是否用 LangGraph 正交,无论如何都要做。
- 可观测性(Langfuse)与本决定正交:Langfuse 不依赖 LangGraph,不构成采用理由。
