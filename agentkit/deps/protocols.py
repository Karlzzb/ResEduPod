"""Typed dependency protocols for Agent leaves (ADR-0003).

An Agent obtains everything it needs from an injected :class:`AgentDeps` bundle
carried on LangGraph's native ``configurable`` channel.  These interfaces are
``runtime_checkable`` Protocols so any structurally-compatible object (including
the test ``FakeDeps``) satisfies them without inheritance.  Agents depend only on
these interfaces — never on a global singleton, never on ``deeptutor.*``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, AsyncIterator, Protocol, runtime_checkable

if TYPE_CHECKING:  # avoid a hard import cycle; only needed for typing
    from agentkit.deps.agent_deps import AgentParams
    from agentkit.models.math_animator import RenderResult


@runtime_checkable
class LLMClient(Protocol):
    """A minimal chat-completion client.

    The DeepTutor-side implementation wraps ``services/llm``; an independent
    integrator can supply a thin OpenAI wrapper.  Only these two methods are
    required.
    """

    async def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        temperature: float,
        max_tokens: int,
        response_format: dict[str, Any] | None = None,
        model: str | None = None,
        agent: str | None = None,
    ) -> str:
        """Return the full assistant text for ``messages``.

        ``agent`` is optional metadata identifying the calling Agent leaf (useful
        for logging / cost attribution); implementations may ignore it.
        """
        ...

    def stream(
        self,
        *,
        messages: list[dict[str, Any]],
        temperature: float,
        max_tokens: int,
        response_format: dict[str, Any] | None = None,
        model: str | None = None,
        agent: str | None = None,
    ) -> AsyncIterator[str]:
        """Yield assistant text chunks.  This is an *async generator*, not a coroutine."""
        ...


@runtime_checkable
class PromptProvider(Protocol):
    """Optional prompt override; en/zh i18n (ADR-0003).

    Returns an override string for ``(agent, key, language)`` or ``None`` — when
    ``None``, the Agent falls back to its own inlined default prompt so it works
    out of the box with no external YAML.
    """

    def get(self, *, agent: str, key: str, language: str) -> str | None: ...


@runtime_checkable
class AgentConfig(Protocol):
    """Per-agent generation parameters (temperature / max_tokens / model)."""

    def params(self, *, agent: str) -> "AgentParams": ...


@runtime_checkable
class Renderer(Protocol):
    """Optional renderer for the manim path.

    Injected so the manim subprocess is swappable for a scripted fake in tests
    (the whole retry cycle can be exercised without launching manim).
    """

    async def render(
        self, *, code: str, output_mode: str, quality: str, turn_id: str
    ) -> "RenderResult": ...

    def supports_vision(self) -> bool: ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Optional embedding backend for semantic long-term memory (ADR-0011)."""

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


__all__ = [
    "AgentConfig",
    "EmbeddingProvider",
    "LLMClient",
    "PromptProvider",
    "Renderer",
]
