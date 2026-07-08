"""``deep_research`` Orchestration — the dynamic-parallel archetype (ADR-0006).

Graph shape (US 21-23)::

    START → supervisor ──dispatch──┬─ Send("research_worker", block) × ≤max_parallel
                                   └─ "report"            (nothing pending)
    research_worker → aggregate
    aggregate ──loop_or_report──┬─ "supervisor"          (pending remains, under cap)
                                └─ "report" → END

This is the third and hardest Orchestration prototype: a *recursive supervisor*
that fans out a batch of research workers with ``Send``, lets each worker append
freshly discovered sub-topics back into shared State via a reducer, then loops so
the next round naturally schedules those appended sub-topics (US 22).  It is the
first use of ``Send`` in agentkit — the earlier archetypes are linear (issue #1)
and single-loop (issue #2).

Why this shape rather than a mutable shared queue driven by ``asyncio.gather`` (the
pre-fork ``ResearchPipeline._drive_queue``):

* The work list ``blocks`` and evidence ``citations`` are **State channels with
  reducers** (:mod:`agentkit.state.deep_research`).  Concurrent workers in one
  ``Send`` superstep return *partial* values that LangGraph folds with those
  reducers — so "worker appends a sub-topic" is a value merge, not a lock-guarded
  mutation, and the O(N²) citation disk-write disappears (ADR-0006).
* The loop is a **visible cycle in the graph** (``aggregate → supervisor``) gated
  by ``rounds`` vs ``safety_cap`` in State, exactly like the ReAct iteration gate
  (ADR-0005) — runaway dynamic growth cannot hide inside a node.

HITL outline confirmation (issue #5) and long-term memory (issue #6) are out of
scope here: this slice takes ``confirmed_outline`` as given input.
"""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from agentkit.agents.contract import emit
from agentkit.agents.deep_research import report_node, research_worker_node
from agentkit.agents.deep_research.queue_ops import block_id_for, find_similar, pending_blocks
from agentkit.models.deep_research import TopicBlock
from agentkit.state.deep_research import (
    DEFAULT_MAX_PARALLEL_TOPICS,
    DEFAULT_QUEUE_MAX_LENGTH,
    DeepResearchState,
    safety_cap_for,
)


def _effective_cap(state: DeepResearchState) -> int:
    """The active safety cap: an explicit per-run override, else the derived default."""
    override = state.get("safety_cap")
    if override:
        return int(override)
    return safety_cap_for(state.get("queue_max_length", DEFAULT_QUEUE_MAX_LENGTH))


def _seed_blocks(outline: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Turn the confirmed outline into initial ``pending`` blocks, deduped by title."""
    seeded: list[dict[str, Any]] = []
    seen: list[str] = []
    for item in outline:
        title = (item.get("title", "") or "").strip()
        if not title or find_similar(title, seen) is not None:
            continue
        seeded.append(
            TopicBlock(
                block_id=block_id_for(title), title=title, overview=item.get("overview", "")
            ).model_dump()
        )
        seen.append(title)
    return seeded


def build_deep_research_graph(
    *,
    max_parallel_topics: int = DEFAULT_MAX_PARALLEL_TOPICS,
    queue_max_length: int = DEFAULT_QUEUE_MAX_LENGTH,
    checkpointer: Any | None = None,
) -> Any:
    """Compile the ``deep_research`` orchestration graph.

    ``max_parallel_topics`` / ``queue_max_length`` are the build-time scheduling
    defaults; a run may override either via the input State, and ``safety_cap`` too.
    """

    async def supervisor_node(state: DeepResearchState, config: RunnableConfig) -> dict[str, Any]:
        """Seed on the first round, recompute nothing-yet, and advance the round gate.

        Runs once per round (re-entered from ``aggregate``); it is the single place
        ``rounds`` advances, so the ``safety_cap`` gate has one clear counter.
        """
        updates: dict[str, Any] = {}
        blocks = list(state.get("blocks", []))
        first_round = state.get("rounds", 0) == 0
        if first_round and not blocks:
            updates["blocks"] = _seed_blocks(state.get("confirmed_outline", []))

        rounds = state.get("rounds", 0) + 1
        updates["rounds"] = rounds
        if "max_parallel_topics" not in state:
            updates["max_parallel_topics"] = max_parallel_topics
        if "queue_max_length" not in state:
            updates["queue_max_length"] = queue_max_length

        current_blocks = updates.get("blocks", blocks)
        # Flag a capped run at the gate so ``report`` can surface it (rather than
        # silently truncating the dynamic growth): if pending work still remains but
        # we've exhausted the round budget, this round is the last one.
        over_cap = rounds > _effective_cap(state)
        if over_cap and pending_blocks(current_blocks):
            updates["status"] = "capped"
            emit(
                "progress",
                stage="supervising",
                agent="deep_research",
                trace_kind="warning",
                safety_cap_reached=True,
                round=rounds,
            )
        else:
            updates.setdefault("status", state.get("status", "running"))

        pending_now = pending_blocks(current_blocks)
        emit(
            "stage_start",
            stage="supervising",
            agent="deep_research",
            round=rounds,
            pending=len(pending_now),
        )
        return updates

    def dispatch(state: DeepResearchState) -> Any:
        """Fan out a bounded batch of workers, or head to the report when idle/capped."""
        blocks = list(state.get("blocks", []))
        pending = pending_blocks(blocks)
        if not pending or state.get("rounds", 0) > _effective_cap(state):
            return "report"
        batch = pending[: state.get("max_parallel_topics", max_parallel_topics)]
        known_titles = [b["title"] for b in blocks]
        payload_common = {
            "topic": state.get("topic", ""),
            "language": state.get("language", "en"),
            "known_titles": known_titles,
            "block_count": len(blocks),
            "queue_max_length": state.get("queue_max_length", queue_max_length),
        }
        return [Send("research_worker", {"block": block, **payload_common}) for block in batch]

    async def aggregate_node(state: DeepResearchState, config: RunnableConfig) -> dict[str, Any]:
        """The ``Send`` join barrier: workers' reducer-merged returns are visible here.

        The merge itself is done by the ``blocks`` / ``citations`` reducers before
        this node runs; it only reports round progress (and is the stable point the
        loop-or-report edge decides from).
        """
        blocks = list(state.get("blocks", []))
        pending = pending_blocks(blocks)
        emit(
            "progress",
            stage="supervising",
            agent="deep_research",
            round=state.get("rounds", 0),
            completed=len(blocks) - len(pending),
            pending=len(pending),
            citations=len(state.get("citations", {})),
        )
        return {}

    def loop_or_report(state: DeepResearchState) -> str:
        """Loop back to the supervisor while sub-topics remain and the cap holds."""
        if state.get("rounds", 0) > _effective_cap(state):
            return "report"
        return "supervisor" if pending_blocks(state.get("blocks", [])) else "report"

    graph = StateGraph(DeepResearchState)
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("research_worker", research_worker_node)
    graph.add_node("aggregate", aggregate_node)
    graph.add_node("report", report_node)

    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges(
        "supervisor", dispatch, {"research_worker": "research_worker", "report": "report"}
    )
    graph.add_edge("research_worker", "aggregate")  # Send join barrier
    graph.add_conditional_edges(
        "aggregate", loop_or_report, {"supervisor": "supervisor", "report": "report"}
    )
    graph.add_edge("report", END)
    return graph.compile(checkpointer=checkpointer)


__all__ = ["build_deep_research_graph"]
