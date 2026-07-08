"""``research_worker`` — the Agent leaf a ``Send`` dispatches once per block.

Per issue #4 the worker is a *single* Agent-leaf ``llm_json`` call (not a nested
ReAct loop — that template already exists as issue #2 and the AC here is the
supervisor / ``Send`` fan-out / reducer scaffold).  Given one ``pending`` block, it
synthesizes findings, grounds them in citations, and may propose freshly discovered
sub-topics to research next round.

It returns a **partial** ``DeepResearchState`` — its own block flipped to
``completed`` plus any new child blocks, and its citations — which the ``blocks`` /
``citations`` reducers fold into the shared State.  It never mutates a shared queue
or citation manager (there is none), so N of these can run concurrently in one
LangGraph superstep with deterministic merges (ADR-0006).
"""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from agentkit.agents.contract import emit, llm_json
from agentkit.agents.deep_research.queue_ops import block_id_for, find_similar
from agentkit.deps import get_deps, resolve_prompt
from agentkit.models.deep_research import STATUS_COMPLETED, TopicBlock, WorkerOutput
from agentkit.state.deep_research import DEFAULT_QUEUE_MAX_LENGTH, DeepResearchState

AGENT = "research_worker"
STAGE = "researching"

DEFAULT_PROMPTS = {
    "en": {
        "system": (
            "You are a focused research worker investigating ONE sub-topic of a larger "
            "research effort. Synthesize what is known about the sub-topic, ground every "
            "claim in a citation, and — only when you genuinely uncover a distinct, "
            "non-overlapping thread worth its own investigation — propose it as a new "
            "sub-topic to research next.\n\n"
            "Respond with a single JSON object:\n"
            "{\n"
            '  "knowledge": "<synthesized findings for this sub-topic>",\n'
            '  "citations": [{"source": "<url or ref>", "title": "<source title>", '
            '"snippet": "<supporting quote>"}],\n'
            '  "append": [{"title": "<distinct new sub-topic>", "overview": "<why it matters>"}]\n'
            "}\n"
            'Leave "append" empty unless a new thread is clearly warranted; do not restate '
            "the current sub-topic."
        ),
        "user_template": (
            "Overall research topic: {topic}\n\n"
            "Your sub-topic: {title}\n"
            "Overview: {overview}\n\n"
            "Already-tracked sub-topics (do NOT re-propose these): {known}\n"
        ),
    }
}


def _seed_from_worker_output(
    *,
    block: dict[str, Any],
    output: WorkerOutput,
    known_titles: list[str],
    queue_max_length: int,
    current_block_count: int,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Turn one worker's LLM output into partial ``blocks`` + ``citations`` returns.

    Applies the fuzzy-dedup and queue-length cap that used to live on the mutable
    ``DynamicTopicQueue``: a proposed child that fuzzily matches a known title, or
    that would push the list past ``queue_max_length``, is dropped (mirroring the
    pre-fork ``append_child`` returning ``None`` when full).
    """
    parent_id = block["block_id"]

    # Mint this block's citations with worker-local, globally-unique ids.
    citations: dict[str, dict[str, Any]] = {}
    citation_ids: list[str] = []
    for seq, cit in enumerate(output.citations, start=1):
        citation_id = f"CIT-{parent_id}-{seq:02d}"
        citation_ids.append(citation_id)
        citations[citation_id] = {
            "citation_id": citation_id,
            "block_id": parent_id,
            "source": cit.source,
            "title": cit.title,
            "snippet": cit.snippet,
        }

    completed = TopicBlock(
        block_id=parent_id,
        title=block["title"],
        overview=block.get("overview", ""),
        status=STATUS_COMPLETED,
        knowledge=output.knowledge,
        parent=block.get("parent"),
        citation_ids=citation_ids,
    ).model_dump()

    returned_blocks = [completed]

    # Fuzzy-dedup children against everything already tracked *and* siblings this
    # same worker just proposed; enforce the block-count cap (pre-fork ``is_full``).
    seen_titles = list(known_titles)
    projected_count = current_block_count
    for sub in output.append:
        title = (sub.title or "").strip()
        if not title:
            continue
        if find_similar(title, seen_titles) is not None:
            emit("progress", stage=STAGE, agent=AGENT, trace_kind="dedup", dropped_subtopic=title)
            continue
        if projected_count >= queue_max_length:
            emit(
                "progress",
                stage=STAGE,
                agent=AGENT,
                trace_kind="queue_full",
                dropped_subtopic=title,
            )
            continue
        child = TopicBlock(
            block_id=block_id_for(title),
            title=title,
            overview=sub.overview,
            parent=parent_id,
        ).model_dump()
        returned_blocks.append(child)
        seen_titles.append(title)
        projected_count += 1

    return returned_blocks, citations


async def research_worker_node(state: DeepResearchState, config: RunnableConfig) -> dict[str, Any]:
    """Research the single block handed to this ``Send`` and return partial State.

    The block under research rides in ``state`` because ``Send("research_worker",
    {...})`` delivers a scoped payload; scheduling context (``topic``, the known
    titles, the queue cap) is threaded in with it by the supervisor's fan-out.
    """
    deps = get_deps(config)
    lang = state.get("language", "en")
    block = state["block"]  # injected by the Send payload
    topic = state.get("topic", "")
    known_titles = list(state.get("known_titles", []))
    queue_max_length = state.get("queue_max_length", DEFAULT_QUEUE_MAX_LENGTH)
    current_block_count = state.get("block_count", len(known_titles))

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
    user = user_tpl.format(
        topic=topic,
        title=block["title"],
        overview=block.get("overview", "") or "(none)",
        known=", ".join(known_titles) or "(none)",
    )

    emit("stage_start", stage=STAGE, agent=AGENT, block_id=block["block_id"], title=block["title"])
    payload = await llm_json(
        deps,
        agent=AGENT,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        stage=STAGE,
    )
    output = WorkerOutput.model_validate(payload)
    blocks, citations = _seed_from_worker_output(
        block=block,
        output=output,
        known_titles=known_titles,
        queue_max_length=queue_max_length,
        current_block_count=current_block_count,
    )
    emit(
        "stage_end",
        stage=STAGE,
        agent=AGENT,
        block_id=block["block_id"],
        appended=len(blocks) - 1,
        citations=len(citations),
    )
    return {"blocks": blocks, "citations": citations, "usage": {"calls": 1}}


__all__ = ["DEFAULT_PROMPTS", "research_worker_node"]
