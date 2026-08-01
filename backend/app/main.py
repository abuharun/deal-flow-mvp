import re
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings
from app.db import alembic_script_head, build_engine, build_readiness_probe, build_sessionmaker
from app.errors import register_error_handlers
from app.routers.auth import router as auth_router
from app.routers.founder_analysis import router as founder_analysis_router
from app.routers.founder_consent import router as founder_consent_router
from app.routers.founder_decks import router as founder_decks_router
from app.routers.founder_payment import router as founder_payment_router
from app.routers.founder_startups import router as founder_startups_router
from app.routers.health import router as health_router
from app.security.client_ip import parse_trusted_proxies
from app.security.rate_limit import RateLimiter
from app.services.email_service import (
    ConsoleEmailTransport,
    EmailTransport,
    create_email_transport,
)

REQUEST_ID_HEADER = "X-Request-ID"
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")

# Credentialed CORS must stay exact: explicit origins from validated Settings
# (which reject any wildcard), explicit methods and headers, never `*`.
CORS_ALLOW_METHODS = ("GET", "POST", "PATCH", "DELETE", "OPTIONS")
CORS_ALLOW_HEADERS = ("Authorization", "Content-Type", REQUEST_ID_HEADER)
CORS_EXPOSE_HEADERS = (REQUEST_ID_HEADER,)

# Auth responses carry or set credentials (tokens, cookies) and their errors
# reveal account-flow state; none of it may land in any HTTP cache.
_AUTH_PATH_PREFIX = "/auth/"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    engine = build_engine(settings.database_url)
    app.state.engine = engine
    app.state.sessionmaker = build_sessionmaker(engine)
    app.state.readiness_probe = build_readiness_probe(engine, alembic_script_head())

    # An injected transport (tests, CLI) wins; otherwise the app owns one for
    # its lifetime. No network client ever exists at import time — the httpx
    # client for Resend modes is created here and closed on shutdown.
    owned_http_client = None
    transport = app.state.injected_email_transport
    if transport is None:
        if settings.email_mode == "console":
            transport = ConsoleEmailTransport()
        else:
            import httpx  # deferred so console-only deployments never import it

            owned_http_client = httpx.AsyncClient(timeout=httpx.Timeout(10.0))
            transport = create_email_transport(settings, http_client=owned_http_client)
    app.state.email_transport = transport

    try:
        yield
    finally:
        if owned_http_client is not None:
            await owned_http_client.aclose()
        await engine.dispose()


def create_app(
    settings: Settings | None = None,
    email_transport: EmailTransport | None = None,
    rate_limiter: RateLimiter | None = None,
) -> FastAPI:
    # No explicit settings (the uvicorn --factory path) → load from env/.env.
    app = FastAPI(lifespan=lifespan)
    app.state.settings = settings if settings is not None else Settings()
    app.state.injected_email_transport = email_transport
    # Per-app-instance limiter (injectable for tests): single-process pilot
    # protection only — a shared/Redis limiter is required before scaling
    # beyond one process. Never a module-level global.
    app.state.rate_limiter = rate_limiter if rate_limiter is not None else RateLimiter()
    # Parsed once here so per-request client-IP resolution never re-parses
    # (or mis-parses) the configured CIDRs.
    app.state.trusted_proxy_networks = parse_trusted_proxies(app.state.settings.trusted_proxy_cidrs)

    # Added first, so it runs innermost: canonical error responses (produced
    # just outside the router) still pass through it and get CORS headers,
    # while the request-id middleware below stays outermost.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(app.state.settings.frontend_origins),
        allow_credentials=True,
        allow_methods=list(CORS_ALLOW_METHODS),
        allow_headers=list(CORS_ALLOW_HEADERS),
        expose_headers=list(CORS_EXPOSE_HEADERS),
    )

    @app.middleware("http")
    async def auth_no_store_middleware(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith(_AUTH_PATH_PREFIX):
            response.headers["Cache-Control"] = "no-store"
            response.headers["Pragma"] = "no-cache"
        return response

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        supplied = request.headers.get(REQUEST_ID_HEADER, "")
        request_id = supplied if _SAFE_REQUEST_ID.fullmatch(supplied) else uuid.uuid4().hex
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response

    register_error_handlers(app)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(founder_startups_router)
    app.include_router(founder_decks_router)
    app.include_router(founder_payment_router)
    app.include_router(founder_consent_router)
    app.include_router(founder_analysis_router)
    return app
