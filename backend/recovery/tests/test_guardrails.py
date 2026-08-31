import threading
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.conf import settings
from django.db import connection
from django.utils import timezone

from recovery.guardrails import evaluate_guardrails
from recovery.models import Action, ContactCooldown, Decision, Diagnosis, GuardrailEvent, PromiseToPay, Transaction

pytestmark = pytest.mark.django_db


def _diag(confidence=0.9):
    return Diagnosis(root_cause="card_declined", confidence=confidence, reasoning_text="test")


def _dec(action=Decision.Action.NEW_PAYMENT_LINK):
    return Decision(chosen_action=action, reasoning_text="test")


def test_confidence_floor_blocks_low_confidence(make_transaction):
    txn = make_transaction()
    verdict = evaluate_guardrails(txn, _diag(confidence=0.35), _dec())
    assert verdict.escalate is True
    assert verdict.cleared is False
    event = GuardrailEvent.objects.get(transaction=txn, rule_name="confidence_floor")
    assert event.rule_result == GuardrailEvent.Result.BLOCKED


def test_confidence_floor_passes_high_confidence(make_transaction):
    txn = make_transaction(amount=1000)
    verdict = evaluate_guardrails(txn, _diag(confidence=0.9), _dec(Decision.Action.INVOICE_REMINDER))
    assert verdict.escalate is False
    event = GuardrailEvent.objects.get(transaction=txn, rule_name="confidence_floor")
    assert event.rule_result == GuardrailEvent.Result.PASSED


def test_max_retry_attempts_blocks_after_limit(make_transaction):
    txn = make_transaction()
    for _ in range(3):
        Action.objects.create(transaction=txn, action_type=Action.Type.RETRY, result=Action.Result.FAILED)
    verdict = evaluate_guardrails(txn, _diag(), _dec(Decision.Action.RETRY_ORDER))
    assert verdict.escalate is True
    event = GuardrailEvent.objects.get(transaction=txn, rule_name="max_retry_attempts")
    assert event.rule_result == GuardrailEvent.Result.BLOCKED


def test_max_retry_attempts_passes_under_limit(make_transaction):
    txn = make_transaction(failure_code="insufficient_funds")
    Action.objects.create(transaction=txn, action_type=Action.Type.RETRY, result=Action.Result.FAILED)
    verdict = evaluate_guardrails(txn, _diag(), _dec(Decision.Action.RETRY_ORDER))
    event = GuardrailEvent.objects.get(transaction=txn, rule_name="max_retry_attempts")
    assert event.rule_result == GuardrailEvent.Result.PASSED
    assert verdict.cleared is True


def test_spend_ceiling_blocks_regardless_of_confidence(make_transaction):
    txn = make_transaction(amount=999999)
    verdict = evaluate_guardrails(txn, _diag(confidence=0.99), _dec(Decision.Action.INVOICE_REMINDER))
    assert verdict.escalate is True
    event = GuardrailEvent.objects.get(transaction=txn, rule_name="spend_ceiling")
    assert event.rule_result == GuardrailEvent.Result.BLOCKED


def test_spend_ceiling_passes_under_ceiling(make_transaction):
    txn = make_transaction(amount=100, failure_code="insufficient_funds")
    verdict = evaluate_guardrails(txn, _diag(), _dec(Decision.Action.RETRY_ORDER))
    event = GuardrailEvent.objects.get(transaction=txn, rule_name="spend_ceiling")
    assert event.rule_result == GuardrailEvent.Result.PASSED


def test_card_decline_retry_is_held_not_immediate(make_transaction):
    txn = make_transaction(failure_code="card_declined", amount=500)
    verdict = evaluate_guardrails(txn, _diag(), _dec(Decision.Action.RETRY_ORDER))
    assert verdict.cleared is False
    assert verdict.escalate is False
    assert verdict.hold_until is not None
    assert verdict.hold_until > timezone.now()
    assert verdict.hold_reason == "cooldown_between_retries"


