"""``deep_research`` main seam: supervisor → Send fan-out → aggregate → report.

Drives the full dynamic-parallel graph with ``FakeDeps`` and asserts the event
sequence plus the final State (PRD Testing Decisions).  The scripted run seeds a
two-item outline; the first worker discovers a child sub-topic, so the supervisor
loops and schedules it in a second round before the report — proving the
recursive-supervisor + worker-append-via-reducer loop (US 21-22).
"""

from __future__ import annotations

import pytest

from agentkit import build_deep_research_graph, make_checkpointer
from agentkit.runtime.stream import StreamEventType
from agentkit.testing import make_fake_deps, research_report, research_worker_json


def _scripts() -> dict[str, list[str]]:
    return {
        "research_worker": [
            # Round 1, block A: findings + one grounded citation + a discovered child.
            research_worker_json(
                "A is foundational.",
                citations=[{"source": "http://a", "title": "Paper A", "snippet": "a-quote"}],
                append=[{"title": "A-child", "overview": "spun off from A"}],
            ),
            # Round 1, block B: findings only.
            research_worker_json(
                "B complements A.",
                citations=[{"source": "http://b", "title": "Paper B", "snippet": "b-quote"}],
            ),
            # Round 2, the appended child.
            research_worker_json("A-child ties it together."),
        ],
        "research_report": [research_report("# Report\n\nA, B and their child, synthesized.")],
    }


@pytest.mark.asyncio
async def test_deep_research_full_seam(collect_events) -> None:
    deps = make_fake_deps(llm_scripts=_scripts())
    graph = build_deep_research_graph(max_parallel_topics=2, checkpointer=make_checkpointer())
    events, final = await collect_events(
        graph,
        {
            "topic": "A vs B",
            "confirmed_outline": [
                {"title": "A", "overview": "about A"},
                {"title": "B", "overview": "about B"},
            ],
            "language": "en",
        },
        deps=deps,
        source="deep_research",
    )

    # Final State: two seeded blocks + one dynamically appended child, all completed.
    assert final["status"] == "succeeded"
    assert final["rounds"] == 2
    titles = {(b["title"], b["status"]) for b in final["blocks"]}
    assert titles == {("A", "completed"), ("B", "completed"), ("A-child", "completed")}
    # Citations accumulated in State (reducer union), one per citing worker.
    assert len(final["citations"]) == 2
    assert final["report"].startswith("# Report")

    # LLM call order: 3 worker calls (2 in round 1, 1 in round 2) then the report.
    assert deps.llm.calls == [
        "research_worker",
        "research_worker",
        "research_worker",
        "research_report",
    ]

    # The two supervisor rounds and the report phase opened in order.
    supervising = [
        e.metadata.get("round")
        for e in events
        if e.type == StreamEventType.STAGE_START and e.stage == "supervising"
    ]
    assert supervising == [1, 2]
    report_starts = [
        e for e in events if e.type == StreamEventType.STAGE_START and e.stage == "reporting"
    ]
    assert len(report_starts) == 1
