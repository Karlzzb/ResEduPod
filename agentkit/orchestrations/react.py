"""``ReActOrchestration`` — the loop-archetype template (ADR-0005 / ADR-0008).

A reusable **LLM node ⇄ tool node** cycle, drawn as a *visible* graph loop::

    START → llm ─ route_after_llm ─┬─ "tools"    → tools → llm   (the visible cycle)
                                   ├─ "finalize" → finalize → END (ADR-0005 gate)
                                   └─ "final"    → END

Each capability *instantiates* the template with its own ``owned_tools``,
``agent_name``, and ``system_prompt`` block (ADR-0008); ``question`` is the first
instance (``agentkit/orchestrations/question.py``), sharing this template with the
future ``chat`` family.

The loop is gated two ways (ADR-0005): the ``iteration`` counter lives in ``State``
and is checked in ``route_after_llm`` (a bounded, in-graph gate), and the caller
may also set LangGraph's ``recursion_limit`` as a hard backstop.  Reaching the gate
routes to ``finalize`` for a forced 收尾 rather than looping unbounded.

Because the DI'd :class:`~agentkit.deps.protocols.LLMClient` is deliberately
text-only (ADR-0003), the LLM does not use native function-calling; instead the LLM
node asks for a JSON decision via ``llm_json``::

    {"action": "tool",  "tool_calls": [{"id","name","arguments"}], "content": "..."}
    {"action": "final", "content": "the answer"}

All tool parallelism (``MAX_PARALLEL_TOOL_CALLS = 8``) is consolidated into the one
tool node (:func:`~agentkit.tools.dispatch.dispatch_tool_calls`).

The template also carries the four ``chat``-loop robustness behaviours (PRD US 25 /
issue #3), so every loop-archetype instance (``chat`` / ``question`` / ``deep_solve``)
inherits them without re-implementation:

* **Multi-level provider degradation** — handled one layer down in
  :func:`~agentkit.agents.contract.llm_json` (primary → ordered fallbacks); if every
  provider is exhausted the ``llm_node`` salvages instead of crashing (below).
* **Context-window protection** — before each LLM call the ``llm_node`` snips the
  oldest tool results when the conversation would overflow the model's window
  (:func:`~agentkit.utils.context_window.snip_to_context_budget`).
* **Forced 收尾** — the ADR-0005 iteration gate routes to ``finalize`` (``reason=
  "budget"``); a total provider failure after useful work routes there too
  (``reason="error"``), never losing a turn that already gathered results.
* **Thinking-tag filtering** — inline ``<think>`` scratchpad is split onto the
  ``thinking`` stream in the contract, and scrubbed from ``final_text`` here so it
  never leaks into the user-facing answer.
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from agentkit.agents.contract import emit, llm_json
from agentkit.deps import get_deps
from agentkit.state.react import DEFAULT_MAX_ITERATIONS, ReActState
from agentkit.tools import Tool, dispatch_tool_calls
from agentkit.utils.context_window import (
    resolve_effective_context_window,
    snip_to_context_budget,
)
from agentkit.utils.think_filter import clean_thinking_tags

_STAGE_LLM = "reasoning"
_STAGE_TOOLS = "tools"
_STAGE_FINALIZE = "finalize"

# Forced-收尾 fallback text by reason (issue #3): shown only when there is no
# usable ``final_text`` to close the turn with.
_FORCED_FINISH_TEXT = {
    "budget": "Stopped after reaching the reasoning-loop limit before a final answer.",
    "error": "A step failed; answering with what has been gathered so far.",
}

_PROTOCOL_INSTRUCTIONS = (
    "You run in a reason-act loop. On every turn reply with a single JSON object and "
    "nothing else:\n"
    '  - to use tools: {{"action": "tool", "content": "<brief reasoning>", '
    '"tool_calls": [{{"id": "<unique id>", "name": "<tool name>", "arguments": {{...}}}}]}}\n'
    '  - to answer:   {{"action": "final", "content": "<your complete answer>"}}\n'
    "Call tools only from the advertised list. When you have enough information, emit "
    '"final". Do not wrap the JSON in code fences.'
)


def _system_message(system_prompt: str, tools: list[Tool]) -> str:
    """Compose the instance's prompt block + the ReAct protocol + tool advertisement."""
    parts = [system_prompt.strip(), _PROTOCOL_INSTRUCTIONS]
    if tools:
        advertised = json.dumps([t.schema() for t in tools], ensure_ascii=False)
        parts.append(f"Available tools:\n{advertised}")
    else:
        parts.append('No tools are available; answer directly with a "final" action.')
    return "\n\n".join(p for p in parts if p)


