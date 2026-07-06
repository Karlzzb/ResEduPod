# PRD: 将 DeepTutor 智能体抽取为基于 LangGraph 的独立、可复制基座

> 本 PRD 由一次 `/grilling` + `/domain-modeling` 会话综合而成,可在新会话中独立用于任务划分与代码实现。
> 术语一律遵循 [`CONTEXT.md`](../../CONTEXT.md);所有架构决定的权威来源是 [`docs/adr/0001`–`0013`](../adr/),本 PRD 不覆盖它们,只把它们组织成可执行的产品需求。

## Problem Statement

作为这个项目的维护者,我拥有一套我认为设计很好的智能体和 RAG,但它们被焊死在 DeepTutor 这个大产品里:同一个「智能体」概念在代码里指代四种不同的东西,存在两套互不相通的 Agent 抽象,每个智能体都直接够取全局单例、外部 YAML、PocketBase 与 StreamBus,因此我无法把任何一个智能体单独拿出来调用、测试或复用。
我想以这套智能体为基础模板持续派生更多智能体、接入 LangGraph 生态,但当前的耦合让这件事无法进行。
我不追求运行更快——并行早已是 `asyncio.gather`——我追求的是一套一致、干净、可独立调用、可长期维护和扩展的工业级基座。

## Solution

在一个新的 git 分支上,把这套智能体硬分叉成一个自足的、不依赖 `deeptutor.*` 的代码库,并用 LangGraph 的底层原语(`StateGraph` / checkpointer / `Send` / `interrupt` / `BaseStore`)把它重建为一套标准化的智能体基座。
整个体系收敛为**统一的 [Agent](../../CONTEXT.md) 叶子契约 + 三种 [Orchestration](../../CONTEXT.md) 原型**(流水线类 / 循环类 / 动态并行类)。
每个 Agent 通过注入的 [AgentDeps](../../CONTEXT.md) 获得依赖、自带默认 prompt、内部只用 LangGraph 原生流式,因而可以脱离 DeepTutor 被直接 `graph.invoke()` 调用。
新库定位为**有状态的智能体服务**:短期线程态用 Checkpointer,长期记忆用 `BaseStore`,默认零依赖后端(InMemory/SQLite),生产可换 Postgres(pgvector)。
所有非智能体的产品/交付层(前端、IM 渠道、多用户、学习引擎、产品 API/CLI)永久删除。
重建按「难度递增、地基先行」的顺序进行,并在删旧码前录制黄金样例作为唯一的行为回归参照系。

## User Stories

### 基座与一致性(维护者视角)

1. 作为框架维护者,我想要「智能体」一词在代码里只有一个明确含义,以便新加入的人不再在四种抽象之间困惑。
2. 作为框架维护者,我想要所有智能体共享同一套 Agent 叶子契约,以便消灭今天两套互不相通的 `BaseAgent` 抽象。
3. 作为框架维护者,我想要把编排收敛成三种可命名的 Orchestration 原型,以便任何一个能力都能被一眼归类。
4. 作为框架维护者,我想要循环以图里可见的环表达而非藏在黑盒 node 里,以便控制流可读、可调试、可 checkpoint。
5. 作为框架维护者,我想要一份 glossary 与一组 ADR 固化所有决定,以便半年后没人再来「优化」掉一个刻意的取舍。

### 独立可调用(集成方视角)

6. 作为独立集成方,我想要 `pip install` 后不架任何外部服务就能 `graph.invoke()` 跑一个 Agent,以便零成本试用这个基座。
7. 作为独立集成方,我想要 Agent 内部绝不 import 任何 `deeptutor.*` 或全局单例,以便它在我的项目里不会拖进一堆无关依赖。
8. 作为独立集成方,我想要通过传入一个最小 `AgentDeps`(一个 LLM client + 内联 prompt)就能驱动一个 Agent,以便我用自己的 LLM 与 prompt。
9. 作为独立集成方,我想要每个 Agent 自带默认 prompt,以便复制一个 Agent 当模板时它开箱即用、不依赖磁盘上的 YAML。
10. 作为独立集成方,我想要 Agent 只往 LangGraph 原生事件流写、不认识 StreamBus,以便我能用 `astream_events` 直接消费它的过程与结果。
11. 作为独立集成方,我想要 Agent 与 Orchestration 的输入/输出是类型化的 `State`,以便我在 IDE 里就能看清契约。

