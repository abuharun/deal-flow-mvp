"""The local-only analysis stub: deterministic, honest, and never production.

The stub exists so the founder -> investor path can be exercised in a real
browser on a machine with no OpenAI credentials. These tests pin the two
things that make that acceptable: the output is FIXED (so the UI path is
deterministic) and it is SELF-DESCRIBING (so nobody can mistake stub text,
or a screenshot of it, for real AI research).
"""

import json
import uuid
from decimal import Decimal

import pytest

from app.config import Settings
from app.schemas.report import ReportV1Input
from app.services.analysis_worker_config import (
    LOCAL_STUB_MODEL,
    LOCAL_STUB_PROMPT_VERSION,
    WorkerConfigError,
    require_local_stub_worker_config,
)
from app.services.local_stub_provider import (
    LOCAL_STUB_DISCLOSURE,
    LocalStubResponsesClient,
    build_local_stub_report,
)

TEST_DB_URL = "postgresql+asyncpg://bevosita:bevosita@127.0.0.1:5432/bevosita"


def _settings(**overrides) -> Settings:
    """Test-env settings by default; any field (including `env`) is overridable."""
    fields: dict[str, object] = {"env": "test", "database_url": TEST_DB_URL}
    fields.update(overrides)
    return Settings(_env_file=None, **fields)


class TestStubReportIsValidReportV1:
    def test_payload_validates_against_the_real_schema(self):
        # Not a hand-waved dict: it goes through the same validation a real
        # provider reply does, so the stub can never drift from report.v1.
        ReportV1Input.model_validate(build_local_stub_report())

    def test_payload_is_json_serializable_as_the_provider_would_return_it(self):
        json.loads(json.dumps(build_local_stub_report()))


class TestStubReportIsSelfDescribing:
    def test_executive_summary_discloses_the_stub(self):
        report = build_local_stub_report()["report"]
        assert LOCAL_STUB_DISCLOSURE in report["executive_summary"]

    def test_every_section_narrative_discloses_the_stub(self):
        sections = build_local_stub_report()["report"]["sections"]
        for section in sections.values():
            assert LOCAL_STUB_DISCLOSURE in section["narrative"]

    def test_narrative_draft_discloses_the_stub(self):
        report = build_local_stub_report()["report"]
        assert LOCAL_STUB_DISCLOSURE in report["pitch_narrative_draft"]

    def test_every_source_is_a_documentation_placeholder(self):
        # RFC 2606 reserves example.com for documentation: a reader following
        # a citation lands somewhere that cannot pass for a real finding.
        for source in build_local_stub_report()["sources"]:
            assert source["url"].startswith("https://example.com/")
            assert LOCAL_STUB_DISCLOSURE in source["title"]


class TestStubIsDeterministic:
    def test_two_builds_are_byte_identical(self):
        assert build_local_stub_report() == build_local_stub_report()

    async def test_two_calls_return_the_same_output_text(self):
        client = LocalStubResponsesClient()
        first = await client.responses.create(model="ignored", input="a")
        second = await client.responses.create(model="ignored", input="b")
        assert first.output_text == second.output_text

    async def test_output_does_not_depend_on_the_prompt(self):
        # A stub that echoed the prompt would put untrusted founder text into
        # a stored report; it deliberately ignores every argument.
        client = LocalStubResponsesClient()
        response = await client.responses.create(input="SECRET FOUNDER ANSWER")
        assert "SECRET FOUNDER ANSWER" not in response.output_text


class TestStubUsageAndCost:
    async def test_reports_zero_tokens_because_none_were_spent(self):
        client = LocalStubResponsesClient()
        response = await client.responses.create()
        assert response.usage.input_tokens == 0
        assert response.usage.output_tokens == 0

    async def test_request_id_marks_the_response_as_a_stub(self):
        client = LocalStubResponsesClient()
        response = await client.responses.create()
        assert response.id.startswith("local-stub")

    async def test_counts_its_calls_so_tests_can_assert_one_per_attempt(self):
        client = LocalStubResponsesClient()
        await client.responses.create()
        await client.responses.create()
        assert client.responses.calls == 2

    async def test_close_is_awaitable_like_the_real_client(self):
        await LocalStubResponsesClient().close()


