from datetime import datetime, timedelta, timezone as dt_timezone

import pytest

from agents.pipeline import run_pipeline

pytestmark = pytest.mark.usefixtures("heuristic_only")


def _hours_ago(hours: float) -> str:
    return (datetime.now(dt_timezone.utc) - timedelta(hours=hours)).isoformat()


def _txn(**overrides):
    base = dict(kind="payment_degradation", amount=1000.0, currency="INR", failure_code="", customer_id="cust_x")
    base.update(overrides)
    return base


@pytest.mark.parametrize(
    "failure_code,expected_root_cause",
    [
        ("insufficient_funds", "insufficient_funds"),
        ("card_declined", "card_declined"),
        ("expired", "card_expired"),
        ("payment_timed_out", "network_timeout"),
        ("request_timed_out", "network_timeout"),
        ("reqauth_mandate_not_acknowledged", "reqauth_mandate_not_acknowledged"),
    ],
)
def test_diagnosis_matches_failure_code_pattern(failure_code, expected_root_cause):
    result = run_pipeline(_txn(failure_code=failure_code))
    assert result["diagnosis"]["root_cause"] == expected_root_cause


def test_diagnosis_rule_order_expired_beats_card_declined_on_overlap():
    """_DIAGNOSIS_RULES (the substring fallback tier) checks "expired" before
    "card_declined" — a failure code containing both (like the retired seed shape
    "card_declined_expired", no longer produced by seed_data.py but still a valid
    input the fallback tier must handle per design.md Decision 1's mitigation) is the
    more specific, more actionable diagnosis: an expired card can't succeed on a
    same-card retry, so it must route to card_expired (-> new_payment_link), not a
    generic card_declined (-> retry_order)."""
    result = run_pipeline(_txn(failure_code="card_declined_expired"))
    assert result["diagnosis"]["root_cause"] == "card_expired"
    assert result["decision"]["chosen_action"] == "new_payment_link"


@pytest.mark.parametrize(
    "failure_code,expected_root_cause",
    [
        ("authentication_failed", "authentication_failed"),
        ("card_not_enrolled", "card_not_enrolled"),
        ("invalid_vpa", "invalid_vpa"),
        ("vpa_resolution_failed", "vpa_resolution_failed"),
        ("bank_technical_error", "technical_error"),
        ("gateway_technical_error", "technical_error"),
        ("issuer_technical_error", "technical_error"),
        ("transaction_limit_exceeded", "transaction_limit_exceeded"),
        ("incorrect_cvv", "incorrect_cvv"),
        ("debit_instrument_blocked", "debit_instrument_blocked"),
        ("debit_instrument_inactive", "debit_instrument_inactive"),
    ],
)
def test_diagnosis_resolves_new_real_code_to_specific_root_cause(failure_code, expected_root_cause):
    result = run_pipeline(_txn(failure_code=failure_code))
    diagnosis = result["diagnosis"]
    assert diagnosis["root_cause"] == expected_root_cause
    assert diagnosis["confidence"] >= 0.60


@pytest.mark.parametrize("failure_code", ["payment_timed_out", "request_timed_out"])
def test_diagnosis_recognizes_timed_out_variants_as_timeout_not_generic_default(failure_code):
    """spec scenario: a `payment_timed_out`/`request_timed_out` code resolves to the
    same timeout-class root cause as the "timeout" substring pattern, and must NOT
    fall through to the generic kind-level default. Confidence intentionally matches
    the existing "timeout"/"network" ambiguous-signal convention (0.55, itself below
    the guardrail floor) — recognized as a timeout, not treated as unclassified."""
    result = run_pipeline(_txn(failure_code=failure_code))
    diagnosis = result["diagnosis"]
    assert diagnosis["root_cause"] == "network_timeout"
    assert diagnosis["root_cause"] != "payment_declined"


