# DeepTutor 编排架构与二次开发指南

本文档面向在 DeepTutor（本仓库 `ResEduPod`）之上做二次开发的工程师。
重点讲清楚这个 Agent 的**编排设计（orchestration）**：一条用户消息是如何从入口层，经过编排器、能力层、Agent 循环、工具分发，最终以流式事件返回给前端的。
读完本文，你应当能够独立新增一个工具（Tool）、新增一个能力（Capability），或改造 Agent 循环本身。

> 阅读顺序建议：先读「零、编排不是一个 loop」纠正最常见的误解，再读「一、总体架构」建立心智模型，然后「三、核心编排数据流」把一条消息走通，最后按需查阅分层细节与「扩展开发」章节。

---

## 零、编排不是「一个对话 loop」——它有三种形态

**最容易产生的误解**：以为整个系统就是一个「LLM ↔ 工具」的对话循环。
**并非如此**。那个循环只是默认 `chat` 能力的实现，是 7 个能力里最简单的 1 个。

`ChatOrchestrator` 本身**只负责路由**（根据 `active_capability` 选中某个能力），
真正的**智能体编排逻辑写在每个能力各自的 `run()` / `pipeline` 里**，且分为三种截然不同的形态：

### 形态一：单循环 ReAct（`chat`；`deep_solve` / `mastery_path` 在其上做增强）

一个回合 = 一条不断增长的对话上的多轮「LLM 调用 → 并行工具 → LLM 调用」，
**某一轮不再调用工具即视为结束**（隐式终止协议）。
`deep_solve` / `mastery_path` 复用同一循环，只是通过 `LoopCapability` 叠加自有工具与系统提示，
或用「标签协议」加上「计划 / 每步 done 闸门 / 有界 replan」的确定性骨架。

- 骨架：`agents/chat/agent_loop.py::AgentLoop._run_loop`
- 标签驱动变体：`core/agentic/loop.py::run_agentic_loop`（见「四、Agent 循环设计」）

**形态一数据流（chat）：**

```
UnifiedContext (user_message + history + kb + attachments + enabled_tools)
      │
      ▼  AgenticChatPipeline.run() 准备：组合工具集、构建 tool schema、
      │  （可选）pre_loop 前置简报、KB 种子块注入首条 user 消息
      ▼
 ┌────────────────────── AgentLoop._run_loop（单一增长对话）──────────────────────┐
 │                                                                               │
 │   messages ──▶ 一次 LLM 调用（流式）                                            │
 │                    │  文本边生成边 stream.content 推给用户                       │
 │                    ▼                                                           │
 │              这一轮有 tool_calls 吗？                                           │
 │             ┌────────┴─────────┐                                              │
 │          有 │                  │ 没有                                          │
 │             ▼                  ▼                                              │
 │   dispatch_tool_calls     ★ 这轮文本就是最终答案 ★                             │
 │   （并行执行, ≤8, 去重）      → 结束循环（隐式终止协议）                          │
 │             │                                                                 │
 │             ▼                                                                 │
 │   role=tool 结果 append 回 messages                                           │
 │             │                                                                 │
 │      ┌──────┴───────┬──────────────┐                                          │
 │      │ 普通结果      │ pause(ask_user)│ terminate(某工具要求结束)               │
 │      ▼              ▼               ▼                                          │
 │  回到顶部       等用户回复注入      工具内容即终止产物                           │
 │  下一轮 LLM     后继续下一轮        → 结束循环                                   │
 │      │                                                                        │
 │      └── 轮数预算耗尽仍在要工具？→ 强制追加一轮「禁用工具的 finish 轮」逼出答案   │
 └───────────────────────────────────────────────────────────────────────────────┘
      │
      ▼  emit_capability_result(response, rounds, tool_steps, sources, usage)
   StreamBus  →  turn_runtime 拼装持久化答案（按 call_role 过滤 narration 轮）→ 前端
```

要点：
- **唯一的循环**就是这个「LLM ↔ 工具」多轮环；**没有预设阶段**，模型自己决定何时停（不调工具即答完）。
- 每轮文本都实时流式；轮末的 `call_role`（`narration`=调工具前的旁白 / `finish`=答案）告诉前端与落盘层如何处理。
- `ask_user` 用 `pause` 暂停回合等真人回复；`_guard_context_window`、provider 多级降级、中途失败 `_forced_finish` 抢救是它的健壮性保障（详见「四」）。
- `deep_solve` / `mastery_path` 就是在这张图上，通过 `LoopCapability` 叠加自有工具 + 系统提示（solve 还加计划/done 闸门/replan 骨架），**循环结构不变**。

### 形态二：固定顺序的**多智能体流水线**（`math_animator` / `visualize` / `question`）

这里**根本不是对话循环**，而是**多个专职 Agent 串成一条产线**，前一个的结构化输出喂给后一个。

以 `math_animator` 为例（`agents/math_animator/`）：

- `agents/` 目录下是 5 个独立 Agent 类——`ConceptAnalysisAgent` / `ConceptDesignAgent` /
  `CodeGeneratorAgent` / `VisualReviewAgent` / `SummaryAgent`。
  它们继承的是**另一套** `BaseAgent`（`agents/base_agent.py`，实现 `process()`），
  与 chat 循环用的抽象完全不同。
- `capability.py:81-199` 顺序编排各阶段（每个阶段 `stream.stage(...)` 包裹）：
  ```
  concept_analysis → concept_design → code_generation
      → code_retry（渲染 + 自愈重试子循环）→ summary → render_output
  ```
- `code_retry` 阶段内嵌一个「生成 Manim 代码 → 运行 → 报错 → 重新生成」的**自愈子循环**
  （`retry_manager.py::CodeRetryManager`）。

