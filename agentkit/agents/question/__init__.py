"""``question`` Agent leaves and inline prompts."""

from __future__ import annotations

from agentkit.agents.question.plan import plan_node
from agentkit.agents.question.prompts import (
    EXPLORE_SYSTEM,
    PLAN_SYSTEM,
    PLAN_USER_TEMPLATE,
    QUIZ_SYSTEM,
    QUIZ_USER_TEMPLATE,
)

__all__ = [
    "EXPLORE_SYSTEM",
    "PLAN_SYSTEM",
    "PLAN_USER_TEMPLATE",
    "QUIZ_SYSTEM",
    "QUIZ_USER_TEMPLATE",
    "plan_node",
]
