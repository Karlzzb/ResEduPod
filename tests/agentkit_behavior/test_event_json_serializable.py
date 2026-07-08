"""Every emitted event must be strictly JSON-serializable (AC #6, ADR-0002/0012).

This is the hard constraint carried from the precedent
``tests/core/agentic/test_tool_dispatch_events.py``: the WebSocket push and turn
persistence both ``json.dumps`` events, so a non-serializable payload silently
breaks streaming.
"""

from __future__ import annotations

import json

import pytest

from agentkit import (
    build_deep_research_graph,
    build_math_animator_graph,
    build_visualize_graph,
    make_checkpointer,
)
from agentkit.testing import (
    analysis_json,
    code_json,
    design_json,
    make_fake_deps,
    research_report,
    research_worker_json,
    summary_json,
)


@pytest.mark.asyncio
async def test_all_math_animator_events_json_serializable(collect_events) -> None:

    scripts = {
        "concept_analysis": [analysis_json()],
        "concept_design": [design_json()],
        "code_generator": [code_json("v1"), code_json("repaired")],
        "summary": [summary_json()],
    }
    deps = make_fake_deps(llm_scripts=scripts, render_fail_times=1)
    graph = build_math_animator_graph(checkpointer=make_checkpointer())
    events, _ = await collect_events(
        graph,
        {"user_input": "unit circle", "output_mode": "video", "quality": "low", "language": "en"},
        deps=deps,
        source="math_animator",
    )
    assert events
    for event in events:
        json.dumps(event.to_dict())  # must not raise


@pytest.mark.asyncio
async def test_all_deep_research_events_json_serializable(collect_events) -> None:
    # Exercises the richer metadata deep_research emits (round counters, dedup /
    # queue-full drops, safety-cap warnings) — all must stay JSON-safe.
    deps = make_fake_deps(
        llm_scripts={
            "research_worker": [
                research_worker_json(
                    "A",
                    citations=[{"source": "s", "title": "t", "snippet": "q"}],
                    append=[{"title": "child", "overview": "o"}],
                ),
                research_worker_json("B"),
                research_worker_json("child done"),
            ],
            "research_report": [research_report("# R")],
        }
    )
    graph = build_deep_research_graph(max_parallel_topics=2, checkpointer=make_checkpointer())
    events, _ = await collect_events(
        graph,
        {"topic": "T", "confirmed_outline": [{"title": "A"}, {"title": "B"}], "language": "en"},
        deps=deps,
        source="deep_research",
    )
    assert events
    for event in events:
        json.dumps(event.to_dict())


@pytest.mark.asyncio
async def test_all_visualize_manim_events_json_serializable(collect_events) -> None:

    scripts = {
        "concept_analysis": [analysis_json()],
        "concept_design": [design_json()],
        "code_generator": [code_json("v1")],
        "summary": [summary_json()],
    }
    deps = make_fake_deps(llm_scripts=scripts)
    graph = build_visualize_graph(checkpointer=make_checkpointer())
    events, _ = await collect_events(
        graph,
        {
            "user_input": "unit circle",
            "render_mode": "manim_video",
            "quality": "low",
            "language": "en",
        },
        deps=deps,
        source="visualize",
    )
    assert events
    for event in events:
        json.dumps(event.to_dict())
