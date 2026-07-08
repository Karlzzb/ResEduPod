"""``VisualizeState`` — the ``visualize`` Orchestration State (ADR-0004)."""

from __future__ import annotations

from typing import Any

from agentkit.state.base import BaseState


class VisualizeState(BaseState, total=False):
    # --- inputs ---
    user_input: str
    history_context: str
    render_mode: str  # "auto" | "svg" | ... | "manim_video" | "manim_image"
    quality: str
    style_hint: str
    turn_id: str

    # --- text path ---
    analysis: dict[str, Any]  # VisualizationAnalysis.model_dump()
    render_type: str  # resolved concrete type
    code: str
    review: dict[str, Any]  # ReviewResult.model_dump()

    # --- manim reuse path envelope ---
    manim_result: dict[str, Any]  # final MathAnimatorState envelope, stamped with render_type

    # --- terminal outcome ---
    status: str
    error: str


__all__ = ["VisualizeState"]