def test_diagnosis_exact_match_takes_precedence_over_substring_pattern():
    """`mandate_creation_failed` is an exact-match `_CODE_DIAGNOSES` entry with its own
    root cause and confidence (0.70), but it also contains the "mandate" substring
    needle from the `_DIAGNOSIS_RULES` fallback tier, which alone would resolve it to
    the generic `mandate_charge_failed` (0.75). The exact match must win outright."""
    result = run_pipeline(_txn(kind="subscription_failure", failure_code="mandate_creation_failed"))
    diagnosis = result["diagnosis"]
    assert diagnosis["root_cause"] == "mandate_creation_failed"
    assert diagnosis["root_cause"] != "mandate_charge_failed"
    assert diagnosis["confidence"] == 0.70


def test_diagnosis_exact_match_used_even_when_general_pattern_also_matches():
    """`card_expired` is both an exact-match entry and a match for the broader
    "expired" substring pattern; the result must be the same exact-match resolution
    either way (spec scenario: "An exact known-code match is used even when it would
    also satisfy a general pattern")."""
    result = run_pipeline(_txn(failure_code="card_expired"))
    assert result["diagnosis"]["root_cause"] == "card_expired"
    assert result["diagnosis"]["confidence"] == 0.90


def test_risk_check_failed_always_escalates_regardless_of_confidence():
    """A risk/fraud-engine hold must never be auto-retried, regardless of how
    confident the diagnosis is — this is a deliberate decision-layer routing choice
    (design.md Decision 2), not a low-confidence escalation."""
    result = run_pipeline(_txn(failure_code="payment_risk_check_failed"))
    diagnosis = result["diagnosis"]
    assert diagnosis["root_cause"] == "risk_check_failed"
    assert diagnosis["confidence"] >= 0.60
    assert result["decision"]["chosen_action"] == "escalate"


def test_diagnosis_blank_failure_code_is_low_confidence_unknown():
    result = run_pipeline(_txn(failure_code=""))
    diagnosis = result["diagnosis"]
    assert diagnosis["root_cause"] == "unknown"
    assert diagnosis["confidence"] < 0.60


def test_diagnosis_unrecognized_code_falls_back_to_kind_default():
    """Uses kind="payment_degradation" (not "receivable") deliberately: design.md
    Decision 5 lowers _KIND_DEFAULTS["payment_degradation"]'s confidence from 0.60 to
    0.55 (strictly below the guardrail confidence floor) so a payment-degradation code
    this heuristic can't classify specifically escalates to a human by default instead
    of silently auto-acting — receivable's kind default (0.88) is untouched by this
    change, so it no longer demonstrates the behavior this test is about."""
    result = run_pipeline(_txn(kind="payment_degradation", failure_code="something_no_rule_matches"))
    diagnosis = result["diagnosis"]
    assert diagnosis["root_cause"] == "payment_declined"
    assert diagnosis["confidence"] == 0.55
    assert result["decision"]["chosen_action"] == "escalate"


def test_diagnosis_unrecognized_receivable_code_still_meets_kind_default_floor():
    """receivable's kind default is unaffected by design.md Decision 5 (only
    payment_degradation's moved) — still resolves at/above the guardrail floor."""
    result = run_pipeline(_txn(kind="receivable", failure_code="something_no_rule_matches"))
    assert result["diagnosis"]["root_cause"] == "invoice_overdue"
    assert result["diagnosis"]["confidence"] >= 0.60


def test_subscription_failure_card_decline_routes_to_registration_link():
    result = run_pipeline(_txn(kind="subscription_failure", failure_code="card_declined"))
    assert result["diagnosis"]["root_cause"] == "card_declined"
    assert result["decision"]["chosen_action"] == "registration_link"


def test_payment_degradation_card_decline_routes_to_retry_order():
    result = run_pipeline(_txn(kind="payment_degradation", failure_code="card_declined"))
    assert result["decision"]["chosen_action"] == "retry_order"


def test_subscription_failure_never_produces_retry_order():
    """Regression guard: a subscription-context transaction must never pick an
    Order-reopen action — there's no order to reopen for a recurring mandate."""
    for failure_code in ["card_declined", "insufficient_funds", "mandate_charge_failed", ""]:
        result = run_pipeline(_txn(kind="subscription_failure", failure_code=failure_code))
        assert result["decision"]["chosen_action"] != "retry_order", (
            f"subscription_failure with failure_code={failure_code!r} picked retry_order"
        )


