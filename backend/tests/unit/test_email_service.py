"""Email delivery seam (Task B3, slice A) — settings, transports, no live network.

Security contract under test:
- API keys, raw tokens and provider response bodies never appear in exception
  text/repr or on stdout.
- Console mode touches no network; Resend mode talks only to an injected
  httpx client, so tests are hermetic by construction.
"""

import json
import re
from urllib.parse import parse_qs, quote, urlsplit

import httpx
import pytest
from pydantic import ValidationError

from app.config import Settings
from app.services.email_service import (
    RESEND_API_URL,
    ConsoleEmailTransport,
    EmailDeliveryError,
    ResendEmailTransport,
    build_password_reset_email,
    build_password_reset_url,
    build_verification_email,
    build_verification_url,
    create_email_transport,
)

TEST_DB_URL = "postgresql+asyncpg://bevosita:bevosita@127.0.0.1:5432/bevosita"
STRONG_JWT_SECRET = "9f" * 32
FRONTEND = "https://app.bevosita.example.com"
API_KEY = "re_live_key_abc123def456"
TOKEN = "tok-raw-secret-value"

PROD_KWARGS = {
    "env": "production",
    "database_url": "postgresql+asyncpg://app:s3cure@db.internal:5432/bevosita",
    "jwt_secret": STRONG_JWT_SECRET,
    "frontend_origins": "https://bevosita.example.com",
    "api_public_url": "https://api.bevosita.example.com",
    "frontend_public_url": FRONTEND,
    "email_from": "noreply@bevosita.example.com",
}

ENV_KEYS = (
    "ENV",
    "DATABASE_URL",
    "JWT_SECRET",
    "FRONTEND_ORIGINS",
    "API_PUBLIC_URL",
    "EMAIL_MODE",
    "RESEND_API_KEY",
    "EMAIL_FROM",
    "FRONTEND_PUBLIC_URL",
    "RESEND_TEST_RECIPIENT",
)


@pytest.fixture(autouse=True)
def _isolated_environ(monkeypatch):
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def make_settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


def make_prod(**overrides) -> Settings:
    return make_settings(**{**PROD_KWARGS, **overrides})


def _capture_client(responder=None) -> tuple[httpx.AsyncClient, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if responder is not None:
            return responder(request)
        return httpx.Response(200, json={"id": "email_123"})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler)), requests


class TestSettingsEmailFields:
    def test_local_defaults_are_console_mode_with_localhost_frontend(self):
        settings = make_settings(env="test", database_url=TEST_DB_URL)
        assert settings.email_mode == "console"
        assert settings.resend_api_key is None
        assert settings.email_from == "onboarding@resend.dev"
        assert settings.frontend_public_url.startswith("http://localhost")
        assert settings.resend_test_recipient is None

    def test_unknown_email_mode_rejected(self):
        with pytest.raises(ValidationError):
            make_settings(env="test", database_url=TEST_DB_URL, email_mode="smtp")

    def test_production_requires_https_frontend_public_url(self):
        with pytest.raises(ValidationError, match="(?i)frontend_public_url"):
            make_prod(frontend_public_url="http://app.bevosita.example.com")

    @pytest.mark.parametrize("bad_from", ["", "not-an-email", "a@b", "spaces in@example.com"])
    def test_production_requires_a_sensible_from_address(self, bad_from):
        with pytest.raises(ValidationError, match="(?i)email_from"):
            make_prod(email_from=bad_from)

    @pytest.mark.parametrize("mode", ["resend_test", "resend_prod"])
    def test_production_resend_modes_require_a_real_api_key(self, mode):
        with pytest.raises(ValidationError, match="(?i)resend_api_key"):
            make_prod(email_mode=mode)
        with pytest.raises(ValidationError, match="(?i)resend_api_key"):
            make_prod(email_mode=mode, resend_api_key="re_placeholder")

    def test_production_resend_prod_with_real_key_and_sender_is_valid(self):
        settings = make_prod(email_mode="resend_prod", resend_api_key=API_KEY)
        assert settings.email_mode == "resend_prod"

    def test_production_console_mode_needs_no_api_key(self):
        assert make_prod(email_mode="console").resend_api_key is None

    def test_resend_prod_rejects_the_onboarding_sender_even_outside_production(self):
        with pytest.raises(ValidationError, match="(?i)email_from"):
            make_settings(
                env="test",
                database_url=TEST_DB_URL,
                email_mode="resend_prod",
                resend_api_key=API_KEY,
                email_from="onboarding@resend.dev",
            )