def test_non_card_retry_is_not_held_by_cooldown_rule(make_transaction):
    txn = make_transaction(failure_code="insufficient_funds", amount=500)
    verdict = evaluate_guardrails(txn, _diag(), _dec(Decision.Action.RETRY_ORDER))
    event = GuardrailEvent.objects.get(transaction=txn, rule_name="cooldown_between_retries")
    assert event.rule_result == GuardrailEvent.Result.PASSED
    assert verdict.cleared is True


def test_contact_cap_passes_first_contact(make_transaction):
    txn = make_transaction(customer_id="cust_first_contact", amount=500)
    verdict = evaluate_guardrails(txn, _diag(), _dec(Decision.Action.NEW_PAYMENT_LINK))
    assert verdict.cleared is True
    assert ContactCooldown.objects.get(customer_id="cust_first_contact")


def test_contact_cap_blocks_repeat_contact_within_window(make_transaction):
    txn = make_transaction(customer_id="cust_repeat", amount=500)
    ContactCooldown.objects.create(customer_id="cust_repeat", last_contacted_at=timezone.now() - timedelta(hours=1))
    verdict = evaluate_guardrails(txn, _diag(), _dec(Decision.Action.NEW_PAYMENT_LINK))
    assert verdict.cleared is False
    assert verdict.hold_reason == "contact_frequency_cap"


@pytest.mark.django_db(transaction=True)
@pytest.mark.skipif(
    not connection.features.has_select_for_update,
    reason="select_for_update() is a no-op on this backend (e.g. SQLite has no row-level "
    "locking), so the race this test proves doesn't apply — the guarantee that matters "
    "ships against Postgres in production.",
)
def test_contact_cap_race_only_one_of_two_concurrent_contacts_clears(make_transaction):
    """Two threads evaluate a NEW_PAYMENT_LINK decision for the same brand-new customer
    at (as close to) the same time. select_for_update() must serialize them so at most
    one clears; the loser sees itself inside the just-created cooldown window."""
    txn_a = make_transaction(customer_id="cust_race", amount=500)
    txn_b = make_transaction(customer_id="cust_race", amount=500)

    results = {}
    start_barrier = threading.Barrier(2)

    def worker(key, txn_id):
        from django.db import close_old_connections, connections
        from recovery.models import Transaction

        close_old_connections()
        try:
            txn = Transaction.objects.get(id=txn_id)
            start_barrier.wait(timeout=5)
            verdict = evaluate_guardrails(txn, _diag(), _dec(Decision.Action.NEW_PAYMENT_LINK))
            results[key] = verdict.cleared
        finally:
            connections.close_all()

    t1 = threading.Thread(target=worker, args=("a", txn_a.id))
    t2 = threading.Thread(target=worker, args=("b", txn_b.id))
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    assert set(results.keys()) == {"a", "b"}
    cleared_count = sum(1 for v in results.values() if v)
    assert cleared_count == 1, f"expected exactly one of two concurrent contacts to clear, got {results}"
    assert ContactCooldown.objects.filter(customer_id="cust_race").count() == 1


def test_broken_promise_blocks_and_escalates_even_outside_cooldown(make_transaction):
    txn = make_transaction(customer_id="cust_broken_promise", amount=500)
    ContactCooldown.objects.create(
        customer_id="cust_broken_promise", last_contacted_at=timezone.now() - timedelta(days=10)
    )
    other_txn = make_transaction(customer_id="cust_broken_promise", amount=200)
    PromiseToPay.objects.create(
        transaction=other_txn, promised_amount=200, promise_date=timezone.localdate() - timedelta(days=1),
        source=PromiseToPay.Source.VOICE, status=PromiseToPay.Status.BROKEN,
    )

    verdict = evaluate_guardrails(txn, _diag(confidence=0.9), _dec(Decision.Action.NEW_PAYMENT_LINK))

    assert verdict.cleared is False
    assert verdict.escalate is True
    assert verdict.hold_until is None
    event = GuardrailEvent.objects.filter(transaction=txn, rule_name="contact_frequency_cap").latest("triggered_at")
    assert event.rule_result == GuardrailEvent.Result.BLOCKED


