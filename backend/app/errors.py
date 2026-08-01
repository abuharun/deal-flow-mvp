"""Canonical error envelope shared by all API error responses."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message_key: str,
        detail: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.message_key = message_key
        self.detail = detail
        self.headers = headers


def error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message_key: str,
    detail: str,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        headers=headers,
        content={
            "error": {
                "code": code,
                "message_key": message_key,
                "detail": detail,
                "request_id": getattr(request.state, "request_id", ""),
            }
        },
    )


def _safe_validation_summary(exc: RequestValidationError) -> str:
    """Field names and pydantic error types only — never submitted values.

    Pydantic's own `msg`/`input` fields can echo user input (notably from the
    email validator), so they are deliberately excluded.
    """
    parts: list[str] = []
    for error in exc.errors():
        loc = ".".join(str(piece) for piece in error.get("loc", ()) if piece != "body")
        parts.append(f"{loc or 'request'}: {error.get('type', 'invalid')}")
    return "; ".join(dict.fromkeys(parts))


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
        return error_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            message_key=exc.message_key,
            detail=exc.detail,
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return error_response(
            request,
            status_code=422,
            code="VALIDATION_FAILED",
            message_key="errors.validationFailed",
            detail=_safe_validation_summary(exc),
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        # Catch-all: exception text can carry SQL fragments, driver detail,
        # or submitted values, so only a fixed safe envelope leaves the app.
        # Starlette still re-raises after this response, so server logs keep
        # the full traceback.
        return error_response(
            request,
            status_code=500,
            code="SERVER_ERROR",
            message_key="errors.serverError",
            detail="an unexpected error occurred",
        )
