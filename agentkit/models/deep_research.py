"""Structured domain contracts for the ``deep_research`` orchestration.

Faithful, slimmed ports of the shapes carried by the pre-fork
``deeptutor/agents/research/data_structures.py`` (``TopicBlock``,
``DynamicTopicQueue`` entries) and ``utils/citation_manager.py`` (citation
records).  As with the other agentkit orchestrations these are pydantic models so
nodes can ``model_validate`` LLM output and store ``model_dump()`` dicts inside the
LangGraph ``State`` (ADR-0004); the checkpointer then serializes plain dicts with
no custom serde.

The mutable ``DynamicTopicQueue`` / lock-guarded ``CitationManager`` *objects* do
not survive the fork: their scheduling role is taken by the supervisor node plus
the ``blocks`` reducer, and their evidence role by the ``citations`` reducer (see
:mod:`agentkit.state.deep_research`).  What remains here is only the value shapes.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# Block lifecycle states (ported from ``BlockStatus``; workers only ever move a
# block ``pending → completed``/``failed`` — ``researching`` is transient and not
# needed once scheduling is a per-round recompute rather than a shared mutation).
STATUS_PENDING = "pending"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"


class SubTopic(BaseModel):
    """One outline entry / discovered sub-topic (pre-fork ``SubTopicItem``)."""

    title: str
    overview: str = ""


class TopicBlock(BaseModel):
    """A schedulable research unit (pre-fork ``TopicBlock``, minus mutable traces).

    ``knowledge`` holds the worker's synthesized findings once completed; ``parent``
    records which block spawned it (``None`` for outline-seeded roots) so the report
    can reflect the discovery tree if it wants.
    """

    block_id: str
    title: str
    overview: str = ""
    status: str = STATUS_PENDING
    knowledge: str = ""
    parent: str | None = None
    citation_ids: list[str] = Field(default_factory=list)


class CitationDraft(BaseModel):
    """A source the worker cites, *before* the worker assigns it a stable id.

    The LLM only supplies the evidence (``source``/``title``/``snippet``); the
    worker mints the ``citation_id`` / ``block_id`` when folding it into
    :class:`Citation`, so those ids stay deterministic and worker-local rather than
    LLM-chosen.
    """

    source: str = ""
    title: str = ""
    snippet: str = ""


class Citation(BaseModel):
    """A single stored evidence record (pre-fork ``CitationManager`` entry, flattened)."""

    citation_id: str
    block_id: str
    source: str = ""
    title: str = ""
    snippet: str = ""


class WorkerOutput(BaseModel):
    """The strict JSON one ``research_worker`` Agent leaf returns.

    ``knowledge`` is the block's synthesized findings; ``citations`` are the sources
    it grounded them in (id-less drafts); ``append`` are freshly discovered
    sub-topics to schedule next round (the pre-fork ``APPEND`` label, now a
    structured field instead of a parsed control token).
    """

    knowledge: str = ""
    citations: list[CitationDraft] = Field(default_factory=list)
    append: list[SubTopic] = Field(default_factory=list)


def as_block_dict(block: TopicBlock) -> dict[str, Any]:
    """``model_dump`` helper kept next to the model for symmetry with callers."""
    return block.model_dump()


__all__ = [
    "STATUS_COMPLETED",
    "STATUS_FAILED",
    "STATUS_PENDING",
    "Citation",
    "CitationDraft",
    "SubTopic",
    "TopicBlock",
    "WorkerOutput",
    "as_block_dict",
]
