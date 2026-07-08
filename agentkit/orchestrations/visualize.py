"""``visualize`` Orchestration — text render path + reuse of the math_animator graph.

Graph shape::

    analyzing ─ route_render_type ─┬─ "text"  → generating → reviewing → END
                                   └─ "manim" → manim → END

The ``manim`` node reuses the compiled ``math_animator`` orchestration verbatim
(mapping ``VisualizeState`` → ``MathAnimatorState`` and back, propagating the same
``config`` so ``deps`` flow through), mirroring the pre-fork
``VisualizeCapability._run_manim_path``.  The text path ports the deterministic
``validate_visualization`` gate + single targeted repair + HTML fallback.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

from agentkit.agents.contract import emit
from agentkit.agents.visualize import analysis_node, codegen_node, review
from agentkit.orchestrations.math_animator import build_math_animator_graph
from agentkit.state.math_animator import MathAnimatorState
from agentkit.state.visualize import VisualizeState
from agentkit.utils import build_fallback_html, validate_visualization

_MANIM_MODES = {"manim_video", "manim_image"}


@lru_cache(maxsize=1)
def _manim_graph() -> Any:
    # Reused inline; the parent orchestration owns checkpointing, so the nested
    # graph runs without its own checkpointer.
    return build_math_animator_graph()


def route_render_type(state: VisualizeState) -> str:
    return "manim" if state.get("render_type") in _MANIM_MODES else "text"


async def manim_node(state: VisualizeState, config: RunnableConfig) -> dict[str, Any]:
    """Reuse the math_animator orchestration for the manim render types.

    The child is driven with ``astream`` (not ``ainvoke``) so its native custom
    events can be re-emitted through this node's own ``get_stream_writer``; a bare
    ``ainvoke`` would swallow them, since LangGraph does not bubble a nested graph's
    custom stream up to the parent.  The final child State is accumulated from the
    ``updates`` chunks.
    """
    render_type = state.get("render_type", "manim_video")
    output_mode = "image" if render_type == "manim_image" else "video"
    sub_input: MathAnimatorState = {
        "user_input": state.get("user_input", ""),
        "history_context": state.get("history_context", ""),
        "output_mode": output_mode,
        "quality": state.get("quality", "medium"),
        "style_hint": state.get("style_hint", ""),
        "turn_id": state.get("turn_id", "visualize"),
        "language": state.get("language", "zh"),
    }
    writer = get_stream_writer()
    final: dict[str, Any] = {}
    async for mode, chunk in _manim_graph().astream(
        sub_input, config=config, stream_mode=["custom", "updates"]
    ):
        if mode == "custom":
            writer(chunk)  # re-emit the child's stage/progress events into the parent stream
        elif mode == "updates":
            for delta in chunk.values():
                if isinstance(delta, dict):
                    final.update(delta)
    envelope = dict(final)
    envelope["render_type"] = render_type  # frontend discriminator (parity with old capability)
    status = final.get("status", "succeeded")
    return {"manim_result": envelope, "status": status, "error": final.get("error", "")}


async def reviewing_node(state: VisualizeState, config: RunnableConfig) -> dict[str, Any]:
    """Deterministic validation → ship, HTML fallback, or one targeted repair."""
    render_type = state.get("render_type", "svg")
    code = state.get("code", "")
    ok, error = validate_visualization(code, render_type)
    if ok:
        return {"status": "succeeded", "review": {"changed": False, "review_notes": "passed local validation"}}

    if render_type == "html":
        fallback = build_fallback_html(title="Visualization", summary=state.get("user_input", ""), note=error)
        emit("content", stage="reviewing", agent="viz_review", content="Used fallback HTML.")
        return {"code": fallback, "status": "succeeded", "review": {"changed": True, "review_notes": f"fallback: {error}"}}

    # svg / chartjs / mermaid → one targeted repair, then re-validate.
    result = await review.repair(state, config, error=error)
    repaired_code = result.optimized_code or code
    ok_again, _ = validate_visualization(repaired_code, render_type)
    return {
        "code": repaired_code,
        "status": "succeeded" if ok_again else "failed",
        "error": "" if ok_again else f"validation still failing: {error}",
        "review": result.model_dump(),
    }


def build_visualize_graph(*, checkpointer: Any | None = None) -> Any:
    """Compile the ``visualize`` orchestration graph."""
    graph = StateGraph(VisualizeState)
    graph.add_node("analyzing", analysis_node)
    graph.add_node("generating", codegen_node)
    graph.add_node("reviewing", reviewing_node)
    graph.add_node("manim", manim_node)

    graph.add_edge(START, "analyzing")
    graph.add_conditional_edges("analyzing", route_render_type, {"manim": "manim", "text": "generating"})
    graph.add_edge("generating", "reviewing")
    graph.add_edge("reviewing", END)
    graph.add_edge("manim", END)
    return graph.compile(checkpointer=checkpointer)


__all__ = ["build_visualize_graph", "manim_node", "reviewing_node", "route_render_type"]
