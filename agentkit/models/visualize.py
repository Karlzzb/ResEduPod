"""Structured domain contracts for the ``visualize`` orchestration.

Faithfully ported from ``deeptutor/agents/visualize/models.py``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

RenderType = Literal["svg", "chartjs", "mermaid", "html", "manim_video", "manim_image"]


class VisualizationAnalysis(BaseModel):
    render_type: RenderType
    description: str = ""
    data_description: str = ""
    chart_type: str = ""
    visual_elements: list[str] = []
    rationale: str = ""
    visual_genre: Literal[
        "", "flowchart", "structural", "illustrative", "chart", "stepper", "interactive", "mockup", "art"
    ] = ""


class ReviewResult(BaseModel):
    optimized_code: str = ""
    changed: bool = False
    review_notes: str = ""


__all__ = ["ReviewResult", "RenderType", "VisualizationAnalysis"]
