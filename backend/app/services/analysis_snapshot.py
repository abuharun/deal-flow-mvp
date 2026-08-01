"""Immutable, in-memory-only analysis input snapshot for one claimed job.

Contract: everything the OpenAI provider adapter sees comes from exactly this
snapshot -- never a live query, never raw deck bytes, never the ORM objects
themselves. Every founder/deck-provided string is wrapped in `Untrusted`,
which exists purely as a type-level reminder: wherever a value is read out of
it, the caller is handling UNTRUSTED DATA that must be labeled as data (never
as instructions) in any prompt built from it -- this is the load-bearing
defense against prompt injection from deck text, submission answers, or a
dataroom URL.

Nothing built here is ever persisted: report provenance already records
model/prompt/input_revision (see app.services.analysis_report_service); a raw
snapshot or provider body must never land in a row, a log, or an audit entry.

Callers must already hold row locks on both `job` (analysis_repository.
get_for_update) and `startup` (startup_repository.get_for_update, with
with_submission=True) -- the same convention as complete_job_with_report.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Startup
from app.models.analysis_job import AnalysisJob
from app.models.payment import PAYMENT_STATUS_PAID
from app.repositories import payment_repository
from app.security.urls import normalize_safe_http_url
from app.services.consent_service import current_ai_privacy_consent_granted
from app.services.deck_storage import DeckStorage
from app.services.deck_text_extraction import DeckTextExtractionError, extract_deck_text

# Pilot cap on each founder-provided answer fed to the provider prompt.
MAX_FIELD_CHARS = 4000


class SnapshotError(Exception):
    """The snapshot cannot be built. `reason` is a fixed, safe catalogue value."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"cannot build analysis snapshot: {reason}")
        self.reason = reason


@dataclass(frozen=True, slots=True)
class Untrusted:
    """Founder- or deck-provided text: DATA, never instructions.

    Every prompt-building call site must treat `.value` as untrusted content
    to be labeled and quoted, never concatenated as if it were a system or
    developer instruction.
    """

    value: str


def _bounded(value: str | None, *, max_chars: int = MAX_FIELD_CHARS) -> Untrusted:
    text = value or ""
    return Untrusted(text[:max_chars])


def _bounded_or_none(value: str | None, *, max_chars: int = MAX_FIELD_CHARS) -> Untrusted | None:
    if not value:
        return None
    return Untrusted(value[:max_chars])


def _safe_dataroom_url(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return normalize_safe_http_url(value)
    except ValueError:
        # An unsafe/unparseable dataroom URL must never abort analysis and
        # must never be forwarded verbatim -- silently drop it.
        return None


@dataclass(frozen=True, slots=True)
class AnalysisInputSnapshot:
    startup_id: uuid.UUID
    job_id: uuid.UUID
    input_revision: int

    startup_name: Untrusted
    one_liner: Untrusted
    sector: Untrusted
    funding_stage: Untrusted
    city: Untrusted

    problem: Untrusted
    product: Untrusted
    market: Untrusted
    traction: Untrusted
    team: Untrusted
    ask: Untrusted
    revenue: Untrusted | None
    growth: Untrusted | None
    ask_amount: int | None
    dataroom_url: str | None

    deck_text: Untrusted
    deck_text_truncated: bool


async def build_snapshot(
    session: AsyncSession,
    *,
    job: AnalysisJob,
    startup: Startup,
    deck_storage: DeckStorage,
) -> AnalysisInputSnapshot:
    """Validate every precondition, then build the bounded in-memory snapshot.

    Raises SnapshotError (never a bare provider/DB exception) if the job
    doesn't belong to this startup, input_revision has drifted, consent or
    payment is missing, the deck is missing, or the deck's text cannot be
    safely extracted.
    """
    if job.startup_id != startup.id:
        raise SnapshotError("job_startup_mismatch")
    if startup.input_revision != job.input_revision:
        raise SnapshotError("input_revision_mismatch")

    if not await current_ai_privacy_consent_granted(session, startup=startup):
        raise SnapshotError("consent_missing")

    payment = await payment_repository.get_for_startup(session, startup_id=startup.id)
    if payment is None or payment.status != PAYMENT_STATUS_PAID:
        raise SnapshotError("payment_not_paid")

    # Verify the AUTHORIZED, current deck for this exact startup before ever
    # touching its bytes: a metadata-only lookup first, then confirm the
    # content fetch returns metadata for that SAME row (id/sha256/size) --
    # defense in depth against ever analyzing arbitrary/wrong-row bytes.
    metadata = await deck_storage.get_metadata(startup.id)
    if metadata is None:
        raise SnapshotError("deck_missing")

    deck = await deck_storage.get_content(startup.id)
    if deck is None:
        raise SnapshotError("deck_missing")
    content_metadata, content = deck
    if (
        content_metadata.startup_id != startup.id
        or content_metadata.id != metadata.id
        or content_metadata.sha256 != metadata.sha256
        or content_metadata.size_bytes != len(content)
    ):
        raise SnapshotError("deck_missing")

    try:
        extracted = extract_deck_text(content)
    except DeckTextExtractionError as exc:
        raise SnapshotError(f"deck_{exc.reason}") from None

    submission = startup.submission

    return AnalysisInputSnapshot(
        startup_id=startup.id,
        job_id=job.id,
        input_revision=job.input_revision,
        startup_name=_bounded(startup.name),
        one_liner=_bounded(startup.one_liner),
        sector=_bounded(startup.sector),
        funding_stage=_bounded(startup.funding_stage),
        city=_bounded(startup.city),
        problem=_bounded(submission.problem if submission else None),
        product=_bounded(submission.product if submission else None),
        market=_bounded(submission.market if submission else None),
        traction=_bounded(submission.traction if submission else None),
        team=_bounded(submission.team if submission else None),
        ask=_bounded(submission.ask if submission else None),
        revenue=_bounded_or_none(submission.revenue if submission else None),
        growth=_bounded_or_none(submission.growth if submission else None),
        ask_amount=submission.ask_amount if submission else None,
        dataroom_url=_safe_dataroom_url(submission.dataroom_url if submission else None),
        deck_text=Untrusted(extracted.text),
        deck_text_truncated=extracted.truncated,
    )
