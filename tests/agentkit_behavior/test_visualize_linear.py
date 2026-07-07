"""visualize text render path (svg) — no manim node visited (AC #3)."""

from __future__ import annotations

import json

import pytest

from agentkit import build_visualize_graph, make_checkpointer
from agentkit.runtime.stream import StreamEventType
from agentkit.testing import make_fake_deps

_SVG = '<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg"><circle cx="50" cy="50" r="40"/></svg>'


def _analysis_svg() -> str:
    return json.dumps(
        {
            "render_type": "svg",
            "description": "a circle",
            "visual_elements": ["circle"],
            "rationale": "simple shape",
        }
    )


@pytest.mark.asyncio
async def test_visualize_svg_linear_path(collect_events) -> None:
    scripts = {
        "analysis": [_analysis_svg()],
        "viz_code_generator": [f"```svg\n{_SVG}\n```"],
    }
    deps = make_fake_deps(llm_scripts=scripts)
    graph = build_visualize_graph(checkpointer=make_checkpointer())
    events, final = await collect_events(
        graph,
        {"user_input": "draw a circle", "render_mode": "svg", "language": "en"},
        deps=deps,
        source="visualize",
    )

    assert final["render_type"] == "svg"
    assert final["status"] == "succeeded"
    assert "<svg" in final["code"] and "viewBox" in final["code"]
    # local validation passed → no repair LLM call, manim never entered.
    assert "viz_review" not in deps.llm.calls
    assert final.get("manim_result") is None
    stages = [e.stage for e in events if e.type == StreamEventType.STAGE_START]
    assert "analyzing" in stages and "generating" in stages
    assert "concept_analysis" not in stages  # manim subgraph not run
