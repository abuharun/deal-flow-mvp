"""`python -m app.cli run-analysis-worker` against real Postgres.

No real OpenAI network call is ever made here: `openai.AsyncOpenAI` is
monkeypatched to a fake client, and every scenario resolves in a single
`--once` invocation (no real sleep, no polling loop).
"""

import json
import uuid

import pytest
import sqlalchemy as sa
from typer.testing import CliRunner

import app.cli as cli_module
from app.db import build_engine, build_sessionmaker
from app.models.consent import CONSENT_KIND_AI_PRIVACY, CURRENT_AI_PRIVACY_VERSION
from app.models.payment import PAYMENT_STATUS_PAID
from app.repositories.deck_repository import PostgresDeckStorage
from app.services.pdf_validation import validate_deck

runner = CliRunner()

VALID_REPORT_PAYLOAD = {
    "schema_version": "report.v1",
    "language": "en",
    "report": {
        "executive_summary": "A concise, non-obvious executive summary.",
        "sections": {
            "uzbekistan_central_asia_market": {"narrative": "Market.", "citation_ids": [1]},
            "global_competitors": {"narrative": "Competitors.", "citation_ids": [2]},
            "us_vc_readiness": {"narrative": "Readiness.", "citation_ids": [3]},
        },
        "competitors": [],
        "claims": [],
        "contradictions": [],
        "unsupported_claims": [],
        "readiness_checklist": [
            {
                "item": "data_room",
                "status": "unknown",
                "confidence": "low",
                "evidence": [],
                "evidence_gap": "no data room shared yet",
            }
        ],
        "pitch_narrative_draft": "Draft narrative.",
    },
    "sources": [
        {
            "url": f"https://example.com/article-{i}",
            "title": f"Article {i}",
            "accessed_date": "2026-01-01",
            "source_quality": "reputable_media",
            "confidence": "medium",
        }
        for i in (1, 2, 3)
    ],
}


class FakeUsage:
    def __init__(self, input_tokens=1000, output_tokens=1000):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class FakeResponse:
    def __init__(self, payload):
        self.output_text = json.dumps(payload)
        self.usage = FakeUsage()
        self.id = "resp_fake"


class FakeResponses:
    def __init__(self, payload):
        self._payload = payload
        self.calls = 0

    async def create(self, **kwargs):
        self.calls += 1
        return FakeResponse(self._payload)


class FakeAsyncOpenAI:
    last_instance: "FakeAsyncOpenAI | None" = None

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key
        self.responses = FakeResponses(VALID_REPORT_PAYLOAD)
        FakeAsyncOpenAI.last_instance = self

    async def close(self) -> None:
        pass


def make_pdf_with_text(text: str = "Deck body text.") -> bytes:
    content = f"BT /F1 24 Tf 100 700 Td ({text}) Tj ET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> "
        b"/MediaBox [0 0 612 792] /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_offset = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\n".encode()
    out += f"startxref\n{xref_offset}\n%%EOF".encode()
    return bytes(out)


@pytest.fixture(autouse=True)
async def _clean_analysis_jobs(test_database_url, db_at_head):
    # This suite asserts on the GLOBAL "is anything due" state (the worker
    # has no per-startup filter by design), so -- like
    # tests/integration/test_analysis_repository_claim.py -- it needs a clean
    # table rather than tolerating a queued/retrying job some earlier test
    # (in this file or another) left behind in the shared database.
    engine = build_engine(test_database_url)
    try:
        async with build_sessionmaker(engine)() as session:
            await session.execute(sa.text("DELETE FROM analysis_jobs"))
            await session.commit()
    finally:
        await engine.dispose()


@pytest.fixture()
def cli_env(monkeypatch, test_database_url, db_at_head):
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key-value")
    monkeypatch.setenv("OPENAI_INPUT_PRICE_PER_MILLION_USD", "1.00")
    monkeypatch.setenv("OPENAI_OUTPUT_PRICE_PER_MILLION_USD", "1.00")
    monkeypatch.setenv("OPENAI_WEB_SEARCH_COST_USD", "0.01")
    monkeypatch.setenv("OPENAI_REPORT_SCHEMA_VERSION", "report.v1")
    return test_database_url


@pytest.fixture()
def fake_openai(monkeypatch):
    monkeypatch.setattr(cli_module.openai, "AsyncOpenAI", FakeAsyncOpenAI)
    yield FakeAsyncOpenAI


