"""Partner backend — historically consulted one of the user's own partners.

The partners layer (IM channels + partner runtime) was removed with the product
delivery tier, so this backend is now inert: it stays registered for API/UI and
registry stability (``PARTNER_BACKEND_KIND`` is still referenced by the subagent
capability), but every consult fails closed. Restoring live partner consultation
is part of re-introducing the partners layer, not this module.
"""

from __future__ import annotations

from deeptutor.services.subagent.base import OnEvent, SubagentBackend
from deeptutor.services.subagent.config import BackendConfig
from deeptutor.services.subagent.types import ConsultResult, DetectResult

PARTNER_BACKEND_KIND = "partner"


class PartnerBackend(SubagentBackend):
    """Inert partner backend — registered but unavailable (partners removed)."""

    kind = PARTNER_BACKEND_KIND
    display_name = "Partner"
    cli_command = ""
    local_cli = False

    async def detect(self) -> DetectResult:
        return DetectResult(
            kind=self.kind,
            display_name=self.display_name,
            available=False,
            detail="Partner backends are unavailable in this build (partners layer removed).",
        )

    async def consult(
        self,
        question: str,
        *,
        on_event: OnEvent,
        cwd: str | None = None,  # noqa: ARG002 — CLI-only; partners have no cwd
        session_id: str | None = None,  # noqa: ARG002 — partner session key, unused now
        config: BackendConfig | None = None,  # noqa: ARG002 — partner runs its own soul
        images: list[str] | None = None,  # noqa: ARG002 — no partner runtime to receive them
        partner_id: str | None = None,  # noqa: ARG002 — no partner to bind to
    ) -> ConsultResult:
        return ConsultResult(
            success=False,
            error="Partner backends are unavailable in this build (partners layer removed).",
        )


__all__ = ["PARTNER_BACKEND_KIND", "PartnerBackend"]
