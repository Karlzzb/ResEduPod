"""Shared helpers for the agentkit behavior-test suite.

The main seam (PRD Testing Decisions) is the compiled Orchestration graph driven
by ``graph.astream`` with a ``FakeDeps`` bundle; the ``collect_events`` fixture
lifts the precedent
``tests/core/agentic/test_tool_dispatch_events.py::_collect_events`` pattern from
``capability.run`` up to the graph, returning the ordered event list plus the
final State.

``collect_events`` is exposed as a fixture (rather than an importable function) so
tests need no cross-module import — this directory is intentionally NOT named
``agentkit`` to avoid shadowing the real package under pytest's importlib mode.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from agentkit.deps import AgentDeps
from agentkit.runtime import StreamBus, run_to_stream_bus


async def _collect_events(
    graph: Any,
    input_state: dict[str, Any],
    *,
    deps: AgentDeps,
    thread_id: str = "t",
    source: str = "orchestration",
    recursion_limit: int = 50,
) -> tuple[list, dict[str, Any]]:
    """Drive ``graph`` under ``deps`` and return ``(events, final_state)``."""
    bus = StreamBus()
    events: list = []

    async def consume() -> None:
        async for event in bus.subscribe():
            events.append(event)

    consumer = asyncio.create_task(consume())
    await asyncio.sleep(0)  # let the subscriber attach before the first emit
    config = {
        "configurable": {"deps": deps, "thread_id": thread_id},
        "recursion_limit": recursion_limit,
    }
    final = await run_to_stream_bus(graph, input_state, config=config, bus=bus, source=source)
    await consumer
    return events, final


@pytest.fixture
def collect_events():
    """Return the :func:`_collect_events` driver for the main-seam behavior tests."""
    return _collect_events
