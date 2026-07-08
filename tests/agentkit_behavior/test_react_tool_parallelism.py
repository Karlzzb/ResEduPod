"""ReAct tool node: parallel dispatch capped at MAX_PARALLEL_TOOL_CALLS = 8 (ADR-0008)."""

from __future__ import annotations

import asyncio

import pytest

from agentkit import MAX_PARALLEL_TOOL_CALLS, build_react_orchestration_graph
from agentkit.runtime.stream import StreamEventType
from agentkit.testing import make_fake_deps, react_final, react_tool_decision, tool_call
from agentkit.tools import Tool


@pytest.mark.asyncio
async def test_tool_calls_capped_at_eight(collect_events) -> None:
    ran: list[str] = []

    async def _handler(arguments: dict) -> str:
        ran.append(arguments.get("i", "?"))
        return "ok"

    tool = Tool(name="t", description="fake", handler=_handler)
    # Request 12 calls in one turn — 4 over the cap.
    twelve = [tool_call("t", call_id=f"c{i}", arguments={"i": i}) for i in range(12)]
    deps = make_fake_deps(
        llm_scripts={"react": [react_tool_decision(twelve), react_final("done")]}
    )
    graph = build_react_orchestration_graph(tools=[tool], agent_name="react", system_prompt="x")
    events, final = await collect_events(graph, {"input": "go"}, deps=deps, source="react")

    # Exactly the first 8 ran; the extra 4 were dropped.
    assert len(ran) == MAX_PARALLEL_TOOL_CALLS
    assert ran == list(range(MAX_PARALLEL_TOOL_CALLS))

    # A warning event named the cap.
    warnings = [
        e for e in events
        if e.type == StreamEventType.PROGRESS and e.metadata.get("trace_kind") == "warning"
    ]
    assert warnings and warnings[0].metadata.get("limit") == MAX_PARALLEL_TOOL_CALLS


@pytest.mark.asyncio
async def test_tool_batch_runs_concurrently(collect_events) -> None:
    """The batch is dispatched concurrently (single gather), not sequentially."""
    barrier = asyncio.Barrier(3)  # 3 concurrent calls must all arrive to proceed

    async def _handler(arguments: dict) -> str:
        await barrier.wait()  # deadlocks if the calls run one-at-a-time
        return "ok"

    tool = Tool(name="t", description="fake", handler=_handler)
    three = [tool_call("t", call_id=f"c{i}") for i in range(3)]
    deps = make_fake_deps(
        llm_scripts={"react": [react_tool_decision(three), react_final("done")]}
    )
    graph = build_react_orchestration_graph(tools=[tool], agent_name="react", system_prompt="x")

    # If dispatch were sequential the barrier would never release → TimeoutError.
    _events, final = await asyncio.wait_for(
        collect_events(graph, {"input": "go"}, deps=deps, source="react"), timeout=5.0
    )
    assert final["status"] == "succeeded"
