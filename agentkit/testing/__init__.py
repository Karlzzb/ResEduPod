"""Test doubles for driving agentkit orchestrations without network or services."""

from __future__ import annotations

from agentkit.testing.fake_deps import (
    FakeLLM,
    FakeRenderer,
    InlinePromptProvider,
    StaticAgentConfig,
    analysis_json,
    code_json,
    design_json,
    make_fake_deps,
    research_report,
    research_worker_json,
    summary_json,
)
from agentkit.testing.fake_tools import (
    make_fake_tool,
    question_plan_json,
    quiz_pair_json,
    react_final,
    react_tool_decision,
    tool_call,
)

__all__ = [
    "FakeLLM",
    "FakeRenderer",
    "InlinePromptProvider",
    "StaticAgentConfig",
    "analysis_json",
    "code_json",
    "design_json",
    "make_fake_deps",
    "make_fake_tool",
    "question_plan_json",
    "quiz_pair_json",
    "react_final",
    "react_tool_decision",
    "research_report",
    "research_worker_json",
    "summary_json",
    "tool_call",
]