async def _insert_ready_job(database_url) -> uuid.UUID:
    engine = build_engine(database_url)
    try:
        email = f"cli-worker-{uuid.uuid4().hex}@example.com"
        async with build_sessionmaker(engine)() as session:
            founder_id = (
                await session.execute(
                    sa.text(
                        "INSERT INTO users (email, password_hash, full_name, role, "
                        "email_verified_at) VALUES (:email, 'x', 'CLI Owner', 'founder', now()) "
                        "RETURNING id"
                    ),
                    {"email": email},
                )
            ).scalar_one()
            startup_id = (
                await session.execute(
                    sa.text(
                        "INSERT INTO startups (founder_id, name, status, input_revision) "
                        "VALUES (:fid, 'CLI Startup', 'submitted', 1) RETURNING id"
                    ),
                    {"fid": str(founder_id)},
                )
            ).scalar_one()
            await session.execute(
                sa.text(
                    "INSERT INTO submissions (startup_id, problem, product, market, traction, "
                    "team, ask) VALUES (:sid, 'p', 'p', 'm', 't', 't', 'a')"
                ),
                {"sid": str(startup_id)},
            )
            await session.execute(
                sa.text(
                    "INSERT INTO consents (startup_id, founder_id, kind, text_version) "
                    "VALUES (:sid, :fid, :kind, :ver)"
                ),
                {
                    "sid": str(startup_id),
                    "fid": str(founder_id),
                    "kind": CONSENT_KIND_AI_PRIVACY,
                    "ver": CURRENT_AI_PRIVACY_VERSION,
                },
            )
            await session.execute(
                sa.text(
                    "INSERT INTO payments (startup_id, status, paid_at) "
                    "VALUES (:sid, :status, now())"
                ),
                {"sid": str(startup_id), "status": PAYMENT_STATUS_PAID},
            )
            job_id = (
                await session.execute(
                    sa.text(
                        "INSERT INTO analysis_jobs (startup_id, input_revision) "
                        "VALUES (:sid, 1) RETURNING id"
                    ),
                    {"sid": str(startup_id)},
                )
            ).scalar_one()
            await session.commit()

        content = make_pdf_with_text()
        deck_file = validate_deck(content, filename="deck.pdf", declared_mime="application/pdf")
        async with build_sessionmaker(engine)() as session:
            await PostgresDeckStorage(session).put(startup_id, deck_file, content)
            await session.commit()
        return job_id
    finally:
        await engine.dispose()


class TestMissingConfig:
    def test_missing_api_key_exits_nonzero_with_safe_message(
        self, test_database_url, monkeypatch, db_at_head
    ):
        monkeypatch.setenv("DATABASE_URL", test_database_url)
        monkeypatch.setenv("ENV", "test")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        result = runner.invoke(cli_module.app, ["run-analysis-worker", "--once"])
        assert result.exit_code != 0
        assert "worker config invalid" in result.output
        assert "openai_api_key_missing" in result.output


class TestOnceWithNoJobDue:
    def test_reports_no_job_due(self, cli_env, fake_openai):
        result = runner.invoke(cli_module.app, ["run-analysis-worker", "--once"])
        assert result.exit_code == 0
        assert "no_job_due" in result.output
        assert FakeAsyncOpenAI.last_instance.responses.calls == 0


class TestOnceProcessesExactlyOneJob:
    def test_succeeds_end_to_end_with_no_real_network_call(self, cli_env, fake_openai):
        import asyncio

        job_id = asyncio.run(_insert_ready_job(cli_env))
        result = runner.invoke(cli_module.app, ["run-analysis-worker", "--once"])
        assert result.exit_code == 0
        assert "succeeded" in result.output
        assert FakeAsyncOpenAI.last_instance.responses.calls == 1

        async def check():
            engine = build_engine(cli_env)
            try:
                async with engine.connect() as conn:
                    row = (
                        (
                            await conn.execute(
                                sa.text("SELECT status FROM analysis_jobs WHERE id = :id"),
                                {"id": job_id},
                            )
                        )
                        .mappings()
                        .one()
                    )
                    return row["status"]
            finally:
                await engine.dispose()

        assert asyncio.run(check()) == "completed"

    def test_api_key_never_appears_in_output(self, cli_env, fake_openai):
        result = runner.invoke(cli_module.app, ["run-analysis-worker", "--once"])
        assert "sk-test-key-value" not in result.output