这是典型的 **planner → executor → reviewer 分工流水线**。`visualize`、`question`（`question/agents/`）同构。

**形态二数据流（math_animator）：**

```
UnifiedContext (user_message + attachments + config_overrides)
      │
      ▼   capability.run() 顺序编排，每段用 stream.stage(...) 包裹
┌───────────────────┐
│ ConceptAnalysis   │  process() → analysis  ── 结构化对象（pydantic model）
│      Agent        │
└─────────┬─────────┘
          │ analysis
          ▼
┌───────────────────┐
│ ConceptDesign     │  process(analysis) → design
│      Agent        │
└─────────┬─────────┘
          │ design
          ▼
┌───────────────────┐
│ CodeGenerator     │  process(analysis, design) → generated.code
│      Agent        │
└─────────┬─────────┘
          │ initial_code
          ▼
┌──────────────────────────── code_retry ────────────────────────────┐
│  CodeRetryManager.render_with_retries   （自愈子循环, 最多 N 次）      │
│                                                                     │
│   code ──▶ ManimRenderService.render ──成功──▶ (可选)VisualReview ──▶ │
│    ▲                    │                            │  不合格         │
│    │ repair_callback    │ 渲染报错                     ▼               │
│    └── CodeGenerator ◀──┴──────────────◀────── 反馈 error/review 意见  │
│         Agent（按报错重新生成代码）                                    │
└─────────┬───────────────────────────────────────────────────────────┘
          │ final_code + render_result(artifacts, retry_history)
          ▼
┌───────────────────┐
│  Summary Agent    │  process(analysis, design, render_result) → summary_text
└─────────┬─────────┘
          │
          ▼
   emit_capability_result(response=summary, code, artifacts, timings, …)
          │
          ▼        （全程各 Agent 的 LLM 调用经 trace_callback 桥接为
     StreamBus       stream.progress/thinking 事件，实时推给前端追踪面板）
```

要点：**阶段间传递的是结构化对象**（`analysis`/`design`/`render_result`），不是自由文本对话；
每个 Agent 只做一件事、可独立测试；唯一的循环是 `code_retry` 里那个「渲染失败→按报错重生成」的自愈环。

### 形态三：**动态分解 + 并行子智能体 + 人在环**（`deep_research`）

系统里最复杂的编排（`agents/research/pipeline.py`，约 2844 行），一个四相流程：

1. **Phase 1 改写 → Phase 2 分解**：把课题拆成子课题大纲（`_decompose`），
   然后**把大纲 `stream.result` 给用户确认**——一个 human-in-the-loop 闸门（`pipeline.py:461-505`）。
2. **Phase 3 并行研究**：确认后的子课题灌入 `DynamicTopicQueue`，
   用 `asyncio.gather` **并行**驱动多个研究块（并发由 `max_parallel_topics` 控制，`pipeline.py:995-998`）；
   每个块内部各自跑一个**标签驱动的 agentic 子循环**。
3. **动态生长**：研究途中一个块可 `queue.append_child(...)` **向队列追加新子课题**（`pipeline.py:2558`）——
   队列自我扩张，这是自主研究智能体的核心特征。
4. **Phase 4 迭代成稿**：汇总所有块的证据 + 引用写成报告（`_write_report`）。

这就是 **orchestrator-workers（规划器分解 → 并行 worker 舰队 → 汇总器）** 模式。

**形态三数据流（deep_research）：**

```
UnifiedContext (topic + kb + attachments)
      │
      ▼  Phase 1
 ┌──────────┐  _rephrase()  精炼课题
 │ rephrasing│──────────────┐
 └──────────┘               ▼  Phase 2
                     ┌────────────┐  _decompose() → 子课题大纲 outline[]
                     │ decomposing│
                     └─────┬──────┘
                           │ stream.result(outline_preview)
                           ▼
                   ╔═══════════════════╗   人在环闸门（human-in-the-loop）
                   ║  等待用户确认大纲   ║   用户可改/确认后带 confirmed_outline
                   ╚═════════╤═════════╝   重新发起同一逻辑研究任务
                             │ confirmed_outline[]
                             ▼  Phase 3
        ┌───────────────── researching ─────────────────────────────┐
        │  DynamicTopicQueue  ←──── append_child() 动态追加新子课题     │
        │        │            （某个 worker 研究中发现需要深挖时）       │
        │        ▼                                          ▲          │
        │  _drive_queue: while 有 pending:                  │          │
        │     取一批(batch = max_parallel_topics)            │          │
        │        │                                          │          │
        │        ▼   asyncio.gather 并行                     │ APPEND   │
        │   ┌─────────┐ ┌─────────┐ ┌─────────┐             │ 标签      │
        │   │ worker1 │ │ worker2 │ │ workerN │ …           │          │
        │   │ 标签驱动 │ │ 标签驱动 │ │ 标签驱动 │────────────┘          │
        │   │ 子循环   │ │ 子循环   │ │ 子循环   │                       │
        │   └────┬────┘ └────┬────┘ └────┬────┘                       │
        │        │  每个 worker: run_agentic_loop (core/agentic/loop) │
        │        │  RAG/web 检索 → _summarise_tool_result → 记引用     │
        │        ▼                                                    │
        │   CitationManager  收集全部引用（跨 worker 共享）             │
        │   循环回到 while，直到队列（含动态追加的子课题）全部研究完      │
        └────────┬───────────────────────────────────────────────────┘
                 │ researched_blocks[]（按队列顺序：父在子前）
                 ▼  Phase 4
          ┌────────────┐  _write_report() 迭代汇总证据+引用
          │  reporting │
          └─────┬──────┘
                │ report_text + metadata(partial?, citation_count…)
                ▼
         emit_capability_result(...)  →  StreamBus  →  前端
```

