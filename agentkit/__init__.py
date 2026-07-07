"""agentkit — a standalone LangGraph agent substrate.

Hard-forked out of DeepTutor (see ``docs/adr/0009``), agentkit rebuilds the agent
substrate on LangGraph primitives with a single unified **Agent** leaf contract
and three **Orchestration** archetypes.  The package is self-contained: it
imports **nothing** from ``deeptutor.*`` and every leaf Agent depends only on an
injected :class:`~agentkit.deps.AgentDeps` bundle (ADR-0003), never on a global
singleton.

This first tracer bullet (issue #1) ships the foundation plus the
``math_animator`` and ``visualize`` orchestrations.
"""

from __future__ import annotations

from agentkit.deps import AgentConfig, AgentDeps, AgentParams, LLMClient, PromptProvider, Renderer
from agentkit.orchestrations.math_animator import build_math_animator_graph
from agentkit.orchestrations.visualize import build_visualize_graph
from agentkit.runtime.bridge import run_to_stream_bus
from agentkit.runtime.checkpointer import make_checkpointer
from agentkit.runtime.stream import StreamEvent, StreamEventType
from agentkit.runtime.stream_bus import StreamBus

__all__ = [
    "AgentConfig",
    "AgentDeps",
    "AgentParams",
    "LLMClient",
    "PromptProvider",
    "Renderer",
    "StreamBus",
    "StreamEvent",
    "StreamEventType",
    "build_math_animator_graph",
    "build_visualize_graph",
    "make_checkpointer",
    "run_to_stream_bus",
]

__version__ = "0.1.0"
