"""``ReActState`` — the loop-archetype Orchestration State (ADR-0004 / ADR-0008).

Extends :class:`~agentkit.state.base.BaseState` with the ReAct control fields: the
running ``iteration`` count that the conditional edge gates on (ADR-0005 — the loop
is a *visible* cycle whose bound lives in State, not buried in a node), the
``pending_tool_calls`` handed from the LLM node to the tool node, and the terminal
``final_text`` / ``status``.  The evolving conversation rides ``messages`` via the
``BaseState`` ``operator.add`` reducer.
"""

from __future__ import annotations

from typing import Any

from agentkit.state.base import BaseState

# Iteration ceiling for the LLM ⇄ tool cycle (ADR-0005 gate).  Matches the
# pre-fork chat / question explore budget (``DEFAULT_MAX_EXPLORE_ITERATIONS = 8``).
DEFAULT_MAX_ITERATIONS = 8


class ReActState(BaseState, total=False):
    # --- input ---
    input: str  # the task/question that seeds the loop

    # --- loop control (ADR-0005 gate) ---
    iteration: int  # completed LLM turns; gated in the conditional edge
    max_iterations: int  # per-run override of the build-time ceiling
    pending_tool_calls: list[dict[str, Any]]  # LLM node → tool node hand-off

    # --- terminal outcome ---
    final_text: str  # the loop's user-facing answer
    status: str  # "running" | "succeeded" | "finalized"
    # Why the loop was force-closed (issue #3 forced-收尾): "budget" (iteration
    # gate) | "error" (LLM/provider exhaustion salvage).  Unset on a clean finish.
    finalize_reason: str


__all__ = ["DEFAULT_MAX_ITERATIONS", "ReActState"]
