"""A deterministic, local-only stand-in for the OpenAI Responses API.

Why this exists: the founder -> investor pilot has to be walkable in a real
browser on a machine that has no OpenAI credentials, without ever pretending
an AI produced something it did not. This module is that seam and nothing
else -- it is not a mock inside a test, it is a named, disclosed provider.

The honesty contract, all of it enforced by
tests/unit/test_local_stub_provider.py:

- The report is FIXED text. It ignores every argument it is handed, so no
  founder answer and no deck byte can ever be echoed back into a stored
  report, and the UI path is identical on every run.
- Every narrative field and every source title carries
  `LOCAL_STUB_DISCLOSURE`, and every source URL is an RFC 2606
  documentation address. Stub content -- including a screenshot of it --
  announces itself as stub content.
- It reports zero tokens, because it spent none. Paired with the zero prices
  in `require_local_stub_worker_config`, the persisted cost estimate is
  $0.0000: true, rather than a plausible-looking invented charge.
- It is only reachable through `require_local_stub_worker_config`, which
  refuses outright when env == "production", and whose WorkerConfig records
  model="local-stub" -- so the dossier's provenance names the stub, never a
  real model that never ran.

Nothing here weakens the real path: `app.services.openai_provider.run_analysis`
still validates this output through `ReportV1Input`, exactly as it validates
a live reply.
"""

import json
from typing import Any

# The phrase that must appear in every human-readable field the stub emits.
# Deliberately in English, like the report schema's `language` literal, and
# deliberately shouty: it is a disclosure, not a footnote.
LOCAL_STUB_DISCLOSURE = "[LOCAL TEST STUB - NOT AI-GENERATED RESEARCH]"

_ACCESSED_DATE = "2026-01-01"

_SUMMARY = (
    f"{LOCAL_STUB_DISCLOSURE} This report was produced by Bevosita's offline test "
    "provider so the founder and investor screens can be exercised end to end "
    "without contacting any AI service. No model was called, no source was read, "
    "and nothing below is a finding about any real company or market. Replace this "
    "run with the live provider before any of it is shown to an investor."
)

_SECTION_NARRATIVE = (
    f"{LOCAL_STUB_DISCLOSURE} Placeholder text stands in for the {{topic}} section. "
    "The live analysis worker fills this section with sourced research; the local "
    "stub fills it with this sentence so the page layout, citation markers, and "
    "founder narrative flow can be verified without a provider call."
)

_NARRATIVE_DRAFT = (
    f"{LOCAL_STUB_DISCLOSURE} This is the draft narrative the local stub hands the "
    "founder to edit. It carries no claim about any company. Rewrite it completely "
    "before approving anything for investors."
)

_SOURCES = (
    ("uzbekistan-central-asia-market", "Uzbekistan and Central Asia market"),
    ("global-competitors", "Global competitors"),
    ("us-vc-readiness", "US venture readiness"),
)


def build_local_stub_report() -> dict[str, Any]:
    """The one fixed report.v1 payload the stub ever returns.

    Rebuilt per call (rather than shared) so no caller can mutate the stub's
    output from under another; equality across calls is part of the contract.
    """
    return {
        "schema_version": "report.v1",
        "language": "en",
        "report": {
            "executive_summary": _SUMMARY,
            "sections": {
                "uzbekistan_central_asia_market": {
                    "narrative": _SECTION_NARRATIVE.format(topic="local market"),
                    "citation_ids": [1],
                },
                "global_competitors": {
                    "narrative": _SECTION_NARRATIVE.format(topic="global competitor"),
                    "citation_ids": [2],
                },
                "us_vc_readiness": {
                    "narrative": _SECTION_NARRATIVE.format(topic="US venture readiness"),
                    "citation_ids": [3],
                },
            },
            "competitors": [],
            "claims": [],
            "contradictions": [],
            # An honest stub has exactly one thing to say about evidence: it
            # has none. Saying so through the schema's own "unknown" status
            # keeps the founder's checklist truthful.
            "unsupported_claims": [
                f"{LOCAL_STUB_DISCLOSURE} Every statement in this report is placeholder "
                "text with no evidence behind it."
            ],
            "readiness_checklist": [
                {
                    "item": "live_analysis_run",
                    "status": "unknown",
                    "confidence": "low",
                    "evidence": [],
                    "evidence_gap": (
                        f"{LOCAL_STUB_DISCLOSURE} No live AI analysis has been run for "
                        "this startup yet."
                    ),
                }
            ],
            "pitch_narrative_draft": _NARRATIVE_DRAFT,
        },
        "sources": [
            {
                "url": f"https://example.com/bevosita-local-stub/{slug}",
                "title": f"{LOCAL_STUB_DISCLOSURE} Placeholder source: {label}",
                "accessed_date": _ACCESSED_DATE,
                "source_quality": "unknown",
                "confidence": "low",
                "snippet": None,
            }
            for slug, label in _SOURCES
        ],
    }


class _StubUsage:
    """Zero tokens, because the stub spent none."""

    input_tokens = 0
    output_tokens = 0


class _StubResponse:
    def __init__(self, output_text: str, call_index: int) -> None:
        self.output_text = output_text
        self.usage = _StubUsage()
        # Shaped like a provider request id but unmistakably not one.
        self.id = f"local-stub-{call_index}"


class _StubResponses:
    def __init__(self) -> None:
        self.calls = 0

    async def create(self, **_ignored: Any) -> _StubResponse:
        """Ignore every argument on purpose -- see the module docstring."""
        self.calls += 1
        return _StubResponse(json.dumps(build_local_stub_report()), self.calls)


class LocalStubResponsesClient:
    """Satisfies `app.services.openai_provider.ResponsesClient`, offline.

    Takes no API key: there is no credential involved in any code path here,
    so there is none to leak, misconfigure, or accidentally spend.
    """

    def __init__(self) -> None:
        self.responses = _StubResponses()

    async def close(self) -> None:
        """Mirrors `openai.AsyncOpenAI.close` so the CLI's teardown is uniform."""
