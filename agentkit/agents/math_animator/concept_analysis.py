"""``concept_analysis`` Agent leaf — turns a request into a structured brief.

Ported from ``deeptutor/agents/math_animator/agents/concept_analysis_agent.py``;
the default prompts are inlined (ADR-0003) so the Agent runs with no external YAML.
"""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from agentkit.agents.contract import emit, llm_json
from agentkit.deps import get_deps, resolve_prompt
from agentkit.models.math_animator import ConceptAnalysis
from agentkit.state.math_animator import MathAnimatorState

AGENT = "concept_analysis"
STAGE = "concept_analysis"

_SYSTEM = (
    "You are the concept analyst for a math animation capability. Turn the user's "
    "request, history context, and any reference images into a structured brief for "
    "later design and code generation. Do not write Manim code yet. For video mode, "
    "also judge whether the explanation needs more intermediate beats, pauses, and "
    "recap time so the animation does not end before the teaching is complete."
)

_USER_TEMPLATE = (
    "User request:\n{user_input}\n\n"
    "History context:\n{history_context}\n\n"
    "Output mode: {output_mode}\n"
    "Style hint: {style_hint}\n"
    "Reference image count: {reference_count}\n\n"
    "Return JSON:\n"
    "{{\n"
    '  "learning_goal": "What the user wants to teach or demonstrate",\n'
    '  "math_focus": ["core idea 1", "core idea 2"],\n'
    '  "visual_targets": ["desired visual elements that must stay readable"],\n'
    '  "narrative_steps": ["recommended teaching order, granular enough for a complete explanation"],\n'
    '  "reference_usage": "how the reference images should influence design",\n'
    '  "output_intent": "what kind of final video/image should be produced"\n'
    "}}"
)

DEFAULT_PROMPTS: dict[str, dict[str, str]] = {
    "en": {"system": _SYSTEM, "user_template": _USER_TEMPLATE},
    "zh": {"system": _SYSTEM, "user_template": _USER_TEMPLATE},
}


async def concept_analysis_node(state: MathAnimatorState, config: RunnableConfig) -> dict[str, Any]:
    deps = get_deps(config)
    lang = state.get("language", "zh")
    system = resolve_prompt(deps, agent=AGENT, key="system", language=lang, default=DEFAULT_PROMPTS["en"]["system"])
    user_tpl = resolve_prompt(
        deps, agent=AGENT, key="user_template", language=lang, default=DEFAULT_PROMPTS["en"]["user_template"]
    )
    user = user_tpl.format(
        user_input=(state.get("user_input", "") or "").strip(),
        history_context=state.get("history_context", "") or "(none)",
        output_mode=state.get("output_mode", "video"),
        style_hint=state.get("style_hint", "") or "(none)",
        reference_count=0,
    )
    emit("stage_start", stage=STAGE, agent=AGENT)
    payload = await llm_json(
        deps,
        agent=AGENT,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        stage=STAGE,
    )
    analysis = ConceptAnalysis.model_validate(payload)
    emit("stage_end", stage=STAGE, agent=AGENT)
    return {"analysis": analysis.model_dump(), "usage": {"calls": 1}}


__all__ = ["DEFAULT_PROMPTS", "concept_analysis_node"]
