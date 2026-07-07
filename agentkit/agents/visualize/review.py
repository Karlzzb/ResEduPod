"""``review`` Agent leaf for ``visualize`` — targeted repair of invalid code.

Ported from ``deeptutor/agents/visualize/agents/review_agent.py``.  Only invoked
when local ``validate_visualization`` fails (see the orchestration): a single
targeted repair, not an open-ended review.
"""

from __future__ import annotations

import json

from langchain_core.runnables import RunnableConfig

from agentkit.agents.contract import emit, llm_json
from agentkit.deps import get_deps, resolve_prompt
from agentkit.models.visualize import ReviewResult
from agentkit.state.visualize import VisualizeState

AGENT = "viz_review"
STAGE = "reviewing"

_REPAIR_SYSTEM = (
    "You are the repair agent for a visualization capability. The generated code failed "
    "a deterministic validation check. Fix ONLY what the error describes and return the "
    "corrected code. Preserve intent."
)

_REPAIR_USER_TEMPLATE = (
    "User request:\n{user_input}\n\n"
    "Render type: {render_type}\n"
    "Validation error:\n{error}\n\n"
    "Analysis:\n{analysis_json}\n\n"
    "Current code:\n{code}\n\n"
    'Return JSON: {{"optimized_code": "<fixed code>", "changed": true, "review_notes": "<what you fixed>"}}'
)

DEFAULT_PROMPTS: dict[str, dict[str, str]] = {
    "en": {"repair_system": _REPAIR_SYSTEM, "repair_user_template": _REPAIR_USER_TEMPLATE},
}
DEFAULT_PROMPTS["zh"] = DEFAULT_PROMPTS["en"]


async def repair(state: VisualizeState, config: RunnableConfig, *, error: str) -> ReviewResult:
    deps = get_deps(config)
    lang = state.get("language", "zh")
    system = resolve_prompt(
        deps, agent=AGENT, key="repair_system", language=lang, default=DEFAULT_PROMPTS["en"]["repair_system"]
    )
    user_tpl = resolve_prompt(
        deps, agent=AGENT, key="repair_user_template", language=lang,
        default=DEFAULT_PROMPTS["en"]["repair_user_template"],
    )
    user = user_tpl.format(
        user_input=(state.get("user_input", "") or "").strip(),
        render_type=state.get("render_type", ""),
        error=error,
        analysis_json=json.dumps(state.get("analysis", {}), ensure_ascii=False, indent=2),
        code=state.get("code", ""),
    )
    emit("stage_start", stage=STAGE, agent=AGENT)
    payload = await llm_json(
        deps,
        agent=AGENT,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        stage=STAGE,
    )
    result = ReviewResult.model_validate(payload)
    emit("stage_end", stage=STAGE, agent=AGENT)
    return result


__all__ = ["DEFAULT_PROMPTS", "repair"]