def build_react_orchestration_graph(
    *,
    tools: list[Tool] | None = None,
    agent_name: str = "react",
    system_prompt: str = "You are a helpful reasoning agent.",
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    state_schema: type = ReActState,
    checkpointer: Any | None = None,
) -> Any:
    """Compile a ReAct Orchestration graph parameterised for one capability.

    ``tools`` / ``agent_name`` / ``system_prompt`` are the ADR-0008 instantiation
    parameters.  The returned graph is a compiled ``StateGraph`` ready to drive with
    ``astream`` (directly or reused as a subgraph, cf. ``question``).
    """
    owned_tools = list(tools or [])
    tools_by_name = {t.name: t for t in owned_tools}
    system = _system_message(system_prompt, owned_tools)

    async def llm_node(state: ReActState, config: RunnableConfig) -> dict[str, Any]:
        deps = get_deps(config)
        iteration = state.get("iteration", 0)
        prior = list(state.get("messages", []))
        seed: list[dict[str, Any]] = []
        if not prior:  # first turn — seed the task as the opening user message
            seed = [{"role": "user", "content": state.get("input", "")}]
        conversation = prior + seed

        # Context-window protection (issue #3): snip oldest tool results in place
        # before the call so an overgrown conversation never overflows the window.
        params = deps.config.params(agent=agent_name)
        window = resolve_effective_context_window(
            context_window=getattr(params, "context_window", None),
            model=params.model or "",
            max_tokens=params.max_tokens,
        )
        # Copy each message so the guard trims only the wire payload; the stored
        # conversation keeps full-fidelity tool results (recoverable next turn).
        request_messages = [
            {"role": "system", "content": system},
            *({**m} for m in conversation),
        ]
        if snip_to_context_budget(request_messages, context_window=window):
            emit(
                "progress",
                stage=_STAGE_LLM,
                agent=agent_name,
                trace_kind="warning",
                context_window_guard=True,
            )

        emit("stage_start", stage=_STAGE_LLM, agent=agent_name, iteration=iteration)
        next_iteration = iteration + 1
        try:
            decision = await llm_json(
                deps,
                agent=agent_name,
                messages=request_messages,
                stage=_STAGE_LLM,
            )
        except Exception as exc:
            # Multi-level provider degradation exhausted (all providers failed).
            # If earlier iterations already gathered useful work, force a 收尾
            # rather than lose the turn; a first-turn failure has nothing to
            # salvage, so it propagates (matches the pre-fork loop).
            if iteration == 0:
                raise
            emit(
                "progress",
                stage=_STAGE_LLM,
                agent=agent_name,
                trace_kind="warning",
                provider_exhausted=True,
                error=str(exc),
            )
            return {
                "iteration": next_iteration,
                "pending_tool_calls": [],
                "status": "running",
                "finalize_reason": "error",
            }
        emit("stage_end", stage=_STAGE_LLM, agent=agent_name)

        action = str(decision.get("action", "final"))
        content = str(decision.get("content", "") or "")

        if action == "tool" and decision.get("tool_calls"):
            tool_calls = list(decision["tool_calls"])
            assistant = {"role": "assistant", "content": content, "tool_calls": tool_calls}
            return {
                "iteration": next_iteration,
                "pending_tool_calls": tool_calls,
                "messages": seed + [assistant],
            }

        # action == "final" (or a malformed decision — treat as an answer, not a crash).
        # Scrub any inline <think> scratchpad so it never leaks into the answer.
        answer = clean_thinking_tags(content)
        emit("content", stage=_STAGE_LLM, agent=agent_name, content=answer)
        return {
            "iteration": next_iteration,
            "pending_tool_calls": [],
            "final_text": answer,
            "status": "succeeded",
            "messages": seed + [{"role": "assistant", "content": answer}],
        }

    async def tool_node(state: ReActState, config: RunnableConfig) -> dict[str, Any]:
        """The single tool-dispatch point (ADR-0008): parallel, capped at 8."""
        tool_calls = state.get("pending_tool_calls", [])
        tool_messages = await dispatch_tool_calls(
            tool_calls, tools_by_name, agent=agent_name, stage=_STAGE_TOOLS
        )
        return {"messages": tool_messages, "pending_tool_calls": []}

    async def finalize_node(state: ReActState, config: RunnableConfig) -> dict[str, Any]:
        """Forced 收尾 (issue #3): the loop hit the iteration gate (``reason=budget``)
        or every LLM provider was exhausted after useful work (``reason=error``)."""
        reason = state.get("finalize_reason", "budget")
        default = _FORCED_FINISH_TEXT.get(reason, _FORCED_FINISH_TEXT["budget"])
        text = clean_thinking_tags(state.get("final_text", "") or "") or default
        emit(
            "content",
            stage=_STAGE_FINALIZE,
            agent=agent_name,
            content=text,
            forced=True,
            reason=reason,
        )
        return {
            "status": "finalized",
            "final_text": text,
            "pending_tool_calls": [],
            "finalize_reason": reason,
        }

    def route_after_llm(state: ReActState) -> str:
        # Provider exhaustion after useful work asks for a forced 收尾 explicitly.
        if state.get("finalize_reason"):
            return "finalize"
        if state.get("status") == "succeeded" or not state.get("pending_tool_calls"):
            return "final"
        limit = state.get("max_iterations", max_iterations)
        if state.get("iteration", 0) >= limit:  # ADR-0005 gate
            return "finalize"
        return "tools"

    graph = StateGraph(state_schema)
    graph.add_node("llm", llm_node)
    graph.add_node("tools", tool_node)
    graph.add_node("finalize", finalize_node)

    graph.add_edge(START, "llm")
    graph.add_conditional_edges(
        "llm",
        route_after_llm,
        {"tools": "tools", "finalize": "finalize", "final": END},
    )
    graph.add_edge("tools", "llm")  # the visible cycle back to the LLM node
    graph.add_edge("finalize", END)
    return graph.compile(checkpointer=checkpointer)


__all__ = ["build_react_orchestration_graph"]
