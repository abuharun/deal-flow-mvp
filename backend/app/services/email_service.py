"""Email delivery seam (Tasks B3/B5): verification and password reset messages.

Security contract:
- No transport ever logs or prints message content, raw tokens, or API keys;
  delivery failures surface only an HTTP status and a provider request id.
- The console transport touches no network at all; the Resend transport talks
  only through an injected httpx client, so tests are hermetic and nothing
  here can place a live call on its own.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from html import escape
from typing import TYPE_CHECKING, Protocol
from urllib.parse import quote, urlencode

from app.config import Settings

if TYPE_CHECKING:  # httpx is injected by the caller; not a runtime dependency here.
    import httpx

RESEND_API_URL = "https://api.resend.com/emails"
# Resend's shared sandbox sender, used verbatim in resend_test mode.
RESEND_TEST_SENDER = "onboarding@resend.dev"

# Provider request ids are opaque short tokens; anything else (control chars,
# HTML, an echoed API key) is dropped before it can ride inside exception text.
_SAFE_PROVIDER_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def _sanitize_provider_request_id(value: str | None, *, api_key: str) -> str | None:
    if value is None or api_key in value or not _SAFE_PROVIDER_REQUEST_ID.fullmatch(value):
        return None
    return value


# Minimal correct copy per locale; a real i18n system stays out of the backend.
_VERIFY_COPY = {
    "uz": {
        "subject": "Bevosita: email manzilingizni tasdiqlang",
        "body": "Email manzilingizni tasdiqlash uchun quyidagi havolani bosing:",
        "link_label": "Emailni tasdiqlash",
    },
    "ru": {
        "subject": "Bevosita: подтвердите ваш email",
        "body": "Чтобы подтвердить ваш email, перейдите по ссылке:",
        "link_label": "Подтвердить email",
    },
}

_RESET_COPY = {
    "uz": {
        "subject": "Bevosita: parolni tiklash",
        "body": "Parolingizni tiklash uchun quyidagi havolani bosing:",
        "link_label": "Parolni tiklash",
    },
    "ru": {
        "subject": "Bevosita: сброс пароля",
        "body": "Чтобы сбросить пароль, перейдите по ссылке:",
        "link_label": "Сбросить пароль",
    },
}


class EmailDeliveryError(Exception):
    """Delivery failed. Carries only status/request id — never the API key,
    the recipient, a token, or the provider response body."""

    def __init__(
        self,
        *,
        status_code: int | None = None,
        request_id: str | None = None,
        reason: str = "email delivery failed",
    ) -> None:
        self.status_code = status_code
        self.request_id = request_id
        super().__init__(f"{reason} (status={status_code}, request_id={request_id})")


class RecipientNotAllowedError(EmailDeliveryError):
    """resend_test mode refuses any recipient but the configured owner address."""

    def __init__(self) -> None:
        super().__init__(reason="recipient not allowed in resend_test mode")


@dataclass(frozen=True, slots=True)
class EmailMessage:
    to: str
    subject: str
    html: str
    text: str


class EmailTransport(Protocol):
    async def send(self, message: EmailMessage) -> None: ...


def _build_token_url(frontend_public_url: str, path: str, token: str) -> str:
    base = frontend_public_url.rstrip("/")
    # A base already carrying ?/# could smuggle attacker-controlled query
    # parameters next to the token; refuse to build such a URL.
    if "?" in base or "#" in base:
        raise ValueError("frontend_public_url must not already carry a query or fragment")
    # quote (not quote_plus) so the token round-trips byte-for-byte percent-encoded.
    query = urlencode({"token": token}, quote_via=quote)
    return f"{base}{path}?{query}"


def build_verification_url(frontend_public_url: str, token: str) -> str:
    return _build_token_url(frontend_public_url, "/verify-email", token)


def build_password_reset_url(frontend_public_url: str, token: str) -> str:
    return _build_token_url(frontend_public_url, "/reset-password", token)


def _build_link_email(
    *, to: str, url: str, locale: str, copy_by_locale: dict, kind: str
) -> EmailMessage:
    copy = copy_by_locale.get(locale)
    if copy is None:
        raise ValueError(f"unsupported locale for {kind} email: {locale!r}")
    return EmailMessage(
        to=to,
        subject=copy["subject"],
        html=(
            f"<p>{escape(copy['body'])}</p>"
            f'<p><a href="{escape(url)}">{escape(copy["link_label"])}</a></p>'
        ),
        text=f"{copy['body']}\n\n{url}\n",
    )


def build_verification_email(*, to: str, verification_url: str, locale: str) -> EmailMessage:
    return _build_link_email(
        to=to, url=verification_url, locale=locale, copy_by_locale=_VERIFY_COPY, kind="verification"
    )


def build_password_reset_email(*, to: str, reset_url: str, locale: str) -> EmailMessage:
    return _build_link_email(
        to=to, url=reset_url, locale=locale, copy_by_locale=_RESET_COPY, kind="password reset"
    )


@dataclass(slots=True)
class ConsoleEmailTransport:
    """Local/dev delivery: captures messages in memory, no network, no logging.

    The optional sink is the deliberate hand-off of the one-time URL to a
    CLI/dev caller; nothing is printed or logged implicitly.
    """

    sink: Callable[[str], None] | None = None
    outbox: list[EmailMessage] = field(default_factory=list)

    async def send(self, message: EmailMessage) -> None:
        self.outbox.append(message)
        if self.sink is not None:
            self.sink(f"to={message.to} subject={message.subject}\n{message.text}")


class ResendEmailTransport:
    """Delivery via Resend's HTTP API through an injected httpx client."""

    def __init__(
        self,
        http_client: "httpx.AsyncClient",
        *,
        api_key: str,
        sender: str,
        allowed_recipient: str | None = None,
    ) -> None:
        self._http_client = http_client
        self._api_key = api_key
        self._sender = sender
        self._allowed_recipient = allowed_recipient

    async def send(self, message: EmailMessage) -> None:
        if (
            self._allowed_recipient is not None
            and message.to.lower() != self._allowed_recipient.lower()
        ):
            raise RecipientNotAllowedError
        response = await self._http_client.post(
            RESEND_API_URL,
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={
                "from": self._sender,
                "to": [message.to],
                "subject": message.subject,
                "html": message.html,
                "text": message.text,
            },
        )
        if not 200 <= response.status_code < 300:
            raw_request_id = response.headers.get("x-request-id") or response.headers.get(
                "x-resend-request-id"
            )
            raise EmailDeliveryError(
                status_code=response.status_code,
                request_id=_sanitize_provider_request_id(raw_request_id, api_key=self._api_key),
            )


def create_email_transport(
    settings: Settings, *, http_client: "httpx.AsyncClient | None" = None
) -> EmailTransport:
    """Select the transport for the configured EMAIL_MODE.

    resend_test pins the sandbox sender and the single configured owner
    recipient, so a misconfigured test environment can never broadcast email.
    """
    if settings.email_mode == "console":
        return ConsoleEmailTransport()
    if http_client is None:
        raise ValueError("resend email modes require an injected http_client")
    if not settings.resend_api_key:
        raise ValueError("resend_api_key is required for resend email modes")
    if settings.email_mode == "resend_test":
        if not settings.resend_test_recipient:
            raise ValueError("resend_test mode requires resend_test_recipient to be configured")
        return ResendEmailTransport(
            http_client,
            api_key=settings.resend_api_key,
            sender=RESEND_TEST_SENDER,
            allowed_recipient=settings.resend_test_recipient,
        )
    return ResendEmailTransport(
        http_client, api_key=settings.resend_api_key, sender=settings.email_from
    )