def test_receivable_routes_to_invoice_reminder():
    result = run_pipeline(_txn(kind="receivable", failure_code="invoice_overdue"))
    assert result["decision"]["chosen_action"] == "invoice_reminder"


def test_low_confidence_diagnosis_escalates_instead_of_guessing():
    result = run_pipeline(_txn(failure_code=""))
    assert result["diagnosis"]["confidence"] < 0.60
    assert result["decision"]["chosen_action"] == "escalate"


def _dropoff_txn(*, hours_ago, amount, last_payment_method):
    return _txn(
        kind="checkout_dropoff",
        failure_code="",
        amount=amount,
        checkout_initiated_at=_hours_ago(hours_ago),
        last_payment_method=last_payment_method,
    )


@pytest.mark.parametrize(
    "hours_ago,amount,last_payment_method,expected_root_cause,expected_confidence",
    [
        (1, 10000.0, "card", "high_value_recent_dropoff", 0.85),
        (1, 2000.0, "upi", "recent_dropoff_payment_attempted", 0.80),
        (10, 2000.0, "netbanking", "short_window_dropoff", 0.68),
        (50, 2000.0, "", "browse_abandonment", 0.45),
        (50, 2000.0, "card", "aging_dropoff", 0.55),
        (200, 2000.0, "card", "cold_dropoff", 0.32),
    ],
)
def test_checkout_dropoff_diagnosis_decision_tree(hours_ago, amount, last_payment_method, expected_root_cause, expected_confidence):
    result = run_pipeline(_dropoff_txn(hours_ago=hours_ago, amount=amount, last_payment_method=last_payment_method))
    diagnosis = result["diagnosis"]
    assert diagnosis["root_cause"] == expected_root_cause
    assert diagnosis["confidence"] == expected_confidence


def test_checkout_dropoff_missing_checkout_initiated_at_does_not_crash():
    """No time signal at all (e.g. a malformed/absent value) must not raise — it's
    treated as 'long ago', same honest low-confidence territory as any other unclear
    signal, per _hours_since's documented behavior."""
    txn = _txn(kind="checkout_dropoff", failure_code="", amount=2000.0, checkout_initiated_at=None, last_payment_method="")
    result = run_pipeline(txn)
    assert result["diagnosis"]["root_cause"] == "browse_abandonment"


def test_checkout_dropoff_confident_diagnosis_routes_to_new_payment_link():
    result = run_pipeline(_dropoff_txn(hours_ago=1, amount=10000.0, last_payment_method="card"))
    assert result["decision"]["chosen_action"] == "new_payment_link"
    assert "checkout" in result["decision"]["reasoning_text"].lower()


def test_checkout_dropoff_low_confidence_escalates_via_existing_floor():
    """aging_dropoff/cold_dropoff/browse_abandonment all sit below the confidence floor
    and must escalate — with zero new escalation code, via the same confidence check
    every other kind already goes through."""
    for hours_ago, method in [(50, "card"), (200, "card"), (10, "")]:
        result = run_pipeline(_dropoff_txn(hours_ago=hours_ago, amount=2000.0, last_payment_method=method))
        assert result["diagnosis"]["confidence"] < 0.60
        assert result["decision"]["chosen_action"] == "escalate"


def test_checkout_dropoff_never_produces_retry_order():
    """Regression guard: a checkout_dropoff transaction must never pick retry_order —
    Checkout was never completed, so there's no failed payment to retry, even when a
    razorpay_order_id happens to be present (design.md Decision 4)."""
    for hours_ago in [0.5, 1, 10, 50, 200]:
        for amount in [500.0, 2000.0, 15000.0]:
            for last_payment_method in ["", "card", "upi"]:
                txn = _dropoff_txn(hours_ago=hours_ago, amount=amount, last_payment_method=last_payment_method)
                txn["razorpay_order_id"] = "order_sim_dropoff"
                result = run_pipeline(txn)
                assert result["decision"]["chosen_action"] != "retry_order", (
                    f"checkout_dropoff with hours_ago={hours_ago}, amount={amount}, "
                    f"last_payment_method={last_payment_method!r} picked retry_order"
                )
