"""Structured domain contracts for the ``math_animator`` orchestration.

These pydantic models are the typed intermediate products passed between Agent
leaves (ADR-0004: "Agent 间传递的结构化契约是 State 的字段").  They are stored
inside the LangGraph ``State`` as ``model_dump()`` dicts so the checkpointer can
serialize them without a custom serde allowlist; nodes re-validate on read.

Faithfully ported from ``deeptutor/agents/math_animator/models.py``.
"""

from __future__ import annotations

from pydantic import BaseModel


class ConceptAnalysis(BaseModel):
    learning_goal: str = ""
    math_focus: list[str] = []
    visual_targets: list[str] = []
    narrative_steps: list[str] = []
    reference_usage: str = ""
    output_intent: str = ""


class SceneDesign(BaseModel):
    title: str = ""
    scene_outline: list[str] = []
    visual_style: str = ""
    animation_notes: list[str] = []
    image_plan: list[str] = []
    code_constraints: list[str] = []


class GeneratedCode(BaseModel):
    code: str = ""
    rationale: str = ""


class SummaryPayload(BaseModel):
    summary_text: str = ""
    user_request: str = ""
    generated_output: str = ""
    key_points: list[str] = []


class RetryAttempt(BaseModel):
    attempt: int
    error: str


class VisualReviewResult(BaseModel):
    passed: bool = True
    summary: str = ""
    issues: list[str] = []
    suggested_fix: str = ""
    reviewed_frames: int = 0


class RenderedArtifact(BaseModel):
    type: str  # "video" | "image"
    url: str
    filename: str
    content_type: str = ""
    label: str = ""


class RenderResult(BaseModel):
    output_mode: str  # "video" | "image"
    artifacts: list[RenderedArtifact] = []
    public_code_path: str = ""
    source_code_path: str = ""
    quality: str = ""
    retry_attempts: int = 0
    retry_history: list[RetryAttempt] = []
    visual_review: VisualReviewResult | None = None


__all__ = [
    "ConceptAnalysis",
    "GeneratedCode",
    "RenderResult",
    "RenderedArtifact",
    "RetryAttempt",
    "SceneDesign",
    "SummaryPayload",
    "VisualReviewResult",
]
