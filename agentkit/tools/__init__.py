"""Tools — the ``owned_tools`` an Orchestration hands to its ReAct template.

A :class:`Tool` is a self-describing async callable: a ``name`` + JSON-schema
``parameters`` the LLM sees when deciding what to call, and a ``handler`` the tool
node invokes.  Tools are *instantiation parameters* of
:func:`~agentkit.orchestrations.react.build_react_orchestration_graph` (ADR-0008),
not globals — so a capability composes its own tool set and tests inject fakes
without touching any registry.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from agentkit.tools.dispatch import MAX_PARALLEL_TOOL_CALLS, dispatch_tool_calls


@dataclass(frozen=True)
class Tool:
    """A named, self-describing async tool the ReAct loop can call.

    * ``name``        — the identifier the LLM emits in a tool call.
    * ``description`` — shown to the LLM so it knows when to call the tool.
    * ``parameters``  — JSON schema for ``arguments`` (advertised to the LLM).
    * ``handler``     — ``async (arguments: dict) -> str`` returning the tool result
      text that is fed back into the conversation as a ``role=tool`` message.
    """

    name: str
    description: str
    handler: Callable[[dict[str, Any]], Awaitable[str]]
    parameters: dict[str, Any] = field(default_factory=dict)

    async def run(self, arguments: dict[str, Any]) -> str:
        return await self.handler(arguments)

    def schema(self) -> dict[str, Any]:
        """The advertisement the LLM node injects into the system prompt."""
        return {"name": self.name, "description": self.description, "parameters": self.parameters}


__all__ = ["MAX_PARALLEL_TOOL_CALLS", "Tool", "dispatch_tool_calls"]
