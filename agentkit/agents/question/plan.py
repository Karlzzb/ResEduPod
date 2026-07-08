"""``question_plan`` Agent leaf — turns exploration into a structured quiz plan.

A single ``llm_json`` step with no tools (the ADR-0008 "extra node" stacked between
the two ReAct subgraphs).  Follows the standard Agent contract: read ``deps``,
resolve prompts (falling back to the inline defaults), emit stage events, validate.
"""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from agentkit.agents.contract import emit, llm_json
from agentkit.agents.question.prompts import PLAN_SYSTEM, PLAN_USER_TEMPLATE
from agentkit.deps import get_deps, resolve_prompt
from agentkit.models.question import QuizPlan
from agentkit.state.question import QuestionState

AGENT = "question_plan"
STAGE = "plan"


async def plan_node(state: QuestionState, config: RunnableConfig) -> dict[str, Any]:
    deps = get_deps(config)
    lang = state.get("language", "zh")
    system = resolve_prompt(deps, agent=AGENT, key="system", language=lang, default=PLAN_SYSTEM)
    user_tpl = resolve_prompt(
        deps, agent=AGENT, key="user_template", language=lang, default=PLAN_USER_TEMPLATE
    )
    user = user_tpl.format(
        user_input=(state.get("user_input", "") or "").strip(),
        exploration=state.get("exploration", "") or "(none)",
    )
    emit("stage_start", stage=STAGE, agent=AGENT)
    payload = await llm_json(
        deps,
        agent=AGENT,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        stage=STAGE,
    )
    plan = QuizPlan.model_validate(payload)
    emit("stage_end", stage=STAGE, agent=AGENT, templates=len(plan.templates))
    return {"plan": plan.model_dump(), "usage": {"calls": 1}}


__all__ = ["plan_node"]
