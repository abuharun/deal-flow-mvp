"""Pure precondition evaluator for triggering AI research.

No database, no HTTP, no OpenAI: evaluate_ai_preconditions takes plain
values and returns canonical missing-reason codes only. This is the seam
the next slice (actually triggering AI analysis) will call.
"""

import itertools

import pytest

from app.services.ai_precondition import AiPreconditionReason, evaluate_ai_preconditions

ALL_GOOD = {
    "startup_submitted": True,
    "deck_exists": True,
    "payment_status": "paid",
    "consent_granted": True,
}


def test_all_preconditions_met_is_eligible_with_no_missing_reasons():
    result = evaluate_ai_preconditions(**ALL_GOOD)
    assert result.eligible is True
    assert result.missing == ()


def test_startup_not_submitted_is_reported():
    result = evaluate_ai_preconditions(**{**ALL_GOOD, "startup_submitted": False})
    assert result.eligible is False
    assert AiPreconditionReason.STARTUP_NOT_SUBMITTED in result.missing


def test_missing_deck_is_reported():
    result = evaluate_ai_preconditions(**{**ALL_GOOD, "deck_exists": False})
    assert result.eligible is False
    assert AiPreconditionReason.DECK_MISSING in result.missing


@pytest.mark.parametrize("payment_status", [None, "failed"])
def test_unpaid_payment_is_reported(payment_status):
    result = evaluate_ai_preconditions(**{**ALL_GOOD, "payment_status": payment_status})
    assert result.eligible is False
    assert AiPreconditionReason.PAYMENT_NOT_PAID in result.missing


def test_missing_consent_is_reported():
    result = evaluate_ai_preconditions(**{**ALL_GOOD, "consent_granted": False})
    assert result.eligible is False
    assert AiPreconditionReason.CONSENT_MISSING in result.missing


def test_every_combination_of_missing_reasons_is_reported_exhaustively():
    keys = list(ALL_GOOD)
    for combo in itertools.product([True, False], repeat=len(keys)):
        kwargs = dict(zip(keys, combo, strict=True))
        if kwargs["payment_status"] is False:
            kwargs["payment_status"] = None
        else:
            kwargs["payment_status"] = "paid" if kwargs["payment_status"] else "failed"
        result = evaluate_ai_preconditions(**kwargs)
        expected_missing = set()
        if not kwargs["startup_submitted"]:
            expected_missing.add(AiPreconditionReason.STARTUP_NOT_SUBMITTED)
        if not kwargs["deck_exists"]:
            expected_missing.add(AiPreconditionReason.DECK_MISSING)
        if kwargs["payment_status"] != "paid":
            expected_missing.add(AiPreconditionReason.PAYMENT_NOT_PAID)
        if not kwargs["consent_granted"]:
            expected_missing.add(AiPreconditionReason.CONSENT_MISSING)
        assert set(result.missing) == expected_missing
        assert result.eligible == (not expected_missing)


def test_evaluator_never_returns_free_text_answers_or_urls():
    result = evaluate_ai_preconditions(
        startup_submitted=False, deck_exists=False, payment_status=None, consent_granted=False
    )
    for reason in result.missing:
        assert isinstance(reason, AiPreconditionReason)
        assert reason.value.replace("_", "").isalpha()
