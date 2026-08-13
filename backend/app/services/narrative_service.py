"""Founder-editable pitch narrative: seeding, saving, and history reads.

Product contract (MVP): ONE free-text narrative per startup, written in
whatever language the founder chooses -- nothing here takes or stores a
locale. The narrative starts life as a copy of the immutable report's
`pitch_narrative_draft`, materialized the first time the founder reads it,
and every save that actually changes the text appends a new immutable
version. Nothing ever rewrites a version: `narrative_versions` rejects
UPDATE/DELETE at the database level, and the only thing that moves is the
current pointer.

Transaction contract (same as every other service in this codebase): rows
and their audit trail are staged and flushed but never committed -- the
endpoint owns the boundary, so a version, the pointer that names it, and the
audit row describing the save commit or roll back together.

Locking contract: callers that may write (`seed_from_report`,
`save_narrative`) must already hold the startup's row lock
(`_load_owned_startup(..., for_update=True)`). That is what serializes
version allocation, so `current_version + 1` cannot be handed out twice; the
UNIQUE (startup_id, version) constraint is the backstop, not the mechanism.
`get_current`, `list_versions`, and `get_version` are read-only and take no
lock.

Audit hygiene: metadata carries only IDs, the version number, its source,
input_revision, and the text's LENGTH -- never a character of the narrative
itself, which is the founder's private writing.
"""

import uuid

from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AnalysisReport, AuditActorType, NarrativeVersion, Startup, StartupNarrative
from app.models.narrative import SOURCE_FOUNDER_EDIT, SOURCE_REPORT_SEED
from app.repositories import analysis_report_repository, narrative_repository
from app.schemas.narrative import normalize_narrative_content
from app.services.audit_service import write_audit
from app.services.startup_service import StartupLockedError, is_locked

__all__ = [
    "NarrativeNotReadyError",
    "NarrativeVersionNotFoundError",
    "get_current",
    "get_version",
    "list_versions",
    "save_narrative",
    "seed_from_report",
]

PITCH_NARRATIVE_DRAFT_KEY = "pitch_narrative_draft"


class NarrativeNotReadyError(Exception):
    """There is no completed report to seed the narrative from yet.

    The narrative is defined as an edit of the AI report's draft, so before
    a report exists there is nothing to edit -- distinct from "this startup
    does not exist" (404) and from "this startup is frozen" (STARTUP_LOCKED).
    """


class NarrativeVersionNotFoundError(Exception):
    """This startup's history has no such version number."""


def _seed_content(report: AnalysisReport) -> str:
    """The report's pitch narrative draft, normalized like founder input.

    report.v1 guarantees a non-empty draft, but it is provider-produced
    text: running it through the same normalization the PATCH body gets
    means a stray control character can never reach (and be rejected by) the
    column's CHECK constraint as a 500. A draft that cannot survive that is
    treated as nothing to seed from.
    """
    draft = report.report.get(PITCH_NARRATIVE_DRAFT_KEY) if report.report else None
    if not isinstance(draft, str):
        raise NarrativeNotReadyError
    try:
        return normalize_narrative_content(draft)
    except ValueError as exc:
        raise NarrativeNotReadyError from exc


async def _audit(
    session: AsyncSession,
    *,
    startup: Startup,
    version: NarrativeVersion,
    action: str,
) -> None:
    await write_audit(
        session,
        actor_type=AuditActorType.USER,
        actor_id=version.created_by,
        action=action,
        entity_type="startup",
        entity_id=startup.id,
        metadata={
            "startup_id": str(startup.id),
            "narrative_version_id": str(version.id),
            "version": version.version,
            "source": version.source,
            "report_id": str(version.report_id),
            "input_revision": version.input_revision,
            # Length only: the narrative text itself never enters the trail.
            # Spelled "character_count" rather than "content_length" on
            # purpose -- the shared redaction policy masks any key matching
            # /content/, which would store "[REDACTED]" instead of a number.
            "character_count": len(version.content),
        },
    )


