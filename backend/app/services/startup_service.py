"""Founder startup lifecycle: create, edit, autosave, submit.

Transaction contract (same as the auth services): every function stages rows
and flushes but never commits — the endpoint owns the boundary, so a startup,
its submission, and the audit row describing the action commit or roll back
together.

Audit hygiene: audit metadata carries ONLY status and input_revision. Answer
text, URLs, and financial values are the founder's private input and must
never reach the audit trail (or any log).
"""

import uuid
from collections.abc import Mapping

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditActorType, Startup, StartupStatus, Submission
from app.services.audit_service import write_audit

# Fields whose change is a material founder-input revision.
STARTUP_MATERIAL_FIELDS = frozenset({"name", "one_liner", "sector", "funding_stage", "city"})
SUBMISSION_MATERIAL_FIELDS = frozenset(
    {
        "problem",
        "product",
        "market",
        "traction",
        "team",
        "ask",
        "revenue",
        "growth",
        "ask_amount",
        "dataroom_url",
    }
)
# Step bookkeeping is autosave progress, not founder input: it persists but
# never bumps input_revision.
SUBMISSION_PROGRESS_FIELDS = frozenset({"completed_steps"})

# Submit requires every core answer to be filled in.
REQUIRED_ANSWER_FIELDS = ("problem", "product", "market", "traction", "team", "ask")


class StartupLockedError(Exception):
    """The startup is VC-visible; material founder mutations are refused."""


class StartupAlreadySubmittedError(Exception):
    """Submit was called on a startup that is no longer a draft."""


class SubmissionIncompleteError(Exception):
    """Submit was refused; carries only the MISSING field names, never values."""

    def __init__(self, missing_fields: tuple[str, ...]) -> None:
        super().__init__("submission is incomplete")
        self.missing_fields = missing_fields


def is_locked(startup: Startup) -> bool:
    """Editable until VC-visible: either signal alone locks the record."""
    return startup.vc_visible_at is not None or startup.status is StartupStatus.VC_VISIBLE


async def _audit(session: AsyncSession, startup: Startup, action: str) -> None:
    await write_audit(
        session,
        actor_type=AuditActorType.USER,
        actor_id=startup.founder_id,
        action=action,
        entity_type="startup",
        entity_id=startup.id,
        metadata={
            "status": startup.status.value,
            "input_revision": startup.input_revision,
        },
    )


async def create_startup(
    session: AsyncSession,
    *,
    founder_id: uuid.UUID,
    name: str,
    one_liner: str = "",
    sector: str = "",
    funding_stage: str = "",
    city: str = "",
) -> Startup:
    """Stage a draft startup and its empty submission as one unit of work."""
    startup = Startup(
        founder_id=founder_id,
        name=name,
        one_liner=one_liner,
        sector=sector,
        funding_stage=funding_stage,
        city=city,
        status=StartupStatus.DRAFT,
        input_revision=1,
        submission=Submission(
            problem="",
            product="",
            market="",
            traction="",
            team="",
            ask="",
            completed_steps=[],
        ),
    )
    session.add(startup)
    await session.flush()
    await _audit(session, startup, "startup.create")
    return startup


def _apply_changes(target: object, changes: Mapping[str, object], fields: frozenset[str]) -> bool:
    changed = False
    for field, value in changes.items():
        if field in fields and getattr(target, field) != value:
            setattr(target, field, value)
            changed = True
    return changed


async def update_startup(
    session: AsyncSession, *, startup: Startup, changes: Mapping[str, object]
) -> bool:
    """Apply metadata changes; bump input_revision once iff anything changed."""
    if is_locked(startup):
        raise StartupLockedError
    changed = _apply_changes(startup, changes, STARTUP_MATERIAL_FIELDS)
    if changed:
        startup.input_revision += 1
        await session.flush()
        await _audit(session, startup, "startup.update")
    return changed


async def update_submission(
    session: AsyncSession, *, startup: Startup, changes: Mapping[str, object]
) -> bool:
    """Autosave answers/steps; only material fields bump input_revision."""
    if is_locked(startup):
        raise StartupLockedError
    submission = startup.submission
    material = _apply_changes(submission, changes, SUBMISSION_MATERIAL_FIELDS)
    progress = _apply_changes(submission, changes, SUBMISSION_PROGRESS_FIELDS)
    if material:
        startup.input_revision += 1
    if material or progress:
        await session.flush()
        await _audit(session, startup, "startup.submission_update")
    return material or progress


async def submit_startup(session: AsyncSession, *, startup: Startup) -> Startup:
    """Validate completeness and move draft -> submitted exactly once."""
    if is_locked(startup):
        raise StartupLockedError
    if startup.status is not StartupStatus.DRAFT:
        raise StartupAlreadySubmittedError
    missing = tuple(
        field for field in REQUIRED_ANSWER_FIELDS if not getattr(startup.submission, field).strip()
    )
    if missing:
        raise SubmissionIncompleteError(missing)
    startup.status = StartupStatus.SUBMITTED
    startup.submitted_at = func.now()  # DB time, refreshed below for the response
    await session.flush()
    await session.refresh(startup, ("submitted_at",))
    await _audit(session, startup, "startup.submit")
    return startup
