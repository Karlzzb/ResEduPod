"""``deep_research`` dedup: fuzzy + content-hash collapse of duplicate sub-topics.

Two mechanisms keep the dynamic queue from re-researching the same thread:

* within a worker, :func:`find_similar` drops an appended sub-topic that fuzzily
  matches one already tracked (an LLM re-proposing "Neural Nets" as "neural net");
* across concurrent workers, identical titles hash to the same ``block_id`` so the
  ``blocks`` reducer collapses them — asserted here end-to-end.
"""

from __future__ import annotations

import pytest

from agentkit import build_deep_research_graph, make_checkpointer
from agentkit.agents.deep_research.queue_ops import block_id_for, find_similar
from agentkit.testing import make_fake_deps, research_report, research_worker_json


def test_block_id_stable_for_equivalent_titles() -> None:
    # Case / whitespace differences normalize to the same id (cross-worker collapse).
    assert block_id_for("Neural Networks") == block_id_for("  neural   networks ")
    assert block_id_for("A") != block_id_for("B")


def test_find_similar_matches_fuzzy_restatement() -> None:
    # Plural/singular restatement stems to the same token set → fuzzy match.
    assert find_similar("neural networks", ["Neural Network"]) == "Neural Network"
    assert find_similar("completely unrelated", ["Neural Networks"]) is None


@pytest.mark.asyncio
async def test_worker_drops_duplicate_append(collect_events) -> None:
    """A worker that appends a sub-topic matching an existing outline title adds nothing."""
    deps = make_fake_deps(
        llm_scripts={
            "research_worker": [
                # Block A re-proposes "B" (already an outline block) → dropped by find_similar.
                research_worker_json("A findings", append=[{"title": "B", "overview": "dup"}]),
                research_worker_json("B findings"),
            ],
            "research_report": [research_report("# Report")],
        }
    )
    graph = build_deep_research_graph(max_parallel_topics=2, checkpointer=make_checkpointer())
    _events, final = await collect_events(
        graph,
        {"topic": "T", "confirmed_outline": [{"title": "A"}, {"title": "B"}], "language": "en"},
        deps=deps,
        source="deep_research",
    )
    # The duplicate append was dropped — still exactly two blocks, one round only.
    assert [b["title"] for b in final["blocks"]] == ["A", "B"]
    assert final["rounds"] == 1
    assert final["status"] == "succeeded"


@pytest.mark.asyncio
async def test_concurrent_workers_append_same_title_collapse(collect_events) -> None:
    """Two workers in one batch appending the same new title yield ONE child block."""
    deps = make_fake_deps(
        llm_scripts={
            "research_worker": [
                research_worker_json("A", append=[{"title": "Shared Child", "overview": "x"}]),
                research_worker_json("B", append=[{"title": "shared child", "overview": "y"}]),
                # Only one child should be scheduled next round.
                research_worker_json("Shared child done"),
            ],
            "research_report": [research_report("# Report")],
        }
    )
    graph = build_deep_research_graph(max_parallel_topics=2, checkpointer=make_checkpointer())
    _events, final = await collect_events(
        graph,
        {"topic": "T", "confirmed_outline": [{"title": "A"}, {"title": "B"}], "language": "en"},
        deps=deps,
        source="deep_research",
    )
    child_blocks = [b for b in final["blocks"] if b.get("parent")]
    assert len(child_blocks) == 1
    assert child_blocks[0]["status"] == "completed"
    assert len(final["blocks"]) == 3
