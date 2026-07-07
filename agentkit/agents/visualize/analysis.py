"""``analysis`` Agent leaf for ``visualize`` — picks the render type + brief.

Ported from ``deeptutor/agents/visualize/agents/analysis_agent.py``.  When the
request pins a manim mode the node short-circuits with a stub (no LLM call), so
the orchestration can route straight into the reused math_animator subgraph.
"""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from agentkit.agents.contract import emit, llm_json
from agentkit.deps import get_deps, resolve_prompt
from agentkit.models.visualize import VisualizationAnalysis
from agentkit.state.visualize import VisualizeState

AGENT = "analysis"
STAGE = "analyzing"

_TEXT_TYPES = ("svg", "chartjs", "mermaid", "html")

_SYSTEM_AUTO = (
    "You are the analyst for a visualization capability. Choose the best render type "
    "for the user's request among: svg (diagrams/illustrations), chartjs (data charts), "
    "mermaid (flow/sequence/class diagrams), html (interactive/mockups). Return a brief."
)

_SYSTEM_FIXED = (
    "You are the analyst for a visualization capability. The render type is FIXED to "
    "'{render_type}'. Produce a brief tailored to that type. Do not change the type."
)

_USER_TEMPLATE = (
    "User request:\n{user_input}\n\n"
    "History context:\n{history_context}\n\n"
    "Return JSON:\n"
    "{{\n"
    '  "render_type": "{render_type_hint}",\n'
    '  "description": "what to draw",\n'
    '  "data_description": "data involved, if any",\n'
    '  "chart_type": "for charts: bar/line/pie/...",\n'
    '  "visual_elements": ["key elements"],\n'
    '  "rationale": "why this render type"\n'
    "}}"
)

DEFAULT_PROMPTS: dict[str, dict[str, str]] = {
    "en": {"system_auto": _SYSTEM_AUTO, "system_fixed": _SYSTEM_FIXED, "user_template": _USER_TEMPLATE},
}
DEFAULT_PROMPTS["zh"] = DEFAULT_PROMPTS["en"]


async def analysis_node(state: VisualizeState, config: RunnableConfig) -> dict[str, Any]:
    deps = get_deps(config)
    lang = state.get("language", "zh")
    render_mode = state.get("render_mode", "auto")

    # Short-circuit: a pinned manim mode needs no LLM analysis.
    if render_mode in {"manim_video", "manim_image"}:
        analysis = VisualizationAnalysis(render_type=render_mode, description=state.get("user_input", ""))
        return {"analysis": analysis.model_dump(), "render_type": render_mode}

    emit("stage_start", stage=STAGE, agent=AGENT)
    if render_mode in _TEXT_TYPES:
        system = resolve_prompt(
            deps, agent=AGENT, key="system_fixed", language=lang, default=DEFAULT_PROMPTS["en"]["system_fixed"]
        ).format(render_type=render_mode)
        render_type_hint = render_mode
    else:
        system = resolve_prompt(
            deps, agent=AGENT, key="system_auto", language=lang, default=DEFAULT_PROMPTS["en"]["system_auto"]
        )
        render_type_hint = "svg|chartjs|mermaid|html"
    user_tpl = resolve_prompt(
        deps, agent=AGENT, key="user_template", language=lang, default=DEFAULT_PROMPTS["en"]["user_template"]
    )
    user = user_tpl.format(
        user_input=(state.get("user_input", "") or "").strip(),
        history_context=state.get("history_context", "") or "(none)",
        render_type_hint=render_type_hint,
    )
    payload = await llm_json(
        deps,
        agent=AGENT,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        stage=STAGE,
    )
    # When the mode is fixed, trust the request over any model drift.
    if render_mode in _TEXT_TYPES:
        payload["render_type"] = render_mode
    analysis = VisualizationAnalysis.model_validate(payload)
    emit("stage_end", stage=STAGE, agent=AGENT)
    return {"analysis": analysis.model_dump(), "render_type": analysis.render_type}


__all__ = ["DEFAULT_PROMPTS", "analysis_node"]
