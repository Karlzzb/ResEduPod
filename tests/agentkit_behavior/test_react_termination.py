"""ReAct termination gate: loop count in State gated in the conditional edge (ADR-0005).

Scripts a tool action on *every* turn so the model never finishes on its own; the
graph must halt at ``max_iterations`` via the ``finalize`` node rather than looping
unbounded.
"""

from __future__ import annotations

import pytest

from agentkit import build_react_orchestration_graph, make_checkpointer
from agentkit.runtime.stream import StreamEventType
from agentkit.testing import make_fake_deps, make_fake_tool, react_tool_decision, tool_call


@pytest.mark.asyncio
async def test_react_loop_halts_at_max_iterations(collect_events) -> None:
    max_iterations = 3
    # Always ask for a tool — the model never emits "final".
    always_tool = [react_tool_decision([tool_call("search")]) for _ in range(max_iterations)]
    deps = make_fake_deps(llm_scripts={"react": always_tool})
    graph = build_react_orchestration_graph(
        tools=[make_fake_tool("search")],
        agent_name="react",
        system_prompt="Answer.",
        max_iterations=max_iterations,
        checkpointer=make_checkpointer(),
    )
    events, final = await collect_events(
        graph, {"input": "loop forever"}, deps=deps, source="react", recursion_limit=50
    )

    # The gate fired: stopped exactly at the ceiling, forced-finalized.
    assert final["status"] == "finalized"
    assert final["iteration"] == max_iterations
    assert deps.llm.calls == ["react"] * max_iterations

    # A forced finalize content event was emitted.
    forced = [e for e in events if e.type == StreamEventType.CONTENT and e.metadata.get("forced")]
    assert forced, "the finalize node must emit a forced 收尾 content event"
    assert forced[-1].stage == "finalize"


@pytest.mark.asyncio
async def test_react_per_run_max_iterations_override(collect_events) -> None:
    # State-level ``max_iterations`` overrides the build-time default.
    deps = make_fake_deps(
        llm_scripts={"react": [react_tool_decision([tool_call("t")]) for _ in range(2)]}
    )
    graph = build_react_orchestration_graph(
        tools=[make_fake_tool("t")], agent_name="react", system_prompt="x", max_iterations=8
    )
    _events, final = await collect_events(
        graph, {"input": "go", "max_iterations": 2}, deps=deps, source="react"
    )
    assert final["status"] == "finalized"
    assert final["iteration"] == 2