class TestLocalStubProviderPath:
    """`--provider local-stub`: the offline seam the local pilot walks.

    No OPENAI_API_KEY is set in any test here, and `openai.AsyncOpenAI` is
    monkeypatched to a fake that records construction -- so "it never touched
    the OpenAI client" is asserted, not assumed.
    """

    @pytest.fixture()
    def stub_env(self, monkeypatch, test_database_url, db_at_head):
        monkeypatch.setenv("DATABASE_URL", test_database_url)
        monkeypatch.setenv("ENV", "development")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_INPUT_PRICE_PER_MILLION_USD", raising=False)
        monkeypatch.delenv("OPENAI_OUTPUT_PRICE_PER_MILLION_USD", raising=False)
        monkeypatch.delenv("OPENAI_WEB_SEARCH_COST_USD", raising=False)
        return test_database_url

    def test_runs_with_no_openai_config_at_all(self, stub_env, fake_openai):
        FakeAsyncOpenAI.last_instance = None
        result = runner.invoke(
            cli_module.app, ["run-analysis-worker", "--once", "--provider", "local-stub"]
        )
        assert result.exit_code == 0, result.output
        assert "no_job_due" in result.output
        assert FakeAsyncOpenAI.last_instance is None

    def test_discloses_the_stub_in_its_own_output(self, stub_env, fake_openai):
        result = runner.invoke(
            cli_module.app, ["run-analysis-worker", "--once", "--provider", "local-stub"]
        )
        assert "OFFLINE local stub provider" in result.output

    def test_completes_a_job_and_records_stub_provenance(self, stub_env, fake_openai):
        import asyncio

        from app.services.analysis_worker_config import LOCAL_STUB_MODEL
        from app.services.local_stub_provider import LOCAL_STUB_DISCLOSURE

        job_id = asyncio.run(_insert_ready_job(stub_env))
        result = runner.invoke(
            cli_module.app, ["run-analysis-worker", "--once", "--provider", "local-stub"]
        )
        assert result.exit_code == 0, result.output
        assert "succeeded" in result.output

        async def check():
            engine = build_engine(stub_env)
            try:
                async with engine.connect() as conn:
                    return (
                        (
                            await conn.execute(
                                sa.text(
                                    "SELECT j.status, j.cost_estimate_usd, r.model, "
                                    "r.prompt_version, r.report "
                                    "FROM analysis_jobs j "
                                    "JOIN analysis_reports r ON r.startup_id = j.startup_id "
                                    "WHERE j.id = :id"
                                ),
                                {"id": job_id},
                            )
                        )
                        .mappings()
                        .one()
                    )
            finally:
                await engine.dispose()

        row = asyncio.run(check())
        assert row["status"] == "completed"
        # The stored report credits the stub, not a model that never ran, and
        # says so in the text a founder actually reads.
        assert row["model"] == LOCAL_STUB_MODEL
        assert row["prompt_version"] == LOCAL_STUB_MODEL
        assert row["cost_estimate_usd"] == 0
        report = row["report"] if isinstance(row["report"], dict) else json.loads(row["report"])
        assert LOCAL_STUB_DISCLOSURE in report["executive_summary"]

    def test_refused_when_env_is_production(self, stub_env, monkeypatch, fake_openai):
        monkeypatch.setenv("ENV", "production")
        monkeypatch.setenv("JWT_SECRET", "0f9a" * 24)
        monkeypatch.setenv("FRONTEND_ORIGINS", "https://app.example.com")
        monkeypatch.setenv("API_PUBLIC_URL", "https://api.example.com")
        monkeypatch.setenv("FRONTEND_PUBLIC_URL", "https://app.example.com")
        result = runner.invoke(
            cli_module.app, ["run-analysis-worker", "--once", "--provider", "local-stub"]
        )
        assert result.exit_code != 0
        assert "local_stub_forbidden_in_production" in result.output

    def test_unknown_provider_is_refused(self, stub_env, fake_openai):
        result = runner.invoke(
            cli_module.app, ["run-analysis-worker", "--once", "--provider", "gemini"]
        )
        assert result.exit_code != 0
        assert "--provider must be one of" in result.output

    def test_default_provider_is_still_openai(self, stub_env, fake_openai):
        # Omitting --provider must never silently fall back to the stub: with
        # no key configured, the real path fails closed.
        result = runner.invoke(cli_module.app, ["run-analysis-worker", "--once"])
        assert result.exit_code != 0
        assert "openai_api_key_missing" in result.output
