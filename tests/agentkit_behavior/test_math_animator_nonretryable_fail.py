"""Non-retryable environment error (missing LaTeX) routes straight to fail (AC #3)."""

from __future__ import annotations

import pytest

from agentkit import build_math_animator_graph, make_checkpointer
from agentkit.runtime.stream import StreamEventType
from agentkit.testing import analysis_json, code_json, design_json, make_fake_deps


@pytest.mark.asyncio
async def test_missing_latex_is_non_retryable(collect_events) -> None:
    scripts = {
        "concept_analysis": [analysis_json()],
        "concept_design": [design_json()],
        "code_generator": [code_json("v1")],  # no repair should ever be attempted
    }
    deps = make_fake_deps(llm_scripts=scripts, render_fail_times=1, latex_missing=True)
    graph = build_math_animator_graph(checkpointer=make_checkpointer())
    events, final = await collect_events(
        graph,
        {"user_input": "unit circle", "output_mode": "video", "quality": "low", "language": "en"},
        deps=deps,
        source="math_animator",
    )

    assert final["status"] == "failed"
    assert final["retry_count"] == 0  # gate never engaged; no repair attempted
    assert "LaTeX" in final["error"]
    assert deps.renderer.calls == 1  # rendered once, then straight to fail
    assert deps.llm.calls.count("code_generator") == 1  # no repair call

    # A terminal ERROR event is emitted.
    assert any(e.type == StreamEventType.ERROR for e in events)
