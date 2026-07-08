"""Parallel tool dispatch — the single point where a ReAct loop runs its tools.

The pre-fork substrate scattered the ``MAX_PARALLEL_TOOL_CALLS`` cap across every
capability's ``LoopHost.dispatch_tools`` (``deeptutor/core/agentic/tool_dispatch.py``
plus per-pipeline copies in chat / question / research).  Per ADR-0008 the cap and
the ``asyncio.gather`` fan-out are consolidated here, into the one ``tool node`` of
the :func:`~agentkit.orchestrations.react.build_react_orchestration_graph` template.

A ``tool_call`` is a plain JSON dict ``{"id", "name", "arguments"}`` produced by the
LLM node's JSON decision (ADR-0003 keeps the LLM client text-only, so tool calls
ride in the model's structured output rather than native function-calling).
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from agentkit.agents.contract import emit

if TYPE_CHECKING:  # avoid an import cycle; only needed for typing
    from agentkit.tools import Tool

# Faithful port of the parallel-tool ceiling from
# ``deeptutor/core/agentic/tool_dispatch.py`` (MAX_PARALLEL_TOOL_CALLS = 8).
MAX_PARALLEL_TOOL_CALLS = 8


async def dispatch_tool_calls(
    tool_calls: list[dict[str, Any]],
    tools_by_name: dict[str, "Tool"],
    *,
    agent: str,
    stage: str = "tools",
) -> list[dict[str, Any]]:
    """Run a batch of tool calls concurrently and return their ``role=tool`` messages.

    At most :data:`MAX_PARALLEL_TOOL_CALLS` run in one batch; a larger batch is
    sliced (with a ``warning`` progress event), mirroring the pre-fork warn-and-slice
    behavior.  Each call emits ``tool_start`` / ``tool_end`` events, and an unknown
    tool name yields an error message rather than raising (so one bad call cannot
    abort the whole loop).  Order of the returned messages follows the (capped)
    input order, independent of completion order.
    """
    capped = tool_calls[:MAX_PARALLEL_TOOL_CALLS]
    if len(tool_calls) > MAX_PARALLEL_TOOL_CALLS:
        emit(
            "progress",
            stage=stage,
            agent=agent,
            content=f"Too many tool calls ({len(tool_calls)}); capped to {MAX_PARALLEL_TOOL_CALLS}.",
            trace_kind="warning",
            limit=MAX_PARALLEL_TOOL_CALLS,
        )

    async def _run_one(index: int, call: dict[str, Any]) -> dict[str, Any]:
        name = str(call.get("name", ""))
        call_id = str(call.get("id") or f"call_{index}")
        arguments = call.get("arguments") or {}
        emit("tool_start", stage=stage, agent=agent, tool=name, tool_call_id=call_id)
        tool = tools_by_name.get(name)
        if tool is None:
            content = f"Error: unknown tool {name!r}."
        else:
            try:
                content = await tool.run(arguments)
            except Exception as exc:  # a tool failure is data, not a loop-aborting crash
                content = f"Error: tool {name!r} failed: {exc}"
        emit("tool_end", stage=stage, agent=agent, tool=name, tool_call_id=call_id)
        return {"role": "tool", "tool_call_id": call_id, "name": name, "content": content}

    return list(await asyncio.gather(*(_run_one(i, c) for i, c in enumerate(capped))))


__all__ = ["MAX_PARALLEL_TOOL_CALLS", "dispatch_tool_calls"]
