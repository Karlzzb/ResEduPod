"""Main-seam happy path: linear pipeline, no retries (AC #2 / #3 / #6)."""

from __future__ import annotations

import pytest

from agentkit import build_math_animator_graph, make_checkpointer
from agentkit.runtime.stream import StreamEventType
from agentkit.testing import analysis_json, code_json, design_json, make_fake_deps, summary_json


def _happy_scripts() -> dict[str, list[str]]:
    return {
        "concept_analysis": [analysis_json()],
        "concept_design": [design_json()],
        "code_generator": [code_json("v1")],
        "summary": [summary_json()],
    }


@pytest.mark.asyncio
async def test_math_animator_happy_path_events_and_state(collect_events) -> None:
    deps = make_fake_deps(llm_scripts=_happy_scripts())
    graph = build_math_animator_graph(checkpointer=make_checkpointer())
    events, final = await collect_events(
        graph,
        {"user_input": "animate the unit circle", "output_mode": "video", "quality": "low", "language": "en"},
        deps=deps,
        source="math_animator",
    )

    # Final State
    assert final["status"] == "succeeded"
    assert final["retry_count"] == 0
    assert final["render_result"]["artifacts"], "a render artifact must be produced"
    assert final["summary"]["summary_text"] == "Here is your unit circle animation."
    assert final["analysis"]["learning_goal"] == "Show the unit circle"

    # LLM call order: exactly the four pipeline agents, no repair.
    assert deps.llm.calls == ["concept_analysis", "concept_design", "code_generator", "summary"]

    # Stage ordering: each pipeline stage opens before the next.
    stage_starts = [e.stage for e in events if e.type == StreamEventType.STAGE_START]
    assert stage_starts == ["concept_analysis", "concept_design", "code_generation", "render", "summary"]

    # A final user-facing summary content event is emitted.
    contents = [e.content for e in events if e.type == StreamEventType.CONTENT]
    assert any("unit circle animation" in c for c in contents)