### 派生新智能体(智能体开发者视角)

12. 作为智能体开发者,我想要通过实例化 `ReActOrchestration` 模板 + 叠加自有工具来做一个新的循环类能力,以便不必再手写一遍 ReAct 循环。
13. 作为智能体开发者,我想要通过串联若干 Agent 叶子子图来做一个新的流水线类能力,以便复用统一的 Agent 契约与流式。
14. 作为智能体开发者,我想要一个新 Orchestration 从极薄的 `BaseState` 派生,以便自动获得 `messages`/`usage`/`trace_meta`/`language` 等公共机制而不必重写。
15. 作为智能体开发者,我想要把领域中间产物(如分析、设计结果)作为 `State` 的类型化字段传递,以便阶段间是结构化契约而非自由文本对话。
16. 作为智能体开发者,我想要 `mastery_path` 能力将来作为「实例化一次模板」的范例被重建,以便我有一个可照抄的派生样板。

### 三套多智能体的忠实迁移

17. 作为维护者,我想要 `math_animator` 的五段流水线映射为线性图,以便编排结构一目了然。
18. 作为维护者,我想要 `math_animator` 的自愈重试(render→报错→repair→再 render)映射为图里的一个可见条件环,以便每次 render 都是一个 checkpoint 边界。
19. 作为维护者,我想要 render(最慢最易崩的一步)崩溃后能从上次 checkpoint 续跑,以便不必从整条流水线头部重来。
20. 作为维护者,我想要 `visualize` 跟随 `math_animator` 迁移(含其 manim 分支复用),以便两者共享同一套线性原型与 retry 环。
21. 作为维护者,我想要 `deep_research` 的动态自生长队列映射为「递归 supervisor + `Send` 批量 fan-out」,以便 worker 边研究边追加子课题的语义被忠实保留。
22. 作为维护者,我想要 worker 通过 `APPEND` 追加的子课题经 reducer 合并进共享 `State`,以便下一轮 supervisor 能自然看到并调度它们。
23. 作为维护者,我想要 `deep_research` 保留其分批并发上限(`max_parallel_topics`)与 `safety_cap`,以便动态生长不会失控。
24. 作为维护者,我想要 `question` 归入循环类原型(而非流水线类),以便它与 `chat` 系共享 `ReActOrchestration` 模板。
25. 作为维护者,我想要 `chat` 循环的健壮性设计(多级 provider 降级、上下文窗口保护、强制收尾、思考标签过滤)在新模板里逐条落地,以便默认流量的可靠性不回归。

### 人在环(HITL)

26. 作为研究用户,我想要在并行研究开始前先确认大纲,以便昂贵的研究阶段按我认可的方向进行。
27. 作为维护者,我想要大纲确认从「进程退出 + 带 `confirmed_outline` 重新构造」升级为 `interrupt()` + `Command(resume=...)` 的真正暂停恢复,以便 Phase 1-2 的状态被保留而非重算。
28. 作为维护者,我想要 rephrase 阶段的 `ask_user` 澄清也统一到 `interrupt()`,以便整个产品只有一套 HITL 范式。
29. 作为运营者,我想要 HITL 暂停期间进程重启后仍能恢复,以便长任务不会因一次部署而丢失。

### 记忆与持久化(有状态服务)