要点：
- **规划器（decompose）与 worker 是不同角色**；worker 是并行的、每个各跑一个标签驱动子循环。
- **队列会自我生长**：worker 通过 `APPEND` 标签让 `on_intermediate` 钩子调用 `append_child`，
  新子课题在后续调度轮次被取出研究——这是「自主深挖」的来源，也是它区别于固定流水线的关键。
- **有界与兜底**：`safety_cap` 限制调度轮数；未完成的块用空知识回填，报告标记 `partial=True`。
- **人在环**：大纲需用户确认才进入昂贵的并行研究阶段。

### 一张表总览

| 能力 | 编排形态 | 编排骨架文件 |
| --- | --- | --- |
| `chat` | 单循环 ReAct（隐式终止：不调工具即结束） | `agents/chat/agent_loop.py` |
| `deep_solve` / `mastery_path` | 单循环 + 标签协议/LoopCapability 增强 | `capabilities/solve/loop.py` + `core/agentic/loop.py` |
| `math_animator` / `visualize` / `question` | **固定顺序多智能体流水线**（+ 自愈重试子循环） | `agents/*/pipeline.py` + `agents/*/agents/*.py` |
| `deep_research` | **动态分解 + 并行子智能体 + 人在环** | `agents/research/pipeline.py` |
| `subagent`（consult） | 把用户本机 Claude Code/Codex 当**外部委派智能体** | `capabilities/subagent/` + `services/subagent/` |

> 记住这张表，再看后文：`ChatOrchestrator`（第一、三章）是**路由层**；
> 「四、Agent 循环设计」详解的是**形态一**；形态二、三的编排在各能力的 `pipeline.py` 里（见「八、二次开发」的选项 A）。

### 两套 Agent 基类别搞混

系统里存在**两个不同的 `BaseAgent`/Agent 抽象**，对应形态一 vs 形态二/三：

| 抽象 | 位置 | 用途 | 接口 |
| --- | --- | --- | --- |
| chat 循环的 pipeline/loop | `agents/chat/` + `core/agentic/` | 形态一：一个回合一个循环，原生 tool-calling | `AgentLoop.run` / `run_agentic_loop` |
| 专职 `BaseAgent` | `agents/base_agent.py` | 形态二/三：可复用的单一职责 Agent（分析/设计/生成/评审/汇总） | `async process(...)` |

新增「多阶段/多智能体」能力时，你会写若干个继承 `agents/base_agent.py::BaseAgent` 的专职 Agent，
再在能力的 `pipeline` 里把它们编排起来——**而不是**去改 chat 的那个循环。

---

## 一、总体架构

DeepTutor 自称是 **agent-native（智能体原生）** 的终身个性化辅导系统。
它的架构围绕一个「两层插件模型 + 统一编排器」展开：

- **Level 1 — 工具（Tools）**：由 LLM 按需调用的单次函数，例如 `rag`、`web_search`、`exec`、`ask_user`。
- **Level 2 — 能力（Capabilities）**：接管一整个回合（turn）的多阶段流水线，例如 `chat`、`deep_solve`、`deep_research`、`mastery_path`。
- **ChatOrchestrator（编排器）**：所有入口的统一收敛点，把 `UnifiedContext` 路由到某个能力，并管理流式事件总线的生命周期。

三个入口共享同一套编排：

```
入口层:   CLI (Typer)        WebSocket /api/v1/ws        Python SDK (facade)
              |                       |                        |
              +-----------------------+------------------------+
                                      v
                        ┌───────────────────────────────┐
                        │        ChatOrchestrator        │
                        │  UnifiedContext → 选中的能力    │  （默认 chat）
                        └──────────┬──────────┬──────────┘
                                   │          │
                         ┌─────────▼──┐  ┌────▼──────────────┐
                         │ ToolRegistry│  │ CapabilityRegistry │
                         │  (Level 1)  │  │    (Level 2)       │
                         └─────────────┘  └────────────────────┘
                                   │          │
                                   └────┬─────┘
                                        v
                                 ┌─────────────┐
                                 │  StreamBus   │  异步事件扇出
                                 └──────┬──────┘
                                        v
                            消费者（前端 WS / CLI 渲染 / JSON 落盘）
```

关键设计原则：

1. **单一入口收敛**：无论 CLI、WebSocket 还是 SDK，最终都调用 `ChatOrchestrator.handle(context)`。
2. **一切皆事件流**：能力和工具不直接返回结果，而是往 `StreamBus` 上 `emit` 事件；编排器把事件扇出给消费者。这让「实时流式 UI」和「批处理落盘」用同一套代码。
3. **能力接管回合，工具装点回合**：一个回合由唯一一个能力驱动；能力内部可以调用任意多个工具。
4. **Partner（IM 伴学）没有独立引擎**：每条 IM 消息也只是被翻译成一个 `UnifiedContext`，走同一个 `ChatOrchestrator → AgenticChatPipeline`。

对应的关键文件：

| 路径 | 职责 |
| ---- | ---- |
| `deeptutor/runtime/orchestrator.py` | `ChatOrchestrator` — 统一编排入口 |
| `deeptutor/runtime/registry/capability_registry.py` | 能力注册表（内建 + 插件） |
| `deeptutor/runtime/registry/tool_registry.py` | 工具注册表 + OpenAI schema 生成 |
| `deeptutor/runtime/bootstrap/builtin_capabilities.py` | 内建能力的类路径映射 |
| `deeptutor/core/context.py` | `UnifiedContext` 数据类（贯穿全流程的上下文） |
| `deeptutor/core/stream.py` / `stream_bus.py` | `StreamEvent` 协议 + 异步事件总线 |
| `deeptutor/core/capability_protocol.py` | `BaseCapability` + `CapabilityManifest` |
| `deeptutor/core/tool_protocol.py` | `BaseTool` + `ToolDefinition` |
| `deeptutor/agents/chat/agentic_pipeline.py` | 默认 chat 能力的装配核心 |
| `deeptutor/agents/chat/agent_loop.py` | chat 的单循环 Agent（原生 tool-calling） |
| `deeptutor/core/agentic/loop.py` | 通用的「标签驱动」Agent 循环（solve/research 等用） |
| `deeptutor/core/agentic/tool_dispatch.py` | 并行工具分发 + 子追踪 |
| `deeptutor/api/routers/unified_ws.py` | 统一 WebSocket 端点 |
| `deeptutor/services/session/turn_runtime.py` | 回合级运行时（组装 context、消费事件、落盘） |

