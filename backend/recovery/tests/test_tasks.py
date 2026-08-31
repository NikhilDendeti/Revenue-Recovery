from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from recovery import razorpay_client as rc
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
    _execute_action,
    dispatch_scheduled_action,
    process_transaction_event,
    sweep_scheduled_actions,
    trigger_voice_showcase,
)

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("no_razorpay_keys")]


def test_process_transaction_event_cleared_records_recovered_or_failed(make_transaction):
    txn = make_transaction(failure_code="insufficient_funds", amount=500, customer_id="cust_cleared")
    with patch("agents.pipeline.complete_json", return_value=None):
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
    with patch("agents.pipeline.complete_json", return_value=None):
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
    with patch("agents.pipeline.complete_json", return_value=None):
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
    with patch("agents.pipeline.complete_json", return_value=None):
        process_transaction_event(str(txn.id))
    rule_names = set(GuardrailEvent.objects.filter(transaction=txn).values_list("rule_name", flat=True))
    assert rule_names == {
        "confidence_floor", "max_retry_attempts", "spend_ceiling",
        "cooldown_between_retries", "contact_frequency_cap", "compliance_hours",
    }


# --- Action-execution failure handling (harden-action-execution change) ---
# A recovery action's Razorpay call can fail. It must never leave the transaction wedged
# in PROCESSING: an unrecoverable error escalates, and a 404 on a stale order/invoice id
# falls back to a fresh payment link.


def test_execute_action_escalates_on_non_404_api_error(make_transaction):
    txn = make_transaction(failure_code="insufficient_funds", amount=500, customer_id="cust_5xx")
    err = rc.RazorpayError("/orders -> 500: server error", status_code=500)
    with patch("recovery.tasks._call_razorpay", side_effect=err):
        _execute_action(txn, Decision.Action.RETRY_ORDER, 0.82)

    txn.refresh_from_db()
    assert txn.status == Transaction.Status.ESCALATED
    assert txn.status != Transaction.Status.PROCESSING
    assert Action.objects.get(transaction=txn).action_type == Action.Type.ESCALATE
    assert AuditLogEntry.objects.filter(transaction=txn, event_type="action_failed").exists()


def test_execute_action_falls_back_to_payment_link_on_404_order(make_transaction):
    txn = make_transaction(failure_code="insufficient_funds", amount=500, customer_id="cust_404_order")
    err = rc.RazorpayError("/orders/order_missing -> 404: not found", status_code=404)
    # _call_razorpay 404s; the fallback create_payment_link runs for real in simulated mode.
    with patch("recovery.tasks._call_razorpay", side_effect=err):
        _execute_action(txn, Decision.Action.RETRY_ORDER, 0.82)

    txn.refresh_from_db()
    assert txn.status in {Transaction.Status.RECOVERED, Transaction.Status.FAILED}
    action = Action.objects.get(transaction=txn)
    assert action.action_type == Action.Type.EMAIL  # a fresh payment link, not a same-order retry
    assert action.api_response["_recoverai_fallback"]["fallback_from"] == Decision.Action.RETRY_ORDER
    assert action.api_response["short_url"].startswith("https://rzp.io/l/sim")
    assert not AuditLogEntry.objects.filter(transaction=txn, event_type="action_failed").exists()


def test_execute_action_falls_back_to_payment_link_on_404_invoice(make_transaction):
    txn = make_transaction(
        kind=Transaction.Kind.RECEIVABLE, failure_code="invoice_overdue", amount=5000, customer_id="cust_404_inv"
    )
    err = rc.RazorpayError("/invoices/inv_missing/notify_by/sms -> 404", status_code=404)
    with patch("recovery.tasks._call_razorpay", side_effect=err):
        _execute_action(txn, Decision.Action.INVOICE_REMINDER, 0.88)

    txn.refresh_from_db()
    assert txn.status in {Transaction.Status.RECOVERED, Transaction.Status.FAILED}
    action = Action.objects.get(transaction=txn)
    assert action.api_response["_recoverai_fallback"]["fallback_from"] == Decision.Action.INVOICE_REMINDER
    assert action.api_response["short_url"].startswith("https://rzp.io/l/sim")


def test_execute_action_escalates_when_fallback_also_fails(make_transaction):
    txn = make_transaction(failure_code="insufficient_funds", amount=500, customer_id="cust_fallback_fail")
    original = rc.RazorpayError("/orders/x -> 404", status_code=404)
    fallback = rc.RazorpayError("/payment_links -> 500", status_code=500)
    with patch("recovery.tasks._call_razorpay", side_effect=original), \
         patch("recovery.razorpay_client.create_payment_link", side_effect=fallback):
        _execute_action(txn, Decision.Action.RETRY_ORDER, 0.82)

    txn.refresh_from_db()
    assert txn.status == Transaction.Status.ESCALATED
    assert AuditLogEntry.objects.filter(transaction=txn, event_type="action_failed").exists()


def test_process_transaction_event_escalates_on_unexpected_pipeline_error(make_transaction):
    txn = make_transaction(failure_code="insufficient_funds", amount=500, customer_id="cust_pipeline_boom")
    with patch("recovery.tasks.run_pipeline", side_effect=RuntimeError("boom")):
        process_transaction_event(str(txn.id))

    txn.refresh_from_db()
    assert txn.status == Transaction.Status.ESCALATED
    assert txn.status != Transaction.Status.PROCESSING
    assert AuditLogEntry.objects.filter(transaction=txn, event_type="pipeline_error").exists()
    # 'detected' is written before the pipeline runs — the audit trail stays coherent.
    assert AuditLogEntry.objects.filter(transaction=txn, event_type="detected").exists()


def test_dispatch_scheduled_action_escalates_on_unexpected_error(make_transaction):
    txn = make_transaction(failure_code="card_declined", amount=500, customer_id="cust_dispatch_boom")
    Diagnosis.objects.create(transaction=txn, root_cause="card_declined", confidence=0.78, reasoning_text="t")
    scheduled = ScheduledAction.objects.create(
        transaction=txn, action_type="retry_order",
        run_after=timezone.now() - timedelta(minutes=1), status=ScheduledAction.Status.DISPATCHED,
    )
    # A non-RazorpayError from the action layer bypasses _execute_action's inner catch
    # and must be caught by dispatch_scheduled_action's safety net.
    with patch("recovery.tasks._call_razorpay", side_effect=RuntimeError("kaboom")):
        dispatch_scheduled_action(scheduled.id)

    txn.refresh_from_db()
    assert txn.status == Transaction.Status.ESCALATED
    assert AuditLogEntry.objects.filter(transaction=txn, event_type="pipeline_error").exists()
