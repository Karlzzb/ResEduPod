# Issue 切分方案:LangGraph 智能体抽取

> 本文档是 [`0001-langgraph-agent-extraction.md`](./0001-langgraph-agent-extraction.md) 的任务划分,已定稿。
> Issue tracker:GitHub Issues(`Karlzzb/ResEduPod`)。
> 发布时使用的 triage label:`ready-for-agent`。

## 划分原则

采用**垂直切片(tracer bullets)**:每一片穿透全部集成层(Agent 契约 / AgentDeps 注入 / State / 原生流式 / checkpointer),而非某一层的水平切片。
每片完成后可**独立 demo 或验证**——单独「删代码」或单独「搭 trivial 玩具 Agent」都不满足,因此不单列为切片。

硬约束执行顺序(去掉黄金样例环):

> 建新分支删旧码 → math_animator → ReActOrchestration 模板 → deep_research。

### 关于黄金样例:已砍(推翻 PRD US 43 / ADR-0013)

黄金样例的唯一价值是「把旧行为当 oracle」,但本次是**重架构而非保真复制**:HITL 从「进程退出重构造」改为 `interrupt/resume`、`CitationManager` 的 O(N²) 与 Lock 是**故意修的 bug**——把旧输出冻结成基线会把这些故意的改动/修复反向焊死成回归。
需要保真的地方(如 math_animator retry 环),用 `FakeDeps` 驱动的**行为验收标准**(注入一次 render 失败 → 断言触发 repair → 断言最终成功/收尾)比录旧输出更强:它规格化**意图**、不依赖旧码还能跑、不把旧实现的偶然细节当契约。
这正是 PRD「Testing Decisions」定的主 seam。砍掉后唯一失去「自动兜住旧代码未知行为」这层网,由维护者对代码的熟悉补上。

> 每个切片的验收 = `FakeDeps` 驱动、断言事件序列 + 最终 State 的行为测试;**不录黄金样例**。US 43 dropped,应同步更新 ADR-0013。

## 不入 issue 的 User Story

- **US 1-5**:已由现有 `CONTEXT.md` glossary 与 `docs/adr/0001–0013` 交付。
- **US 13, 14, 15**:由各原型的重建过程直接体现,不单列。
- **US 16 / 41 / 42**:Out of Scope 或与本次抽取正交。
- **US 43**:已砍,改由各切片的 `FakeDeps` 行为验收替代。

---

## 切片清单(共 7 片)

### 1. 硬分叉 + 地基 + math_animator + visualize 端到端

- **Blocked by**:无(可立即开始)
- **覆盖 US**:36, 37, 38, 39, 40(硬分叉)/ 6, 7, 8, 9, 10, 11(地基)/ 17, 18, 19, 20, 44(math_animator + visualize)
- **为何合并**:只删非智能体层、或只搭一个 trivial Agent,都无法独立验证——trivial Agent 跑通不代表没删掉真实能力依赖的保留服务(rag / sandbox 等)。只有在新地基上重建出 `math_animator` 并通过行为验收,才能证明删除未破坏根本。
- **说明**:
  - **硬分叉**:新分支上按 ADR-0012 keep/delete ledger 永久删除非智能体产品/交付层(`api/routers`、`multi_user`+`services/auth`、`partners`、`web`/`deeptutor_web`/`deeptutor_cli`、`book`/`co_writer`/`knowledge`、`learning`+`mastery_path`、产品文档);保留 `core/agentic`、`core/context`、`core/stream*`、`core/trace`、`services/{llm,rag,prompt,config,sandbox}`、`services/{session,memory}`、`tools/`(核心)、`subagent`、`runtime/registry`;`runtime/orchestrator` 重写为瘦运行时;偏产品化工具(cron/github/notebook)降级为可选包。删完不依赖任何 `deeptutor.*`。
  - **地基**:落地 `BaseState`(仅 `messages`/`usage`/`trace_meta`/`language`)、`AgentDeps` 契约、Agent 叶子统一契约(编译为最小子图)、LangGraph 原生流式、瘦 `astream_events → StreamBus` bridge、InMemory checkpointer;Agent 内部绝不 import 全局单例,自带默认 prompt,可传入最小 `AgentDeps` 无外部服务 `graph.invoke()`。
  - **math_animator + visualize**:五段流水线映射为线性图;`render → 报错 → codegen(repair) → 再 render` 映射为可见条件环,`max_retries=4` 平移为 gate;每次 render 是 checkpoint 边界,崩溃后从上次 checkpoint 续跑。`visualize` 复用同一线性原型与 retry 环,含 manim 分支复用。
  - **验收**:`FakeDeps` 驱动主 seam,断言事件序列 + 最终 State;retry 环专项——注入一次 render 失败 → 断言触发 repair → 断言最终成功/收尾;checkpointer 续跑专项——render 崩溃后从上次 checkpoint 恢复且状态保留。

