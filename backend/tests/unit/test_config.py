"""Settings fail-fast contract: safe local defaults, strict production validation."""

from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
REPO_DIR = BACKEND_DIR.parent

TEST_DB_URL = "postgresql+asyncpg://bevosita:bevosita@127.0.0.1:5432/bevosita"

# A credible production secret: 64 chars, hex-ish, no placeholder wording.
STRONG_JWT_SECRET = "9f" * 32

PROD_KWARGS = {
    "env": "production",
    "database_url": "postgresql+asyncpg://app:s3cure@db.internal:5432/bevosita",
    "jwt_secret": STRONG_JWT_SECRET,
    "frontend_origins": "https://bevosita.example.com",
    "api_public_url": "https://api.bevosita.example.com",
    "frontend_public_url": "https://bevosita.example.com",
}

ENV_KEYS = (
    "ENV",
    "DATABASE_URL",
    "JWT_SECRET",
    "FRONTEND_ORIGINS",
    "API_PUBLIC_URL",
    "FRONTEND_PUBLIC_URL",
)


@pytest.fixture(autouse=True)
def _isolated_environ(monkeypatch):
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def make_settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


def make_prod(**overrides) -> Settings:
    return make_settings(**{**PROD_KWARGS, **overrides})


class TestLocalDefaults:
    def test_test_env_with_real_db_url_is_valid(self):
        settings = make_settings(env="test", database_url=TEST_DB_URL)
        assert settings.env == "test"
        assert settings.database_url == TEST_DB_URL

    def test_local_defaults_are_safe_and_obviously_non_production(self):
        settings = make_settings(env="test", database_url=TEST_DB_URL)
        assert "local" in settings.jwt_secret.lower()
        assert all(o.startswith("http://localhost") for o in settings.frontend_origins)
        assert settings.api_public_url.startswith("http://localhost")

    def test_development_is_a_valid_env(self):
        assert make_settings(env="development", database_url=TEST_DB_URL).env == "development"


class TestEnvName:
    @pytest.mark.parametrize("bad_env", ["staging", "prod", "PRODUCTION", "", "local"])
    def test_unknown_env_rejected(self, bad_env):
        with pytest.raises(ValidationError):
            make_settings(env=bad_env, database_url=TEST_DB_URL)


class TestProductionRejects:
    def test_missing_jwt_secret_falls_back_to_placeholder_and_fails(self):
        kwargs = {k: v for k, v in PROD_KWARGS.items() if k != "jwt_secret"}
        with pytest.raises(ValidationError, match="(?i)jwt_secret"):
            make_settings(**kwargs)

    @pytest.mark.parametrize(
        "bad_secret",
        [
            "change-me-64-hex" + "x" * 48,  # placeholder wording, even when long
            "placeholder-" + "a" * 52,
            "9f" * 16,  # 32 chars: too short
            "",
        ],
    )
    def test_weak_or_placeholder_jwt_secret_rejected(self, bad_secret):
        with pytest.raises(ValidationError, match="(?i)jwt_secret"):
            make_prod(jwt_secret=bad_secret)

    @pytest.mark.parametrize("bad_origins", ["*", "", "https://a.example.com,*", "   "])
    def test_wildcard_or_empty_frontend_origins_rejected(self, bad_origins):
        with pytest.raises(ValidationError, match="(?i)origin"):
            make_prod(frontend_origins=bad_origins)

    def test_non_https_frontend_origin_rejected(self):
        with pytest.raises(ValidationError, match="(?i)origin"):
            make_prod(frontend_origins="http://bevosita.example.com")

    @pytest.mark.parametrize(
        "bad_url", ["http://api.bevosita.example.com", "ftp://api.example.com", ""]
    )
    def test_non_https_api_public_url_rejected(self, bad_url):
        with pytest.raises(ValidationError, match="(?i)api_public_url"):
            make_prod(api_public_url=bad_url)

    @pytest.mark.parametrize(
        "bad_db",
        [
            "postgresql://app:pw@db.internal:5432/bevosita",
            "postgresql+psycopg://app:pw@db.internal:5432/bevosita",
            "sqlite+aiosqlite:///./app.db",
            "mysql+asyncmy://app:pw@db/bevosita",
        ],
    )
    def test_non_asyncpg_database_url_rejected(self, bad_db):
        with pytest.raises(ValidationError, match="(?i)database_url"):
            make_prod(database_url=bad_db)