def test_no_broken_promise_is_unaffected_by_the_extension(make_transaction):
    txn = make_transaction(customer_id="cust_no_broken_promise", amount=500)
    verdict = evaluate_guardrails(txn, _diag(confidence=0.9), _dec(Decision.Action.NEW_PAYMENT_LINK))
    assert verdict.cleared is True
    assert verdict.escalate is False


def _local_time_at(hour):
    return timezone.localtime(timezone.now()).replace(hour=hour, minute=0, second=0, microsecond=0)


def test_compliance_hours_blocks_b2b_contact_outside_window(make_transaction):
    txn = make_transaction(kind=txn_kind_receivable(), customer_id="cust_hours_blocked", amount=500)
    with patch("recovery.guardrails.timezone.now", return_value=_local_time_at(3)):
        verdict = evaluate_guardrails(txn, _diag(), _dec(Decision.Action.INVOICE_REMINDER))
    assert verdict.cleared is False
    assert verdict.hold_reason == "compliance_hours"


def test_compliance_hours_passes_b2b_contact_inside_window(make_transaction):
    txn = make_transaction(kind=txn_kind_receivable(), customer_id="cust_hours_passed", amount=500)
    with patch("recovery.guardrails.timezone.now", return_value=_local_time_at(12)):
        verdict = evaluate_guardrails(txn, _diag(), _dec(Decision.Action.INVOICE_REMINDER))
    assert verdict.cleared is True


def test_compliance_hours_does_not_apply_to_non_b2b(make_transaction):
    txn = make_transaction(amount=500, failure_code="insufficient_funds")
    with patch("recovery.guardrails.timezone.now", return_value=_local_time_at(3)):
        verdict = evaluate_guardrails(txn, _diag(), _dec(Decision.Action.RETRY_ORDER))
    event = GuardrailEvent.objects.get(
        transaction=txn, rule_name="compliance_hours", detail="not a B2B contact action"
    )
    assert event.rule_result == GuardrailEvent.Result.PASSED
    assert verdict.cleared is True


def txn_kind_receivable():
    from recovery.models import Transaction

    return Transaction.Kind.RECEIVABLE


def test_all_rules_pass_yields_cleared_verdict(make_transaction):
    txn = make_transaction(amount=500, failure_code="insufficient_funds", customer_id="cust_all_clear")
    verdict = evaluate_guardrails(txn, _diag(confidence=0.85), _dec(Decision.Action.RETRY_ORDER))
    assert verdict.cleared is True
    assert verdict.escalate is False
    assert verdict.hold_until is None
    assert GuardrailEvent.objects.filter(transaction=txn, rule_result=GuardrailEvent.Result.BLOCKED).count() == 0


def _dropoff_txn(make_transaction, **overrides):
    overrides.setdefault("failure_code", "")
    return make_transaction(kind=Transaction.Kind.CHECKOUT_DROPOFF, **overrides)


def test_checkout_dropoff_confidence_floor_blocks_low_confidence(make_transaction):
    txn = _dropoff_txn(make_transaction, customer_id="cust_dropoff_low_conf", amount=500)
    verdict = evaluate_guardrails(txn, _diag(confidence=0.32), _dec(Decision.Action.NEW_PAYMENT_LINK))
    assert verdict.escalate is True
    event = GuardrailEvent.objects.get(transaction=txn, rule_name="confidence_floor")
    assert event.rule_result == GuardrailEvent.Result.BLOCKED


def test_checkout_dropoff_confidence_floor_passes_high_confidence(make_transaction):
    txn = _dropoff_txn(make_transaction, customer_id="cust_dropoff_high_conf", amount=500)
    verdict = evaluate_guardrails(txn, _diag(confidence=0.85), _dec(Decision.Action.NEW_PAYMENT_LINK))
    event = GuardrailEvent.objects.get(transaction=txn, rule_name="confidence_floor")
    assert event.rule_result == GuardrailEvent.Result.PASSED