---

## 二、核心抽象

### 2.1 UnifiedContext —— 贯穿全程的上下文

`deeptutor/core/context.py` 中的 `UnifiedContext` 是一个 dataclass，代表「处理单个用户回合所需的一切」。
它从入口层被组装出来，流经编排器、能力、循环，直到每一次工具调用。

关键字段（节选）：

- `session_id` / `user_message` / `conversation_history`：会话标识、当前输入、历史消息（OpenAI 格式）。
- `enabled_tools`：用户在 composer 上勾选启用的工具（`None`=未指定，`[]`=显式全部关闭）。
- `allowed_builtin_tools`：内建工具的白名单闸门（Partner 用它按伴学粒度禁用内建工具）。
- `active_capability`：用户选择的能力名；`None` 走默认 `chat`。
- `knowledge_bases`：本回合要用的知识库（供 RAG）。
- `attachments`：随消息附带的图片/文件。
- `config_overrides`：单次请求的配置微调（如 temperature、`subagent_consult_budget`）。
- `language`：`"en"` / `"zh"`。
- `memory_context` / `persona_context` / `skills_manifest` / `source_manifest`：预先注入到 system prompt 的各类上下文块。
- `metadata`：能力私有的扩展字段（如 `turn_id`、`solve_mode`、`_subagent_state`、`wait_for_user_reply` 等）。

> `metadata` 是能力之间「私有约定」的载体。例如 subagent 能力通过 `metadata["_min_loop_rounds"]` 抬高循环预算，solve 通过 `metadata["solve_mode"]` 声明自己激活。二次开发新增能力时，用 `metadata` 携带回合级私有状态是标准做法。

### 2.2 StreamBus 与 StreamEvent —— 事件扇出

`deeptutor/core/stream_bus.py` 中的 `StreamBus` 是「单个回合」的异步事件总线：

- **生产者**（能力、工具）调用 `bus.content(...)` / `bus.thinking(...)` / `bus.tool_call(...)` / `bus.tool_result(...)` / `bus.progress(...)` / `bus.sources(...)` / `bus.error(...)` 等便捷方法 emit 事件。
- **消费者**通过 `async for event in bus.subscribe()` 拉取事件。
- 支持**多订阅者扇出**，且新订阅者会先收到 `_history` 里的历史事件重放（replay），再接收后续实时事件——这保证「中途接入的消费者」也能拿到完整流。
- `bus.stage(name)` 是个 async 上下文管理器，进出块时自动 emit `STAGE_START` / `STAGE_END`。
- `wait_for_input(prompt)` / `submit_input(content)`：支撑 `ask_user` 这类「暂停回合等用户输入」的交互。

事件类型见 `deeptutor/core/stream.py` 的 `StreamEventType`（`SESSION` / `CONTENT` / `THINKING` / `TOOL_CALL` / `TOOL_RESULT` / `PROGRESS` / `SOURCES` / `RESULT` / `STAGE_START` / `STAGE_END` / `ERROR` / `DONE` / `WAIT_FOR_INPUT` 等）。

事件上大量携带 `metadata`，其中 **trace 元数据**（`call_id` / `trace_id` / `trace_role` / `trace_group` / `trace_kind` / `call_kind` / `call_role`）驱动前端的「调用追踪面板」（把每次 LLM 调用、每个工具调用渲染成可展开的子追踪卡片）。二次开发涉及自定义 UI 呈现时，重点关注 `deeptutor/core/trace.py` 的 `build_trace_metadata` / `derive_trace_metadata` / `merge_trace_metadata`。

### 2.3 每回合总线注册表 —— 支持外部注入用户输入

`stream_bus.py` 底部维护了一个进程级的 `_bus_registry`（`turn_id → StreamBus`）：

- 编排器在回合开始时 `register_bus(turn_id, bus)`，结束时 `unregister_bus(turn_id)`。
- WebSocket 收到 `user_input` 消息时，可以通过 `get_bus(turn_id)` 找到活跃总线并 `submit_input`，从而把用户的回复注入到正在暂停等待的 `ask_user` 流程里。

---

## 三、核心编排数据流（把一条消息走通）

以「WebSocket 前端发来一条聊天消息」为例，完整链路如下：

