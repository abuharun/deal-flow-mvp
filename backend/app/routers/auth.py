"""Public auth endpoints (Tasks B3-B4): a thin HTTP shell over the services.

Each endpoint owns exactly one DB transaction: the service stages every row;
the endpoint commits on success and rolls back on any failure, so no partial
signup or login can ever be observed. Login failures are committed too — the
auth.login_failed audit must survive the 401.
"""

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.deps import SessionDep, enforce_auth_rate_limit, require_allowed_origin
from app.errors import ApiError
from app.models import AuditActorType, User
from app.schemas.auth import (
    AccessTokenResponse,
    ActivateInviteRequest,
    ForgotPasswordRequest,
    LoginRequest,
    LoginResponse,
    OkResponse,
    ResetPasswordRequest,
    UserSummary,
    VerifyEmailRequest,
)
from app.security.cookies import (
    REFRESH_COOKIE_NAME,
    clear_refresh_cookie,
    set_refresh_cookie,
)
from app.security.rate_limit import (
    ACTIVATE_INVITE_SCOPE,
    FORGOT_PASSWORD_SCOPE,
    LOGIN_SCOPE,
    REFRESH_SCOPE,
    RESET_PASSWORD_SCOPE,
    VERIFY_EMAIL_SCOPE,
)
from app.security.tokens import create_access_token
from app.services import auth_service, login_service, password_reset_service
from app.services.audit_service import write_audit
from app.services.login_service import ACCESS_TOKEN_EXPIRES_IN, LoginOutcome
from app.services.session_service import (
    RotateOutcome,
    revoke_family_by_token,
    revoke_session_family,
    rotate_session,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _session_revoked_error() -> ApiError:
    # One fixed 401 for every refresh failure: missing, unknown, expired,
    # revoked, reused, and bad-user-state tokens must be indistinguishable.
    return ApiError(
        401, "AUTH_SESSION_REVOKED", "errors.sessionRevoked", "refresh session is not valid"
    )


@router.post("/activate-invite", status_code=status.HTTP_201_CREATED)
async def activate_invite(
    payload: ActivateInviteRequest, request: Request, session: SessionDep
) -> OkResponse:
    await enforce_auth_rate_limit(request, ACTIVATE_INVITE_SCOPE)
    settings = request.app.state.settings
    try:
        await auth_service.activate_invite(
            session,
            email_transport=request.app.state.email_transport,
            frontend_public_url=settings.frontend_public_url,
            token=payload.token,
            email=str(payload.email),
            password=payload.password.get_secret_value(),
            full_name=payload.full_name,
            locale=payload.locale,
        )
        await session.commit()
    except IntegrityError as exc:
        # A concurrent signup won the unique-email race; the driver message
        # (which carries SQL fragments) must never reach the client.
        await session.rollback()
        raise ApiError(
            409, "CONFLICT", "errors.conflict", "an account with this email already exists"
        ) from exc
    except Exception:
        await session.rollback()
        raise
    return OkResponse()


@router.post("/login")
async def login(
    payload: LoginRequest, request: Request, response: Response, session: SessionDep
) -> LoginResponse:
    # Before any Argon2 or DB work; both the IP and email-hash buckets must
    # admit the attempt, and a blocked one stages no audit row.
    await enforce_auth_rate_limit(request, LOGIN_SCOPE, email=str(payload.email))
    settings = request.app.state.settings
    try:
        result = await login_service.login(
            session,
            email=str(payload.email),
            password=payload.password.get_secret_value(),
            jwt_secret=settings.jwt_secret,
            user_agent=request.headers.get("user-agent"),
        )
        # Commits success rows AND the staged login_failed audit: raising the
        # 401 must not roll the failure's audit trail away.
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    if result.outcome is LoginOutcome.INVALID_CREDENTIALS:
        # One shared answer for unknown email, wrong password, and deleted
        # accounts: the response must not reveal whether the email exists.
        raise ApiError(
            401,
            "AUTH_INVALID_CREDENTIALS",
            "errors.invalidCredentials",
            "email or password is incorrect",
        )
    if result.outcome is LoginOutcome.EMAIL_UNVERIFIED:
        raise ApiError(
            401,
            "AUTH_EMAIL_UNVERIFIED",
            "errors.emailUnverified",
            "email address has not been verified",
        )
    success = result.success
    set_refresh_cookie(response, success.refresh_grant.token)
    user = success.user
    return LoginResponse(
        access_token=success.access_token,
        expires_in=success.expires_in,
        user=UserSummary(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role.value,
            locale=user.locale.value,
        ),
    )


@router.post("/refresh", dependencies=[Depends(require_allowed_origin)])
async def refresh(request: Request, response: Response, session: SessionDep) -> AccessTokenResponse:
    """Rotate the bv_refresh cookie into a fresh access token.

    No body: the only inputs are the Origin header (checked by the dependency
    before this runs) and the hardened cookie. Reuse detection commits the
    family revocation and its audit BEFORE the 401 leaves the app.
    """
    # The Origin dependency has already run; the limiter charges the IP
    # bucket before any cookie or DB handling.
    await enforce_auth_rate_limit(request, REFRESH_SCOPE)
    settings = request.app.state.settings
    token = request.cookies.get(REFRESH_COOKIE_NAME)
    if token is None:
        raise _session_revoked_error()
    try:
        rotation = await rotate_session(session, token=token)
        if rotation.outcome is RotateOutcome.REUSE:
            identity = rotation.identity
            await write_audit(
                session,
                actor_type=AuditActorType.SYSTEM,
                action="auth.refresh_reuse",
                entity_type="user",
                entity_id=identity.user_id,
                metadata={"session_family_id": str(identity.family_id)},
            )
            # The breach response must survive the 401 about to be raised.
            await session.commit()
            raise _session_revoked_error()
        if rotation.outcome is not RotateOutcome.ROTATED:
            raise _session_revoked_error()

        identity = rotation.identity
        raw_child_token = rotation.grant.token
        # Lock the users row so a concurrent delete/verify flip serializes
        # with this refresh; role and account state come from the DB, never
        # from anything the client presented.
        user = (
            await session.execute(select(User).where(User.id == identity.user_id).with_for_update())
        ).scalar_one_or_none()
        if user is None or user.deleted_at is not None or user.email_verified_at is None:
            await revoke_session_family(session, family_id=identity.family_id)
            await session.commit()
            raise _session_revoked_error()

        access_token = create_access_token(
            user_id=user.id, role=user.role, secret=settings.jwt_secret
        )
        await write_audit(
            session,
            actor_type=AuditActorType.USER,
            actor_id=user.id,
            action="auth.refresh",
            entity_type="user",
            entity_id=user.id,
            metadata={"session_family_id": str(identity.family_id)},
        )
        await session.commit()
    except ApiError:
        raise
    except Exception:
        await session.rollback()
        raise
    # Only after the commit: a rolled-back rotation must never set a cookie.
    # Max-Age is the remaining family lifetime, not a fresh 30 days.
    set_refresh_cookie(response, raw_child_token, expires_at=identity.expires_at)
    return AccessTokenResponse(access_token=access_token, expires_in=ACCESS_TOKEN_EXPIRES_IN)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_allowed_origin)],
)
async def logout(request: Request, session: SessionDep) -> Response:
    """Revoke the cookie's whole session family; idempotent and silent.

    Unknown, missing, and already-revoked tokens answer exactly like a real
    logout (204 + cleared cookie) so the endpoint never reveals token state.
    """
    token = request.cookies.get(REFRESH_COOKIE_NAME)
    if token is not None:
        try:
            revocation = await revoke_family_by_token(session, token=token)
            if revocation is not None and revocation.newly_revoked > 0:
                identity = revocation.identity
                await write_audit(
                    session,
                    actor_type=AuditActorType.USER,
                    actor_id=identity.user_id,
                    action="auth.logout",
                    entity_type="user",
                    entity_id=identity.user_id,
                    metadata={"session_family_id": str(identity.family_id)},
                )
            await session.commit()
        except Exception:
            await session.rollback()
            raise
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_refresh_cookie(response)
    return response