30. 作为集成方,我想要新库自带会话与长期记忆存储,以便它是一个有状态的智能体服务而非无状态引擎。
31. 作为集成方,我想要长期记忆走 `BaseStore` 抽象且默认零依赖后端,以便开发期不必架数据库。
32. 作为运营者,我想要生产环境把记忆后端换成 Postgres(pgvector)以获得语义记忆检索,以便按用户召回相关记忆。
33. 作为运营者,我想要 checkpointer 后端可从 InMemory/SQLite 换到 Postgres,以便按部署规模选择持久化强度。
34. 作为集成方,我想要 PocketBase 仅作为一个可选 store 后端存在、非默认非唯一,以便我不被强制引入一个 BaaS。
35. 作为维护者,我想要短期线程态(Checkpointer)与长期跨线程记忆(Store)职责清晰分离,以便二者不再各说各话。

### 硬分叉与边界

36. 作为维护者,我想要在一个新分支上永久删除所有非智能体的产品/交付层代码与文档,以便新库干净自足。
37. 作为维护者,我想要保留 RAG 设计,以便我最看重的检索能力随智能体一起迁移。
38. 作为维护者,我想要删除前端后砍掉 trace 元数据 bridge 的复杂度,以便流式桥接退化为极简映射。
39. 作为维护者,我想要偏产品化的工具(cron/github/notebook)降级为可选包而非核心默认集,以便核心保持精简。
40. 作为维护者,我想要 `runtime/orchestrator` 被重写为新库自己的瘦运行时(承载 bridge)而非照搬,以便入口层不带旧产品包袱。

### 可观测性与生态

41. 作为运营者,我想要后续能接入 Langfuse 做可观测,以便追踪 LLM 调用与成本(此项与 LangGraph 正交,不依赖它)。
42. 作为维护者,我想要记忆与 durable execution 直接复用 LangGraph 生态原语,以便未来能平滑接入更多生态组件。

### 验证与落地

43. 作为维护者,我想要在删旧码之前对三套 Orchestration 各录一组黄金样例,以便硬分叉后仍有客观的行为回归参照系。
44. 作为维护者,我想要重建从 `math_animator` 开始,以便用最低编排复杂度一次性验证整套地基(契约/注入/State/流式/checkpointer/循环环)。
45. 作为维护者,我想要按 `math_animator → ReActOrchestration 模板 → deep_research` 的顺序推进,以便难度递增、风险后置。
46. 作为维护者,我想要每套重建后都对齐其黄金样例,以便证明行为未回归后再进入下一套。

## Implementation Decisions

> 权威细节见对应 ADR;以下是可执行层面的综合。

### 架构骨架

- **基座 = LangGraph 底层原语**(`StateGraph`/checkpointer/`Send`/`interrupt`/`BaseStore`),不采用 `create_react_agent` 之类预制件作为工业级方案(ADR-0001)。
- **原子单元两层**:`Agent`(叶子,编译为最小子图,统一契约 `(输入 State)→(输出 State)+事件流`)与 `Orchestration`(用 `StateGraph` 组合多个 Agent)。一个 `Capability` 恰含一个顶层 Orchestration(CONTEXT.md、ADR-0008)。
- **三种 Orchestration 原型**:流水线类(线性 + 可见 retry 环)、循环类(`ReActOrchestration` 模板:LLM node ⇄ tool node 双节点环)、动态并行类(递归 supervisor + `Send` fan-out)(ADR-0005/0006/0008)。

### Agent 契约(五条边)

- **身份**:叶子子图。
- **事件流**:内部只用 LangGraph 原生流式(`astream_events`/`StreamWriter`);`StreamBus` 桥接收敛到 Orchestration 外壳唯一一处(ADR-0002)。删前端后该 bridge 退化为极简 `astream_events → StreamBus` 映射(ADR-0012)。
- **依赖注入**:`AgentDeps` 显式类型化依赖包,经 LangGraph `configurable` 通道传递;Agent 内部永不 import 全局单例(ADR-0003)。决定性形状(来自设计讨论,非工作代码):

  ```
  AgentDeps:
    llm:    LLMClient          # 现有 services/llm 的 provider 接口
    prompts: PromptProvider    # 覆盖 Agent 自带默认 prompt;负责 en/zh
    config: AgentConfig        # 温度/max_tokens 等
    store:  BaseStore | None   # 长期记忆(可选)
    embed:  EmbeddingProvider | None  # 语义记忆用
  # node 内取用:config["configurable"]["deps"].llm
  ```

