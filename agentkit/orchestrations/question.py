"""``question`` Orchestration — the first ``ReActOrchestration`` instantiation.

Graph shape (ADR-0008: three phases stacked on the loop template)::

    START → explore → plan → quiz → END

``explore`` and ``quiz`` each *reuse* the ``ReActOrchestration`` template as a
nested subgraph (the reuse pattern from ``visualize.manim_node``): a subgraph is
driven with ``astream(stream_mode=["custom","updates"])`` so its native custom
events bubble up through this node's ``get_stream_writer``, and its final ``State``
is accumulated from the ``updates`` chunks.  ``plan`` is a single ``llm_json`` node
(no tools) between the two loops.

This ports ``deeptutor/agents/question/pipeline.py``'s ``QuestionPipeline`` (explore
loop → plan step → per-template quiz loop) onto LangGraph, self-contained and
scriptable with ``FakeDeps``.
"""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

from agentkit.agents.contract import emit
from agentkit.agents.question import plan_node
from agentkit.agents.question.prompts import EXPLORE_SYSTEM, QUIZ_SYSTEM, QUIZ_USER_TEMPLATE
from agentkit.models.question import QuizPair, QuizPlan
from agentkit.orchestrations.react import build_react_orchestration_graph
from agentkit.state.question import (
    DEFAULT_MAX_EXPLORE_ITERATIONS,
    DEFAULT_MAX_QUIZ_ITERATIONS,
    QuestionState,
)
from agentkit.state.react import ReActState
from agentkit.tools import Tool
from agentkit.utils import extract_json_object


async def _run_react_subgraph(
    graph: Any, input_state: ReActState, config: RunnableConfig
) -> dict[str, Any]:
    """Drive a ReAct subgraph, re-emitting its events, and return its final State."""
    writer = get_stream_writer()
    final: dict[str, Any] = {}
    async for mode, chunk in graph.astream(
        input_state, config=config, stream_mode=["custom", "updates"]
    ):
        if mode == "custom":
            writer(chunk)  # bubble the child's stage/tool/content events into the parent
        elif mode == "updates":
            for delta in chunk.values():
                if isinstance(delta, dict):
                    final.update(delta)
    return final


def build_question_graph(
    *,
    tools: list[Tool] | None = None,
    max_explore_iterations: int = DEFAULT_MAX_EXPLORE_ITERATIONS,
    max_quiz_iterations: int = DEFAULT_MAX_QUIZ_ITERATIONS,
    checkpointer: Any | None = None,
) -> Any:
    """Compile the ``question`` orchestration graph.

    ``tools`` are the ``owned_tools`` shared by the explore and quiz ReAct loops.
    """
    owned_tools = list(tools or [])
    explore_graph = build_react_orchestration_graph(
        tools=owned_tools,
        agent_name="question_explore",
        system_prompt=EXPLORE_SYSTEM,
        max_iterations=max_explore_iterations,
    )
    quiz_graph = build_react_orchestration_graph(
        tools=owned_tools,
        agent_name="question_quiz",
        system_prompt=QUIZ_SYSTEM,
        max_iterations=max_quiz_iterations,
    )

    async def explore_node(state: QuestionState, config: RunnableConfig) -> dict[str, Any]:
        emit("stage_start", stage="explore", agent="question")
        sub_input: ReActState = {
            "input": (state.get("user_input", "") or "").strip(),
            "language": state.get("language", "zh"),
        }
        final = await _run_react_subgraph(explore_graph, sub_input, config)
        emit("stage_end", stage="explore", agent="question")
        return {"exploration": final.get("final_text", ""), "status": "running"}

    async def quiz_node(state: QuestionState, config: RunnableConfig) -> dict[str, Any]:
        plan = QuizPlan.model_validate(state.get("plan") or {})
        exploration = state.get("exploration", "") or "(none)"
        pairs: list[dict[str, Any]] = []
        for template in plan.templates:
            emit("stage_start", stage="quiz", agent="question", question_id=template.question_id)
            user = QUIZ_USER_TEMPLATE.format(
                question_id=template.question_id,
                topic=template.topic,
                question_type=template.question_type,
                difficulty=template.difficulty,
                exploration=exploration,
            )
            sub_input: ReActState = {
                "input": user,
                "language": state.get("language", "zh"),
            }
            final = await _run_react_subgraph(quiz_graph, sub_input, config)
            pairs.append(_parse_quiz_pair(final.get("final_text", ""), template))
            emit("stage_end", stage="quiz", agent="question", question_id=template.question_id)
        return {"quiz_pairs": pairs, "status": "succeeded"}

    graph = StateGraph(QuestionState)
    graph.add_node("explore", explore_node)
    graph.add_node("plan", plan_node)
    graph.add_node("quiz", quiz_node)

    graph.add_edge(START, "explore")
    graph.add_edge("explore", "plan")
    graph.add_edge("plan", "quiz")
    graph.add_edge("quiz", END)
    return graph.compile(checkpointer=checkpointer)


def _parse_quiz_pair(final_text: str, template: Any) -> dict[str, Any]:
    """Parse one quiz loop's FINISH text into a ``QuizPair`` dict, tolerating noise.

    A malformed payload degrades to a placeholder pair carrying the raw text rather
    than aborting the whole quiz phase (the pre-fork one-shot-repair intent, reduced
    to a safe fallback here).
    """
    try:
        payload = extract_json_object(final_text)
    except Exception:
        payload = {}
    payload.setdefault("question_id", template.question_id)
    payload.setdefault("question_type", template.question_type)
    payload.setdefault("topic", template.topic)
    payload.setdefault("difficulty", template.difficulty)
    if not payload.get("question"):
        payload["question"] = (final_text or "").strip()
        payload.setdefault("correct_answer", "")
    try:
        return QuizPair.model_validate(payload).model_dump()
    except Exception:
        return QuizPair(
            question_id=template.question_id,
            question=(final_text or "").strip(),
            question_type=template.question_type,
            correct_answer="",
            topic=template.topic,
            difficulty=template.difficulty,
        ).model_dump()


__all__ = ["build_question_graph"]
