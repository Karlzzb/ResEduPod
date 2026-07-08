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
    summary_json,
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
    "summary_json",
]
