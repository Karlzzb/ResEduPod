"""Chat robustness (issue #3): context-window protection on the ReAct template.

Drives a loop whose conversation carries a large tool result, with a deliberately
tiny ``context_window``, and asserts the guard snips the oldest ``role=tool``
message to a marker (rather than overflowing) and emits a single warning — while the
run still finishes cleanly (AC: 超长上下文按策略截断/压缩,不溢出).
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
from agentkit.utils.context_window import TOOL_RESULT_SNIP_MARKER


@pytest.mark.asyncio
async def test_oversized_tool_result_snipped_before_next_call(collect_events) -> None:
    # A big tool result blows a tiny window; round-2's guard must snip it.
    big_result = "x" * 20_000  # ~5k tokens at chars/4 — far over the window below
    tools = [make_fake_tool("search", result=big_result)]
    deps = make_fake_deps(
        llm_scripts={
            "react": [
                react_tool_decision([tool_call("search")], content="look"),
                react_final("done"),
            ]
        },
        context_window=256,  # tiny, so the guard trips on round 2
    )
    graph = build_react_orchestration_graph(
        tools=tools, agent_name="react", system_prompt="x", checkpointer=make_checkpointer()
    )
    events, final = await collect_events(graph, {"input": "go"}, deps=deps, source="react")

    assert final["status"] == "succeeded"
    assert final["final_text"] == "done"

    # The guard fired exactly once with its warning marker.
    guards = [
        e for e in events
        if e.type == StreamEventType.PROGRESS and e.metadata.get("context_window_guard")
    ]
    assert len(guards) == 1

    # The context actually SENT to the provider on round 2 was snipped — the big
    # tool result never reached the model (guard's real contract: no overflow).
    round2 = deps.llm.seen_messages[1]
    tool_sent = [m for m in round2 if m.get("role") == "tool"]
    assert tool_sent and all(m["content"] == TOOL_RESULT_SNIP_MARKER for m in tool_sent)
    assert big_result not in "".join(str(m.get("content")) for m in round2)


@pytest.mark.asyncio
async def test_within_budget_leaves_conversation_untouched(collect_events) -> None:
    tools = [make_fake_tool("search", result="small hit")]
    deps = make_fake_deps(
        llm_scripts={
            "react": [
                react_tool_decision([tool_call("search")], content="look"),
                react_final("done"),
            ]
        },
        context_window=100_000,  # generous — guard must not trip
    )
    graph = build_react_orchestration_graph(tools=tools, agent_name="react", system_prompt="x")
    events, final = await collect_events(graph, {"input": "go"}, deps=deps, source="react")

    guards = [
        e for e in events
        if e.type == StreamEventType.PROGRESS and e.metadata.get("context_window_guard")
    ]
    assert not guards
    assert final["status"] == "succeeded"

    # Round 2 saw the untouched tool result — nothing was snipped.
    round2 = deps.llm.seen_messages[1]
    tool_sent = [m for m in round2 if m.get("role") == "tool"]
    assert tool_sent and tool_sent[0]["content"] == "search:small hit"
