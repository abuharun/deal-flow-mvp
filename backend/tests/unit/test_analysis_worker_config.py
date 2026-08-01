"""Explicit worker-startup config validation (never gates web app import)."""

from decimal import Decimal

import pytest

from app.config import Settings
from app.services.analysis_worker_config import (
    WorkerConfig,
    WorkerConfigError,
    require_worker_config,
)

TEST_DB_URL = "postgresql+asyncpg://bevosita:bevosita@127.0.0.1:5432/bevosita"


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, env="test", database_url=TEST_DB_URL, **overrides)


class TestSettingsRunsWithoutOpenAiConfig:
    def test_default_settings_have_no_api_key(self):
        settings = _settings()
        assert settings.openai_api_key is None

    def test_default_settings_have_no_pricing(self):
        settings = _settings()
        assert settings.openai_input_price_per_million_usd is None
        assert settings.openai_output_price_per_million_usd is None

    def test_settings_construction_never_raises_for_missing_openai_config(self):
        # The web app must be able to start without an OpenAI key at all.
        _settings()


class TestRequireWorkerConfigMissingApiKey:
    def test_missing_api_key_raises(self):
        settings = _settings(
            openai_input_price_per_million_usd=Decimal("0.15"),
            openai_output_price_per_million_usd=Decimal("0.60"),
        )
        with pytest.raises(WorkerConfigError) as excinfo:
            require_worker_config(settings)
        assert excinfo.value.reason == "openai_api_key_missing"

    def test_empty_string_api_key_raises(self):
        settings = _settings(
            openai_api_key="",
            openai_input_price_per_million_usd=Decimal("0.15"),
            openai_output_price_per_million_usd=Decimal("0.60"),
        )
        with pytest.raises(WorkerConfigError):
            require_worker_config(settings)


class TestRequireWorkerConfigMissingPricing:
    def test_missing_input_price_raises(self):
        settings = _settings(
            openai_api_key="sk-real",
            openai_output_price_per_million_usd=Decimal("0.60"),
        )
        with pytest.raises(WorkerConfigError) as excinfo:
            require_worker_config(settings)
        assert excinfo.value.reason == "openai_pricing_missing"

    def test_missing_output_price_raises(self):
        settings = _settings(
            openai_api_key="sk-real",
            openai_input_price_per_million_usd=Decimal("0.15"),
        )
        with pytest.raises(WorkerConfigError) as excinfo:
            require_worker_config(settings)
        assert excinfo.value.reason == "openai_pricing_missing"


class TestRequireWorkerConfigSuccess:
    def test_full_config_returns_worker_config(self):
        settings = _settings(
            openai_api_key="sk-real",
            openai_analysis_model="gpt-4o-mini",
            openai_prompt_version="analysis.v1",
            openai_request_timeout_seconds=45.0,
            openai_max_output_tokens=3000,
            openai_input_price_per_million_usd=Decimal("0.15"),
            openai_output_price_per_million_usd=Decimal("0.60"),
            openai_web_search_cost_usd=Decimal("0.01"),
            analysis_max_cost_usd=Decimal("0.20"),
        )
        config = require_worker_config(settings)
        assert isinstance(config, WorkerConfig)
        assert config.api_key == "sk-real"
        assert config.model == "gpt-4o-mini"
        assert config.prompt_version == "analysis.v1"
        assert config.request_timeout_seconds == 45.0
        assert config.max_output_tokens == 3000
        assert config.input_price_per_million_usd == Decimal("0.15")
        assert config.output_price_per_million_usd == Decimal("0.60")
        assert config.web_search_cost_usd == Decimal("0.01")
        assert config.max_cost_usd == Decimal("0.20")

    def test_error_never_includes_the_api_key(self):
        settings = _settings(openai_api_key="sk-super-secret-value")
        try:
            require_worker_config(settings)
        except WorkerConfigError as exc:
            assert "sk-super-secret-value" not in str(exc)
        else:
            pytest.fail("expected WorkerConfigError")
