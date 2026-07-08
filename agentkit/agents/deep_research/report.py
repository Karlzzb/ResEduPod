"""``report`` — the terminal Agent leaf that assembles the final research report.

The pre-fork report writer was a ~1000-line multi-stage pipeline (outline → intro →
per-section → conclusion → citation linkification).  That richness is out of scope
for issue #4, whose AC is the supervisor/``Send``/reducer scaffold; here the report
is a single Agent-leaf ``llm_text`` call over the completed blocks and their
citations, keeping the seam faithful (completed knowledge + grounded citations in,
one assembled report out) without re-deriving the whole writer.
"""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from agentkit.agents.contract import emit, llm_text
from agentkit.deps import get_deps, resolve_prompt
from agentkit.models.deep_research import STATUS_COMPLETED
from agentkit.state.deep_research import DeepResearchState

AGENT = "research_report"
STAGE = "reporting"

DEFAULT_PROMPTS = {
    "en": {
        "system": (
            "You are a research report writer. Synthesize the per-sub-topic findings below "
            "into one coherent report with a title, a short introduction, a section per "
            "sub-topic, and a conclusion. Preserve the [CIT-...] citation markers exactly "
            "where the findings reference them so they can be linked to the reference list."
        ),
        "user_template": "Research topic: {topic}\n\nFindings by sub-topic:\n{findings}\n",
    }
}


def _render_findings(blocks: list[dict[str, Any]]) -> str:
    """Lay out each completed block's knowledge + its citation ids for the writer."""
    lines: list[str] = []
    for block in blocks:
        if block.get("status") != STATUS_COMPLETED:
            continue
        cites = ", ".join(block.get("citation_ids", [])) or "(none)"
        lines.append(
            f"### {block['title']}\n{block.get('knowledge', '').strip()}\nCitations: {cites}"
        )
    return "\n\n".join(lines) or "(no completed findings)"


async def report_node(state: DeepResearchState, config: RunnableConfig) -> dict[str, Any]:
    """Assemble the final report from completed blocks and mark the run terminal."""
    deps = get_deps(config)
    lang = state.get("language", "en")
    topic = state.get("topic", "")
    blocks = list(state.get("blocks", []))

    system = resolve_prompt(
        deps, agent=AGENT, key="system", language=lang, default=DEFAULT_PROMPTS["en"]["system"]
    )
    user_tpl = resolve_prompt(
        deps,
        agent=AGENT,
        key="user_template",
        language=lang,
        default=DEFAULT_PROMPTS["en"]["user_template"],
    )
    user = user_tpl.format(topic=topic, findings=_render_findings(blocks))

    emit("stage_start", stage=STAGE, agent=AGENT)
    report = await llm_text(
        deps,
        agent=AGENT,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        stage=STAGE,
    )
    emit("stage_end", stage=STAGE, agent=AGENT)
    # ``capped`` is set by the supervisor when the safety cap tripped; a clean finish
    # promotes it to ``succeeded`` but never overwrites the capped signal.
    status = "capped" if state.get("status") == "capped" else "succeeded"
    return {"report": report, "status": status}


__all__ = ["DEFAULT_PROMPTS", "report_node"]
