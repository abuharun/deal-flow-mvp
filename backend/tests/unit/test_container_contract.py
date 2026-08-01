"""Static contracts for Dockerfile, docker-compose.yml and .env.example.

Docker is not required at runtime: everything here is text/YAML inspection
plus the app-factory behavior the Dockerfile CMD relies on.
"""

import re
from pathlib import Path

import pytest
import yaml

from app.config import Settings
from app.main import create_app

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

TEST_DB_URL = "postgresql+asyncpg://bevosita:bevosita@127.0.0.1:5432/bevosita"


def read_backend_file(name: str) -> str:
    path = BACKEND_DIR / name
    assert path.is_file(), f"expected {path} to exist"
    return path.read_text()


class TestDockerfile:
    @pytest.fixture()
    def dockerfile(self) -> str:
        return read_backend_file("Dockerfile")

    @pytest.fixture()
    def instructions(self, dockerfile) -> list[str]:
        return [
            line.strip()
            for line in dockerfile.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]

    def test_base_image_is_python_312_slim(self, instructions):
        from_lines = [line for line in instructions if line.startswith("FROM ")]
        assert from_lines, "Dockerfile must have a FROM instruction"
        assert all(re.search(r"python:3\.12[\w.-]*-slim", line) for line in from_lines)

    def test_creates_and_runs_as_non_root_user(self, dockerfile, instructions):
        assert re.search(r"\b(useradd|adduser)\b", dockerfile)
        user_lines = [line for line in instructions if line.startswith("USER ")]
        assert user_lines, "Dockerfile must switch away from root with USER"
        final_user = user_lines[-1].split(None, 1)[1].strip()
        assert final_user not in ("root", "0")

    def test_installs_the_package(self, dockerfile):
        assert re.search(r"pip install\b[^\n]*\.", dockerfile)

    def test_exposes_port_8000(self, instructions):
        assert any(line == "EXPOSE 8000" for line in instructions)

    def test_starts_uvicorn_via_app_factory(self, dockerfile):
        cmd_lines = [
            line for line in dockerfile.splitlines() if line.startswith(("CMD", "ENTRYPOINT"))
        ]
        assert cmd_lines, "Dockerfile must define a CMD/ENTRYPOINT"
        start = " ".join(cmd_lines)
        assert "uvicorn" in start
        assert "app.main:create_app" in start
        assert "--factory" in start


class TestAppFactory:
    def test_create_app_accepts_explicit_settings(self):
        settings = Settings(_env_file=None, env="test", database_url=TEST_DB_URL)
        app = create_app(settings)
        assert app.state.settings is settings

    def test_create_app_without_args_loads_settings_from_environment(self, monkeypatch):
        monkeypatch.setenv("ENV", "test")
        monkeypatch.setenv("DATABASE_URL", TEST_DB_URL)
        monkeypatch.setenv("FRONTEND_ORIGINS", "http://localhost:5173")
        app = create_app()
        assert app.state.settings.env == "test"
        assert app.state.settings.database_url == TEST_DB_URL


class TestDockerCompose:
    @pytest.fixture()
    def compose(self) -> dict:
        return yaml.safe_load(read_backend_file("docker-compose.yml"))

    @pytest.fixture()
    def db(self, compose) -> dict:
        assert "db" in compose.get("services", {}), "compose must define a db service"
        return compose["services"]["db"]

    def test_postgres_16_image(self, db):
        assert db["image"].startswith("postgres:16")

    def test_bevosita_database_with_local_development_only_credentials(self, db):
        env = db["environment"]
        assert env["POSTGRES_DB"] == "bevosita"
        assert env["POSTGRES_USER"] == "bevosita"
        # Local-development-only value; production credentials come from Render.
        assert env["POSTGRES_PASSWORD"] == "bevosita"

    def test_persistent_named_volume(self, compose, db):
        mounts = db.get("volumes", [])
        named = [m.split(":")[0] for m in mounts if not m.startswith(("/", "."))]
        assert named, "db service must mount a named volume for persistence"
        assert any(m.endswith("/var/lib/postgresql/data") for m in mounts)
        for volume in named:
            assert volume in compose.get("volumes", {}), f"volume {volume} must be declared"

    def test_pg_isready_healthcheck(self, db):
        healthcheck = db.get("healthcheck", {})
        test = healthcheck.get("test", "")
        as_text = " ".join(test) if isinstance(test, list) else test
        assert "pg_isready" in as_text


class TestEnvExample:
    EXPECTED_KEYS = {
        "ENV",
        "DATABASE_URL",
        "JWT_SECRET",
        "FRONTEND_ORIGINS",
        "TRUSTED_PROXY_CIDRS",
        "OPENAI_API_KEY",
        "OPENAI_ANALYSIS_MODEL",
        "OPENAI_PROMPT_VERSION",
        "OPENAI_REPORT_SCHEMA_VERSION",
        "OPENAI_REQUEST_TIMEOUT_SECONDS",
        "OPENAI_MAX_OUTPUT_TOKENS",
        "OPENAI_INPUT_PRICE_PER_MILLION_USD",
        "OPENAI_OUTPUT_PRICE_PER_MILLION_USD",
        "OPENAI_WEB_SEARCH_COST_USD",
        "ANALYSIS_MAX_COST_USD",
        "EMAIL_MODE",
        "RESEND_API_KEY",
        "EMAIL_FROM",
        "FRONTEND_PUBLIC_URL",
        "SENTRY_DSN",
        "API_PUBLIC_URL",
        "BACKUP_BUCKET_URL",
        "BACKUP_AGE_PUBLIC_KEY",
    }

    @pytest.fixture()
    def env_example(self) -> str:
        return read_backend_file(".env.example")

    @pytest.fixture()
    def entries(self, env_example) -> dict[str, str]:
        parsed = {}
        for raw in env_example.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            key, sep, value = line.partition("=")
            assert sep, f"malformed .env.example line: {raw!r}"
            parsed[key.strip()] = value.split("#", 1)[0].strip()
        return parsed

    def test_lists_exactly_the_expected_keys(self, entries):
        assert set(entries) == self.EXPECTED_KEYS

    def test_no_real_openai_or_resend_secret_shapes(self, env_example):
        assert not re.search(r"sk-[A-Za-z0-9]{20}", env_example)
        assert not re.search(r"re_[A-Za-z0-9]{16}", env_example)

    def test_no_vite_keys(self, entries):
        assert not [key for key in entries if key.upper().startswith("VITE")]

    def test_values_are_obvious_placeholders_or_local(self, entries):
        assert entries["ENV"] == "development"
        assert entries["DATABASE_URL"].startswith(
            "postgresql+asyncpg://bevosita:bevosita@localhost"
        )
        assert "change" in entries["JWT_SECRET"].lower()
        assert entries["FRONTEND_ORIGINS"].startswith("http://localhost")
        assert entries["API_PUBLIC_URL"].startswith("http://localhost")
        assert entries["FRONTEND_PUBLIC_URL"].startswith("http://localhost")
        assert "placeholder" in entries["OPENAI_API_KEY"]
        assert "placeholder" in entries["RESEND_API_KEY"]
