"""``concept_design`` Agent leaf — turns the analysis brief into a scene design.

Ported from ``deeptutor/agents/math_animator/agents/concept_design_agent.py``.
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.runnables import RunnableConfig

from agentkit.agents.contract import emit, llm_json
from agentkit.deps import get_deps, resolve_prompt
from agentkit.models.math_animator import SceneDesign
from agentkit.state.math_animator import MathAnimatorState

AGENT = "concept_design"
STAGE = "concept_design"

_SYSTEM = (
    "You are the scene designer for a math animation capability. Given the concept "
    "analysis, produce a concrete scene design: title, ordered scene outline, visual "
    "style, animation notes, an image plan, and hard code constraints for the code "
    "generator. Do not write Manim code yet."
)

_USER_TEMPLATE = (
    "User request:\n{user_input}\n\n"
    "Output mode: {output_mode}\n"
    "Style hint: {style_hint}\n\n"
    "Concept analysis:\n{analysis_json}\n\n"
    "Return JSON:\n"
    "{{\n"
    '  "title": "short scene title",\n'
    '  "scene_outline": ["ordered beats"],\n'
    '  "visual_style": "overall visual style",\n'
    '  "animation_notes": ["timing / motion notes"],\n'
    '  "image_plan": ["for image mode: what each still should show"],\n'
    '  "code_constraints": ["hard constraints the code generator must obey"]\n'
    "}}"
)

DEFAULT_PROMPTS: dict[str, dict[str, str]] = {
    "en": {"system": _SYSTEM, "user_template": _USER_TEMPLATE},
    "zh": {"system": _SYSTEM, "user_template": _USER_TEMPLATE},
}


async def concept_design_node(state: MathAnimatorState, config: RunnableConfig) -> dict[str, Any]:
    deps = get_deps(config)
    lang = state.get("language", "zh")
    system = resolve_prompt(deps, agent=AGENT, key="system", language=lang, default=DEFAULT_PROMPTS["en"]["system"])
    user_tpl = resolve_prompt(
        deps, agent=AGENT, key="user_template", language=lang, default=DEFAULT_PROMPTS["en"]["user_template"]
    )
    user = user_tpl.format(
        user_input=(state.get("user_input", "") or "").strip(),
        output_mode=state.get("output_mode", "video"),
        style_hint=state.get("style_hint", "") or "(none)",
        analysis_json=json.dumps(state.get("analysis", {}), ensure_ascii=False, indent=2),
    )
    emit("stage_start", stage=STAGE, agent=AGENT)
    payload = await llm_json(
        deps,
        agent=AGENT,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        stage=STAGE,
    )
    design = SceneDesign.model_validate(payload)
    emit("stage_end", stage=STAGE, agent=AGENT)
    return {"design": design.model_dump(), "usage": {"calls": 1}}


__all__ = ["DEFAULT_PROMPTS", "concept_design_node"]