async def _append(
    session: AsyncSession,
    *,
    startup: Startup,
    actor_id: uuid.UUID,
    content: str,
    version_number: int,
    source: str,
    report_id: uuid.UUID,
    action: str,
) -> tuple[StartupNarrative, NarrativeVersion]:
    """Insert one immutable version, move the pointer, and audit it."""
    version = await narrative_repository.insert_version(
        session,
        version=NarrativeVersion(
            startup_id=startup.id,
            version=version_number,
            content=content,
            source=source,
            report_id=report_id,
            input_revision=startup.input_revision,
            created_by=actor_id,
        ),
    )
    current = await narrative_repository.set_current_version(
        session, startup_id=startup.id, version=version_number
    )
    # created_at/updated_at are database-stamped; refresh so the response
    # reports what was actually written, not None.
    await session.refresh(version, ("created_at",))
    await session.refresh(current, ("updated_at",))
    await _audit(session, startup=startup, version=version, action=action)
    return current, version


async def get_current(
    session: AsyncSession, *, startup: Startup
) -> tuple[StartupNarrative, NarrativeVersion] | None:
    """The current narrative, or None if it has never been materialized."""
    return await narrative_repository.get_current_with_version(session, startup_id=startup.id)


async def seed_from_report(
    session: AsyncSession, *, startup: Startup, actor_id: uuid.UUID
) -> tuple[StartupNarrative, NarrativeVersion, bool]:
    """Materialize version 1 from the report draft, once. Idempotent.

    Re-checks for an existing narrative first, so two concurrent first reads
    serialized by the startup's row lock produce exactly one version 1: the
    second call sees the first's committed row and seeds nothing.

    Seeding is deliberately allowed on a VC-visible (locked) startup: it
    copies immutable report text rather than accepting founder input, and a
    locked startup must still be readable. Only `save_narrative` is refused.
    """
    existing = await narrative_repository.get_current_with_version(session, startup_id=startup.id)
    if existing is not None:
        return existing[0], existing[1], False

    report = await analysis_report_repository.get_for_startup(session, startup_id=startup.id)
    if report is None:
        raise NarrativeNotReadyError
    current, version = await _append(
        session,
        startup=startup,
        actor_id=actor_id,
        content=_seed_content(report),
        version_number=1,
        source=SOURCE_REPORT_SEED,
        report_id=report.id,
        action="startup.narrative_seed",
    )
    return current, version, True


async def save_narrative(
    session: AsyncSession, *, startup: Startup, actor_id: uuid.UUID, content: str
) -> tuple[StartupNarrative, NarrativeVersion, bool]:
    """Append the founder's text as the next version, unless nothing changed.

    Returns (current pointer, current version, changed). An identical save is
    a no-op: autosave retries and re-submits of unchanged text must not pad
    the history with duplicate versions, and nothing is audited for them.

    A never-read narrative is seeded first, so version 1 is always the
    report's draft and the founder's own text lands as version 2 -- the
    lineage stays legible no matter which endpoint the founder touched first.
    """
    if is_locked(startup):
        raise StartupLockedError
    current, version, _ = await seed_from_report(session, startup=startup, actor_id=actor_id)

    if content == version.content:
        return current, version, False

    current, version = await _append(
        session,
        startup=startup,
        actor_id=actor_id,
        content=content,
        version_number=current.current_version + 1,
        source=SOURCE_FOUNDER_EDIT,
        # The lineage's report: exactly one report exists per startup, and an
        # edit never re-parents the narrative onto a different one.
        report_id=version.report_id,
        action="startup.narrative_edit",
    )
    return current, version, True


async def list_versions(
    session: AsyncSession, *, startup: Startup
) -> tuple[StartupNarrative, list[Row]]:
    """The pointer plus every version's metadata, ascending. Read-only."""
    current = await narrative_repository.get_current(session, startup_id=startup.id)
    if current is None:
        raise NarrativeNotReadyError
    summaries = await narrative_repository.list_version_summaries(session, startup_id=startup.id)
    return current, summaries


async def get_version(session: AsyncSession, *, startup: Startup, version: int) -> NarrativeVersion:
    """One immutable version of this startup's narrative. Read-only."""
    row = await narrative_repository.get_version(session, startup_id=startup.id, version=version)
    if row is None:
        raise NarrativeVersionNotFoundError
    return row