```
前端 WS 消息
  → api/routers/unified_ws.py                （WebSocket 端点，鉴权、解析）
  → services/session/turn_runtime.py::_run_turn
        · 组装 UnifiedContext（历史、记忆、persona、skills、附件、turn_id…）
        · 建立 ask_user 回复队列，注入 metadata["wait_for_user_reply"]
  → runtime/orchestrator.py::ChatOrchestrator.handle(context)
        · 若无 active_capability → 默认 "chat"
        · 从 CapabilityRegistry 取出能力实例
        · emit SESSION 事件
        · 新建 StreamBus，register_bus(turn_id, bus)
        · asyncio.create_task 跑 capability.run(context, bus)
        · async for event in bus.subscribe(): yield event   ← 事件流出
        · 回合结束 emit DONE、close bus、发布 CAPABILITY_COMPLETE 到全局 EventBus
  → capability.run 内部（以 chat 为例）
  → agents/chat/capability.py::ChatCapability.run
  → agents/chat/agentic_pipeline.py::AgenticChatPipeline.run
        · 准备 deferred tools（MCP）、判定 exec 权限
        · 组合本回合启用的工具集（compose_enabled_tools）
        · 构建 OpenAI tool schema
  → agents/chat/agent_loop.py::AgentLoop.run
        · 运行 pre_loop 前置简报（如 explore_context）
        · 检索 KB 种子块（kb_seed）注入首条 user 消息
        · 进入 _run_loop：多轮「LLM 调用 + 工具分发」
  → core/agentic/tool_dispatch.py::dispatch_tool_calls
        · 并行执行本轮所有工具调用，每个工具一条子追踪
  → StreamBus.emit(...)  ← 一路把 content/thinking/tool_call/tool_result 推出去
  → turn_runtime 消费事件：过滤、拼装最终答案、落盘会话
  → unified_ws 把事件序列化推给前端
```

回合结束后，编排器还会向**全局 EventBus**（`deeptutor/events/event_bus.py`）发布一条 `CAPABILITY_COMPLETE` 事件——这是一个与 `StreamBus`（回合内）不同层级的、进程级的发布订阅总线，用于跨回合/跨子系统的解耦通知（如后台记忆更新、统计等）。

> **两条总线不要混淆**：`StreamBus` 是「单回合内、生产者→消费者」的流式扇出；`EventBus` 是「进程级、跨回合」的发布订阅。

---

## 四、Agent 循环设计（形态一的详解）

> 本章只深入「零章·形态一」的**单循环**能力（`chat` 及其增强）。
> 形态二（多智能体流水线）、形态三（动态分解 + 并行）的编排不在这里，
> 它们各自的骨架在对应能力的 `pipeline.py`（见「零、编排不是一个 loop」与「八、二次开发·选项 A」）。

DeepTutor 的单循环能力有**两套循环实现**，服务于不同能力，理解它们的差异是二次开发的关键。

### 4.1 chat 的「单循环」Agent（原生 tool-calling）

文件：`deeptutor/agents/chat/agent_loop.py::AgentLoop`。这是默认 chat 能力用的循环，设计非常干净：

- **一个回合 = 一条不断增长的对话（single growing conversation）上的一个循环**。
- 每一轮（round）= 一次 LLM 调用：
  - LLM 的文本**边生成边流式**推给用户（作为 `content`）。
  - LLM 的 tool_calls 被并行分发执行，`role=tool` 的结果 append 回对话，然后进入下一轮。
- **终止判定极简**：某一轮如果 LLM **没有调用任何工具**，这一轮的文本就是最终答案，循环结束（模型自己决定「我说完了」）。
  - 首轮就不调用工具 = 「无需探索」的快捷路径。
- **预算耗尽兜底**：如果轮数预算用完时模型还在要求调工具，则强制追加一轮「禁用工具的 finish 轮」逼它给出答案（`_forced_finish`）。
- 每轮完成时 emit 一个 `call_role`（`narration` 表示这轮文本只是调工具前的旁白，`finish` 表示这轮文本就是答案），前端据此决定如何渲染、`turn_runtime` 据此决定哪些文本进入「持久化答案」。

其中值得关注的健壮性设计：

- `InlineThinkFilter`：增量切分流式内容里的 `<think>`/`<thinking>` 标签，把推理内容分流到 thinking 通道，保持 content 通道干净。
- `_create_response_stream` 里的**多级降级**：provider 不支持 `stream_options` → 去掉重试；不支持原生 tool schema → 去掉 tools 重试；不支持图片输入 → 剥离图片重试。
- `_guard_context_window`：超出上下文窗口 90% 时，把较早的 `role=tool` 结果替换为占位标记（snip），必要时提示模型「需要就重新调工具」。
- 中途某轮 LLM 失败（非首轮）会走 `_forced_finish` 抢救，而不是丢弃整个回合。

`AgenticChatPipeline`（`agentic_pipeline.py`）是 chat 的**装配器**，负责循环之外的一切准备工作：

- **工具组合** `_compose_enabled_tools`：把「用户勾选的工具」+「上下文自动挂载的内建工具」（由 `ToolMountFlags` 决定：有没有 KB、有没有附件、有没有 memory/notebook/skills、exec 是否可用、有没有 deferred/MCP 工具）+「激活能力自带的 owned_tools」组合起来。
- **KB 种子** `_retrieve_kb_seed_block`：回合开始先对挂载的知识库做一次检索，把结果作为「种子上下文」塞进首条 user 消息（而非 system prompt，以保持 system prompt 字节稳定、利于 provider 的 prefix 缓存）。
- **每工具私有 kwargs 注入** `_augment_tool_kwargs`：服务端为不同工具注入私有参数（如 `exec` 的沙箱工作目录与挂载、`cron` 的 owner 路由、`rag` 的默认 mode），**模型永远看不到也无法伪造**这些参数。
- **deferred tools（渐进式披露）**：MCP 工具默认不全量塞进 schema，而是先给一个「清单」，模型通过 `load_tools` 工具按需加载，避免 schema 爆炸。

### 4.2 通用「标签驱动」循环（solve / research / mastery 等）

文件：`deeptutor/core/agentic/loop.py::run_agentic_loop`。这是一个**能力无关**的、由「标签协议」驱动的循环。

核心思想：让 LLM 在每轮输出的**第一行**打一个标签（label），循环据此决定动作：

- `LabelProtocol` 声明这个能力的标签词表：
  - `allowed`：允许出现的所有标签。
  - `terminal`：会**退出循环**的标签（如 `FINISH`）。
  - `intermediate`：让循环**继续**的标签（如 `THINK`，其后文本作为 assistant 上下文保留）。
  - `final`：其后文本应作为「正文」emit 给用户的标签。
  - `tool_label`：唯一表示「本轮要调工具」的标签（或 `None` 禁用原生 tool-calling）。
