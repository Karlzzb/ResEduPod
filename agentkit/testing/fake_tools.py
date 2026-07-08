"""Scripted tools + canned JSON payloads for the ReAct / question behavior tests.

Mirrors ``fake_deps.py``: no network, deterministic.  ``make_fake_tool`` builds a
:class:`~agentkit.tools.Tool` whose async handler optionally appends to a shared
``record`` list, letting a test assert both *that* a tool ran and the concurrency /
order of a parallel batch.  The JSON helpers produce exactly the shapes the ReAct
LLM node and the ``question`` phases expect, so ``FakeLLM`` scripts stay readable.
"""

from __future__ import annotations

import json
from typing import Any

from agentkit.tools import Tool


def make_fake_tool(name: str, *, result: str = "ok", record: list[str] | None = None) -> Tool:
    """A :class:`Tool` that returns ``f"{name}:{result}"`` and logs its name to ``record``."""

    async def _handler(arguments: dict[str, Any]) -> str:
        if record is not None:
            record.append(name)
        return f"{name}:{result}"

    return Tool(
        name=name,
        description=f"Fake tool {name}",
        handler=_handler,
        parameters={"type": "object", "properties": {}},
    )


def react_tool_decision(tool_calls: list[dict[str, Any]], *, content: str = "") -> str:
    """A scripted LLM ``action=tool`` decision for the ReAct loop."""
    return json.dumps({"action": "tool", "content": content, "tool_calls": tool_calls})


def react_final(content: str) -> str:
    """A scripted LLM ``action=final`` decision for the ReAct loop."""
    return json.dumps({"action": "final", "content": content})


def tool_call(name: str, *, call_id: str | None = None, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """One tool-call entry for :func:`react_tool_decision`."""
    return {"id": call_id or f"call_{name}", "name": name, "arguments": arguments or {}}


def question_plan_json(templates: list[dict[str, str]], *, analysis: str = "plan analysis") -> str:
    """A scripted ``question_plan`` payload."""
    return json.dumps({"analysis": analysis, "templates": templates})


def quiz_pair_json(
    question_id: str,
    *,
    question: str = "What is 2 + 2?",
    question_type: str = "short_answer",
    correct_answer: str = "4",
    explanation: str = "Because arithmetic.",
    topic: str = "math",
    difficulty: str = "easy",
) -> str:
    """A scripted quiz-loop FINISH payload (the strict per-question JSON)."""
    return json.dumps(
        {
            "question_id": question_id,
            "question": question,
            "question_type": question_type,
            "correct_answer": correct_answer,
            "explanation": explanation,
            "options": None,
            "topic": topic,
            "difficulty": difficulty,
        }
    )


__all__ = [
    "make_fake_tool",
    "question_plan_json",
    "quiz_pair_json",
    "react_final",
    "react_tool_decision",
    "tool_call",
]
