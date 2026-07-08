"""The :class:`AgentDeps` bundle and node-side accessor (ADR-0003).

``AgentDeps`` is a frozen, explicitly-typed collection of the services an Agent
needs.  It rides LangGraph's ``configurable`` channel:

    config = {"configurable": {"deps": AgentDeps(...), "thread_id": "t1"}}
    graph.ainvoke(state, config=config)

and is read inside a node with :func:`get_deps`::

    deps = get_deps(config)
    text = await deps.llm.complete(...)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agentkit.deps.protocols import (
    AgentConfig,
    EmbeddingProvider,
    LLMClient,
    PromptProvider,
    Renderer,
)


@dataclass(frozen=True)
class AgentParams:
    """Generation parameters for a single Agent."""

    temperature: float = 0.7
    max_tokens: int = 4096
    model: str | None = None


@dataclass(frozen=True)
class AgentDeps:
    """The explicit, typed dependency bundle injected into every Agent."""

    llm: LLMClient
    prompts: PromptProvider
    config: AgentConfig
    renderer: Renderer | None = None
    store: Any | None = None  # langgraph BaseStore | None (long-term memory; ADR-0011)
    embed: EmbeddingProvider | None = None


def get_deps(config: dict[str, Any] | None) -> AgentDeps:
    """Read the :class:`AgentDeps` bundle from a LangGraph node ``config``."""
    if not config:
        raise KeyError("node config is missing; expected configurable['deps']")
    try:
        deps = config["configurable"]["deps"]
    except (KeyError, TypeError) as exc:
        raise KeyError("configurable['deps'] is required (inject an AgentDeps)") from exc
    if not isinstance(deps, AgentDeps):
        raise TypeError(f"configurable['deps'] must be an AgentDeps, got {type(deps)!r}")
    return deps


def resolve_prompt(
    deps: AgentDeps,
    *,
    agent: str,
    key: str,
    language: str,
    default: str,
) -> str:
    """Return an override from the prompt provider, else the Agent's inline default."""
    override = deps.prompts.get(agent=agent, key=key, language=language)
    return override if override is not None else default


__all__ = ["AgentDeps", "AgentParams", "get_deps", "resolve_prompt"]