@router.post("/verify-email")
async def verify_email(
    payload: VerifyEmailRequest, request: Request, session: SessionDep
) -> OkResponse:
    await enforce_auth_rate_limit(request, VERIFY_EMAIL_SCOPE)
    try:
        await auth_service.verify_email(session, token=payload.token)
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return OkResponse()


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(
    payload: ForgotPasswordRequest, request: Request, session: SessionDep
) -> OkResponse:
    """Always the same generic 202: the answer must never reveal whether the
    email belongs to an account, is unverified, or failed delivery."""
    await enforce_auth_rate_limit(request, FORGOT_PASSWORD_SCOPE, email=str(payload.email))
    settings = request.app.state.settings
    try:
        result = await password_reset_service.request_password_reset(
            session,
            email_transport=request.app.state.email_transport,
            frontend_public_url=settings.frontend_public_url,
            email=str(payload.email),
        )
        if result.outcome is password_reset_service.ForgotPasswordOutcome.DELIVERY_FAILED:
            # The token and audit must not survive an unsent email — but the
            # response stays the generic 202, so provider state is no oracle.
            await session.rollback()
        else:
            await session.commit()
    except Exception:  # noqa: BLE001 - post-lookup work runs only for real
        # accounts, so surfacing an internal failure as a 500 would be an
        # existence oracle; roll back and keep the generic 202. Cancellation
        # (BaseException) still propagates.
        await session.rollback()
    return OkResponse()


@router.post("/reset-password")
async def reset_password(
    payload: ResetPasswordRequest, request: Request, session: SessionDep
) -> OkResponse:
    await enforce_auth_rate_limit(request, RESET_PASSWORD_SCOPE, token=payload.token)
    try:
        await password_reset_service.reset_password(
            session,
            token=payload.token,
            new_password=payload.new_password.get_secret_value(),
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return OkResponse()
