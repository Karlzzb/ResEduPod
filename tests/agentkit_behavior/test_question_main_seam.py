"""``question`` main seam: explore → plan → quiz on the ReActOrchestration template.

Drives the full three-phase graph with ``FakeDeps``, asserting the phase products,
the LLM call order across phases, and the event sequence (issue #2 acceptance:
``question`` 走通模板主 seam).
"""

from __future__ import annotations

import pytest

from agentkit import build_question_graph, make_checkpointer
from agentkit.runtime.stream import StreamEventType
from agentkit.testing import (
    make_fake_deps,
    make_fake_tool,
    question_plan_json,
    quiz_pair_json,
    react_final,
    react_tool_decision,
    tool_call,
)


def _scripts() -> dict[str, list[str]]:
    templates = [
        {"question_id": "q1", "topic": "algebra", "question_type": "short_answer", "difficulty": "easy"},
        {"question_id": "q2", "topic": "geometry", "question_type": "true_false", "difficulty": "medium"},
    ]
    return {
        # Explore ReAct loop: one tool round, then a briefing.
        "question_explore": [
            react_tool_decision([tool_call("lookup", arguments={"topic": "math"})], content="scan"),
            react_final("Learner wants a short algebra + geometry quiz."),
        ],
        # Plan step: a two-question plan.
        "question_plan": [question_plan_json(templates)],
        # Quiz ReAct loop: one direct answer per template (2 templates → 2 calls).
        # The strict quiz JSON rides inside the ReAct "final" action's content.
        "question_quiz": [
            react_final(
                quiz_pair_json("q1", question="What is x if x+2=4?", correct_answer="2", topic="algebra")
            ),
            react_final(
                quiz_pair_json(
                    "q2",
                    question="A triangle has 3 sides.",
                    question_type="true_false",
                    correct_answer="true",
                    topic="geometry",
                    difficulty="medium",
                )
            ),
        ],
    }


@pytest.mark.asyncio
async def test_question_full_three_phase(collect_events) -> None:
    deps = make_fake_deps(llm_scripts=_scripts())
    graph = build_question_graph(
        tools=[make_fake_tool("lookup")], checkpointer=make_checkpointer()
    )
    events, final = await collect_events(
        graph, {"user_input": "quiz me on basic math", "language": "en"}, deps=deps, source="question"
    )

    # Phase products.
    assert final["status"] == "succeeded"
    assert "algebra" in final["exploration"]
    assert len(final["plan"]["templates"]) == 2
    pairs = final["quiz_pairs"]
    assert [p["question_id"] for p in pairs] == ["q1", "q2"]
    assert pairs[0]["correct_answer"] == "2"
    assert pairs[1]["question_type"] == "true_false"

    # LLM call order across phases: explore(2) → plan(1) → quiz(1 per template).
    assert deps.llm.calls == [
        "question_explore",
        "question_explore",
        "question_plan",
        "question_quiz",
        "question_quiz",
    ]

    # The three phases opened in order (explore/plan/quiz stage_start events from the
    # parent orchestration nodes).
    phase_stages = [
        e.stage
        for e in events
        if e.type == StreamEventType.STAGE_START and e.stage in {"explore", "plan", "quiz"}
    ]
    assert phase_stages == ["explore", "plan", "quiz", "quiz"]


@pytest.mark.asyncio
async def test_question_events_json_serializable(collect_events) -> None:
    import json

    deps = make_fake_deps(llm_scripts=_scripts())
    graph = build_question_graph(tools=[make_fake_tool("lookup")])
    events, _final = await collect_events(
        graph, {"user_input": "quiz me", "language": "en"}, deps=deps, source="question"
    )
    for event in events:
        json.dumps(event.to_dict())  # hard constraint: every event must serialize
