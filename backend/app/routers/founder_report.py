"""Founder-only immutable AI-report read endpoint (/founder/startups/{id}/report).

Access model mirrors the other founder-startup routes: founder bearer
principal (VC gets the canonical 403), a founder-scoped SQL lookup (foreign
== unknown == one canonical 404 STARTUP_NOT_FOUND), and no Origin requirement
-- this is a read, never a mutation.

A startup with no report yet (job never triggered, still running, or
otherwise incomplete) answers the canonical 404 REPORT_NOT_FOUND, distinct
from STARTUP_NOT_FOUND so a caller can tell "wrong startup" from "no report
on this one yet" without either leaking ownership. The response is an
explicit safe projection (report body re-validated through ReportBody,
normalized sources, provenance, and `stale`) -- never the underlying
analysis job's internal bookkeeping or any raw provider data.
"""

from uuid import UUID

from fastapi import APIRouter

from app.deps import SessionDep
from app.errors import ApiError
from app.models.analysis_report import AnalysisReport, ReportSource
from app.routers.founder_startups import FounderPrincipal, _load_owned_startup
from app.schemas.report import ReportDetailResponse
from app.services import analysis_report_service
from app.services.analysis_report_service import ReportNotFoundError

router = APIRouter(prefix="/founder/startups/{startup_id}/report", tags=["founder-report"])


def _report_not_found() -> ApiError:
    return ApiError(404, "REPORT_NOT_FOUND", "errors.reportNotFound", "no report on record")


def _to_response(
    report: AnalysisReport, sources: list[ReportSource], *, stale: bool
) -> ReportDetailResponse:
    return ReportDetailResponse(
        id=report.id,
        startup_id=report.startup_id,
        schema_version=report.schema_version,
        language=report.language,
        report=report.report,
        sources=sources,
        model=report.model,
        prompt_version=report.prompt_version,
        partial=report.partial,
        evidence_count=report.evidence_count,
        input_revision=report.input_revision,
        generated_at=report.generated_at,
        created_at=report.created_at,
        stale=stale,
    )


@router.get("")
async def get_report(
    startup_id: UUID, principal: FounderPrincipal, session: SessionDep
) -> ReportDetailResponse:
    startup = await _load_owned_startup(session, startup_id, principal)
    try:
        report, sources, stale = await analysis_report_service.get_report_for_startup(
            session, startup=startup
        )
    except ReportNotFoundError:
        raise _report_not_found() from None
    return _to_response(report, sources, stale=stale)
