"""Chat robustness (issue #3): thinking-tag filtering on the ReAct template.

Scripts a ``final`` decision whose ``content`` embeds a ``<think>`` scratchpad and
asserts it is scrubbed from ``final_text`` (never leaks to the user) while the
reasoning still surfaces on the THINKING stream, not the CONTENT stream
(AC: thinking 标签不泄漏到最终输出).
"""

from __future__ import annotations

import json

import pytest

from agentkit import build_react_orchestration_graph
from agentkit.runtime.stream import StreamEventType
from agentkit.testing import make_fake_deps


def _final_with_think(reasoning: str, answer: str) -> str:
    return json.dumps(
        {"action": "final", "content": f"<think>{reasoning}</think>{answer}"}
    )


@pytest.mark.asyncio
async def test_thinking_tags_stripped_from_final_text(collect_events) -> None:
    deps = make_fake_deps(
        llm_scripts={"react": [_final_with_think("secret plan", "The answer is 42.")]}
    )
    graph = build_react_orchestration_graph(agent_name="react", system_prompt="Answer.")
    events, final = await collect_events(graph, {"input": "hi"}, deps=deps, source="react")

    # The scratchpad never reaches the user-facing answer.
    assert final["final_text"] == "The answer is 42."
    assert "<think>" not in final["final_text"]
    assert "secret plan" not in final["final_text"]

    # The persisted assistant message is likewise clean.
    assistant = [m for m in final["messages"] if m.get("role") == "assistant"][-1]
    assert assistant["content"] == "The answer is 42."

    # The reasoning surfaced on the THINKING stream, tagged reasoning=True,
    # and never on a CONTENT event.
    thinking = [
        e for e in events
        if e.type == StreamEventType.THINKING and e.metadata.get("reasoning")
    ]
    assert thinking, "the <think> scratchpad must stream as reasoning"
    assert "secret plan" in "".join(e.content for e in thinking)
    contents = [e.content for e in events if e.type == StreamEventType.CONTENT]
    assert "secret plan" not in "".join(contents)


@pytest.mark.asyncio
async def test_unclosed_thinking_block_scrubbed(collect_events) -> None:
    # A stream cut off mid-reasoning must never expose the partial scratchpad.
    deps = make_fake_deps(
        llm_scripts={
            "react": [json.dumps({"action": "final", "content": "ok<think>leaking"})]
        }
    )
    graph = build_react_orchestration_graph(agent_name="react", system_prompt="x")
    _events, final = await collect_events(graph, {"input": "hi"}, deps=deps, source="react")
    assert final["final_text"] == "ok"
    assert "leaking" not in final["final_text"]
