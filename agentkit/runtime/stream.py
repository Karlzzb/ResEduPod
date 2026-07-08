"""Thin port of the DeepTutor stream protocol (``core/stream.py``).

Kept intentionally minimal per ADR-0012: with the frontend deleted, no consumer
needs the ``call_id`` / ``trace_role`` / ``trace_kind`` trace-metadata machinery,
so the event carries only what a plain consumer needs.  Every event must be
strictly JSON-serializable (``json.dumps(event.to_dict())``) — a hard constraint
inherited from the pre-fork WebSocket push + turn-persistence contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class StreamEventType(str, Enum):
    STAGE_START = "stage_start"
    STAGE_END = "stage_end"
    THINKING = "thinking"
    CONTENT = "content"
    PROGRESS = "progress"
    RESULT = "result"
    ERROR = "error"


@dataclass
class StreamEvent:
    type: StreamEventType
    source: str
    stage: str = ""
    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    seq: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "source": self.source,
            "stage": self.stage,
            "content": self.content,
            "metadata": self.metadata,
            "seq": self.seq,
        }


__all__ = ["StreamEvent", "StreamEventType"]
