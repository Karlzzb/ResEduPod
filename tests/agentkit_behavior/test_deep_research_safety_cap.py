"""``deep_research`` safety cap: dynamic growth cannot loop forever (US 23).

A worker that keeps appending a fresh sub-topic every round would grow the queue
without end.  ``safety_cap`` bounds the number of supervisor rounds; when it trips
the run stops scheduling and heads to the report with any still-pending sub-topics
left untouched, and the terminal ``status`` is ``"capped"`` (a visible signal, not
a silent truncation).
"""

from __future__ import annotations

import pytest

from agentkit import build_deep_research_graph, make_checkpointer
from agentkit.runtime.stream import StreamEventType
from agentkit.testing import make_fake_deps, research_report, research_worker_json


@pytest.mark.asyncio
async def test_safety_cap_halts_runaway_growth(collect_events) -> None:
    # Each worker discovers one brand-new child, so pending never drains on its own;
    # only the round cap can stop it.  Cap = 3, one worker per round (max_parallel=1).
    deps = make_fake_deps(
        llm_scripts={
            "research_worker": [
                research_worker_json("root", append=[{"title": "C1", "overview": ""}]),
                research_worker_json("c1", append=[{"title": "C2", "overview": ""}]),
                research_worker_json("c2", append=[{"title": "C3", "overview": ""}]),
            ],
            "research_report": [research_report("# Partial Report")],
        }
    )
    graph = build_deep_research_graph(max_parallel_topics=1, checkpointer=make_checkpointer())
    events, final = await collect_events(
        graph,
        {
            "topic": "endless",
            "confirmed_outline": [{"title": "root"}],
            "safety_cap": 3,
            "queue_max_length": 50,  # high, so the round cap (not the length cap) is what bites
            "language": "en",
        },
        deps=deps,
        source="deep_research",
    )

    # Stopped at the cap: exactly 3 workers ran, the 3rd-appended child is still pending.
    assert final["status"] == "capped"
    assert final["rounds"] == 4  # the round that detects rounds > cap and bails to report
    assert deps.llm.calls.count("research_worker") == 3
    pending = [b["title"] for b in final["blocks"] if b["status"] == "pending"]
    assert pending == ["C3"]
    # The report still ran (a partial report beats nothing) and preserved the signal.
    assert final["report"].startswith("# Partial Report")

    # The cap emitted a visible warning rather than truncating silently.
    warnings = [
        e
        for e in events
        if e.type == StreamEventType.PROGRESS and e.metadata.get("safety_cap_reached")
    ]
    assert len(warnings) == 1
