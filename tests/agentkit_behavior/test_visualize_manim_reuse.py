"""visualize reuses the math_animator orchestration for manim modes (AC #3)."""

from __future__ import annotations

import pytest

from agentkit import build_visualize_graph, make_checkpointer
from agentkit.runtime.stream import StreamEventType
from agentkit.testing import analysis_json, code_json, design_json, make_fake_deps, summary_json


@pytest.mark.asyncio
async def test_visualize_manim_video_reuses_math_animator(collect_events) -> None:
    # analysis short-circuits for a pinned manim mode (no LLM), then the manim node
    # drives the full math_animator subgraph — which needs its four agent scripts.
    scripts = {
        "concept_analysis": [analysis_json()],
        "concept_design": [design_json()],
        "code_generator": [code_json("v1")],
        "summary": [summary_json()],
    }
    deps = make_fake_deps(llm_scripts=scripts)
    graph = build_visualize_graph(checkpointer=make_checkpointer())
    events, final = await collect_events(
        graph,
        {"user_input": "animate the unit circle", "render_mode": "manim_video", "quality": "low", "language": "en"},
        deps=deps,
        source="visualize",
    )

    assert final["status"] == "succeeded"
    envelope = final["manim_result"]
    assert envelope["render_type"] == "manim_video"  # frontend discriminator stamped
    assert envelope["status"] == "succeeded"
    assert envelope["render_result"]["artifacts"]
    assert envelope["summary"]["summary_text"]

    # The reused math_animator subgraph actually ran its agents.
    assert deps.llm.calls == ["concept_analysis", "concept_design", "code_generator", "summary"]
    # analysis agent did NOT run (short-circuit for pinned manim mode).
    assert "analysis" not in deps.llm.calls

    # The subgraph's stages surface in the parent stream (custom events propagate).
    stages = {e.stage for e in events if e.type == StreamEventType.STAGE_START}
    assert {"concept_analysis", "render", "summary"} <= stages
