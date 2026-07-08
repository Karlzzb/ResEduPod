"""Checkpointer resume after a render crash (AC #5).

``render`` is a checkpoint boundary (ADR-0005).  When the render subprocess is
killed (a non-``ManimRenderError`` crash), the exception propagates uncaught and
LangGraph leaves a resumable checkpoint at ``render`` with the upstream stages'
State preserved.  Re-invoking on the same ``thread_id`` resumes from that
checkpoint: ``render`` re-runs, but ``concept_analysis`` / ``concept_design`` /
``code_generation`` do NOT.
"""

from __future__ import annotations

import pytest

from agentkit import build_math_animator_graph, make_checkpointer
from agentkit.testing import analysis_json, code_json, design_json, make_fake_deps, summary_json


@pytest.mark.asyncio
async def test_render_crash_resumes_from_checkpoint() -> None:
    scripts = {
        "concept_analysis": [analysis_json()],
        "concept_design": [design_json()],
        "code_generator": [code_json("v1")],
        "summary": [summary_json()],
    }
    # crash_times=1: the FIRST render raises a plain RuntimeError (killed subprocess);
    # the second (on resume) succeeds.
    deps = make_fake_deps(llm_scripts=scripts, crash_times=1)
    checkpointer = make_checkpointer()  # shared instance across both invocations
    graph = build_math_animator_graph(checkpointer=checkpointer)
    config = {"configurable": {"deps": deps, "thread_id": "resume-1"}}

    # First invocation crashes inside render.
    with pytest.raises(RuntimeError, match="subprocess killed"):
        await graph.ainvoke(
            {"user_input": "unit circle", "output_mode": "video", "quality": "low", "language": "en"},
            config=config,
        )

    # Upstream stages ran exactly once; the crash left a checkpoint at render.
    assert deps.llm.calls == ["concept_analysis", "concept_design", "code_generator"]
    snapshot = await graph.aget_state(config)
    assert snapshot.next == ("render",), "must resume at the render node"
    preserved_code = snapshot.values["code"]
    preserved_analysis = snapshot.values["analysis"]
    assert preserved_code and preserved_analysis

    # Resume: re-invoke with None input on the same thread.
    final = await graph.ainvoke(None, config=config)

    # State preserved across the crash: upstream never re-ran.
    assert deps.llm.calls == ["concept_analysis", "concept_design", "code_generator", "summary"]
    assert final["code"] == preserved_code
    assert final["analysis"] == preserved_analysis
    assert final["status"] == "succeeded"
    assert deps.renderer.calls == 2  # crashed once, succeeded on resume
