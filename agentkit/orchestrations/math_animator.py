"""``math_animator`` Orchestration — a linear pipeline with a VISIBLE retry cycle.

Graph shape (ADR-0008 pipeline archetype, ADR-0005 visible loop)::

    concept_analysis → concept_design → code_generation → render ─┐
                                                                   │ route_after_render
                          ┌──────────── code_repair ◄── "repair" ──┤
                          │  (loops back to render)                ├── "summary" → END
                          └──────────────► render                  └── "fail"    → END

``render`` is the checkpoint boundary (ADR-0005): it is the slowest, most
crash-prone step, so a crash resumes from the last checkpoint rather than the top
of the pipeline.  The self-healing retry loop from
``deeptutor/agents/math_animator/retry_manager.py`` is expressed here as an
explicit conditional cycle instead of a black-box callback loop:

* a retryable render error → ``code_repair`` (which increments ``retry_count``)
  → back to ``render``;
* ``retry_count >= max_retries`` → ``fail`` (the ADR-0005 gate);
* a non-retryable environment error (missing LaTeX) → straight to ``fail``;
* success (and a passing visual review, when enabled) → ``summary``.
"""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from agentkit.agents.contract import emit
from agentkit.agents.math_animator import (
    code_generation_node,
    code_repair_node,
    concept_analysis_node,
    concept_design_node,
    summary_node,
)
from agentkit.deps import get_deps
from agentkit.models.math_animator import RenderResult
from agentkit.renderer.manim import ManimRenderError, _is_non_retriable_environment_error
from agentkit.state.math_animator import DEFAULT_MAX_RETRIES, MathAnimatorState

_LATEX_GUIDANCE = (
    "Render failed because local LaTeX is missing. Please avoid Tex/MathTex in "
    "generated code or install a LaTeX distribution."
)


async def render_node(state: MathAnimatorState, config: RunnableConfig) -> dict[str, Any]:
    """Checkpoint boundary.  Calls the injected renderer; records outcome for the router.

    Retryable ``ManimRenderError``s are recorded into ``last_error`` (the router
    decides whether to loop or give up — keeping the loop visible).  A
    non-retryable environment error short-circuits to ``failed``.  Any other
    exception (e.g. a killed subprocess) propagates uncaught so LangGraph leaves a
    resumable checkpoint at this node (ADR-0005 / durable execution).
    """
    deps = get_deps(config)
    if deps.renderer is None:
        raise RuntimeError("math_animator requires deps.renderer (inject a Renderer)")
    attempt = state.get("retry_count", 0)
    emit("stage_start", stage="render", agent="render", attempt=attempt)
    try:
        result = await deps.renderer.render(
            code=state.get("code", ""),
            output_mode=state.get("output_mode", "video"),
            quality=state.get("quality", "medium"),
            turn_id=state.get("turn_id", "math-animator"),
        )
    except ManimRenderError as exc:
        message = str(exc)
        if _is_non_retriable_environment_error(message):
            emit("stage_end", stage="render", agent="render")
            return {"status": "failed", "error": _LATEX_GUIDANCE, "last_error": message, "render_result": None}
        emit("stage_end", stage="render", agent="render", error=message)
        return {"last_error": message, "render_result": None}
    if not isinstance(result, RenderResult):  # defensive: a fake may hand back a dict
        result = RenderResult.model_validate(result)
    emit("stage_end", stage="render", agent="render")
    return {"render_result": result.model_dump(), "last_error": ""}


def route_after_render(state: MathAnimatorState, *, max_retries: int = DEFAULT_MAX_RETRIES) -> str:
    """The ADR-0005 gate: decide summary / repair / fail after a render attempt.

    The retry ceiling is ``state["max_retries"]`` when the caller supplies it,
    otherwise the graph's build-time ``max_retries`` default.
    """
    if state.get("status") == "failed":  # non-retryable env error already flagged
        return "fail"
    last_error = state.get("last_error") or ""
    render_result = state.get("render_result") or {}
    review = render_result.get("visual_review") if isinstance(render_result, dict) else None
    review_failed = isinstance(review, dict) and review.get("passed") is False
    if not last_error and not review_failed:
        return "summary"
    limit = state.get("max_retries", max_retries)
    if state.get("retry_count", 0) >= limit:
        return "fail"
    return "repair"


async def fail_node(state: MathAnimatorState, config: RunnableConfig) -> dict[str, Any]:
    """Terminal failure收尾: emit the error and mark the run failed."""
    message = state.get("error") or state.get("last_error") or "Render failed after all retries."
    emit("error", stage="fail", agent="math_animator", content=message)
    return {"status": "failed", "error": message}


def build_math_animator_graph(*, checkpointer: Any | None = None, max_retries: int = DEFAULT_MAX_RETRIES) -> Any:
    """Compile the ``math_animator`` orchestration graph."""

    def _route(state: MathAnimatorState) -> str:
        return route_after_render(state, max_retries=max_retries)

    graph = StateGraph(MathAnimatorState)
    graph.add_node("concept_analysis", concept_analysis_node)
    graph.add_node("concept_design", concept_design_node)
    graph.add_node("code_generation", code_generation_node)
    graph.add_node("render", render_node)
    graph.add_node("code_repair", code_repair_node)
    graph.add_node("summary", summary_node)
    graph.add_node("fail", fail_node)

    graph.add_edge(START, "concept_analysis")
    graph.add_edge("concept_analysis", "concept_design")
    graph.add_edge("concept_design", "code_generation")
    graph.add_edge("code_generation", "render")
    graph.add_conditional_edges(
        "render",
        _route,
        {"repair": "code_repair", "summary": "summary", "fail": "fail"},
    )
    graph.add_edge("code_repair", "render")  # the visible cycle back to render
    graph.add_edge("summary", END)
    graph.add_edge("fail", END)
    return graph.compile(checkpointer=checkpointer)


__all__ = ["build_math_animator_graph", "fail_node", "render_node", "route_after_render"]
