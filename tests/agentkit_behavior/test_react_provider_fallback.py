"""Chat robustness (issue #3): multi-level provider degradation on the ReAct template.

Two behaviours, both driven by ``FakeDeps`` at the main seam:

* a primary provider that fails *before any output* falls over to the next
  provider in order and the run still succeeds (AC: 主 provider 失败按序回退);
* when every provider is exhausted mid-loop (after ≥1 useful round), the loop
  forces a 收尾 rather than crashing (AC: 断言最终成功或按策略收尾).
"""

from __future__ import annotations

import pytest

from agentkit import build_react_orchestration_graph, make_checkpointer
from agentkit.runtime.stream import StreamEventType
from agentkit.testing import (
    make_fake_deps,
    make_fake_tool,
    react_final,
    react_tool_decision,
    tool_call,
)


@pytest.mark.asyncio
async def test_primary_provider_fails_falls_over_to_secondary(collect_events) -> None:
    # Primary raises before emitting anything; the ordered fallback answers.
    deps = make_fake_deps(
        llm_scripts={"react": [RuntimeError("primary provider 503")]},
        fallback_scripts=[{"react": [react_final("Answer from the backup provider.")]}],
    )
    graph = build_react_orchestration_graph(
        agent_name="react", system_prompt="Answer.", checkpointer=make_checkpointer()
    )
    events, final = await collect_events(graph, {"input": "hi"}, deps=deps, source="react")

    # The run succeeded on the fallback's answer.
    assert final["status"] == "succeeded"
    assert final["final_text"] == "Answer from the backup provider."

    # Both providers were called once, in order (primary then secondary).
    assert deps.llm.calls == ["react"]
    assert deps.llm_fallbacks[0].calls == ["react"]

    # A fallback warning named the failed provider index.
    warnings = [
        e for e in events
        if e.type == StreamEventType.PROGRESS and e.metadata.get("provider_fallback")
    ]
    assert warnings and warnings[0].metadata.get("failed_provider_index") == 0


@pytest.mark.asyncio
async def test_all_providers_exhausted_midloop_forces_finish(collect_events) -> None:
    calls: list[str] = []
    tools = [make_fake_tool("search", result="hit", record=calls)]
    # Round 1 succeeds (a tool call → useful work). Round 2: every provider fails.
    deps = make_fake_deps(
        llm_scripts={
            "react": [
                react_tool_decision([tool_call("search")], content="looking"),
                RuntimeError("primary down"),
            ]
        },
        fallback_scripts=[{"react": [RuntimeError("backup down too")]}],
    )
    graph = build_react_orchestration_graph(
        tools=tools, agent_name="react", system_prompt="Answer.", checkpointer=make_checkpointer()
    )
    events, final = await collect_events(graph, {"input": "go"}, deps=deps, source="react")

    # The turn was salvaged into a forced 收尾 (reason=error), not crashed.
    assert final["status"] == "finalized"
    assert final["finalize_reason"] == "error"
    assert calls == ["search"]  # the first round's tool actually ran

    forced = [e for e in events if e.type == StreamEventType.CONTENT and e.metadata.get("forced")]
    assert forced and forced[-1].metadata.get("reason") == "error"


@pytest.mark.asyncio
async def test_first_round_total_failure_propagates() -> None:
    # Nothing gathered yet → a first-round exhaustion has nothing to salvage.
    deps = make_fake_deps(llm_scripts={"react": [RuntimeError("primary down")]})
    graph = build_react_orchestration_graph(agent_name="react", system_prompt="x")
    with pytest.raises(Exception):
        await graph.ainvoke(
            {"input": "q"}, config={"configurable": {"deps": deps, "thread_id": "t"}}
        )
