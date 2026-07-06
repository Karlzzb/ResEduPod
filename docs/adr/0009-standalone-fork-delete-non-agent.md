# 独立硬分叉:新分支即智能体代码库,永久删除非智能体代码,不依赖 deeptutor

本次抽取不采用「独立包 + DeepTutor 反向依赖」的方案,而是**硬分叉**:在一个新 git 分支上,把这套智能体([Agent](../../CONTEXT.md) / [Orchestration](../../CONTEXT.md) / [Tool](../../CONTEXT.md) + 其运行所需的 substrate)保留下来,**永久删除所有非智能体关联的代码与文档**,新代码库**不 import 任何 `deeptutor.*`、不反向依赖原项目**。

## 为什么

- 「工业级 + 可复制基座」要求边界是硬的:只有当新库根本不依赖 deeptutor 时,「独立可调用」才是结构保证而非纪律要求。
- 用户明确不希望保留对原 deeptutor 的依赖,倾向一个干净的、自足的新起点。
- 新分支上删除 = 仍可经 git 历史/`main` 恢复,故此步安全、可逆;真正不可逆的删除(改写历史)是后续单独决定,不在本步。

## 对既有 ADR 的改写

[ADR-0002](./0002-streaming-boundary-native-inside-bridge-outside.md) 与 [ADR-0003](./0003-agent-dependency-injection-and-self-contained-prompts.md) 中「DeepTutor 侧提供 bridge / `AgentDeps` 实现」的措辞,改为:**这些默认实现(bridge、`AgentDeps` 默认实现、StreamBus)住在新库自己的 runtime/infra 层**,而非一个外部 DeepTutor。Agent 核心层与该 runtime 层仍是同一决策的两侧,只是都在新库内。

## 待定(后续 ADR 解决)

「非智能体」的边界不是一条干净的线——Agent 运行需要一整套 substrate(LLM providers、prompt、config、sandbox、render、tools),而用户已明确 **RAG 设计要保留**。因此 keep-set 的精确边界(尤其是共享 substrate 与产品/交付层的切分)由后续 ADR 逐项钉死。