class TestProductionAccepts:
    def test_full_valid_production_config(self):
        settings = make_prod()
        assert settings.env == "production"
        assert settings.jwt_secret == STRONG_JWT_SECRET
        assert settings.frontend_origins == ("https://bevosita.example.com",)
        assert settings.api_public_url == "https://api.bevosita.example.com"

    def test_multiple_https_origins_accepted(self):
        settings = make_prod(
            frontend_origins="https://bevosita.example.com, https://vc.bevosita.example.com"
        )
        assert settings.frontend_origins == (
            "https://bevosita.example.com",
            "https://vc.bevosita.example.com",
        )


class TestProductionPublicUrlHardening:
    """URL fields are parsed, not regex-matched: userinfo, query, fragment and
    injection characters must be rejected before they can reach emails or CORS."""

    @pytest.mark.parametrize("field", ["api_public_url", "frontend_public_url"])
    @pytest.mark.parametrize(
        "bad_url",
        [
            "https://user:secretpw@api.bevosita.example.com",
            "https://api.bevosita.example.com/?attacker=1",
            "https://api.bevosita.example.com/#fragment",
            "https://",
            'https://api.bevosita.example.com/">',
            "https://api.bevosita.example.com/'quote",
            "https://api.bevosita.example.com/pa th",
            "https://api.bevosita.example.com/\tpath",
            "https://api.bevosita.example.com/\x00null",
        ],
    )
    def test_hostile_public_urls_rejected(self, field, bad_url):
        with pytest.raises(ValidationError, match=f"(?i){field}"):
            make_prod(**{field: bad_url})

    def test_password_in_rejected_userinfo_url_is_not_echoed(self):
        with pytest.raises(ValidationError) as excinfo:
            make_prod(api_public_url="https://user:sup3rsecretpw@api.example.com")
        assert "sup3rsecretpw" not in str(excinfo.value)

    @pytest.mark.parametrize(
        "bad_origin",
        [
            "https://bevosita.example.com/path",
            "https://bevosita.example.com/",
            "https://bevosita.example.com?x=1",
            "https://bevosita.example.com#frag",
            "https://user:pw@bevosita.example.com",
            'https://bevosita.example.com">',
        ],
    )
    def test_origins_must_be_bare_origins(self, bad_origin):
        with pytest.raises(ValidationError, match="(?i)origin"):
            make_prod(frontend_origins=bad_origin)


class TestNonProductionUrlSafety:
    def test_localhost_http_urls_remain_valid_in_dev_and_test(self):
        for env in ("development", "test"):
            settings = make_settings(
                env=env,
                database_url=TEST_DB_URL,
                api_public_url="http://localhost:8000",
                frontend_public_url="http://localhost:5173",
                frontend_origins="http://localhost:5173",
            )
            assert settings.frontend_public_url == "http://localhost:5173"

    @pytest.mark.parametrize("field", ["api_public_url", "frontend_public_url"])
    def test_injection_characters_rejected_even_outside_production(self, field):
        with pytest.raises(ValidationError, match=f"(?i){field}"):
            make_settings(env="test", database_url=TEST_DB_URL, **{field: 'http://localhost/">'})

    def test_userinfo_rejected_even_outside_production(self):
        with pytest.raises(ValidationError, match="(?i)frontend_public_url"):
            make_settings(
                env="test",
                database_url=TEST_DB_URL,
                frontend_public_url="http://user:pw@localhost:5173",
            )

    def test_non_http_scheme_rejected_outside_production(self):
        with pytest.raises(ValidationError, match="(?i)api_public_url"):
            make_settings(env="test", database_url=TEST_DB_URL, api_public_url="ftp://localhost")


