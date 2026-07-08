"""Shared helpers for Agent leaf nodes (the unified Agent contract, ADR-0002).

Every Agent leaf is a node function ``(state, config) -> partial state`` that:

* reads its services from the injected :class:`AgentDeps` (never a global singleton);
* carries its OWN default prompt inline (``DEFAULT_PROMPTS``), overridable via the
  injected :class:`PromptProvider`;
* streams progress with LangGraph-native custom events via ``get_stream_writer()``
  — it NEVER touches a ``StreamBus`` (that bridge lives once, in the runtime).

All emitted writer payloads are plain JSON dicts so the downstream bridge stays
strictly JSON-serializable.

The streaming helpers add two ``chat``-robustness behaviours (issue #3) at this one
seam so every loop archetype inherits them:

* **Multi-level provider degradation** — :func:`llm_json` / :func:`llm_text` try
  ``deps.llm`` then each of ``deps.llm_fallbacks`` in order, but only fall over when
  a provider fails *before yielding any output*; a mid-stream failure propagates
  (the caller salvages) so already-streamed text is never duplicated.
* **Thinking-tag splitting** — inline ``<think>`` / ``<thinking>`` segments are
  streamed on a distinct ``thinking`` event instead of ``llm_chunk`` so a
  reasoning scratchpad never rides the same channel as real output.  The raw text
  (tags included) is still returned unchanged, so JSON / code extraction and every
  existing caller behave exactly as before.
"""

from __future__ import annotations

from typing import Any, AsyncIterator

from langgraph.config import get_stream_writer

from agentkit.deps import AgentDeps
from agentkit.deps.protocols import LLMClient
from agentkit.utils.think_filter import InlineThinkFilter


def emit(event: str, *, stage: str, agent: str, **fields: Any) -> None:
    """Write a LangGraph-native custom event (no-op when nobody is subscribed)."""
    writer = get_stream_writer()
    writer({"event": event, "stage": stage, "agent": agent, **fields})


def _providers(deps: AgentDeps) -> list[LLMClient]:
    """The primary client followed by its ordered fallbacks (issue #3)."""
    return [deps.llm, *deps.llm_fallbacks]


async def _stream_raw(
    deps: AgentDeps,
    *,
    agent: str,
    messages: list[dict[str, Any]],
    stage: str,
    response_format: dict[str, Any] | None,
) -> str:
    """Stream a completion with provider fallback + think-splitting.

    Emits ``thinking`` events for ``<think>`` segments and ``llm_chunk`` events for
    real content, then returns the full raw text (tags included) unchanged so the
    caller's parsing is byte-identical to the single-provider path.
    """
    params = deps.config.params(agent=agent)
    providers = _providers(deps)
    for index, client in enumerate(providers):
        chunks: list[str] = []
        splitter = InlineThinkFilter()
        produced = False
        try:
            stream: AsyncIterator[str] = client.stream(
                messages=messages,
                response_format=response_format,
                temperature=params.temperature,
                max_tokens=params.max_tokens,
                model=params.model,
                agent=agent,
            )
            async for chunk in stream:
                produced = True
                chunks.append(chunk)
                _emit_segments(splitter.feed(chunk), stage=stage, agent=agent)
            _emit_segments(splitter.flush(), stage=stage, agent=agent)
            return "".join(chunks)
        except Exception:
            # Fall over only when nothing was streamed yet and a fallback remains;
            # a mid-stream failure must propagate so the caller can salvage without
            # replaying already-emitted output.
            if produced or index + 1 >= len(providers):
                raise
            emit(
                "progress",
                stage=stage,
                agent=agent,
                trace_kind="warning",
                provider_fallback=True,
                failed_provider_index=index,
                next_provider_index=index + 1,
            )
    # Unreachable: the loop either returns or re-raises on the last provider.
    raise RuntimeError("no LLM provider available")


def _emit_segments(segments: list[tuple[str, str]], *, stage: str, agent: str) -> None:
    for kind, segment in segments:
        if not segment:
            continue
        if kind == "thinking":
            # Reasoning scratchpad on its own event, tagged so a consumer can tell
            # it apart from a live content-preview chunk (both ride the THINKING
            # stream) and never render it as the answer.
            emit("thinking", stage=stage, agent=agent, chunk=segment, reasoning=True)
        else:
            emit("llm_chunk", stage=stage, agent=agent, chunk=segment)


async def llm_json(
    deps: AgentDeps,
    *,
    agent: str,
    messages: list[dict[str, Any]],
    stage: str,
) -> dict[str, Any]:
    """Stream a JSON-object completion (with fallback + think-split) and parse it."""
    from agentkit.utils import extract_json_object

    raw = await _stream_raw(
        deps,
        agent=agent,
        messages=messages,
        stage=stage,
        response_format={"type": "json_object"},
    )
    return extract_json_object(raw)


async def llm_text(
    deps: AgentDeps,
    *,
    agent: str,
    messages: list[dict[str, Any]],
    stage: str,
) -> str:
    """Stream a free-text completion (with fallback + think-split) and return it."""
    return await _stream_raw(
        deps,
        agent=agent,
        messages=messages,
        stage=stage,
        response_format=None,
    )


__all__ = ["emit", "llm_json", "llm_text"]