- `LoopHost` 是能力提供的回调协议：`dispatch_tools` / `guard_context_window` / `validate_terminal` / `force_finalize` / `on_intermediate` / `before_iteration` / `emit_final` 等，把「能力专属的行为」注入通用循环。
- 循环负责**协议校验**：只能有一个标签、不能行内重复、tools 只能和 tool_label 一起出现；违规时 emit 重试提示并把「修复 prompt」喂回下一轮（`_append_repair_messages`）。

这套设计让 solve/research 这类需要「显式规划—执行—复盘」结构的能力，能在不失去 Agent 灵活性的前提下，获得**确定性的骨架**。例如 `deeptutor/capabilities/solve/loop.py` 的 `SolveLoopCapability` 在 chat 循环之上叠加了「已提交的计划 + 每步 done 闸门 + 有界 replan」三个自有工具。

> **两套循环的取舍**：
> - chat 单循环：靠「不调工具即结束」的隐式协议，简单、延迟低，适合开放式对话。
> - 标签驱动循环：靠显式标签协议，适合需要多阶段、可校验、可强制收尾的深度能力。

### 4.3 LoopCapability —— 在 chat 循环上做「非侵入式增强」

文件：`deeptutor/capabilities/protocol.py`。这里有两个概念，注意与 Level 2 的 `BaseCapability` 区分：

- `LoopCapability`（Protocol）：**每回合的可选扩展点**，挂在 chat Agent 循环上。它复用 chat 的**完整工具面**（所有内建工具 + 用户勾选照旧生效），并在激活时叠加自己的 `owned_tools`。
  - 关键方法：`is_active(context)` / `system_block(...)`（贡献一段 system prompt）/ `augment_kwargs(...)`（注入自有工具的私有参数）/ `pre_loop_seed(...)`（往首条 user 消息追加种子）。
  - 可选 `pre_loop` 钩子：在答案循环第一次 LLM 调用**之前**跑一次有界前置 pass（如 `explore_context` 先客观地把附件源梳理一遍）。
- `KnowledgeCapability`（基类）：一种**独占（exclusive）** 的 LoopCapability。激活时它**替换**整个工具面，只留自己的 `owned_tools` + `ask_user` 兜底，而不是叠加。典型是 subagent 能力。

这解释了 `deep_solve`、`mastery_path` 为什么能「既是 Level 2 能力，又复用 chat 循环」：它们在 Level 2 层声明自己（供用户选择、走 `ChatOrchestrator` 路由），内部又实例化 `AgenticChatPipeline` 并激活对应的 `LoopCapability` 增强。

### 4.4 工具分发（并行 + 去重 + 暂停/终止）

文件：`deeptutor/core/agentic/tool_dispatch.py::dispatch_tool_calls`。能力无关的并行分发器：

- 一批 tool_calls **并行执行**（上限 `MAX_PARALLEL_TOOL_CALLS = 8`），每个工具一条独立子追踪。
- **批内去重** `_detect_duplicate_calls`：模型偶尔在一条 assistant 消息里发重复 tool_calls；重复的用桩结果短路，保持 OpenAI 的 tool_call/tool_message 配对完整。`ask_user` 更严：一批里第二个 `ask_user` 一律算重复（UI 只能挂一张待答卡）。
- **私有 kwargs 剥离**：以 `_` 开头的服务端注入参数（如 `_sandbox_mounts`）不进事件 payload（既是安全隔离，也避免不可序列化对象炸掉 WS 推送与落盘）。
- 返回 `DispatchOutcome`，其中：
  - `pause`（如 `ask_user`）：回合不结束，调用方等用户回复，把回复替换进对应 `role=tool` 消息后继续迭代。
  - `terminate`：某工具要求本轮后结束，其内容成为终止产物。
- 单个工具的实际执行在 `execute_tool_call`，它统一了「retrieve 风格进度事件」的 emit，并把工具异常兜成结构化失败结果（不让单个工具异常掀翻整个回合）。

---

## 五、注册与发现机制

### 5.1 能力注册表

`deeptutor/runtime/registry/capability_registry.py`：

- 内建能力来自 `builtin_capabilities.py` 的 `BUILTIN_CAPABILITY_CLASSES`（name → `module:Class` 字符串），首次访问 `get_capability_registry()` 时惰性 import 并实例化。
- 插件能力通过 `deeptutor.plugins.loader` 的 `discover_plugins` / `load_plugin_capability` 动态发现。
- 每个能力有一个 `CapabilityManifest`（`name` / `description` / `stages` / `tools_used` / `cli_aliases` / `request_schema` / `config_defaults`），供前端展示与 CLI 别名路由。

当前内建能力：`chat`、`deep_solve`、`deep_question`、`deep_research`、`math_animator`、`visualize`、`mastery_path`。

### 5.2 工具注册表

`deeptutor/runtime/registry/tool_registry.py`：

- 内建工具来自 `deeptutor/tools/builtin/__init__.py` 的 `BUILTIN_TOOL_TYPES`；`TOOL_ALIASES` 支持别名 + 默认参数。
- 支持 `deferred`（渐进式披露）标记的工具（MCP 工具走这条路）。
- `build_openai_schemas()` 生成 OpenAI function-calling schema；`build_prompt_text()` 生成多种格式的工具清单文本（供 system prompt）。
- `execute(name, /, **kwargs)`：`name` 是 positional-only，避免和工具自身名为 `name` 的参数冲突。

