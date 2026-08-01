from fastapi import APIRouter, Request

from app.db import NotReadyError
from app.errors import ApiError

router = APIRouter()


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(request: Request) -> dict[str, str]:
    probe = request.app.state.readiness_probe
    try:
        await probe()
    except NotReadyError as exc:
        raise ApiError(503, "NOT_READY", "errors.notReady", exc.detail) from exc
    return {"status": "ready"}
