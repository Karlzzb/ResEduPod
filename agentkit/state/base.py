"""``BaseState`` — the thin common base for every Orchestration State (ADR-0004).

Only mechanistic fields shared by *all* Agents live here (``messages`` /
``usage`` / ``trace_meta`` / ``language``); each Orchestration extends it with
its own domain fields.  Consistency lives at this common layer, not by flattening
every domain into one mega-schema.

State is a ``TypedDict`` (not pydantic): nodes return **partial** dicts that
LangGraph merges via the annotated reducers, which is the idiomatic and
best-supported shape for reducer channels and checkpoint serialization.  Domain
contracts (``ConceptAnalysis`` etc.) are stored *inside* State fields as
``model_dump()`` dicts so the checkpointer serializes them without a custom
serde allowlist.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class Usage(TypedDict, total=False):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    calls: int


_USAGE_KEYS = ("prompt_tokens", "completion_tokens", "total_tokens", "calls")


def accumulate_usage(left: Usage | None, right: Usage | None) -> Usage:
    """Reducer: element-wise add two partial usage records."""
    left = left or {}
    right = right or {}
    return {key: int(left.get(key, 0)) + int(right.get(key, 0)) for key in _USAGE_KEYS}


class BaseState(TypedDict, total=False):
    """Common mechanistic fields for every Orchestration State (ADR-0004)."""

    messages: Annotated[list[dict[str, Any]], operator.add]
    usage: Annotated[Usage, accumulate_usage]
    trace_meta: dict[str, Any]
    language: str  # "en" | "zh"


__all__ = ["BaseState", "Usage", "accumulate_usage"]
