"""ReAct template happy path: llm → tool → llm → final (issue #2 main seam)."""

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
async def test_react_loop_tool_then_final(collect_events) -> None:
    calls: list[str] = []
    tools = [make_fake_tool("search", result="found the answer", record=calls)]
    # Turn 1: call the tool.  Turn 2: answer.
    deps = make_fake_deps(
        llm_scripts={
            "react": [
                react_tool_decision([tool_call("search", arguments={"q": "x"})], content="let me look"),
                react_final("The answer is 42."),
            ]
        }
    )
    graph = build_react_orchestration_graph(
        tools=tools,
        agent_name="react",
        system_prompt="Answer the question.",
        checkpointer=make_checkpointer(),
    )
    events, final = await collect_events(
        graph, {"input": "what is the answer?"}, deps=deps, source="react"
    )

    # Final State: the loop finished with the model's answer after exactly one tool round.
    assert final["status"] == "succeeded"
    assert final["final_text"] == "The answer is 42."
    assert final["iteration"] == 2
    assert final["pending_tool_calls"] == []

    # The tool actually ran (once).
    assert calls == ["search"]

    # Two LLM turns, in order.
    assert deps.llm.calls == ["react", "react"]

    # Stage ordering: reasoning → (tool round) → reasoning, ending in a content event.
    stages = [e.stage for e in events if e.type == StreamEventType.STAGE_START]
    assert stages == ["reasoning", "reasoning"]
    contents = [e.content for e in events if e.type == StreamEventType.CONTENT]
    assert contents[-1] == "The answer is 42."


@pytest.mark.asyncio
async def test_react_tool_result_fed_back_into_conversation() -> None:
    """The tool result lands in the reduced ``messages`` so the next turn sees it.

    Asserted against the fully-reduced State (``ainvoke``) rather than the streaming
    bridge's naively-accumulated view, which does not replay the ``messages`` reducer.
    """
    deps = make_fake_deps(
        llm_scripts={
            "react": [
                react_tool_decision([tool_call("search")], content="look"),
                react_final("done"),
            ]
        }
    )
    graph = build_react_orchestration_graph(
        tools=[make_fake_tool("search", result="hit")], agent_name="react", system_prompt="x"
    )
    final = await graph.ainvoke(
        {"input": "q"}, config={"configurable": {"deps": deps, "thread_id": "t"}}
    )
    roles = [m.get("role") for m in final["messages"]]
    assert "tool" in roles
    tool_msg = next(m for m in final["messages"] if m.get("role") == "tool")
    assert tool_msg["content"] == "search:hit"


def test_react_graph_has_visible_llm_tool_cycle() -> None:
    """ADR-0005/0008: the loop is a cycle drawn in the graph, not hidden in a node."""
    graph = build_react_orchestration_graph(
        tools=[make_fake_tool("t")], agent_name="react", system_prompt="x"
    )
    edges = graph.get_graph().edges
    pairs = {(e.source, e.target) for e in edges}
    # llm → tools (via the conditional router) and tools → llm close the visible cycle.
    assert ("tools", "llm") in pairs
    assert any(src == "llm" and dst == "tools" for src, dst in pairs)
    assert any(src == "llm" and dst == "finalize" for src, dst in pairs)


@pytest.mark.asyncio
async def test_react_loop_no_tools_direct_answer(collect_events) -> None:
    deps = make_fake_deps(llm_scripts={"react": [react_final("Direct answer.")]})
    graph = build_react_orchestration_graph(agent_name="react", system_prompt="Answer.")
    _events, final = await collect_events(graph, {"input": "hi"}, deps=deps, source="react")

    assert final["status"] == "succeeded"
    assert final["final_text"] == "Direct answer."
    assert final["iteration"] == 1
    assert deps.llm.calls == ["react"]