- **prompt**:每个 Agent 自带默认 prompt(内聚到 Agent 模块),注入的 `prompts` provider 可覆盖;i18n(en/zh)由 provider 处理(ADR-0003)。

### State 模型

- 每个 Orchestration 有独立 `State` schema,均继承极薄 `BaseState`;`BaseState` 只含公共机制字段(`messages`/`usage`/`trace_meta`/`language`),领域字段各自扩展(ADR-0004)。
- `deep_research` 的 `State` 携带 `queue`(`DynamicTopicQueue`)与 `citations`(`CitationManager`),二者已可 JSON 序列化;**必须为它们编写 LangGraph reducer**,决定多个并发 worker 的追加如何合并(ADR-0006)。
- 需复核 `CitationManager` 的 `asyncio.Lock` 在 LangGraph 执行模型下的正确性,并修掉其 write-on-every-add 的 O(N²) 全量写盘(ADR-0006)。

### 循环与并行

- 所有循环用条件边画成图里可见的环,循环计数入 `State` 并在条件边 gate,或设 `recursion_limit`(ADR-0005)。
- `math_animator` retry 环:`render` 后条件边——成功且过 review→`summary`;失败未超次→回 `codegen`(带 error);超次/不可重试(缺 LaTeX)→失败收尾;`max_retries=4` 平移为 gate(ADR-0005)。
- `deep_research` 调度:`supervisor`(每轮重算 `pending`)→`Send(批, ≤max_parallel_topics)`→`aggregate`→条件边(仍有 pending?回 supervisor:去 report)(ADR-0006)。
- 工具并行(`MAX_PARALLEL_TOOL_CALLS=8`)收进 `ReActOrchestration` 的 tool node 一处(ADR-0008)。

### HITL

- 两套 HITL 全部收敛到 `interrupt()` + checkpointer;大纲确认用 `Command(resume=confirmed_outline)` 续跑;`ask_user` 在 worker 子图内部同样用 `interrupt()`(ADR-0007)。
- 现有 WebSocket 的 `_bus_registry` 输入回填机制改造为对接 `Command(resume=...)`;`interrupt` 嵌在 mapped subgraph 内时 resume 需路由回正确 worker(ADR-0007)。
- 正确性链条:HITL 恢复依赖 checkpointer 真正持久化 `State`,与 reducer/序列化正确性同链,须一起验证(ADR-0006/0007)。

### 定位与记忆

- 新库 = 有状态智能体服务;双层记忆:线程态→Checkpointer,长期→`BaseStore`(ADR-0010)。
- 记忆后端:默认 InMemory/SQLite,生产 `PostgresStore`(pgvector)+ `PostgresSaver`;`services/memory` 重写为 `BaseStore` 实现;PocketBase 降为可选后端(ADR-0011)。
- 语义记忆的 embedding provider 并入 `AgentDeps`(ADR-0011)。

### 边界(硬分叉)

- 保留:`core/agentic`、`core/context`、`core/stream*`、`core/trace`、`core/*_protocol`、`services/{llm,rag,prompt,config,sandbox}`、`services/{session,memory}`(重写为 Store)、`tools/`(核心)、`services/skill`+`skills/builtin`、`subagent`、`events/event_bus`(瘦身)、`runtime/registry`;`runtime/orchestrator` 重写为瘦运行时(ADR-0012)。
- 删除:`api/routers`、`multi_user`+`services/auth`、`partners`、`web`/`deeptutor_web`/`deeptutor_cli`、`book`/`co_writer`/`knowledge`、`learning`+`mastery_path`、产品文档(ADR-0009/0012)。
- 不依赖任何 `deeptutor.*`;bridge/`AgentDeps` 默认实现/StreamBus 住在新库自己的 runtime 层(ADR-0009)。

## Testing Decisions

### 什么是好测试