class TestBuildVerificationUrl:
    def test_uses_verify_email_path_under_the_frontend(self):
        url = build_verification_url(FRONTEND, TOKEN)
        assert url.startswith(f"{FRONTEND}/verify-email?")

    def test_no_duplicate_slash_regardless_of_trailing_slash_on_base(self):
        url = build_verification_url(f"{FRONTEND}/", TOKEN)
        assert url == build_verification_url(FRONTEND, TOKEN)
        assert "//" not in url.removeprefix("https://")

    def test_token_appears_only_as_the_single_token_query_value(self):
        parts = urlsplit(build_verification_url(FRONTEND, TOKEN))
        assert parse_qs(parts.query, strict_parsing=True) == {"token": [TOKEN]}
        assert build_verification_url(FRONTEND, TOKEN).count(TOKEN) == 1

    def test_query_parameter_is_percent_safe(self):
        hostile = "a b/c&d=e?f#g+h%i"
        parts = urlsplit(build_verification_url(FRONTEND, hostile))
        assert parse_qs(parts.query, strict_parsing=True) == {"token": [hostile]}
        assert quote(hostile, safe="") in parts.query


class TestVerificationMessageCopy:
    URL = f"{FRONTEND}/verify-email?token={TOKEN}"

    @pytest.mark.parametrize("locale", ["uz", "ru"])
    def test_message_carries_recipient_link_and_nonempty_copy(self, locale):
        message = build_verification_email(
            to="founder@example.com", verification_url=self.URL, locale=locale
        )
        assert message.to == "founder@example.com"
        assert message.subject.strip()
        assert message.text.count(self.URL) == 1
        assert re.search(rf'href="{re.escape(self.URL)}"', message.html)

    def test_uz_and_ru_copy_differ(self):
        uz = build_verification_email(to="a@example.com", verification_url=self.URL, locale="uz")
        ru = build_verification_email(to="a@example.com", verification_url=self.URL, locale="ru")
        assert uz.subject != ru.subject
        assert uz.text != ru.text

    def test_ru_subject_is_russian_and_uz_is_not(self):
        uz = build_verification_email(to="a@example.com", verification_url=self.URL, locale="uz")
        ru = build_verification_email(to="a@example.com", verification_url=self.URL, locale="ru")
        assert re.search(r"[а-яА-ЯёЁ]", ru.subject)
        assert not re.search(r"[а-яА-ЯёЁ]", uz.subject)

    def test_unsupported_locale_is_rejected(self):
        with pytest.raises(ValueError, match="(?i)locale"):
            build_verification_email(to="a@example.com", verification_url=self.URL, locale="en")


class TestConsoleTransport:
    async def test_captures_message_without_stdout_or_network(self, capsys):
        transport = ConsoleEmailTransport()
        message = build_verification_email(
            to="founder@example.com",
            verification_url=f"{FRONTEND}/verify-email?token={TOKEN}",
            locale="uz",
        )
        await transport.send(message)
        assert transport.outbox == [message]
        assert capsys.readouterr().out == "", "console transport must not print implicitly"

    async def test_optional_sink_receives_the_verification_url_for_cli_use(self):
        lines: list[str] = []
        transport = ConsoleEmailTransport(sink=lines.append)
        url = f"{FRONTEND}/verify-email?token={TOKEN}"
        await transport.send(
            build_verification_email(to="founder@example.com", verification_url=url, locale="ru")
        )
        assert any(url in line for line in lines)


