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
        ("network_timeout", "network_timeout"),
        ("issuer_unavailable_timeout", "network_timeout"),
        ("mandate_charge_failed", "mandate_charge_failed"),
    ],
)
def test_diagnosis_matches_failure_code_pattern(failure_code, expected_root_cause):
    result = run_pipeline(_txn(failure_code=failure_code))
    assert result["diagnosis"]["root_cause"] == expected_root_cause


def test_diagnosis_rule_order_expired_beats_card_declined_on_overlap():
    """_DIAGNOSIS_RULES checks "expired" before "card_declined" — a failure code
    containing both (like seed_data's "card_declined_expired") is the more specific,
    more actionable diagnosis: an expired card can't succeed on a same-card retry, so
    it must route to card_expired (-> new_payment_link), not a generic card_declined
    (-> retry_order)."""
    result = run_pipeline(_txn(failure_code="card_declined_expired"))
    assert result["diagnosis"]["root_cause"] == "card_expired"
    assert result["decision"]["chosen_action"] == "new_payment_link"


def test_diagnosis_blank_failure_code_is_low_confidence_unknown():
    result = run_pipeline(_txn(failure_code=""))
    diagnosis = result["diagnosis"]
    assert diagnosis["root_cause"] == "unknown"
    assert diagnosis["confidence"] < 0.60


def test_diagnosis_unrecognized_code_falls_back_to_kind_default():
    result = run_pipeline(_txn(kind="receivable", failure_code="something_no_rule_matches"))
    assert result["diagnosis"]["root_cause"] == "invoice_overdue"
    assert result["diagnosis"]["confidence"] >= 0.60


# --- Decision heuristic: kind-aware routing (the subscription regression) ---


def test_subscription_failure_card_decline_routes_to_registration_link():
    result = run_pipeline(_txn(kind="subscription_failure", failure_code="card_declined_mandate"))
    assert result["diagnosis"]["root_cause"] == "card_declined"
    assert result["decision"]["chosen_action"] == "registration_link"


def test_payment_degradation_card_decline_routes_to_retry_order():
    result = run_pipeline(_txn(kind="payment_degradation", failure_code="card_declined"))
    assert result["decision"]["chosen_action"] == "retry_order"


def test_subscription_failure_never_produces_retry_order():
    """Regression guard: a subscription-context transaction must never pick an
    Order-reopen action — there's no order to reopen for a recurring mandate."""
    for failure_code in ["card_declined_mandate", "insufficient_funds", "mandate_charge_failed", ""]:
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
