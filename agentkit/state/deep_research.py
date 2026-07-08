"""``DeepResearchState`` — the dynamic-parallel Orchestration State (ADR-0006).

This is the third Orchestration archetype's State: a *recursive supervisor +
``Send`` fan-out* whose defining challenge is that several research workers run
concurrently in one LangGraph superstep and each may **append** freshly discovered
sub-topics back into a shared work list.  The merge rules for those concurrent
returns live here as two custom reducers, because "how concurrent worker appends
combine into shared State" is exactly what a reducer is for (ADR-0006).

Two things the pre-fork ``deeptutor/agents/research`` implementation did with a
mutable ``DynamicTopicQueue`` + a lock-guarded ``CitationManager`` are replaced by
value-merge semantics here:

* **``blocks``** — the work list.  A worker never mutates a shared object; it
  returns a *partial* list of blocks (its own block, flipped to ``completed``,
  plus any children it discovered).  :func:`merge_blocks` folds those into the
  canonical list, **upserting by ``block_id``** so a status flip replaces in place
  and a genuinely new child appends exactly once.  Because a child's ``block_id``
  is a deterministic content hash of its title (see
  ``agentkit.agents.deep_research.queue_ops.block_id_for``), two workers that
  discover the *same* sub-topic in the same round collapse to one block — the
  concurrency-safe replacement for the old shared-queue-under-GIL append.

* **``citations``** — a ``block_id → citation`` mapping is the wrong shape (workers
  key independently); instead ``citations`` is a ``citation_id → citation`` dict
  merged by :func:`merge_citations` (plain dict union, last-writer-wins on an id
  collision, which cannot happen for distinct ids).  This structurally removes the
  old ``CitationManager``'s ``asyncio.Lock`` *and* its O(N²) "rewrite the whole
  file on every add": citations accumulate in State and the checkpointer persists
  them **once per superstep**, not once per citation (ADR-0006).

Everything is JSON-serializable plain data (dicts/lists) so the checkpointer needs
no custom serde, matching how ``math_animator`` stores its ``model_dump()`` dicts.
"""

from __future__ import annotations

from typing import Annotated, Any

from agentkit.state.base import BaseState

# --- scheduling defaults (faithful port of the pre-fork ``deep`` depth policy) ---

# Max workers dispatched per supervisor round (the ``Send`` batch ceiling).
DEFAULT_MAX_PARALLEL_TOPICS = 3
# Cap on total blocks; a worker stops appending children once the list is full.
DEFAULT_QUEUE_MAX_LENGTH = 8
# Fuzzy-dedup threshold for "is this appended sub-topic the same as an existing one".
DEFAULT_SIMILARITY_THRESHOLD = 0.85


def safety_cap_for(queue_max_length: int) -> int:
    """Runaway-growth backstop on supervisor rounds (pre-fork: ``max(20, N*4)``)."""
    return max(20, queue_max_length * 4)


def merge_blocks(
    left: list[dict[str, Any]] | None, right: list[dict[str, Any]] | None
) -> list[dict[str, Any]]:
    """Reducer: upsert blocks by ``block_id``, preserving first-seen order.

    ``left`` is the accumulated list, ``right`` a node's partial return (one worker's
    own updated block plus any children it discovered; or the supervisor's seed).
    A block whose ``block_id`` already exists is **replaced** (a status flip
    ``pending → completed`` overwrites the stale copy); an unseen ``block_id`` is
    **appended** at the tail so the next supervisor round sees it.  Ordering is
    stable — existing blocks keep their positions, new ones arrive in ``right``'s
    order — which keeps ``pending`` slicing deterministic across rounds.

    Concurrent workers in one superstep are folded left-to-right by LangGraph, so N
    workers each returning ``[own_completed, *children]`` compose associatively:
    duplicate child ids (two workers, same discovered sub-topic) collapse to one.
    """
    merged = list(left or [])
    index = {block["block_id"]: pos for pos, block in enumerate(merged)}
    for block in right or []:
        block_id = block["block_id"]
        pos = index.get(block_id)
        if pos is None:
            index[block_id] = len(merged)
            merged.append(block)
        else:
            merged[pos] = block
    return merged


def merge_citations(
    left: dict[str, dict[str, Any]] | None, right: dict[str, dict[str, Any]] | None
) -> dict[str, dict[str, Any]]:
    """Reducer: union two ``citation_id → citation`` maps (concurrent-worker safe).

    Distinct workers mint distinct citation ids (``CIT-{block}-{seq}``), so the union
    never loses or duplicates an entry; an id collision (impossible for well-formed
    ids) resolves last-writer-wins.  Accumulating in State — rather than a shared
    manager that rewrites ``citations.json`` on every add — is what removes the old
    O(N²) disk-write and the lock (ADR-0006).
    """
    merged = dict(left or {})
    merged.update(right or {})
    return merged


class DeepResearchState(BaseState, total=False):
    # --- input ---
    topic: str  # the (already rephrased/confirmed) research topic
    # The confirmed outline seeds the initial blocks; HITL confirmation itself is
    # issue #5, so this slice takes it as given input.
    confirmed_outline: list[dict[str, Any]]  # [{"title", "overview"}, ...]

    # --- scheduling knobs (per-run overrides of the build-time defaults) ---
    max_parallel_topics: int  # Send-batch ceiling per round
    queue_max_length: int  # block-count cap (gates worker appends)
    safety_cap: int  # supervisor-round backstop against runaway growth

    # --- shared work list + evidence (merged by the reducers above) ---
    blocks: Annotated[list[dict[str, Any]], merge_blocks]  # TopicBlock dicts
    citations: Annotated[dict[str, dict[str, Any]], merge_citations]  # id → citation

    # --- scheduler bookkeeping ---
    rounds: int  # completed supervisor rounds (gated against safety_cap)

    # --- terminal outcome ---
    report: str  # the assembled final report (markdown/html)
    status: str  # "running" | "succeeded" | "capped"


__all__ = [
    "DEFAULT_MAX_PARALLEL_TOPICS",
    "DEFAULT_QUEUE_MAX_LENGTH",
    "DEFAULT_SIMILARITY_THRESHOLD",
    "DeepResearchState",
    "merge_blocks",
    "merge_citations",
    "safety_cap_for",
]
