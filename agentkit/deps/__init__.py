"""Typed dependency injection for Agent leaves (ADR-0003)."""

from __future__ import annotations

from agentkit.deps.agent_deps import AgentDeps, AgentParams, get_deps, resolve_prompt
from agentkit.deps.protocols import (
    AgentConfig,
    EmbeddingProvider,
    LLMClient,
    PromptProvider,
    Renderer,
)

__all__ = [
    "AgentConfig",
    "AgentDeps",
    "AgentParams",
    "EmbeddingProvider",
    "LLMClient",
    "PromptProvider",
    "Renderer",
    "get_deps",
    "resolve_prompt",
]
