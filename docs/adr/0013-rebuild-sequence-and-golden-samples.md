# 重建顺序与黄金样例前置验证

重建顺序按「难度递增、地基先行、风险后置」:

1. **`math_animator`** —— 最干净(线性 + 一个可见 retry 环),用最低编排复杂度一次性打完全部地基:[Agent](../../CONTEXT.md) 叶子契约、[AgentDeps](../../CONTEXT.md) 注入([ADR-0003](./0003-agent-dependency-injection-and-self-contained-prompts.md))、[BaseState](../../CONTEXT.md)([ADR-0004](./0004-state-schema-thin-base-plus-per-orchestration.md))、原生流式→bridge([ADR-0002](./0002-streaming-boundary-native-inside-bridge-outside.md))、checkpointer 接线、可见循环环([ADR-0005](./0005-loops-as-visible-graph-cycles.md))。render 步顺带验 checkpointer(最易崩的一步)。
2. **`chat` / `ReActOrchestration` 模板**([ADR-0008](./0008-react-orchestration-template-and-three-archetypes.md)) —— 默认流量 + 最多健壮性设计(多级 provider 降级、`_guard_context_window`、`_forced_finish`、`InlineThinkFilter`),在地基验证后再扛。
3. **`deep_research`** —— 最硬(动态队列 reducer [ADR-0006](./0006-dynamic-queue-as-recursive-supervisor.md) + 双 HITL interrupt [ADR-0007](./0007-unify-hitl-on-interrupt.md)),放最后,待地基与 ReAct 模板成熟再啃。

否决从 `chat` 起(第一套即扛最重健壮性包袱)或从 `deep_research` 起(最高风险全压在未磨合的地基上)。

## 黄金样例前置(硬约束)

硬分叉([ADR-0009](./0009-standalone-fork-delete-non-agent.md))删除旧代码后,将**永久失去新旧 A/B 对跑的能力**。因此在**建分支、删旧码之前**,必须先专门做一轮「录黄金样例」:

- 对三套 Orchestration 各录一组固定输入 → 抓当前旧实现的输出与关键中间产物(`math_animator` 的 `analysis`/`design`/`code`;`deep_research` 的 outline/citations 等)存档。
- 重写后用新实现跑同样输入,对齐黄金样例——这是硬分叉下**唯一**能客观证明「行为无回归」的参照系。

顺序强约束:**录黄金样例 → 建分支 → 删旧码 → 按 1/2/3 重建并逐套对齐黄金样例。**
