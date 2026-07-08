"""``deep_research`` reducer merge — the core issue #4 acceptance.

Two layers of assertion:

* **Unit** — the ``merge_blocks`` / ``merge_citations`` reducers fold concurrent
  partial returns with no loss and no duplication (upsert by ``block_id`` /
  union by ``citation_id``), including the associativity LangGraph relies on when
  folding N worker returns in one superstep.
* **Behavior** — a real run where a full batch of workers appends sub-topics
  concurrently; the next supervisor round schedules every appended child exactly
  once (US 22), proving the reducer merge holds end-to-end through the graph.
"""

from __future__ import annotations

import pytest

from agentkit import build_deep_research_graph, make_checkpointer
from agentkit.state.deep_research import merge_blocks, merge_citations
from agentkit.testing import make_fake_deps, research_report, research_worker_json


def test_merge_blocks_upserts_by_id_no_loss_no_dup() -> None:
    seed = [
        {"block_id": "a", "title": "A", "status": "pending"},
        {"block_id": "b", "title": "B", "status": "pending"},
    ]
    # Two workers complete their own block and each append a *distinct* child.
    worker_a = [
        {"block_id": "a", "title": "A", "status": "completed"},
        {"block_id": "ca", "title": "CA", "status": "pending"},
    ]
    worker_b = [
        {"block_id": "b", "title": "B", "status": "completed"},
        {"block_id": "cb", "title": "CB", "status": "pending"},
    ]
    # LangGraph folds left-to-right: seed ⊕ worker_a ⊕ worker_b.
    merged = merge_blocks(merge_blocks(seed, worker_a), worker_b)
    by_id = {b["block_id"]: b["status"] for b in merged}
    assert by_id == {"a": "completed", "b": "completed", "ca": "pending", "cb": "pending"}
    # No duplication and stable order (existing blocks keep position, children append).
    assert [b["block_id"] for b in merged] == ["a", "b", "ca", "cb"]


def test_merge_blocks_collapses_same_id_child() -> None:
    seed = [{"block_id": "a", "status": "pending"}, {"block_id": "b", "status": "pending"}]
    # Two workers discover the SAME sub-topic → same content-hash id → one block.
    worker_a = [
        {"block_id": "a", "status": "completed"},
        {"block_id": "shared", "status": "pending"},
    ]
    worker_b = [
        {"block_id": "b", "status": "completed"},
        {"block_id": "shared", "status": "pending"},
    ]
    merged = merge_blocks(merge_blocks(seed, worker_a), worker_b)
    assert [b["block_id"] for b in merged] == ["a", "b", "shared"]
    assert sum(b["block_id"] == "shared" for b in merged) == 1


def test_merge_blocks_order_independent() -> None:
    seed = [{"block_id": "a", "status": "pending"}]
    wa = [{"block_id": "a", "status": "completed"}, {"block_id": "x", "status": "pending"}]
    wb = [{"block_id": "a", "status": "completed"}, {"block_id": "y", "status": "pending"}]
    ids = lambda m: sorted(b["block_id"] for b in m)  # noqa: E731
    assert ids(merge_blocks(merge_blocks(seed, wa), wb)) == ids(
        merge_blocks(merge_blocks(seed, wb), wa)
    )


def test_merge_citations_unions_without_loss() -> None:
    left = {"CIT-a-01": {"block_id": "a"}}
    right = {"CIT-b-01": {"block_id": "b"}}
    merged = merge_citations(left, right)
    assert set(merged) == {"CIT-a-01", "CIT-b-01"}
    # Empty / None sides are safe (a worker with no citations).
    assert merge_citations(left, None) == left
    assert merge_citations(None, None) == {}


@pytest.mark.asyncio
async def test_concurrent_worker_appends_merge_end_to_end(collect_events) -> None:
    """A batch of 3 workers each append a distinct child; all are scheduled next round."""
    deps = make_fake_deps(
        llm_scripts={
            "research_worker": [
                # Round 1: three workers in one Send batch, each appends one child.
                research_worker_json("A", append=[{"title": "A-child", "overview": ""}]),
                research_worker_json("B", append=[{"title": "B-child", "overview": ""}]),
                research_worker_json("C", append=[{"title": "C-child", "overview": ""}]),
                # Round 2: the three appended children (order follows the merged queue).
                research_worker_json("A-child done"),
                research_worker_json("B-child done"),
                research_worker_json("C-child done"),
            ],
            "research_report": [research_report("# Report")],
        }
    )
    graph = build_deep_research_graph(max_parallel_topics=3, checkpointer=make_checkpointer())
    _events, final = await collect_events(
        graph,
        {
            "topic": "T",
            "confirmed_outline": [{"title": "A"}, {"title": "B"}, {"title": "C"}],
            "language": "en",
        },
        deps=deps,
        source="deep_research",
    )

    # No loss (all 6 blocks present), no dup, all completed by the appended round.
    completed = [b["title"] for b in final["blocks"] if b["status"] == "completed"]
    assert sorted(completed) == ["A", "A-child", "B", "B-child", "C", "C-child"]
    assert len(final["blocks"]) == 6
    assert final["rounds"] == 2
    # Six worker calls total: 3 roots + 3 appended children, each researched once.
    assert deps.llm.calls.count("research_worker") == 6
