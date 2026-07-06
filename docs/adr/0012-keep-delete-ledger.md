# 硬分叉的 keep/delete 总账

在 [ADR-0009](./0009-standalone-fork-delete-non-agent.md) 的硬分叉下,新分支的删/留边界按「有状态智能体服务([ADR-0010](./0010-positioning-stateful-agent-service-two-tier-memory.md))+ 不依赖 deeptutor 产品层」裁定如下。此表即执行阶段(建分支后)的删除清单依据。

## 留(Agent substrate)

- `core/agentic/`、`core/context.py`、`core/stream*.py`、`core/trace.py`、`core/*_protocol.py`
- `services/llm/`、`services/rag/`(用户点名保留)、`services/prompt/`、`services/config/`、`services/sandbox/`
- `services/session` + `services/memory`(重写为 `BaseStore` 后端,见 [ADR-0011](./0011-memory-backend-basestore-not-pocketbase.md))
- `tools/`(核心工具);`cron`/`github`/`notebook` 等偏产品工具**降级为可选包**,不进默认集
- `services/skill/` + `skills/builtin/`、`capabilities/subagent` + `services/subagent`
- `events/event_bus.py`(瘦身保留)、`runtime/registry/`
- `runtime/orchestrator.py`:**重写**为新库瘦运行时(承载 StreamBus bridge),不照搬

## 删(产品/交付层)

- `api/routers/`(WebSocket)→ 换一个最小调用入口或纯库无 API
- `multi_user/` + `services/auth.py`、`partners/`(11 个 IM 渠道)
- `web/`、`deeptutor_web/`、`deeptutor_cli/`
- `book/`、`co_writer/`、`knowledge/`(与 `services/rag` 重叠)
- `learning/` + `mastery_path` 能力(见下)
- 产品文档(README、CONTAINERIZATION、AGENTS.md、partners 文档等)→ 换新库文档(含本 ADR/CONTEXT)

## 两项显式裁决

1. **删前端 → trace-bridge 大幅简化。** CallTracePanel 移除后,无人消费 `call_id`/`trace_role`/`trace_kind` 等 trace 元数据。因此 [ADR-0002](./0002-streaming-boundary-native-inside-bridge-outside.md) 中「精确复刻 trace 元数据」的成本基本蒸发:bridge 退化为一个极简的 `astream_events → StreamBus` 映射(或直接暴露 LangGraph 原生事件流)。这是本次流式迁移的净简化。

2. **删 `mastery_path` + `learning/`。** 它不属于「三套多智能体」,是形态一之上的教学法产品特性(掌握度追踪 + 间隔重复),拖带整个 `learning/` 教育领域引擎。删除不影响三套核心;未来作为 `ReActOrchestration` 模板([ADR-0008](./0008-react-orchestration-template-and-three-archetypes.md))的**首个模板派生范例**重建,以验证模板体系。
