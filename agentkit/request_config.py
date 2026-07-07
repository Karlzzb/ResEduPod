"""Request configs for the two orchestrations (ported from DeepTutor)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class MathAnimatorRequestConfig(BaseModel):
    output_mode: Literal["video", "image"] = "video"
    quality: Literal["low", "medium", "high"] = "medium"
    style_hint: str = Field(default="", max_length=500)


class VisualizeRequestConfig(BaseModel):
    render_mode: Literal[
        "auto", "svg", "chartjs", "mermaid", "html", "manim_video", "manim_image"
    ] = "auto"
    quality: Literal["low", "medium", "high"] = "medium"
    style_hint: str = Field(default="", max_length=500)


__all__ = ["MathAnimatorRequestConfig", "VisualizeRequestConfig"]