### 2. `ReActOrchestration` 模板 + question 实例化

- **Blocked by**:#1
- **覆盖 US**:12, 24
- **说明**:循环类原型模板,LLM node ⇄ tool node 双节点环;循环计数入 State 并在条件边 gate,或设 `recursion_limit`;工具并行(`MAX_PARALLEL_TOOL_CALLS=8`)收进 tool node 一处。
  `question` 归入循环类原型(而非流水线类),作为模板的首个实例化范例落地。
  验收:终止判定与工具并行专项断言;`question` 走通模板主 seam。

### 3. chat 循环健壮性逐条落地到模板

- **Blocked by**:#2
- **覆盖 US**:25
- **说明**:多级 provider 降级、上下文窗口保护、强制收尾、思考标签过滤逐条落地,保证默认流量可靠性不回归。
  验收:`FakeDeps` 脚本化各降级/截断场景,断言事件序列与最终 State。

### 4. deep_research:递归 supervisor + `Send` fan-out + reducer 合并

- **Blocked by**:#2
- **覆盖 US**:21, 22, 23
- **说明**:supervisor 每轮重算 pending → `Send(批, ≤max_parallel_topics)` → aggregate → 条件边(仍有 pending 回 supervisor,否则去 report)。
  为 `queue`(`DynamicTopicQueue`)与 `citations`(`CitationManager`)编写 LangGraph reducer,worker 经 `APPEND` 追加的子课题合并进共享 State;保留 `safety_cap`。
  复核 `CitationManager` 的 `asyncio.Lock` 在 LangGraph 执行模型下的正确性,修掉 write-on-every-add 的 O(N²) 全量写盘。
  验收:reducer 合并专项——并发 worker 追加 → 断言队列合并正确、无丢失/无重复。

### 5. HITL 统一到 `interrupt()` + `Command(resume)`

- **Blocked by**:#4
- **覆盖 US**:26, 27, 28, 29
- **说明**:大纲确认从「进程退出 + 带 `confirmed_outline` 重新构造」升级为 `interrupt()` + `Command(resume=confirmed_outline)` 的真正暂停恢复,保留 Phase 1-2 状态;rephrase 的 `ask_user` 澄清在 worker 子图内同样用 `interrupt()`。
  WebSocket `_bus_registry` 输入回填改对接 `Command(resume=...)`;`interrupt` 嵌在 mapped subgraph 内时 resume 路由回正确 worker;进程重启后仍能恢复。
  验收:`interrupt → Command(resume) →` 断言从断点续跑且状态保留。

### 6. 双层记忆:Checkpointer + `BaseStore`,默认零依赖后端

- **Blocked by**:#4(后置于 deep_research)
- **覆盖 US**:30, 31, 34, 35
- **说明**:短期线程态 → Checkpointer,长期跨线程记忆 → `BaseStore`,职责清晰分离。
  `services/memory` 重写为 `BaseStore` 实现;默认 InMemory/SQLite;语义记忆的 embedding provider 并入 `AgentDeps`;PocketBase 降为可选后端,非默认非唯一。

### 7. 生产持久化后端:Postgres(pgvector)Store + PostgresSaver 可切换

- **Blocked by**:#6
- **覆盖 US**:32, 33
- **说明**:生产环境记忆后端换成 `PostgresStore`(pgvector);checkpointer 后端可从 InMemory/SQLite 换到 `PostgresSaver`。
  接口与默认后端在范围内,生产部署编排本身不在范围。

---

## 依赖关系图

```
#1 硬分叉 + 地基 + math_animator + visualize
 └─> #2 ReAct 模板 + question
      ├─> #3 chat 健壮性
      └─> #4 deep_research ──┬─> #5 HITL
                             └─> #6 双层记忆 ──> #7 Postgres 后端
```