class TestFrontendOriginsParsing:
    def test_comma_delimited_string_normalizes_to_tuple(self):
        settings = make_settings(
            env="test",
            database_url=TEST_DB_URL,
            frontend_origins="http://localhost:5173, http://localhost:4173",
        )
        assert settings.frontend_origins == (
            "http://localhost:5173",
            "http://localhost:4173",
        )

    def test_wildcard_never_allowed_even_outside_production(self):
        with pytest.raises(ValidationError, match="(?i)origin"):
            make_settings(env="development", database_url=TEST_DB_URL, frontend_origins="*")


class TestDotenvLoading:
    def test_settings_load_values_from_env_file(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "ENV=test\n"
            f"DATABASE_URL={TEST_DB_URL}\n"
            "JWT_SECRET=from-dotenv-local-secret\n"
            "FRONTEND_ORIGINS=http://localhost:9999\n"
        )
        settings = Settings(_env_file=env_file)
        assert settings.env == "test"
        assert settings.database_url == TEST_DB_URL
        assert settings.jwt_secret == "from-dotenv-local-secret"
        assert settings.frontend_origins == ("http://localhost:9999",)

    def test_default_env_file_is_backend_dotenv(self):
        assert Path(Settings.model_config["env_file"]) == BACKEND_DIR / ".env"

    def test_real_dotenv_stays_gitignored_and_uncreated(self):
        gitignore = (REPO_DIR / ".gitignore").read_text()
        assert "backend/.env" in gitignore.splitlines()
        assert not (BACKEND_DIR / ".env").exists()


class TestOpenAiAnalysisConfig:
    """The API must start with zero OpenAI config; bounds still apply when set."""

    def test_defaults_are_safe_and_present(self):
        settings = make_settings(env="test", database_url=TEST_DB_URL)
        assert settings.openai_api_key is None
        assert settings.openai_analysis_model
        assert settings.openai_prompt_version
        assert settings.openai_request_timeout_seconds > 0
        assert settings.openai_max_output_tokens > 0
        assert settings.openai_input_price_per_million_usd is None
        assert settings.openai_output_price_per_million_usd is None
        assert settings.analysis_max_cost_usd == Decimal("0.25")

    def test_analysis_max_cost_usd_over_hard_cap_rejected(self):
        with pytest.raises(ValidationError, match="(?i)analysis_max_cost_usd"):
            make_settings(env="test", database_url=TEST_DB_URL, analysis_max_cost_usd="0.26")

    def test_analysis_max_cost_usd_zero_or_negative_rejected(self):
        with pytest.raises(ValidationError, match="(?i)analysis_max_cost_usd"):
            make_settings(env="test", database_url=TEST_DB_URL, analysis_max_cost_usd="0")

    def test_prompt_version_over_32_chars_rejected(self):
        with pytest.raises(ValidationError, match="(?i)prompt_version"):
            make_settings(env="test", database_url=TEST_DB_URL, openai_prompt_version="x" * 33)

    def test_request_timeout_must_be_positive(self):
        with pytest.raises(ValidationError, match="(?i)timeout"):
            make_settings(env="test", database_url=TEST_DB_URL, openai_request_timeout_seconds=0)

    def test_max_output_tokens_must_be_positive(self):
        with pytest.raises(ValidationError, match="(?i)max_output_tokens"):
            make_settings(env="test", database_url=TEST_DB_URL, openai_max_output_tokens=0)

    def test_negative_pricing_rejected(self):
        with pytest.raises(ValidationError, match="(?i)price"):
            make_settings(
                env="test",
                database_url=TEST_DB_URL,
                openai_input_price_per_million_usd="-1",
            )

    def test_settings_are_constructible_in_production_without_openai_key(self):
        # The web app must run in production with zero AI config; only the
        # worker's explicit startup check (require_worker_config) enforces it.
        settings = make_prod()
        assert settings.openai_api_key is None
