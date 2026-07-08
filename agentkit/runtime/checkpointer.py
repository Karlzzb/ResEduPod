"""Checkpointer wiring (ADR-0001 durable execution; ADR-0005 checkpoint boundaries).

The default is a zero-dependency in-memory saver.  Every node boundary — most
importantly the ``render`` node, the slowest and most crash-prone step — is a
checkpoint, so a crash resumes from the last completed node rather than the top
of the pipeline (ADR-0005, PRD user-story 19).
"""

from __future__ import annotations

from typing import Any


def make_checkpointer(kind: str = "memory") -> Any:
    """Return a LangGraph checkpointer.  Only ``"memory"`` is in scope for issue #1."""
    if kind == "memory":
        from langgraph.checkpoint.memory import InMemorySaver

        return InMemorySaver()
    raise ValueError(f"unsupported checkpointer kind: {kind!r} (only 'memory' is available)")


__all__ = ["make_checkpointer"]
