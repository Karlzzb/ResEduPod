"""Shared helpers for Agent leaf nodes (the unified Agent contract, ADR-0002).

Every Agent leaf is a node function ``(state, config) -> partial state`` that:

* reads its services from the injected :class:`AgentDeps` (never a global singleton);
* carries its OWN default prompt inline (``DEFAULT_PROMPTS``), overridable via the
  injected :class:`PromptProvider`;
* streams progress with LangGraph-native custom events via ``get_stream_writer()``
  — it NEVER touches a ``StreamBus`` (that bridge lives once, in the runtime).

All emitted writer payloads are plain JSON dicts so the downstream bridge stays
strictly JSON-serializable.
"""

from __future__ import annotations

from typing import Any

from langgraph.config import get_stream_writer

from agentkit.deps import AgentDeps


def emit(event: str, *, stage: str, agent: str, **fields: Any) -> None:
    """Write a LangGraph-native custom event (no-op when nobody is subscribed)."""
    writer = get_stream_writer()
    writer({"event": event, "stage": stage, "agent": agent, **fields})


async def llm_json(
    deps: AgentDeps,
    *,
    agent: str,
    messages: list[dict[str, Any]],
    stage: str,
) -> dict[str, Any]:
    """Stream a JSON-object completion, emitting ``llm_chunk`` events, and parse it."""
    from agentkit.utils import extract_json_object

    params = deps.config.params(agent=agent)
    chunks: list[str] = []
    async for chunk in deps.llm.stream(
        messages=messages,
        response_format={"type": "json_object"},
        temperature=params.temperature,
        max_tokens=params.max_tokens,
        model=params.model,
        agent=agent,
    ):
        chunks.append(chunk)
        emit("llm_chunk", stage=stage, agent=agent, chunk=chunk)
    return extract_json_object("".join(chunks))


async def llm_text(
    deps: AgentDeps,
    *,
    agent: str,
    messages: list[dict[str, Any]],
    stage: str,
) -> str:
    """Stream a free-text completion, emitting ``llm_chunk`` events, and return it."""
    params = deps.config.params(agent=agent)
    chunks: list[str] = []
    async for chunk in deps.llm.stream(
        messages=messages,
        response_format=None,
        temperature=params.temperature,
        max_tokens=params.max_tokens,
        model=params.model,
        agent=agent,
    ):
        chunks.append(chunk)
        emit("llm_chunk", stage=stage, agent=agent, chunk=chunk)
    return "".join(chunks)


__all__ = ["emit", "llm_json", "llm_text"]
