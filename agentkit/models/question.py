"""Structured domain contracts for the ``question`` Orchestration.

Faithful ports of the shapes from ``deeptutor/agents/question/pipeline.py`` (which
used frozen dataclasses).  Here they are pydantic models so nodes can
``model_validate`` LLM output and store ``model_dump()`` dicts in State, matching
how ``math_animator`` handles its contracts (ADR-0004).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class QuizTemplate(BaseModel):
    """One planned question the quiz phase will flesh out."""

    question_id: str
    topic: str
    question_type: str
    difficulty: str


class QuizPlan(BaseModel):
    """The plan phase output: an analysis plus per-question templates."""

    analysis: str = ""
    templates: list[QuizTemplate] = Field(default_factory=list)


class QuizPair(BaseModel):
    """The final shape one question takes (mirrors the legacy ``QAPair``)."""

    question_id: str
    question: str
    question_type: str
    correct_answer: str
    explanation: str = ""
    options: dict[str, str] | None = None
    topic: str = ""
    difficulty: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = ["QuizPair", "QuizPlan", "QuizTemplate"]
