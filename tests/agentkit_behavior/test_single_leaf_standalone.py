"""A single Agent leaf runs standalone via ``graph.invoke`` with a minimal AgentDeps,
and its process/result are consumable from ``astream_events`` (AC #2, user-story 6/8/10).

This is the "secondary seam" (PRD Testing Decisions): one Agent compiled as a
1-node subgraph, driven with the smallest possible dependency bundle — a scripted
LLM client + inline prompts + static config, and NO external services.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph
import pytest

from agentkit.agents.math_animator.concept_analysis import concept_analysis_node
from agentkit.deps import AgentDeps
from agentkit.state.math_animator import MathAnimatorState
from agentkit.testing import InlinePromptProvider, StaticAgentConfig, analysis_json
from agentkit.testing.fake_deps import FakeLLM


def _single_leaf_graph():
    graph = StateGraph(MathAnimatorState)
    graph.add_node("concept_analysis", concept_analysis_node)
    graph.add_edge(START, "concept_analysis")
    graph.add_edge("concept_analysis", END)
    return graph.compile()


def _minimal_deps() -> AgentDeps:
    # One LLM client + inline prompt + static config. No renderer, no store, no services.
    return AgentDeps(
        llm=FakeLLM(scripts={"concept_analysis": [analysis_json()]}),
        prompts=InlinePromptProvider(),  # returns None → Agent uses its OWN inline default prompt
        config=StaticAgentConfig(),
    )


@pytest.mark.asyncio
async def test_single_leaf_invoke_with_minimal_deps() -> None:
    graph = _single_leaf_graph()
    config = {"configurable": {"deps": _minimal_deps()}}
    final = await graph.ainvoke(
        {"user_input": "show the unit circle", "output_mode": "video", "language": "en"},
        config=config,
    )
    assert final["analysis"]["learning_goal"] == "Show the unit circle"


@pytest.mark.asyncio
async def test_single_leaf_astream_events_yields_process_and_result() -> None:
    graph = _single_leaf_graph()
    config = {"configurable": {"deps": _minimal_deps()}}

    seen_types: set[str] = set()
    result_outputs: list[dict] = []
    async for event in graph.astream_events(
        {"user_input": "show the unit circle", "output_mode": "video", "language": "en"},
        config=config,
        version="v2",
    ):
        seen_types.add(event["event"])
        # The top-level graph's terminal event carries the final State.
        if event["event"] == "on_chain_end" and event.get("name") == "LangGraph":
            output = event["data"].get("output")
            if isinstance(output, dict):
                result_outputs.append(output)

    # Process is observable as node lifecycle; the leaf's fine-grained custom events
    # (get_stream_writer) ride the `custom` stream, which the main-seam astream test
    # exercises — astream_events surfaces the run structure, not that channel.
    assert "on_chain_start" in seen_types and "on_chain_end" in seen_types
    # Result is consumable: the terminal event delivers the computed analysis.
    assert any(o.get("analysis", {}).get("learning_goal") == "Show the unit circle" for o in result_outputs)
