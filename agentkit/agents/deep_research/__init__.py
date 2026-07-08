"""deep_research Agent leaves (ADR-0006 dynamic-parallel archetype)."""

from __future__ import annotations

from agentkit.agents.deep_research.report import report_node
from agentkit.agents.deep_research.worker import research_worker_node

__all__ = ["report_node", "research_worker_node"]