def test_checkout_dropoff_spend_ceiling_blocks_high_value_cart(make_transaction):
    over_ceiling = settings.GUARDRAILS["SPEND_CEILING_INR"] + 1000
    txn = _dropoff_txn(make_transaction, customer_id="cust_dropoff_over_ceiling", amount=over_ceiling)
    verdict = evaluate_guardrails(txn, _diag(confidence=0.99), _dec(Decision.Action.NEW_PAYMENT_LINK))
    assert verdict.escalate is True
    event = GuardrailEvent.objects.get(transaction=txn, rule_name="spend_ceiling")
    assert event.rule_result == GuardrailEvent.Result.BLOCKED


def test_checkout_dropoff_spend_ceiling_passes_under_ceiling(make_transaction):
    txn = _dropoff_txn(make_transaction, customer_id="cust_dropoff_under_ceiling", amount=500)
    verdict = evaluate_guardrails(txn, _diag(confidence=0.85), _dec(Decision.Action.NEW_PAYMENT_LINK))
    event = GuardrailEvent.objects.get(transaction=txn, rule_name="spend_ceiling")
    assert event.rule_result == GuardrailEvent.Result.PASSED


def test_checkout_dropoff_contact_frequency_cap_blocks_repeat_contact(make_transaction):
    txn = _dropoff_txn(make_transaction, customer_id="cust_dropoff_repeat", amount=500)
    ContactCooldown.objects.create(customer_id="cust_dropoff_repeat", last_contacted_at=timezone.now() - timedelta(hours=1))
    verdict = evaluate_guardrails(txn, _diag(confidence=0.85), _dec(Decision.Action.NEW_PAYMENT_LINK))
    assert verdict.cleared is False
    assert verdict.hold_reason == "contact_frequency_cap"


def test_checkout_dropoff_contact_frequency_cap_passes_first_contact(make_transaction):
    txn = _dropoff_txn(make_transaction, customer_id="cust_dropoff_first_contact", amount=500)
    verdict = evaluate_guardrails(txn, _diag(confidence=0.85), _dec(Decision.Action.NEW_PAYMENT_LINK))
    assert verdict.cleared is True
    assert ContactCooldown.objects.get(customer_id="cust_dropoff_first_contact")


def test_checkout_dropoff_is_not_held_outside_business_hours(make_transaction):
    """Regression guard distinguishing checkout_dropoff from receivable: the B2B
    compliance-hours rule is gated on Kind.RECEIVABLE only, so a checkout_dropoff's
    new_payment_link decision must clear even outside business hours."""
    txn = _dropoff_txn(make_transaction, customer_id="cust_dropoff_hours", amount=500)
    with patch("recovery.guardrails.timezone.now", return_value=_local_time_at(3)):
        verdict = evaluate_guardrails(txn, _diag(confidence=0.85), _dec(Decision.Action.NEW_PAYMENT_LINK))
    event = GuardrailEvent.objects.get(
        transaction=txn, rule_name="compliance_hours", detail="not a B2B contact action"
    )
    assert event.rule_result == GuardrailEvent.Result.PASSED
    assert verdict.cleared is True


def test_checkout_dropoff_never_hits_retry_guardrails(make_transaction):
    """max_retry_attempts and cooldown_between_retries are both gated on
    chosen_action in RETRY_ACTIONS ({retry_order}) — never true for checkout_dropoff,
    which always decides new_payment_link or escalate. Both rules PASS as a no-op,
    exactly like any other kind's non-retry decision."""
    txn = _dropoff_txn(make_transaction, customer_id="cust_dropoff_no_retry", amount=500)
    verdict = evaluate_guardrails(txn, _diag(confidence=0.85), _dec(Decision.Action.NEW_PAYMENT_LINK))
    max_retry_event = GuardrailEvent.objects.filter(transaction=txn, rule_name="max_retry_attempts")
    assert not max_retry_event.exists()
    cooldown_event = GuardrailEvent.objects.get(transaction=txn, rule_name="cooldown_between_retries")
    assert cooldown_event.rule_result == GuardrailEvent.Result.PASSED
    assert verdict.cleared is True