工具集合（节选，来自 AGENTS.md）：用户可勾选的有 `brainstorm` / `web_search` / `paper_search` / `reason`；上下文自动挂载的有 `rag` / `read_source` / `read_memory` / `write_memory` / `read_skill` / `load_tools` / `exec` / `code_execution` / `list_notebook` / `write_note` / `web_fetch` / `github` / `cron` / `ask_user` 以及 mastery 相关工具。

---

## 六、支撑服务层（services/）

Agent 循环调用的一切外部能力都在 `deeptutor/services/` 下，采用「工厂/单例 + 注册表」模式，通过 `_augment_tool_kwargs` 或工具内部按需引入。重点：

- `services/llm/`：LLM provider 抽象、流式、原生 tool-calling 能力探测、多模态消息准备、上下文窗口解析、思考标签清洗。`provider_registry.py` + `model_selection/` 负责多 provider/多模型选择。
- `services/mcp/`：Model Context Protocol 集成。`manager.py` 管理 MCP server 生命周期，把远端工具暴露为 deferred tools（配合 `load_tools`）。
- `services/rag/`：检索增强。`factory.py` 装配不同引擎（LightRAG / LlamaIndex / FAISS），`smart_retriever.py`、`pipelines/` 负责索引与查询；`kb_paths.py`、`index_versioning.py` 管理知识库路径与索引版本。
- `services/subagent/`：把用户本机的 **Claude Code / Codex** 作为「委派子智能体」拉起并流式监听（`claude_code.py` / `codex.py` / `process.py` / `sessions.py`）。这是 `consult_subagent` 工具与 subagent 能力的后端。
- `services/session/` + `services/memory/`：会话状态、上下文构建（`context_builder.py` 负责历史压缩/token 计数）、记忆存取，持久化到 PocketBase（`services/pocketbase_client.py`）。
- `services/sandbox/`：exec / code_execution 的隔离沙箱（`IsolationLevel`：SYSTEM / APPLICATION）。
- `services/skill/` + `deeptutor/skills/builtin/`：技能系统（system prompt 里给清单，模型用 `read_skill` 按需拉全文）。
- `services/partners/`：把 IM 消息驱动成一个 chat 回合（见下）。

---

## 七、上层产品子系统

### 7.1 Partners（IM 伴学）

`deeptutor/partners/`（channels/bus/config/network）+ `deeptutor/services/partners/runtime.py`。

**核心事实：Partner 没有自己的引擎**。每条入站 IM 消息都被翻译成一个 `UnifiedContext`，走**完全相同**的 `ChatOrchestrator → AgenticChatPipeline`，只不过运行在 partner 的「合成用户作用域（synthetic user scope）」里，从而让 rag/skills/notebook 工具原生读写该 partner 的工作区。

- `partners/channels/`：各 IM 渠道适配器（Discord / Feishu / Slack / Telegram / Matrix / Mattermost / WhatsApp / QQ / 企业微信 / 钉钉 / MS Teams / Zulip 等），统一实现 `base.py` 的渠道协议，由 `manager.py` + `registry.py` 管理。
- `partners/bus/`：`MessageBus` 队列，`InboundMessage` / `OutboundMessage` 事件模型。
- `runtime.py` 里定义了 StreamEvent → IM 消息的映射（`RESULT` → 回复正文；`llm_final_response` 的 `CONTENT` → 终止/ask_user 文本；`narration` 轮 → 可选进度提示；`TOOL_CALL` → 可选工具提示）。
- Partner 回合以合成非管理员用户身份运行，但**权限沿用其管理员 owner**（授权通过 context metadata 的 `mcp_tools_filter` / exec 闸门传递，而非合成用户的授权文件）。

### 7.2 学习引擎（learning/）

`deeptutor/learning/`：Guided Learning / 掌握度追踪 / 间隔重复的引擎（`grading.py` / `mastery.py` / `policy.py` / `scheduler.py` / `service.py` / `models.py`）。对应 Level 2 的 `mastery_path` 能力，通过 mastery 系列工具在 chat 循环里读写学习状态。

### 7.3 其他

- `deeptutor/co_writer/`：协作写作 Agent（`edit_agent.py`）。
- `deeptutor/knowledge/` + `deeptutor/book/`：知识库与「book」概念（`book/engine.py` 也会调用编排器）。
- `deeptutor/multi_user/`：多用户模型（`identity` / `grants` / `context` / `*_access.py` 各类授权），`services/auth.py` 负责鉴权。
- `web/`：Next.js 16 前端，通过 WebSocket 与后端流式通信。

---

## 八、二次开发指南

### 8.1 新增一个「工具（Tool）」

1. 在 `deeptutor/tools/` 下新建工具类，继承 `deeptutor/core/tool_protocol.py::BaseTool`，实现 `get_definition()`（返回 `ToolDefinition`，含 name/description/参数 JSON schema）与 `async execute(**kwargs) -> ToolResult`。
2. 在 `deeptutor/tools/builtin/__init__.py` 的 `BUILTIN_TOOL_TYPES` 注册（需要别名/默认参数就加进 `TOOL_ALIASES`）。
3. 若工具需要服务端注入的私有参数（沙箱目录、owner 路由等），在 `AgenticChatPipeline._augment_tool_kwargs` 里按 `tool_name` 分支注入，**用 `_` 前缀命名**，这样会自动从事件 payload 里剥离。
4. 若希望默认对话就能用，把它加入自动挂载逻辑（看 `agents/_shared/tool_composition.py` 与 `ToolMountFlags`）；否则它就是「用户勾选/`--tool` 显式启用」型工具。
5. 需要长运行进度可见性时，为它接 `event_sink`（参考 `execute_tool_call` 里 `retrieve_meta` 的用法），并在 `_retrieve_trace_metadata` 加一条分支。

### 8.2 新增一个「能力（Capability）」

**选项 A：真正接管整个回合的多阶段能力**（如 deep_research 那样有自己的阶段流水线）：

