"""``MathAnimatorState`` — the ``math_animator`` Orchestration State (ADR-0004).

Extends :class:`~agentkit.state.base.BaseState` with the linear-pipeline domain
fields plus the visible retry-cycle control fields (ADR-0005).  Domain contracts
are stored as ``model_dump()`` dicts (see ``models/math_animator.py``); nodes
re-validate on read.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any

from agentkit.state.base import BaseState

# Faithful port of the retry gate from
# ``deeptutor/agents/math_animator/retry_manager.py`` (max_retries=4).
DEFAULT_MAX_RETRIES = 4


class MathAnimatorState(BaseState, total=False):
    # --- inputs ---
    user_input: str
    history_context: str
    output_mode: str  # "video" | "image"
    quality: str  # "low" | "medium" | "high"
    style_hint: str
    turn_id: str
    duration_target_seconds: float | None

    # --- intermediate products (pydantic DTOs stored as dicts) ---
    analysis: dict[str, Any]  # ConceptAnalysis.model_dump()
    design: dict[str, Any]  # SceneDesign.model_dump()
    code: str  # current code under test (updated by codegen + repair)
    render_result: dict[str, Any] | None  # RenderResult.model_dump()
    summary: dict[str, Any]  # SummaryPayload.model_dump()

    # --- retry-cycle control (ADR-0005 gate) ---
    retry_count: int  # 0..max_retries
    max_retries: int
    last_error: str  # feeds the repair node
    retry_history: Annotated[list[dict[str, Any]], operator.add]

    # --- terminal outcome ---
    status: str  # "running" | "succeeded" | "failed"
    error: str  # terminal failure message
    render_type: str  # stamped by the visualize manim reuse path ("" for pure math_animator)


__all__ = ["DEFAULT_MAX_RETRIES", "MathAnimatorState"]
