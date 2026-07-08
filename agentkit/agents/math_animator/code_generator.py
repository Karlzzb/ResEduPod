"""``code_generator`` Agent leaf — generates Manim code and repairs it on failure.

Ported from ``deeptutor/agents/math_animator/agents/code_generator_agent.py``.
Exposes two node functions sharing the same prompts:

* :func:`code_generation_node` — the initial generation step;
* :func:`code_repair_node` — the loop-back repair step; it increments the
  ``retry_count`` gate (ADR-0005) and regenerates code from ``last_error``.
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.runnables import RunnableConfig

from agentkit.agents.contract import emit, llm_json
from agentkit.deps import get_deps, resolve_prompt
from agentkit.models.math_animator import GeneratedCode
from agentkit.renderer.duration_utils import parse_target_duration_seconds
from agentkit.state.math_animator import MathAnimatorState
from agentkit.utils import build_repair_error_message

AGENT = "code_generator"

_GENERATE_SYSTEM = (
    "You are the Manim code generator for a math animation capability. Given the "
    "concept analysis and scene design, produce runnable Manim code as JSON. The code "
    "must define exactly one renderable Scene subclass. For image mode, wrap each still "
    "in ### YON_IMAGE_n_START ### / ### YON_IMAGE_n_END ### anchor blocks and emit nothing "
    "outside them. Prefer shapes and Text over LaTeX (Tex/MathTex) unless a local LaTeX "
    "install is guaranteed."
)

_GENERATE_USER_TEMPLATE = (
    "User request:\n{user_input}\n\n"
    "Output mode: {output_mode}\n"
    "{duration_requirement}\n\n"
    "Concept analysis:\n{analysis_json}\n\n"
    "Scene design:\n{design_json}\n\n"
    'Return JSON: {{"code": "<full manim code>", "rationale": "<why this design>"}}'
)

_RETRY_SYSTEM = (
    "You are repairing Manim code that failed to render. Fix the specific error while "
    "preserving the teaching intent. Return corrected, runnable code. Keep exactly one "
    "renderable Scene subclass. Avoid LaTeX (Tex/MathTex) if the error indicates a "
    "missing LaTeX install."
)

_RETRY_USER_TEMPLATE = (
    "User request:\n{user_input}\n\n"
    "Output mode: {output_mode}\n"
    "Repair attempt: #{attempt}\n"
    "{duration_requirement}\n\n"
    "Render/review error to fix:\n{error_message}\n\n"
    "Current code:\n{current_code}\n\n"
    'Return JSON: {{"code": "<corrected manim code>", "rationale": "<what you changed>"}}'
)

DEFAULT_PROMPTS: dict[str, dict[str, str]] = {
    "en": {
        "generate_system": _GENERATE_SYSTEM,
        "generate_user_template": _GENERATE_USER_TEMPLATE,
        "retry_system": _RETRY_SYSTEM,
        "retry_user_template": _RETRY_USER_TEMPLATE,
    },
}
DEFAULT_PROMPTS["zh"] = DEFAULT_PROMPTS["en"]


def _duration_seconds(state: MathAnimatorState) -> float | None:
    if state.get("duration_target_seconds") is not None:
        return state["duration_target_seconds"]
    text = f"{state.get('user_input', '')} {state.get('style_hint', '')}"
    return parse_target_duration_seconds(text)


def _duration_requirement(seconds: float | None, *, repair: bool) -> str:
    if seconds is None:
        return "No explicit duration target; use a standard teaching pace."
    if repair:
        return f"Target duration ~{seconds:.1f}s; keep close to it after the fix."
    return f"Target duration ~{seconds:.1f}s; budget the animation pacing around it."


async def code_generation_node(state: MathAnimatorState, config: RunnableConfig) -> dict[str, Any]:
    deps = get_deps(config)
    lang = state.get("language", "zh")
    system = resolve_prompt(
        deps, agent=AGENT, key="generate_system", language=lang, default=DEFAULT_PROMPTS["en"]["generate_system"]
    )
    user_tpl = resolve_prompt(
        deps, agent=AGENT, key="generate_user_template", language=lang,
        default=DEFAULT_PROMPTS["en"]["generate_user_template"],
    )
    seconds = _duration_seconds(state)
    user = user_tpl.format(
        user_input=(state.get("user_input", "") or "").strip(),
        output_mode=state.get("output_mode", "video"),
        duration_requirement=_duration_requirement(seconds, repair=False),
        analysis_json=json.dumps(state.get("analysis", {}), ensure_ascii=False, indent=2),
        design_json=json.dumps(state.get("design", {}), ensure_ascii=False, indent=2),
    )
    emit("stage_start", stage="code_generation", agent=AGENT)
    payload = await llm_json(
        deps,
        agent=AGENT,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        stage="code_generation",
    )
    generated = GeneratedCode.model_validate(payload)
    emit("stage_end", stage="code_generation", agent=AGENT)
    return {
        "code": generated.code,
        "retry_count": 0,
        "duration_target_seconds": seconds,
        "usage": {"calls": 1},
    }


async def code_repair_node(state: MathAnimatorState, config: RunnableConfig) -> dict[str, Any]:
    deps = get_deps(config)
    lang = state.get("language", "zh")
    attempt = state.get("retry_count", 0) + 1
    system = resolve_prompt(
        deps, agent=AGENT, key="retry_system", language=lang, default=DEFAULT_PROMPTS["en"]["retry_system"]
    )
    user_tpl = resolve_prompt(
        deps, agent=AGENT, key="retry_user_template", language=lang,
        default=DEFAULT_PROMPTS["en"]["retry_user_template"],
    )
    seconds = _duration_seconds(state)
    user = user_tpl.format(
        user_input=(state.get("user_input", "") or "").strip(),
        output_mode=state.get("output_mode", "video"),
        attempt=attempt,
        duration_requirement=_duration_requirement(seconds, repair=True),
        error_message=build_repair_error_message(state.get("last_error", "")),
        current_code=state.get("code", ""),
    )
    emit("stage_start", stage="code_retry", agent=AGENT, attempt=attempt)
    payload = await llm_json(
        deps,
        agent=AGENT,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        stage="code_retry",
    )
    repaired = GeneratedCode.model_validate(payload)
    new_code = (repaired.code or "").strip() or state.get("code", "")
    emit("stage_end", stage="code_retry", agent=AGENT, attempt=attempt)
    return {
        "code": new_code,
        "retry_count": attempt,  # the ADR-0005 gate counter
        "retry_history": [{"attempt": attempt, "error": state.get("last_error", "")}],
        "usage": {"calls": 1},
    }


__all__ = ["DEFAULT_PROMPTS", "code_generation_node", "code_repair_node"]
