"""``QuestionState`` — the ``question`` Orchestration State (ADR-0004 / ADR-0008).

``question`` is the loop archetype's first instance: an ``explore → plan → quiz``
flow where the ``explore`` and ``quiz`` phases each reuse the ``ReActOrchestration``
template as a nested subgraph.  This State carries the per-phase products; the ReAct
loop's own control fields live in :class:`~agentkit.state.react.ReActState` inside
those subgraphs.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any

from agentkit.state.base import BaseState

# Ported from ``deeptutor/agents/question/pipeline.py``.
DEFAULT_MAX_EXPLORE_ITERATIONS = 8
DEFAULT_MAX_QUIZ_ITERATIONS = 5


class QuestionState(BaseState, total=False):
    # --- input ---
    user_input: str

    # --- phase products ---
    exploration: str  # explore-phase FINISH text (context for planning)
    plan: dict[str, Any]  # QuizPlan.model_dump()
    quiz_pairs: Annotated[list[dict[str, Any]], operator.add]  # QuizPair.model_dump() each

    # --- terminal outcome ---
    status: str  # "running" | "succeeded" | "failed"


__all__ = ["DEFAULT_MAX_EXPLORE_ITERATIONS", "DEFAULT_MAX_QUIZ_ITERATIONS", "QuestionState"]
