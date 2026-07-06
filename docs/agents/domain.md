# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

This repo is **single-context**: one `CONTEXT.md` + `docs/adr/` at the repo root.

## Before exploring, read these

- **`CONTEXT.md`** at the repo root — the project's glossary (Agent / Orchestration / Capability / Tool / Subagent / AgentDeps / State / BaseState).
- **`docs/adr/`** — read ADRs that touch the area you're about to work in (currently `0001`–`0013`, covering the LangGraph agent-extraction architecture).

If any of these files don't exist, **proceed silently**. Don't flag their absence; don't suggest creating them upfront. The `/domain-modeling` skill (reached via `/grill-with-docs` and `/improve-codebase-architecture`) creates them lazily when terms or decisions actually get resolved.

## File structure

Single-context repo (this repo):

```
/
├── CONTEXT.md
├── docs/adr/
│   ├── 0001-langgraph-as-agent-substrate.md
│   └── ... (through 0013)
└── deeptutor/
```

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in `CONTEXT.md`. Don't drift to synonyms the glossary explicitly avoids (e.g. use **Agent**, not "worker" or "专职 Agent"; use **Orchestration**, not "pipeline" or "workflow").

If the concept you need isn't in the glossary yet, that's a signal — either you're inventing language the project doesn't use (reconsider) or there's a real gap (note it for `/domain-modeling`).

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> _Contradicts ADR-0009 (standalone fork, delete non-agent code) — but worth reopening because…_
