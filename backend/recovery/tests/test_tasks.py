from datetime import timedelta

import pytest
from django.utils import timezone

from recovery.models import (
    Action,
    AuditLogEntry,
    Decision,
    Diagnosis,
    GuardrailEvent,
    ScheduledAction,
    Transaction,
)
from recovery.tasks import (
    dispatch_scheduled_action,
    process_transaction_event,
    sweep_scheduled_actions,
    trigger_voice_showcase,
)

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("no_razorpay_keys")]


def test_process_transaction_event_cleared_records_recovered_or_failed(make_transaction):
    txn = make_transaction(failure_code="insufficient_funds", amount=500, customer_id="cust_cleared")
    process_transaction_event(str(txn.id))

    txn.refresh_from_db()
    assert txn.status in {Transaction.Status.RECOVERED, Transaction.Status.FAILED}
    assert Diagnosis.objects.filter(transaction=txn).exists()
    assert Decision.objects.filter(transaction=txn, chosen_action="retry_order").exists()
    action = Action.objects.get(transaction=txn)
    assert action.result in {Action.Result.SUCCESS, Action.Result.FAILED}
    assert ScheduledAction.objects.filter(transaction=txn).count() == 0
    assert set(
        AuditLogEntry.objects.filter(transaction=txn).values_list("event_type", flat=True)
    ) >= {"detected", "diagnosed", "decided", "action_executed"}


def test_process_transaction_event_held_creates_one_scheduled_action(make_transaction):
    txn = make_transaction(failure_code="card_declined", amount=500, customer_id="cust_held")
    process_transaction_event(str(txn.id))

    txn.refresh_from_db()
    assert txn.status == Transaction.Status.HELD
    scheduled = ScheduledAction.objects.get(transaction=txn)
    assert scheduled.status == ScheduledAction.Status.PENDING
    assert scheduled.run_after > timezone.now()
    assert scheduled.action_type == "retry_order"
    assert Action.objects.filter(transaction=txn).count() == 0


def test_process_transaction_event_escalated_on_low_confidence(make_transaction):
    txn = make_transaction(failure_code="", amount=500, customer_id="cust_escalated")
    process_transaction_event(str(txn.id))

    txn.refresh_from_db()
    assert txn.status == Transaction.Status.ESCALATED
    action = Action.objects.get(transaction=txn)
    assert action.action_type == Action.Type.ESCALATE
    assert ScheduledAction.objects.filter(transaction=txn).count() == 0


def test_process_transaction_event_is_idempotent_against_double_dispatch(make_transaction):
    txn = make_transaction(failure_code="insufficient_funds", amount=500, customer_id="cust_idempotent")
    process_transaction_event(str(txn.id))
    action_count_after_first = Action.objects.filter(transaction=txn).count()

    process_transaction_event(str(txn.id))  # txn.status is no longer OPEN — must no-op
    assert Action.objects.filter(transaction=txn).count() == action_count_after_first


def test_sweep_scheduled_actions_only_dispatches_due_items(make_transaction):
    txn_due = make_transaction(customer_id="cust_due")
    txn_future = make_transaction(customer_id="cust_future")
    due = ScheduledAction.objects.create(
        transaction=txn_due, action_type="retry_order", run_after=timezone.now() - timedelta(minutes=1)
    )
    future = ScheduledAction.objects.create(
        transaction=txn_future, action_type="retry_order", run_after=timezone.now() + timedelta(hours=1)
    )

    result = sweep_scheduled_actions()

    assert result["dispatched"] == 1
    due.refresh_from_db()
    future.refresh_from_db()
    assert due.status == ScheduledAction.Status.DISPATCHED
    assert future.status == ScheduledAction.Status.PENDING


def test_dispatch_scheduled_action_executes_and_uses_prior_diagnosis_confidence(make_transaction):
    txn = make_transaction(failure_code="card_declined", amount=500, customer_id="cust_dispatch")
    Diagnosis.objects.create(transaction=txn, root_cause="card_declined", confidence=0.78, reasoning_text="t")
    scheduled = ScheduledAction.objects.create(
        transaction=txn, action_type="retry_order", reason="cooldown_between_retries",
        run_after=timezone.now() - timedelta(minutes=1), status=ScheduledAction.Status.DISPATCHED,
    )

    dispatch_scheduled_action(scheduled.id)

    assert Action.objects.filter(transaction=txn).count() == 1
    assert AuditLogEntry.objects.filter(transaction=txn, event_type="scheduled_action_dispatched").exists()


def test_trigger_voice_showcase_creates_action_and_promise_to_pay(make_transaction):
    txn = make_transaction(kind=Transaction.Kind.RECEIVABLE, amount=79713, failure_code="invoice_overdue")

    result = trigger_voice_showcase(str(txn.id))

    action = Action.objects.get(transaction=txn, action_type=Action.Type.VOICE)
    assert action.result == Action.Result.SIMULATED
    assert "79,713" in action.api_response["transcript"]
    entry = AuditLogEntry.objects.get(transaction=txn, event_type="voice_promise_to_pay")
    assert entry.payload["promise_to_pay_date"] == result["promise_to_pay_date"]


def test_guardrail_events_are_logged_for_every_processed_transaction(make_transaction):
    txn = make_transaction(failure_code="insufficient_funds", amount=500)
    process_transaction_event(str(txn.id))
    rule_names = set(GuardrailEvent.objects.filter(transaction=txn).values_list("rule_name", flat=True))
    assert rule_names == {
        "confidence_floor", "max_retry_attempts", "spend_ceiling",
        "cooldown_between_retries", "contact_frequency_cap", "compliance_hours",
    }