1. 新建类继承 `deeptutor/core/capability_protocol.py::BaseCapability`，提供 `manifest`（`CapabilityManifest`），实现 `async run(context, stream)`。
2. 在 `run` 内用 `stream.stage("阶段名")` 包裹各阶段，往 `stream` emit 事件；收尾统一调用 `emit_capability_result()`（见 `deeptutor/capabilities/_shared.py` / `agents/_shared/capability_result.py`）以保证同一 envelope。
3. 若需要 Agent 循环，直接复用 `core/agentic/loop.py::run_agentic_loop` + 自定义 `LoopHost` + `LabelProtocol`（标签驱动），或实例化 `AgenticChatPipeline`（chat 循环）。
4. 在 `runtime/bootstrap/builtin_capabilities.py` 的 `BUILTIN_CAPABILITY_CLASSES` 注册 `name → "module:Class"`。
5. 前端能力选择、CLI 别名会自动从 manifest 读取；i18n 文案放 `capabilities/prompts/{en,zh}/<name>.yaml`。

**选项 B：在 chat 循环上做非侵入式增强**（如 solve / mastery，复用 chat 完整工具面）：

1. 实现一个满足 `capabilities/protocol.py::LoopCapability` 结构的类：`name` / `owned_tools` / `is_active` / `system_block` / `augment_kwargs` / `pre_loop_seed`（可选 `pre_loop`）。
2. 通过 `context.metadata` 上的开关声明激活（如 solve 用 `metadata["solve_mode"]`）。
3. 若要**独占**工具面（替换而非叠加），改为继承 `KnowledgeCapability`（`exclusive_tools = True`）。
4. 在 `active_loop_capabilities`（`deeptutor/capabilities/__init__.py`）的发现逻辑里让它可被找到。
5. 通常还需要一个 Level 2 的 `BaseCapability` 外壳来让用户能显式选择该模式，并在其 `run` 里设置好 metadata 后交给 `AgenticChatPipeline`。

### 8.3 改造 Agent 循环本身

- 想改「chat 的隐式结束/预算/兜底」行为 → `agents/chat/agent_loop.py::AgentLoop._run_loop`。
- 想改「标签协议/校验/强制收尾」行为 → `core/agentic/loop.py::run_agentic_loop` + 相关 `LoopHost` 实现。
- 想改「并行度/去重/暂停终止语义」 → `core/agentic/tool_dispatch.py`。
- 想改「system prompt 组装/工具清单/KB 种子」 → `agents/chat/agentic_pipeline.py` + `agents/chat/prompt_blocks.py`。

### 8.4 本地约定与注意事项

- **设置存储**：运行期设置在 `data/user/settings/*.json`；项目根的 `.env` 被有意忽略。
- **入口对齐**：任何新入口都应最终收敛到 `ChatOrchestrator.handle`，不要绕过编排器直接驱动循环。
- **不要混淆两条总线**：回合内流式用 `StreamBus`，跨回合解耦通知用 `EventBus`。
- **私有 kwargs 安全**：一切服务端注入、模型不该看到的参数用 `_` 前缀。
- **i18n**：面向用户的文案走 `services/prompt` + `prompts/{en,zh}/*.yaml`，代码里用 `self._t("key", default=...)` 取。
- 依赖分层与安装 extra 见 `pyproject.toml` 与 `AGENTS.md`（`.[cli]` / `.[server]` / `.[partners]` / `.[math-animator]` 等）。

---

## 九、快速索引（按「我想做 X」查文件）

| 我想…… | 去看 |
| ------ | ---- |
| 搞清楚「到底是不是一个 loop」 | 「零、编排不是一个 loop」（三种形态总览表） |
| 理解一条消息的总流程 | `runtime/orchestrator.py` → `services/session/turn_runtime.py` |
| 改默认对话的 Agent 行为（形态一） | `agents/chat/agent_loop.py`、`agents/chat/agentic_pipeline.py` |
| 做**固定顺序多智能体流水线**（形态二） | `agents/math_animator/pipeline.py`、`agents/*/agents/*.py`、`agents/base_agent.py` |
| 做**动态分解 + 并行子智能体**（形态三） | `agents/research/pipeline.py`（`DynamicTopicQueue` + `asyncio.gather`） |
| 加/改一个工具 | `deeptutor/tools/`、`tools/builtin/__init__.py`、`agentic_pipeline._augment_tool_kwargs` |
| 加一个深度能力 | `core/capability_protocol.py`、`runtime/bootstrap/builtin_capabilities.py`、`capabilities/` |
| 写一个可复用的专职 Agent | `agents/base_agent.py`（实现 `process()`），参考 `agents/math_animator/agents/` |
| 做「标签驱动」多阶段循环 | `core/agentic/loop.py`（参考 `capabilities/solve/`） |
| 在 chat 循环上叠增强 | `capabilities/protocol.py`（参考 `capabilities/solve/loop.py`、`capabilities/subagent/`） |
| 改工具并行/去重/暂停 | `core/agentic/tool_dispatch.py` |
| 改流式事件/前端追踪 | `core/stream.py`、`core/stream_bus.py`、`core/trace.py` |
| 接一个 IM 渠道 | `partners/channels/`、`services/partners/runtime.py` |
| 接一个外部子智能体 | `services/subagent/`、`capabilities/subagent/`、`tools/`（consult_subagent） |
| 改多用户/权限 | `multi_user/`、`services/auth.py` |
| 改 RAG / 知识库 | `services/rag/`、`deeptutor/knowledge/` |
| 改 WebSocket 端点 | `api/routers/unified_ws.py` |

---

> 本文基于对仓库源码的静态梳理编写，作为二次开发的导航图。
> 具体实现以代码为准；涉及关键路径改动前，建议先按「三、核心编排数据流」把目标链路完整走读一遍。
