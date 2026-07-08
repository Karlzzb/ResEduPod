"""``summary`` Agent leaf — produces the closing summary after a successful render.

Ported from ``deeptutor/agents/math_animator/agents/summary_agent.py``.
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.runnables import RunnableConfig

from agentkit.agents.contract import emit, llm_json
from agentkit.deps import get_deps, resolve_prompt
from agentkit.models.math_animator import SummaryPayload
from agentkit.state.math_animator import MathAnimatorState

AGENT = "summary"
STAGE = "summary"

_SYSTEM = (
    "You are the summarizer for a math animation capability. Given the analysis, design, "
    "and render result, write a short user-facing summary of what was produced and the key "
    "teaching points. Be concise and encouraging."
)

_USER_TEMPLATE = (
    "User request:\n{user_input}\n\n"
    "Output mode: {output_mode}\n\n"
    "Concept analysis:\n{analysis_json}\n\n"
    "Scene design:\n{design_json}\n\n"
    "Render result:\n{render_json}\n\n"
    "Return JSON:\n"
    "{{\n"
    '  "summary_text": "user-facing summary",\n'
    '  "user_request": "restate the request",\n'
    '  "generated_output": "what was generated (video/image)",\n'
    '  "key_points": ["takeaway 1", "takeaway 2"]\n'
    "}}"
)

DEFAULT_PROMPTS: dict[str, dict[str, str]] = {
    "en": {"system": _SYSTEM, "user_template": _USER_TEMPLATE},
    "zh": {"system": _SYSTEM, "user_template": _USER_TEMPLATE},
}


async def summary_node(state: MathAnimatorState, config: RunnableConfig) -> dict[str, Any]:
    deps = get_deps(config)
    lang = state.get("language", "zh")
    system = resolve_prompt(deps, agent=AGENT, key="system", language=lang, default=DEFAULT_PROMPTS["en"]["system"])
    user_tpl = resolve_prompt(
        deps, agent=AGENT, key="user_template", language=lang, default=DEFAULT_PROMPTS["en"]["user_template"]
    )
    user = user_tpl.format(
        user_input=(state.get("user_input", "") or "").strip(),
        output_mode=state.get("output_mode", "video"),
        analysis_json=json.dumps(state.get("analysis", {}), ensure_ascii=False, indent=2),
        design_json=json.dumps(state.get("design", {}), ensure_ascii=False, indent=2),
        render_json=json.dumps(state.get("render_result", {}) or {}, ensure_ascii=False, indent=2),
    )
    emit("stage_start", stage=STAGE, agent=AGENT)
    payload = await llm_json(
        deps,
        agent=AGENT,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        stage=STAGE,
    )
    summary = SummaryPayload.model_validate(payload)
    if summary.summary_text:
        emit("content", stage=STAGE, agent=AGENT, content=summary.summary_text)
    emit("stage_end", stage=STAGE, agent=AGENT)
    return {"summary": summary.model_dump(), "status": "succeeded", "usage": {"calls": 1}}


__all__ = ["DEFAULT_PROMPTS", "summary_node"]