class TestResendTransport:
    def _message(self) -> object:
        return build_verification_email(
            to="founder@example.com",
            verification_url=f"{FRONTEND}/verify-email?token={TOKEN}",
            locale="uz",
        )

    async def test_posts_to_resend_with_bearer_auth_and_full_payload(self):
        client, requests = _capture_client()
        transport = ResendEmailTransport(
            client, api_key=API_KEY, sender="noreply@bevosita.example.com"
        )
        message = self._message()
        await transport.send(message)

        (request,) = requests
        assert str(request.url) == RESEND_API_URL == "https://api.resend.com/emails"
        assert request.method == "POST"
        assert request.headers["authorization"] == f"Bearer {API_KEY}"
        body = json.loads(request.content)
        assert body["from"] == "noreply@bevosita.example.com"
        assert body["to"] == ["founder@example.com"]
        assert body["subject"] == message.subject
        assert body["html"] == message.html
        assert body["text"] == message.text

    async def test_non_2xx_raises_typed_error_with_status_and_request_id_only(self):
        def responder(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                422,
                headers={"x-request-id": "req_789"},
                json={"message": "super-secret-response-body"},
            )

        client, _ = _capture_client(responder)
        transport = ResendEmailTransport(
            client, api_key=API_KEY, sender="noreply@bevosita.example.com"
        )
        with pytest.raises(EmailDeliveryError) as excinfo:
            await transport.send(self._message())

        assert excinfo.value.status_code == 422
        assert excinfo.value.request_id == "req_789"
        leakable = str(excinfo.value) + repr(excinfo.value)
        assert API_KEY not in leakable, "API key must never leak"
        assert TOKEN not in leakable, "the raw token must never leak"
        assert "super-secret-response-body" not in leakable, "response body must never leak"
        assert "founder@example.com" not in leakable, "recipient must never leak"


class TestBuildVerificationUrlBaseHardening:
    @pytest.mark.parametrize(
        "bad_base",
        [f"{FRONTEND}?attacker=1", f"{FRONTEND}/?utm=1", f"{FRONTEND}#fragment"],
    )
    def test_base_with_query_or_fragment_is_rejected(self, bad_base):
        # A base that already carries ?/# could smuggle attacker-controlled
        # query parameters next to the token; refuse to build such a URL.
        with pytest.raises(ValueError, match="(?i)query|fragment"):
            build_verification_url(bad_base, TOKEN)


class TestVerificationEmailHtmlEscaping:
    def test_hostile_url_cannot_break_out_of_the_href_attribute(self):
        hostile = 'https://evil.example/"><script>alert(1)</script>'
        message = build_verification_email(
            to="a@example.com", verification_url=hostile, locale="uz"
        )
        assert "<script>" not in message.html
        assert '"><' not in message.html

    def test_href_value_is_attribute_escaped(self):
        url = f"{FRONTEND}/verify-email?token=x&other=y"
        message = build_verification_email(to="a@example.com", verification_url=url, locale="ru")
        assert "&amp;" in message.html
        assert 'href="https://' in message.html


class TestResendRequestIdSanitization:
    def _failing_transport(self, request_id_value: str) -> ResendEmailTransport:
        def responder(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                500, headers={"x-request-id": request_id_value}, json={"message": "boom"}
            )

        client, _ = _capture_client(responder)
        return ResendEmailTransport(client, api_key=API_KEY, sender="noreply@bevosita.example.com")

    def _message(self):
        return build_verification_email(
            to="founder@example.com",
            verification_url=f"{FRONTEND}/verify-email?token={TOKEN}",
            locale="uz",
        )

    @pytest.mark.parametrize(
        "hostile",
        [
            'req"<img src=x onerror=alert(1)>',
            "req\tid\twith\ttabs",
            "x" * 500,
            "req id with spaces",
            "req;Set-Cookie=evil",
        ],
    )
    async def test_hostile_request_id_header_is_omitted(self, hostile):
        transport = self._failing_transport(hostile)
        with pytest.raises(EmailDeliveryError) as excinfo:
            await transport.send(self._message())
        assert excinfo.value.request_id is None, "a hostile provider id must be dropped"
        assert hostile not in str(excinfo.value) + repr(excinfo.value)

    async def test_request_id_echoing_the_api_key_is_omitted(self):
        transport = self._failing_transport(f"leak.{API_KEY}")
        with pytest.raises(EmailDeliveryError) as excinfo:
            await transport.send(self._message())
        assert excinfo.value.request_id is None
        assert API_KEY not in str(excinfo.value) + repr(excinfo.value)

    async def test_plain_request_id_is_preserved(self):
        transport = self._failing_transport("req_789.ok-1")
        with pytest.raises(EmailDeliveryError) as excinfo:
            await transport.send(self._message())
        assert excinfo.value.request_id == "req_789.ok-1"


