"""Founder AI/privacy consent grants: explicit, versioned, per startup.

Transaction contract (same as the other services): every function stages
rows and flushes but never commits — the endpoint owns the boundary.

Product contract: consent rows are append-only. Granting again at the same
(startup, kind, text_version) is idempotent — it returns the existing row,
never a duplicate. A never-yet-granted text_version is a brand-new grant
that leaves every earlier version's row untouched, so history is preserved
and future input changes never silently revoke a prior grant. There is no
revoke endpoint in this slice.

Audit hygiene: metadata carries only IDs, kind, and text_version — never any
policy text.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditActorType, Consent, Startup
from app.models.consent import CONSENT_KIND_AI_PRIVACY, CURRENT_AI_PRIVACY_VERSION
from app.repositories import consent_repository
from app.services.audit_service import write_audit
from app.services.startup_service import StartupLockedError, is_locked


class ConsentVersionInvalidError(Exception):
    """The requested kind/text_version is not the currently supported one."""


def ensure_consent_mutable(startup: Startup) -> None:
    """Refuse consent mutations once the startup is VC-visible."""
    if is_locked(startup):
        raise StartupLockedError


async def _audit(session: AsyncSession, startup: Startup, consent: Consent) -> None:
    await write_audit(
        session,
        actor_type=AuditActorType.USER,
        actor_id=startup.founder_id,
        action="startup.consent_grant",
        entity_type="startup",
        entity_id=startup.id,
        metadata={
            "status": startup.status.value,
            "consent_id": str(consent.id),
            "kind": consent.kind,
            "text_version": consent.text_version,
        },
    )


async def grant_consent(
    session: AsyncSession, *, startup: Startup, kind: str, text_version: str
) -> tuple[Consent, bool]:
    """Record an explicit consent grant. Returns (consent, created)."""
    ensure_consent_mutable(startup)
    if kind != CONSENT_KIND_AI_PRIVACY or text_version != CURRENT_AI_PRIVACY_VERSION:
        raise ConsentVersionInvalidError

    existing = await consent_repository.get(
        session, startup_id=startup.id, kind=kind, text_version=text_version
    )
    if existing is not None:
        return existing, False

    consent = Consent(
        startup_id=startup.id, founder_id=startup.founder_id, kind=kind, text_version=text_version
    )
    session.add(consent)
    await session.flush()
    await _audit(session, startup, consent)
    return consent, True


async def current_ai_privacy_consent_granted(session: AsyncSession, *, startup: Startup) -> bool:
    """Whether the startup already has a grant at the CURRENT ai_privacy version."""
    existing = await consent_repository.get(
        session,
        startup_id=startup.id,
        kind=CONSENT_KIND_AI_PRIVACY,
        text_version=CURRENT_AI_PRIVACY_VERSION,
    )
    return existing is not None
