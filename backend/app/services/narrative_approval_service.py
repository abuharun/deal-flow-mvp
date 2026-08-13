"""Founder approval: freeze one narrative version and go VC-visible.

Product contract: going VC-visible is an explicit act by the founder, never a
side effect of finishing an analysis. Approving records WHICH immutable
narrative version was approved, WHO approved it, and WHEN, and in the same
transaction moves the startup to its locked, VC-visible state. From then on
that exact text is what an investor will read: the approval stores no copy of
it, it names the version row, and the database refuses both a new version and
any movement of the current pointer for an approved startup.

What approval is NOT: a delivery. No email is sent, no investor is assigned,
and nothing is queued. Which investors may see an approved startup, and when,
is deliberately left as future work -- the audience policy is not decided
here.

Preconditions, checked in this order so the failure a founder sees is the one
that actually blocks them:
1. Already approved? The same version again is idempotent (nothing is written
   and nothing is audited); a DIFFERENT version is the canonical
   STARTUP_LOCKED -- the narrative is frozen and cannot be re-pointed.
2. Locked by any other means -> StartupLockedError.
3. A completed, immutable analysis report exists (the narrative is defined as
   an edit of its draft).
4. A current narrative version exists. Approval never seeds one: a founder
   must have actually looked at the narrative before freezing it.
5. The version the founder named IS the current one. A mismatch is refused,
   never coerced -- an edit saved in another tab must not be approved unseen.

Transaction contract (same as every other service in this codebase): rows and
their audit trail are staged and flushed but never committed -- the endpoint
owns the boundary, so the approval, the startup's transition, and the audit
row commit or roll back together.

Locking contract: `approve_narrative` must be called with the startup's row
lock already held (`_load_owned_startup(..., for_update=True)`). That is what
serializes two concurrent approvals; the UNIQUE (startup_id) constraint is
the backstop, not the mechanism. `get_approval` is read-only and takes no
lock.

Audit hygiene: metadata carries only IDs, the version number, its source and
input_revision -- never a character of the narrative or of the report.
"""

import uuid

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AuditActorType,
    NarrativeApproval,
    NarrativeVersion,
    Startup,
    StartupStatus,
)
from app.repositories import (
    analysis_report_repository,
    narrative_approval_repository,
    narrative_repository,
)
from app.services.audit_service import write_audit
from app.services.narrative_service import NarrativeNotReadyError
from app.services.startup_service import StartupLockedError, is_locked

__all__ = [
    "NarrativeApprovalNotFoundError",
    "NarrativeVersionMismatchError",
    "approve_narrative",
    "get_approval",
]

APPROVAL_ACTION = "startup.narrative_approved"


class NarrativeApprovalNotFoundError(Exception):
    """This startup's narrative has not been approved yet."""


class NarrativeVersionMismatchError(Exception):
    """The named version is not the startup's current narrative version.

    Carries the current version number so the founder can be told what to
    re-read -- their own data, never another startup's.
    """

    def __init__(self, *, requested: int, current: int) -> None:
        super().__init__(f"version {requested} is not the current version {current}")
        self.requested = requested
        self.current = current


async def get_approval(
    session: AsyncSession, *, startup: Startup
) -> tuple[NarrativeApproval, NarrativeVersion]:
    """The approval and the exact frozen version. Read-only.

    The version comes back verbatim however much history precedes it: it is
    an immutable row, named by id, that nothing can rewrite.
    """
    approved = await narrative_approval_repository.get_with_version(session, startup_id=startup.id)
    if approved is None:
        raise NarrativeApprovalNotFoundError
    return approved


async def approve_narrative(
    session: AsyncSession, *, startup: Startup, actor_id: uuid.UUID, version: int
) -> tuple[NarrativeApproval, NarrativeVersion, bool]:
    """Freeze `version` and lock the startup. Returns (approval, version, created).

    `created` is False when this exact version was already approved: a retried
    or double-clicked approval must be safe, so nothing is written and nothing
    is audited the second time.
    """
    existing = await narrative_approval_repository.get_with_version(session, startup_id=startup.id)
    if existing is not None:
        approval, approved_version = existing
        if approval.version != version:
            # The narrative is frozen; approving something else would mean
            # replacing what an investor was promised.
            raise StartupLockedError
        return approval, approved_version, False

    if is_locked(startup):
        raise StartupLockedError

    report = await analysis_report_repository.get_for_startup(session, startup_id=startup.id)
    if report is None:
        raise NarrativeNotReadyError
    current = await narrative_repository.get_current_with_version(session, startup_id=startup.id)
    if current is None:
        raise NarrativeNotReadyError
    _, current_version = current
    if current_version.version != version:
        raise NarrativeVersionMismatchError(requested=version, current=current_version.version)

    approval = await narrative_approval_repository.insert_approval(
        session,
        approval=NarrativeApproval(
            startup_id=startup.id,
            narrative_version_id=current_version.id,
            version=current_version.version,
            # The version's own report: exactly one report exists per startup,
            # and the composite FK refuses any other value anyway.
            report_id=current_version.report_id,
            approved_by=actor_id,
        ),
    )
    startup.status = StartupStatus.VC_VISIBLE
    startup.vc_visible_at = func.now()  # DB time, refreshed below for the response
    await session.flush()
    await session.refresh(approval, ("approved_at",))
    await session.refresh(startup, ("vc_visible_at", "updated_at"))

    await write_audit(
        session,
        actor_type=AuditActorType.USER,
        actor_id=actor_id,
        action=APPROVAL_ACTION,
        entity_type="startup",
        entity_id=startup.id,
        metadata={
            "startup_id": str(startup.id),
            "approval_id": str(approval.id),
            "narrative_version_id": str(current_version.id),
            "version": current_version.version,
            "source": current_version.source,
            "report_id": str(current_version.report_id),
            "input_revision": current_version.input_revision,
            "status": startup.status.value,
        },
    )
    return approval, current_version, True