class TestCreateEmailTransport:
    def test_console_mode_builds_the_console_transport(self):
        settings = make_settings(env="test", database_url=TEST_DB_URL, email_mode="console")
        assert isinstance(create_email_transport(settings), ConsoleEmailTransport)

    def test_resend_modes_require_an_injected_http_client(self):
        settings = make_settings(
            env="test",
            database_url=TEST_DB_URL,
            email_mode="resend_prod",
            resend_api_key=API_KEY,
            email_from="noreply@bevosita.example.com",
        )
        with pytest.raises(ValueError, match="(?i)http"):
            create_email_transport(settings)

    def test_resend_modes_require_an_api_key(self):
        client, _ = _capture_client()
        settings = make_settings(
            env="test",
            database_url=TEST_DB_URL,
            email_mode="resend_test",
            resend_test_recipient="owner@example.com",
        )
        with pytest.raises(ValueError, match="(?i)resend_api_key"):
            create_email_transport(settings, http_client=client)

    async def test_resend_test_mode_uses_onboarding_sender_and_only_the_owner_recipient(self):
        client, requests = _capture_client()
        settings = make_settings(
            env="test",
            database_url=TEST_DB_URL,
            email_mode="resend_test",
            resend_api_key=API_KEY,
            email_from="noreply@bevosita.example.com",
            resend_test_recipient="owner@example.com",
        )
        transport = create_email_transport(settings, http_client=client)
        url = f"{FRONTEND}/verify-email?token={TOKEN}"

        await transport.send(
            build_verification_email(to="owner@example.com", verification_url=url, locale="uz")
        )
        (request,) = requests
        assert json.loads(request.content)["from"] == "onboarding@resend.dev"

        with pytest.raises(EmailDeliveryError):
            await transport.send(
                build_verification_email(
                    to="stranger@example.com", verification_url=url, locale="uz"
                )
            )
        assert len(requests) == 1, "a blocked recipient must never reach the network"

    def test_resend_test_mode_without_a_configured_recipient_is_rejected(self):
        client, _ = _capture_client()
        settings = make_settings(
            env="test",
            database_url=TEST_DB_URL,
            email_mode="resend_test",
            resend_api_key=API_KEY,
        )
        with pytest.raises(ValueError, match="(?i)resend_test_recipient"):
            create_email_transport(settings, http_client=client)

    async def test_resend_prod_mode_uses_the_verified_sender(self):
        client, requests = _capture_client()
        settings = make_settings(
            env="test",
            database_url=TEST_DB_URL,
            email_mode="resend_prod",
            resend_api_key=API_KEY,
            email_from="noreply@bevosita.example.com",
        )
        transport = create_email_transport(settings, http_client=client)
        await transport.send(
            build_verification_email(
                to="founder@example.com",
                verification_url=f"{FRONTEND}/verify-email?token={TOKEN}",
                locale="ru",
            )
        )
        (request,) = requests
        assert json.loads(request.content)["from"] == "noreply@bevosita.example.com"


class TestBuildPasswordResetUrl:
    def test_uses_reset_password_path_under_the_frontend(self):
        url = build_password_reset_url(FRONTEND, TOKEN)
        assert url.startswith(f"{FRONTEND}/reset-password?")

    def test_no_duplicate_slash_regardless_of_trailing_slash_on_base(self):
        url = build_password_reset_url(f"{FRONTEND}/", TOKEN)
        assert url == build_password_reset_url(FRONTEND, TOKEN)
        assert "//" not in url.removeprefix("https://")

    def test_token_appears_only_as_the_single_token_query_value(self):
        parts = urlsplit(build_password_reset_url(FRONTEND, TOKEN))
        assert parse_qs(parts.query, strict_parsing=True) == {"token": [TOKEN]}
        assert build_password_reset_url(FRONTEND, TOKEN).count(TOKEN) == 1

    def test_query_parameter_is_percent_safe(self):
        hostile = "a b/c&d=e?f#g+h%i"
        parts = urlsplit(build_password_reset_url(FRONTEND, hostile))
        assert parse_qs(parts.query, strict_parsing=True) == {"token": [hostile]}
        assert quote(hostile, safe="") in parts.query

    @pytest.mark.parametrize(
        "bad_base",
        [f"{FRONTEND}?attacker=1", f"{FRONTEND}/?utm=1", f"{FRONTEND}#fragment"],
    )
    def test_base_with_query_or_fragment_is_rejected(self, bad_base):
        # Same hardening as the verification URL: a base already carrying ?/#
        # could smuggle attacker-controlled parameters next to the token.
        with pytest.raises(ValueError, match="(?i)query|fragment"):
            build_password_reset_url(bad_base, TOKEN)