class TestLocalStubWorkerConfig:
    def test_refused_in_production(self):
        settings = _settings(
            env="production",
            jwt_secret="0f9a" * 24,
            frontend_origins=("https://app.example.com",),
            api_public_url="https://api.example.com",
            frontend_public_url="https://app.example.com",
        )
        with pytest.raises(WorkerConfigError) as excinfo:
            require_local_stub_worker_config(settings)
        assert excinfo.value.reason == "local_stub_forbidden_in_production"

    def test_needs_no_openai_key_or_pricing_at_all(self):
        config = require_local_stub_worker_config(_settings())
        assert config.api_key == ""

    def test_records_the_stub_as_the_producing_model(self):
        # The persisted report's provenance must name the stub, never the
        # configured real model, or the dossier would credit an AI that never ran.
        config = require_local_stub_worker_config(_settings(openai_analysis_model="gpt-4o-mini"))
        assert config.model == LOCAL_STUB_MODEL
        assert config.prompt_version == LOCAL_STUB_PROMPT_VERSION

    def test_prices_the_run_at_zero_because_nothing_is_charged(self):
        config = require_local_stub_worker_config(
            _settings(
                openai_input_price_per_million_usd=Decimal("999"),
                openai_output_price_per_million_usd=Decimal("999"),
                openai_web_search_cost_usd=Decimal("0.2"),
            )
        )
        assert config.input_price_per_million_usd == Decimal("0")
        assert config.output_price_per_million_usd == Decimal("0")
        assert config.web_search_cost_usd == Decimal("0")

    def test_still_refuses_an_unsupported_report_schema_version(self, monkeypatch):
        settings = _settings()
        monkeypatch.setattr(settings, "openai_report_schema_version", "report.v99")
        with pytest.raises(WorkerConfigError) as excinfo:
            require_local_stub_worker_config(settings)
        assert excinfo.value.reason == "report_schema_version_unsupported"

    def test_model_and_prompt_version_fit_the_report_columns(self):
        from app.models.analysis_report import MAX_MODEL_LENGTH, MAX_PROMPT_VERSION_LENGTH

        assert 1 <= len(LOCAL_STUB_MODEL) <= MAX_MODEL_LENGTH
        assert 1 <= len(LOCAL_STUB_PROMPT_VERSION) <= MAX_PROMPT_VERSION_LENGTH


class TestStubRunsThroughTheRealProviderAdapter:
    async def test_run_analysis_accepts_the_stub_client(self):
        from app.services.analysis_snapshot import AnalysisInputSnapshot, Untrusted
        from app.services.openai_provider import run_analysis

        def _u(value: str) -> Untrusted:
            return Untrusted(value)

        snapshot = AnalysisInputSnapshot(
            startup_id=uuid.uuid4(),
            job_id=uuid.uuid4(),
            input_revision=1,
            startup_name=_u("Stub Startup"),
            one_liner=_u("one liner"),
            sector=_u("fintech"),
            funding_stage=_u("pre-seed"),
            city=_u("Tashkent"),
            problem=_u("problem"),
            product=_u("product"),
            market=_u("market"),
            traction=_u("traction"),
            team=_u("team"),
            ask=_u("ask"),
            revenue=None,
            growth=None,
            ask_amount=None,
            dataroom_url=None,
            deck_text=_u("deck text"),
            deck_text_truncated=False,
        )
        result = await run_analysis(
            LocalStubResponsesClient(),
            snapshot=snapshot,
            config=require_local_stub_worker_config(_settings()),
        )
        assert result.model == LOCAL_STUB_MODEL
        assert result.cost_estimate_usd == Decimal("0.0000")
        assert LOCAL_STUB_DISCLOSURE in result.report_input.report.executive_summary
