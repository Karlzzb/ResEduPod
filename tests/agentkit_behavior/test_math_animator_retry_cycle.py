"""Visible retry cycle: inject one render failure → repair → success (AC #4)."""

from __future__ import annotations

import pytest

from agentkit import build_math_animator_graph, make_checkpointer
from agentkit.testing import analysis_json, code_json, design_json, make_fake_deps, summary_json


@pytest.mark.asyncio
async def test_retry_cycle_triggers_repair_then_succeeds(collect_events) -> None:
    # One retryable render failure, then success. The repair agent needs a
    # scripted response for its extra code_generator call.
    scripts = {
        "concept_analysis": [analysis_json()],
        "concept_design": [design_json()],
        "code_generator": [code_json("v1"), code_json("repaired")],  # generate + one repair
        "summary": [summary_json()],
    }
    deps = make_fake_deps(llm_scripts=scripts, render_fail_times=1)
    graph = build_math_animator_graph(checkpointer=make_checkpointer())
    events, final = await collect_events(
        graph,
        {"user_input": "unit circle", "output_mode": "video", "quality": "low", "language": "en"},
        deps=deps,
        source="math_animator",
    )

    # The visible cycle fired exactly once: one repair, retry_count == 1.
    assert final["status"] == "succeeded"
    assert final["retry_count"] == 1
    assert len(final["retry_history"]) == 1
    assert final["retry_history"][0]["attempt"] == 1

    # code_generator was called twice (generate + repair); render ran twice.
    assert deps.llm.calls.count("code_generator") == 2
    assert deps.renderer.calls == 2

    # The repaired code (marker) is what finally succeeded.
    assert "repaired" in final["code"]

    # A code_retry stage was opened (the visible loop is observable in the stream).
    assert any(e.stage == "code_retry" for e in events)


@pytest.mark.asyncio
async def test_retry_exhaustion_hits_gate_and_fails(collect_events) -> None:
    # Fail more times than max_retries -> the gate routes to fail收尾.
    scripts = {
        "concept_analysis": [analysis_json()],
        "concept_design": [design_json()],
        # 1 generate + up to max_retries repairs.
        "code_generator": [code_json(f"v{i}") for i in range(6)],
    }
    deps = make_fake_deps(llm_scripts=scripts, render_fail_times=99)
    graph = build_math_animator_graph(checkpointer=make_checkpointer(), max_retries=2)
    _events, final = await collect_events(
        graph,
        {"user_input": "unit circle", "output_mode": "video", "quality": "low",
         "language": "en", "max_retries": 2},
        deps=deps,
        source="math_animator",
    )

    assert final["status"] == "failed"
    # gate at max_retries=2: render attempts = initial + 2 retries = 3.
    assert deps.renderer.calls == 3
    assert final["retry_count"] == 2
