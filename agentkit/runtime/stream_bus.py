"""``StreamBus`` — a minimal async fan-out bus (thin port of ``core/stream_bus.py``).

This is the single StreamBus bridge point mandated by ADR-0002: Agents and
Orchestrations never touch it; only the outer runtime adapter
(:func:`agentkit.runtime.bridge.run_to_stream_bus`) writes to it.  Consumers read
via :meth:`subscribe`.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from agentkit.runtime.stream import StreamEvent, StreamEventType


class StreamBus:
    """A single-producer / multi-consumer async event bus with fan-out."""

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[StreamEvent | None]] = []
        self._seq = 0
        self._closed = False

    async def emit(self, event: StreamEvent) -> None:
        event.seq = self._seq
        self._seq += 1
        for queue in list(self._subscribers):
            queue.put_nowait(event)

    async def subscribe(self) -> AsyncIterator[StreamEvent]:
        queue: asyncio.Queue[StreamEvent | None] = asyncio.Queue()
        self._subscribers.append(queue)
        try:
            while True:
                event = await queue.get()
                if event is None:  # sentinel from close()
                    return
                yield event
        finally:
            if queue in self._subscribers:
                self._subscribers.remove(queue)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for queue in list(self._subscribers):
            queue.put_nowait(None)

    # --- convenience producers (used by the bridge only) ---

    async def _emit(
        self,
        type_: StreamEventType,
        *,
        source: str,
        stage: str = "",
        content: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        await self.emit(
            StreamEvent(type=type_, source=source, stage=stage, content=content, metadata=metadata or {})
        )

    async def progress(self, message: str, *, source: str, stage: str = "", metadata: dict[str, Any] | None = None) -> None:
        await self._emit(StreamEventType.PROGRESS, source=source, stage=stage, content=message, metadata=metadata)

    async def error(self, message: str, *, source: str, stage: str = "", metadata: dict[str, Any] | None = None) -> None:
        await self._emit(StreamEventType.ERROR, source=source, stage=stage, content=message, metadata=metadata)

    async def result(self, data: dict[str, Any], *, source: str, metadata: dict[str, Any] | None = None) -> None:
        await self._emit(StreamEventType.RESULT, source=source, content="", metadata={"data": data, **(metadata or {})})

    @asynccontextmanager
    async def stage(self, name: str, *, source: str) -> AsyncIterator[None]:
        await self._emit(StreamEventType.STAGE_START, source=source, stage=name)
        try:
            yield
        finally:
            await self._emit(StreamEventType.STAGE_END, source=source, stage=name)


__all__ = ["StreamBus"]
