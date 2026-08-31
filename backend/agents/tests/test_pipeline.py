import pytest

from agents.pipeline import run_pipeline

pytestmark = pytest.mark.usefixtures("heuristic_only")


def _txn(**overrides):
    base = dict(kind="payment_degradation", amount=1000.0, currency="INR", failure_code="", customer_id="cust_x")
    base.update(overrides)
    return base


# --- Diagnosis heuristic: failure-code pattern matches ---


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


# --- Diagnosis heuristic: real Razorpay codes with an unambiguous root cause ---


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
    # Every one of these is a real, known code with an unambiguous cause — confidence
    # must be at or above the guardrail confidence floor so the diagnosis isn't
    # generic-defaulted into a silent escalation.
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
    assert diagnosis["root_cause"] != "payment_declined"  # not the generic kind default


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
    assert diagnosis["confidence"] >= 0.60  # high-confidence diagnosis, not a guess
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


# --- Decision heuristic: kind-aware routing (the subscription regression) ---


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


# --- Escalation on low confidence / unknown root cause ---


def test_low_confidence_diagnosis_escalates_instead_of_guessing():
    result = run_pipeline(_txn(failure_code=""))
    assert result["diagnosis"]["confidence"] < 0.60
    assert result["decision"]["chosen_action"] == "escalate"
