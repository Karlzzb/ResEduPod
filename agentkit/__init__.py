"""agentkit — a standalone LangGraph agent substrate.

Hard-forked out of DeepTutor (see ``docs/adr/0009``), agentkit rebuilds the agent
substrate on LangGraph primitives with a single unified **Agent** leaf contract
and three **Orchestration** archetypes.  The package is self-contained: it
imports **nothing** from ``deeptutor.*`` and every leaf Agent depends only on an
injected :class:`~agentkit.deps.AgentDeps` bundle (ADR-0003), never on a global
singleton.

The tracer bullets landed so far: the foundation plus ``math_animator`` /
``visualize`` (issue #1), the ``ReActOrchestration`` loop template with its
``question`` instance (issue #2), and the ``chat``-loop robustness behaviours —
multi-level provider degradation, context-window protection, forced 收尾, and
thinking-tag filtering — carried onto that template (issue #3).
"""

from __future__ import annotations

from agentkit.deps import AgentConfig, AgentDeps, AgentParams, LLMClient, PromptProvider, Renderer
from agentkit.orchestrations.math_animator import build_math_animator_graph
from agentkit.orchestrations.question import build_question_graph
from agentkit.orchestrations.react import build_react_orchestration_graph
from agentkit.orchestrations.visualize import build_visualize_graph
from agentkit.runtime.bridge import run_to_stream_bus
from agentkit.runtime.checkpointer import make_checkpointer
from agentkit.runtime.stream import StreamEvent, StreamEventType
from agentkit.runtime.stream_bus import StreamBus
from agentkit.tools import MAX_PARALLEL_TOOL_CALLS, Tool

__all__ = [
    "MAX_PARALLEL_TOOL_CALLS",
    "AgentConfig",
    "AgentDeps",
    "AgentParams",
    "LLMClient",
    "PromptProvider",
    "Renderer",
    "StreamBus",
    "StreamEvent",
    "StreamEventType",
    "Tool",
    "build_math_animator_graph",
    "build_question_graph",
    "build_react_orchestration_graph",
    "build_visualize_graph",
    "make_checkpointer",
    "run_to_stream_bus",
]

__version__ = "0.1.0"
