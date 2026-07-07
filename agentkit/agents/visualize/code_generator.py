"""``code_generator`` Agent leaf for ``visualize`` (text render types).

Ported from ``deeptutor/agents/visualize/agents/code_generator_agent.py``.
Produces free-text code (SVG / Chart.js JSON / Mermaid / HTML), extracted from a
fenced block.
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.runnables import RunnableConfig

from agentkit.agents.contract import emit, llm_text
from agentkit.deps import get_deps, resolve_prompt
from agentkit.state.visualize import VisualizeState
from agentkit.utils import extract_code_block

AGENT = "viz_code_generator"
STAGE = "generating"

_SYSTEM_BASE = (
    "You are the code generator for a visualization capability. Produce ONLY the "
    "visualization code for the requested render type inside a single fenced code block. "
    "No commentary."
)

_RULES = {
    "svg": "Output a single self-contained <svg> with a camelCase viewBox. No external assets.",
    "chartjs": "Output a strict-JSON Chart.js config object with 'type' and 'data'. No JS callbacks.",
    "mermaid": "Output Mermaid diagram code starting with a valid diagram keyword (graph/flowchart/...).",
    "html": "Output a single self-contained HTML document (<!DOCTYPE html>...). Inline all CSS/JS.",
}

_USER_TEMPLATE = (
    "User request:\n{user_input}\n\n"
    "Analysis:\n{analysis_json}\n\n"
    "Render type: {render_type}\n"
    "{rules}\n\n"
    "Return the code in a single ```{lang}``` fenced block."
)

DEFAULT_PROMPTS: dict[str, dict[str, str]] = {
    "en": {"system_base": _SYSTEM_BASE, "user_template": _USER_TEMPLATE},
}
DEFAULT_PROMPTS["zh"] = DEFAULT_PROMPTS["en"]

_LANG_HINT = {"svg": "svg", "chartjs": "json", "mermaid": "mermaid", "html": "html"}


async def codegen_node(state: VisualizeState, config: RunnableConfig) -> dict[str, Any]:
    deps = get_deps(config)
    lang = state.get("language", "zh")
    render_type = state.get("render_type", "svg")
    system = resolve_prompt(
        deps, agent=AGENT, key="system_base", language=lang, default=DEFAULT_PROMPTS["en"]["system_base"]
    )
    user_tpl = resolve_prompt(
        deps, agent=AGENT, key="user_template", language=lang, default=DEFAULT_PROMPTS["en"]["user_template"]
    )
    user = user_tpl.format(
        user_input=(state.get("user_input", "") or "").strip(),
        analysis_json=json.dumps(state.get("analysis", {}), ensure_ascii=False, indent=2),
        render_type=render_type,
        rules=_RULES.get(render_type, ""),
        lang=_LANG_HINT.get(render_type, ""),
    )
    emit("stage_start", stage=STAGE, agent=AGENT)
    response = await llm_text(
        deps,
        agent=AGENT,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        stage=STAGE,
    )
    code = extract_code_block(response, _LANG_HINT.get(render_type, ""))
    emit("stage_end", stage=STAGE, agent=AGENT)
    return {"code": code, "usage": {"calls": 1}}


__all__ = ["DEFAULT_PROMPTS", "codegen_node"]
