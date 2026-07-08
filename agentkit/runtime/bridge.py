"""The single ``astream → StreamBus`` bridge (ADR-0002 / ADR-0012).

Agents emit LangGraph-native custom events via ``get_stream_writer()``; this is
the one and only place those events are translated onto a :class:`StreamBus`.
Post-fork the translation is a minimal map (ADR-0012): a handful of event kinds,
no trace-metadata reconstruction.

Consumers that prefer raw LangGraph can skip this and use
``graph.astream_events(...)`` directly.
"""

from __future__ import annotations

from typing import Any

from agentkit.runtime.stream import StreamEvent, StreamEventType
from agentkit.runtime.stream_bus import StreamBus

# writer "event" kind -> StreamEventType
_EVENT_MAP = {
    "stage_start": StreamEventType.STAGE_START,
    "stage_end": StreamEventType.STAGE_END,
    "llm_chunk": StreamEventType.THINKING,
    "thinking": StreamEventType.THINKING,  # split-off <think> scratchpad (issue #3)
    "content": StreamEventType.CONTENT,
    "progress": StreamEventType.PROGRESS,
    "result": StreamEventType.RESULT,
    "error": StreamEventType.ERROR,
}


def _writer_event_to_stream_event(payload: dict[str, Any], *, source: str) -> StreamEvent:
    kind = str(payload.get("event", "progress"))
    type_ = _EVENT_MAP.get(kind, StreamEventType.PROGRESS)
    stage = str(payload.get("stage", ""))
    content = str(payload.get("content", "") or payload.get("chunk", ""))
    # Everything except the reserved keys becomes metadata; it must stay JSON-safe.
    metadata = {k: v for k, v in payload.items() if k not in {"event", "stage", "content", "chunk"}}
    return StreamEvent(type=type_, source=source, stage=stage, content=content, metadata=metadata)


async def run_to_stream_bus(
    graph: Any,
    input_state: dict[str, Any],
    *,
    config: dict[str, Any],
    bus: StreamBus,
    source: str = "orchestration",
) -> dict[str, Any]:
    """Drive ``graph`` and bridge its native stream onto ``bus``.

    Returns the fully-reduced final State.  Closes ``bus`` when the run finishes
    (including on error, so consumers always terminate).

    The final State is taken from the ``values`` stream — LangGraph's post-superstep
    snapshot of the *reduced* channels — rather than folded from ``updates`` deltas.
    That distinction matters for reducer channels accumulated across supersteps
    (e.g. a ``Send`` fan-out where each worker returns a partial ``blocks`` list, or
    ``math_animator``'s ``retry_history``): ``update``-ing raw deltas would overwrite
    the reduced value with whichever node reported last, whereas ``values`` already
    reflects every reducer.  ``updates`` is still consumed to emit a per-node
    progress event.
    """
    final_state: dict[str, Any] = {}
    try:
        async for mode, chunk in graph.astream(
            input_state, config=config, stream_mode=["custom", "updates", "values"]
        ):
            if mode == "custom":
                await bus.emit(_writer_event_to_stream_event(chunk, source=source))
            elif mode == "values":
                # The full reduced State after this superstep; the last one wins.
                if isinstance(chunk, dict):
                    final_state = chunk
            elif mode == "updates":
                # chunk == {node_name: partial_state_delta}; used only for progress.
                for node_name, _delta in chunk.items():
                    await bus.progress(
                        "", source=source, stage=str(node_name), metadata={"node": node_name}
                    )
    finally:
        await bus.close()
    return final_state


__all__ = ["run_to_stream_bus"]
