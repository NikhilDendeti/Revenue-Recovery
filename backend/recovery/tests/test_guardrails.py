import threading
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.db import connection
from django.utils import timezone

from recovery.guardrails import evaluate_guardrails
from recovery.models import Action, ContactCooldown, Decision, Diagnosis, GuardrailEvent, PromiseToPay

pytestmark = pytest.mark.django_db


def _diag(confidence=0.9):
    return Diagnosis(root_cause="card_declined", confidence=confidence, reasoning_text="test")


def _dec(action=Decision.Action.NEW_PAYMENT_LINK):
    return Decision(chosen_action=action, reasoning_text="test")


# --- 1. Confidence floor ---


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


# --- 2. Max retry attempts ---


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
    # insufficient_funds (not "card") clears the cooldown rule too, so this should fully clear
    assert verdict.cleared is True


# --- 3. Spend / action ceiling ---


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


# --- 4. Cooldown between retries ---


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


# --- 5. Contact frequency cap ---


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


# --- 5b. Contact frequency cap, extended: a broken promise-to-pay ---


def test_broken_promise_blocks_and_escalates_even_outside_cooldown(make_transaction):
    txn = make_transaction(customer_id="cust_broken_promise", amount=500)
    # Well outside the ordinary 24h cooldown — the timestamp check alone would pass.
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


# --- 6. Compliance hours ---


def _local_time_at(hour):
    # Build an aware datetime at `hour` in the project's actual local timezone
    # (Asia/Kolkata) — replacing hour on a UTC-aware now() would silently test the
    # wrong wall-clock hour once converted to local time inside guardrails.py.
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


# --- Full pass ---


def test_all_rules_pass_yields_cleared_verdict(make_transaction):
    txn = make_transaction(amount=500, failure_code="insufficient_funds", customer_id="cust_all_clear")
    verdict = evaluate_guardrails(txn, _diag(confidence=0.85), _dec(Decision.Action.RETRY_ORDER))
    assert verdict.cleared is True
    assert verdict.escalate is False
    assert verdict.hold_until is None
    assert GuardrailEvent.objects.filter(transaction=txn, rule_result=GuardrailEvent.Result.BLOCKED).count() == 0