class TestPasswordResetMessageCopy:
    URL = f"{FRONTEND}/reset-password?token={TOKEN}"

    @pytest.mark.parametrize("locale", ["uz", "ru"])
    def test_message_carries_recipient_link_and_nonempty_copy(self, locale, capsys):
        message = build_password_reset_email(
            to="founder@example.com", reset_url=self.URL, locale=locale
        )
        assert message.to == "founder@example.com"
        assert message.subject.strip()
        assert message.text.count(self.URL) == 1
        assert re.search(rf'href="{re.escape(self.URL)}"', message.html)
        assert capsys.readouterr().out == "", "building the email must never print"

    def test_uz_and_ru_copy_differ(self):
        uz = build_password_reset_email(to="a@example.com", reset_url=self.URL, locale="uz")
        ru = build_password_reset_email(to="a@example.com", reset_url=self.URL, locale="ru")
        assert uz.subject != ru.subject
        assert uz.text != ru.text

    def test_ru_subject_is_russian_and_uz_is_not(self):
        uz = build_password_reset_email(to="a@example.com", reset_url=self.URL, locale="uz")
        ru = build_password_reset_email(to="a@example.com", reset_url=self.URL, locale="ru")
        assert re.search(r"[а-яА-ЯёЁ]", ru.subject)
        assert not re.search(r"[а-яА-ЯёЁ]", uz.subject)

    def test_reset_copy_differs_from_verification_copy(self):
        for locale in ("uz", "ru"):
            reset = build_password_reset_email(
                to="a@example.com", reset_url=self.URL, locale=locale
            )
            verify = build_verification_email(
                to="a@example.com",
                verification_url=f"{FRONTEND}/verify-email?token={TOKEN}",
                locale=locale,
            )
            assert reset.subject != verify.subject

    def test_unsupported_locale_is_rejected(self):
        with pytest.raises(ValueError, match="(?i)locale"):
            build_password_reset_email(to="a@example.com", reset_url=self.URL, locale="en")


class TestPasswordResetEmailHtmlEscaping:
    def test_hostile_url_cannot_break_out_of_the_href_attribute(self):
        hostile = 'https://evil.example/"><script>alert(1)</script>'
        message = build_password_reset_email(to="a@example.com", reset_url=hostile, locale="uz")
        assert "<script>" not in message.html
        assert '"><' not in message.html

    def test_href_value_is_attribute_escaped(self):
        url = f"{FRONTEND}/reset-password?token=x&other=y"
        message = build_password_reset_email(to="a@example.com", reset_url=url, locale="ru")
        assert "&amp;" in message.html
        assert 'href="https://' in message.html


class TestResendTransportWithResetEmail:
    async def test_failure_repr_leaks_neither_token_nor_key_nor_recipient(self):
        def responder(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                500,
                headers={"x-request-id": "req_456"},
                json={"message": "super-secret-response-body"},
            )

        client, _ = _capture_client(responder)
        transport = ResendEmailTransport(
            client, api_key=API_KEY, sender="noreply@bevosita.example.com"
        )
        message = build_password_reset_email(
            to="founder@example.com",
            reset_url=f"{FRONTEND}/reset-password?token={TOKEN}",
            locale="ru",
        )
        with pytest.raises(EmailDeliveryError) as excinfo:
            await transport.send(message)

        leakable = str(excinfo.value) + repr(excinfo.value)
        assert TOKEN not in leakable, "the raw reset token must never leak"
        assert API_KEY not in leakable, "API key must never leak"
        assert "founder@example.com" not in leakable, "recipient must never leak"
        assert "super-secret-response-body" not in leakable
