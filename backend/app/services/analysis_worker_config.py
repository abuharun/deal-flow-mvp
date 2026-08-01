"""Explicit worker-startup config validation.

`app.config.Settings` makes every OpenAI/analysis field optional with a safe
default specifically so the web API can construct Settings and start with
zero AI config -- see the field comment there. This module is the ONE place
that turns "missing AI config" into a hard failure, and it is called only by
the worker's CLI entrypoint at startup, never at web app import or
`create_app`. `WorkerConfigError.reason` is a fixed, safe code; the actual
key/price values never appear in the exception text.
"""

from dataclasses import dataclass
from decimal import Decimal

from app.config import SUPPORTED_REPORT_SCHEMA_VERSIONS, Settings


class WorkerConfigError(Exception):
    """The worker cannot start: required AI config is missing or invalid."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"worker config invalid: {reason}")
        self.reason = reason


@dataclass(frozen=True, slots=True)
class WorkerConfig:
    """Validated, non-optional worker config -- safe to pass to the provider."""

    api_key: str
    model: str
    prompt_version: str
    report_schema_version: str
    request_timeout_seconds: float
    max_output_tokens: int
    input_price_per_million_usd: Decimal
    output_price_per_million_usd: Decimal
    web_search_cost_usd: Decimal
    max_cost_usd: Decimal


def require_worker_config(settings: Settings) -> WorkerConfig:
    """Validate `settings` carries everything the worker needs, or raise.

    Called once at worker startup (CLI), before the worker claims any job.
    """
    if not settings.openai_api_key:
        raise WorkerConfigError("openai_api_key_missing")
    if (
        settings.openai_input_price_per_million_usd is None
        or settings.openai_output_price_per_million_usd is None
    ):
        raise WorkerConfigError("openai_pricing_missing")
    if settings.openai_web_search_cost_usd is None:
        raise WorkerConfigError("openai_web_search_cost_missing")
    # Settings already validates this at construction time; re-checked here
    # too (defense in depth, same posture as re-validating PDF bounds at
    # extraction time) so a worker never starts against an unsupported
    # schema even if that guarantee ever weakens upstream.
    if settings.openai_report_schema_version not in SUPPORTED_REPORT_SCHEMA_VERSIONS:
        raise WorkerConfigError("report_schema_version_unsupported")
    return WorkerConfig(
        api_key=settings.openai_api_key,
        model=settings.openai_analysis_model,
        prompt_version=settings.openai_prompt_version,
        report_schema_version=settings.openai_report_schema_version,
        request_timeout_seconds=settings.openai_request_timeout_seconds,
        max_output_tokens=settings.openai_max_output_tokens,
        input_price_per_million_usd=settings.openai_input_price_per_million_usd,
        output_price_per_million_usd=settings.openai_output_price_per_million_usd,
        web_search_cost_usd=settings.openai_web_search_cost_usd,
        max_cost_usd=settings.analysis_max_cost_usd,
    )