只测**外部行为**,不测实现细节。对本项目而言,外部行为 = 一次运行产生的**流式事件序列** + **最终 `State`**(以及关键领域中间产物),而非 node 内部如何实现。
测试通过注入 `FakeDeps`(脚本化 LLM + 内联 prompt + InMemory store)驱动图,使断言确定、无网络、无外部服务。

### 测试的模块与 seam

- **主 seam(最高):编译后的 Orchestration 图。** 用 `graph.astream(input_state, config={"configurable":{"deps": FakeDeps}})` 驱动,断言事件序列与最终 `State`。每个 Orchestration 一个 seam,覆盖其全部外部行为。这是理想的「一个 seam」入口。
- **次 seam:Agent 叶子子图。** 同一契约在叶子层复用,验证单个 Agent 在 `FakeDeps` 下的输入→输出 `State`。
- 需专门覆盖的行为点:`math_animator` retry 环(注入一次 render 失败→断言触发 repair 并最终成功/收尾)、`deep_research` 的 reducer 合并(并发 worker 追加→断言队列合并正确)、HITL(`interrupt`→`Command(resume)`→断言从断点续跑且状态保留)、`ReActOrchestration` 的终止判定与工具并行。
- **黄金样例 seam(跨切):** 在同一 Orchestration 主 seam 上,录旧实现的固定输入→输出/中间产物,重写后对齐(ADR-0013)。

### 先例(codebase 既有同类测试)

- `tests/core/test_capabilities_runtime.py::_collect_events`:构造裸 `StreamBus`、订阅、跑 `capability.run(context, bus)`、收集事件断言——主 seam 就是把它从 `capability.run` 抬升到 `graph.astream` 的直接后继。
- `tests/core/agentic/test_tool_dispatch_events.py`:用假 registry + 假 bus 隔离测 `dispatch_tool_calls`,并断言 `json.dumps(event.to_dict())` 可序列化——这条「事件必须 JSON 可序列化」的断言在新 bridge/Store 上仍是硬约束。

## Out of Scope

- **运行时性能优化**:并行已是 `asyncio.gather`,本次不以提速为目标;性能只需持平(设计会话结论)。
- **`mastery_path` 能力与 `learning/` 引擎**:本次删除,未来作为模板派生范例单独重建(ADR-0012)。
- **产品/交付层**:前端、IM 渠道(partners)、多用户/鉴权、产品 API/CLI、book/co_writer/knowledge——一律删除,不在本 PRD(ADR-0012)。
- **PocketBase 作为默认存储**:仅作可选后端,不实现其默认路径(ADR-0011)。
- **Langfuse 接入**:与本次抽取正交,可后续独立进行,不阻塞本 PRD(ADR-0011 记为正交)。
- **生产 Postgres/pgvector 部署与运维**:接口与默认后端在范围内,生产部署编排不在。
- **新增第三方 LLM provider**:沿用现有 `services/llm` provider 集,不新增。
- **真实历史改写式的「永久删除」**:本次删除仅在新分支工作树,`main` 历史保留(ADR-0009)。

## Further Notes

- **执行顺序是硬约束**(ADR-0013):**录黄金样例 → 建新分支 → 按 ADR-0012 删旧码 → 从 `math_animator` 起,按 `math_animator → ReActOrchestration 模板 → deep_research` 重建,每套对齐黄金样例。** 黄金样例必须在旧代码仍可运行时录制,否则硬分叉后失去参照系。
- **RAG 明确保留**:用户点名其设计好,随智能体一起迁移,通过工具面被 Orchestration 调用。
- **`AgentDeps` 是包间/层间接口的稳定点**:一旦作为契约冻结应克制演进,这种「被迫想清楚」是工业级基座应付的税。
- **三原型 + 统一 Agent 契约**即本项目「基础模板体系」的最终形态;「以此派生更多智能体」= 复制一个 Agent 叶子 / 实例化一个 Orchestration 原型。
- 本 PRD 的所有决定均可追溯至 `docs/adr/0001`–`0013` 与 `CONTEXT.md`;实现中如需推翻某决定,应先更新对应 ADR。
