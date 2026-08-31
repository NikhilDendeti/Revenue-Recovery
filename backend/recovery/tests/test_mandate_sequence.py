"""add-mandate-recovery-sequence: a subscription_failure transaction that ignores its
first registration-link nudge gets a real cadence — a follow-up nudge on a different
channel, then escalation to the human queue — instead of sitting FAILED forever with no
further lever pulled.

Every test here patches agents.pipeline.complete_json to None (the heuristic-fallback
path), matching the existing convention in test_tasks.py, so behaviour is deterministic
regardless of whether a real LLM key is configured in this environment. Outcome dice
rolls are forced deterministically via recovery.tasks.random.random.
"""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from recovery.models import (
    Action,
    AuditLogEntry,
    Decision,
    Diagnosis,
    GuardrailEvent,
    MandateSequence,
    ScheduledAction,
    Transaction,
)
from recovery.tasks import dispatch_scheduled_action, process_transaction_event, sweep_scheduled_actions

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("no_razorpay_keys")]


def _sub_txn(make_transaction, **overrides):
    defaults = dict(
        kind=Transaction.Kind.SUBSCRIPTION_FAILURE,
        failure_code="card_declined",  # a retriable root cause
        amount=500,
    )
    defaults.update(overrides)
    return make_transaction(**defaults)


# --- Step 0: MandateSequence creation is gated on "retriable and didn't immediately escalate" ---


def test_registration_link_decision_creates_active_mandate_sequence(make_transaction):
    txn = _sub_txn(make_transaction, customer_id="cust_seq_create")
    with patch("agents.pipeline.complete_json", return_value=None), \
         patch("recovery.tasks.random.random", return_value=0.0):  # force SUCCESS — irrelevant here
        process_transaction_event(str(txn.id))

    sequence = MandateSequence.objects.get(transaction=txn)
    assert sequence.current_step == 0


def test_non_retriable_root_cause_never_creates_mandate_sequence(make_transaction):
    """An immediate decision-level escalation (non-retriable root cause) must never
    create a MandateSequence row — there's no first nudge to track a cadence for."""
    txn = _sub_txn(make_transaction, failure_code="recurring_payment_not_enabled", customer_id="cust_seq_nonretriable")
    with patch("agents.pipeline.complete_json", return_value=None):
        process_transaction_event(str(txn.id))

    txn.refresh_from_db()
    assert txn.status == Transaction.Status.ESCALATED
    assert MandateSequence.objects.count() == 0


def test_guardrail_escalation_never_creates_mandate_sequence(make_transaction):
    """The decision itself resolves to registration_link (retriable), but a guardrail
    (spend ceiling) forces an immediate escalation — this must also never create a
    MandateSequence row, matching the 'never sequenced' spec scenario for any
    transaction that never got its first nudge actually sent."""
    txn = _sub_txn(make_transaction, amount=60000, customer_id="cust_seq_guardrail_escalate")
    with patch("agents.pipeline.complete_json", return_value=None):
        process_transaction_event(str(txn.id))

    txn.refresh_from_db()
    assert txn.status == Transaction.Status.ESCALATED
    assert MandateSequence.objects.count() == 0


# --- Step 0 -> step 1: an ignored first nudge schedules the follow-up ---


def test_step_0_failed_outcome_schedules_step_1_voice_reminder(make_transaction):
    txn = _sub_txn(make_transaction, customer_id="cust_seq_step0_fail")
    with patch("agents.pipeline.complete_json", return_value=None), \
         patch("recovery.tasks.random.random", return_value=0.999):  # force FAILED
        process_transaction_event(str(txn.id))

    txn.refresh_from_db()
    # Visibly HELD, never left stuck FAILED — the crux behaviour design.md Decision 1 describes.
    assert txn.status == Transaction.Status.HELD

    sequence = MandateSequence.objects.get(transaction=txn)
    assert sequence.current_step == 1
    assert sequence.status == MandateSequence.Status.ACTIVE

    scheduled = ScheduledAction.objects.get(transaction=txn, status=ScheduledAction.Status.PENDING)
    assert scheduled.reason == "mandate_sequence_step"
    assert scheduled.action_type == "voice_reminder"
    assert scheduled.run_after > timezone.now()
    assert AuditLogEntry.objects.filter(transaction=txn, event_type="mandate_sequence_step_scheduled").exists()


def test_step_0_recovered_outcome_marks_sequence_recovered_not_scheduled(make_transaction):
    txn = _sub_txn(make_transaction, customer_id="cust_seq_step0_recovered")
    with patch("agents.pipeline.complete_json", return_value=None), \
         patch("recovery.tasks.random.random", return_value=0.0):  # force SUCCESS
        process_transaction_event(str(txn.id))

    txn.refresh_from_db()
    assert txn.status == Transaction.Status.RECOVERED
    sequence = MandateSequence.objects.get(transaction=txn)
    assert sequence.status == MandateSequence.Status.RECOVERED
    assert sequence.current_step == 0
    assert ScheduledAction.objects.filter(transaction=txn).count() == 0


# --- Step 1 dispatch: guardrails re-run, and a held step re-schedules itself ---


def test_step_1_dispatch_cleared_creates_voice_reminder_action_through_guardrails(make_transaction):
    txn = _sub_txn(make_transaction, customer_id="cust_seq_step1_dispatch")
    sequence = MandateSequence.objects.create(transaction=txn, current_step=1, status=MandateSequence.Status.ACTIVE)
    txn.status = Transaction.Status.HELD
    txn.save(update_fields=["status"])
    scheduled = ScheduledAction.objects.create(
        transaction=txn, action_type="voice_reminder", reason="mandate_sequence_step",
        run_after=timezone.now() - timedelta(minutes=1), status=ScheduledAction.Status.DISPATCHED,
    )

    with patch("agents.pipeline.complete_json", return_value=None), \
         patch("recovery.tasks.random.random", return_value=0.999):  # force FAILED -> advances to step 2
        dispatch_scheduled_action(scheduled.id)

    action = Action.objects.get(transaction=txn, action_type=Action.Type.VOICE)
    assert action.result == Action.Result.FAILED
    assert Diagnosis.objects.filter(transaction=txn).exists()
    assert Decision.objects.filter(transaction=txn, chosen_action="voice_reminder").exists()
    assert GuardrailEvent.objects.filter(transaction=txn).exists()
    assert AuditLogEntry.objects.filter(transaction=txn, event_type="diagnosed").exists()
    assert AuditLogEntry.objects.filter(transaction=txn, event_type="decided").exists()

    sequence.refresh_from_db()
    assert sequence.current_step == 2
    assert sequence.status == MandateSequence.Status.ACTIVE
    txn.refresh_from_db()
    assert txn.status == Transaction.Status.HELD

    next_scheduled = ScheduledAction.objects.get(transaction=txn, status=ScheduledAction.Status.PENDING)
    assert next_scheduled.reason == "mandate_sequence_step"
    assert next_scheduled.action_type == "escalate"


def test_step_2_dispatch_always_escalates_and_marks_sequence_escalated(make_transaction):
    txn = _sub_txn(make_transaction, customer_id="cust_seq_step2_dispatch")
    sequence = MandateSequence.objects.create(transaction=txn, current_step=2, status=MandateSequence.Status.ACTIVE)
    txn.status = Transaction.Status.HELD
    txn.save(update_fields=["status"])
    scheduled = ScheduledAction.objects.create(
        transaction=txn, action_type="escalate", reason="mandate_sequence_step",
        run_after=timezone.now() - timedelta(minutes=1), status=ScheduledAction.Status.DISPATCHED,
    )

    with patch("agents.pipeline.complete_json", return_value=None):
        dispatch_scheduled_action(scheduled.id)

    txn.refresh_from_db()
    assert txn.status == Transaction.Status.ESCALATED
    action = Action.objects.get(transaction=txn, action_type=Action.Type.ESCALATE)
    assert action is not None
    assert Decision.objects.filter(transaction=txn, chosen_action="escalate").exists()

    sequence.refresh_from_db()
    assert sequence.status == MandateSequence.Status.ESCALATED


# --- Cancellation on mid-sequence recovery ---


def test_cancellation_when_transaction_already_resolved_before_step_fires(make_transaction):
    txn = _sub_txn(make_transaction, customer_id="cust_seq_cancel")
    sequence = MandateSequence.objects.create(transaction=txn, current_step=1, status=MandateSequence.Status.ACTIVE)
    scheduled = ScheduledAction.objects.create(
        transaction=txn, action_type="voice_reminder", reason="mandate_sequence_step",
        run_after=timezone.now() - timedelta(minutes=1), status=ScheduledAction.Status.PENDING,
    )
    # The customer paid through some other path before the follow-up ever fired.
    txn.status = Transaction.Status.RECOVERED
    txn.save(update_fields=["status"])

    result = sweep_scheduled_actions()
    assert result["dispatched"] == 1
    scheduled.refresh_from_db()
    assert scheduled.status == ScheduledAction.Status.DISPATCHED

    action_count_before = Action.objects.filter(transaction=txn).count()
    dispatch_scheduled_action(scheduled.id)

    sequence.refresh_from_db()
    assert sequence.status == MandateSequence.Status.CANCELLED
    assert Action.objects.filter(transaction=txn).count() == action_count_before  # zero new actions
    assert ScheduledAction.objects.filter(transaction=txn, status=ScheduledAction.Status.PENDING).count() == 0
    assert AuditLogEntry.objects.filter(transaction=txn, event_type="mandate_sequence_cancelled").exists()


# --- Worker-restart survival: the DB row alone carries the pending step ---


def test_worker_restart_survival_sweep_picks_up_due_step_from_db_alone(make_transaction):
    """A step-1 ScheduledAction with run_after already in the past (as if a worker was
    down while it became due) is created purely via the ORM — no in-process reference
    to how/when it was scheduled. A freshly-called sweep_scheduled_actions must still
    discover and correctly dispatch it, proving the row (not worker memory) carries the
    pending step."""
    txn = _sub_txn(make_transaction, customer_id="cust_seq_restart")
    MandateSequence.objects.create(transaction=txn, current_step=1, status=MandateSequence.Status.ACTIVE)
    txn.status = Transaction.Status.HELD
    txn.save(update_fields=["status"])
    scheduled = ScheduledAction.objects.create(
        transaction=txn, action_type="voice_reminder", reason="mandate_sequence_step",
        run_after=timezone.now() - timedelta(days=1), status=ScheduledAction.Status.PENDING,
    )

    result = sweep_scheduled_actions()
    assert result["dispatched"] == 1
    scheduled.refresh_from_db()
    assert scheduled.status == ScheduledAction.Status.DISPATCHED

    with patch("agents.pipeline.complete_json", return_value=None), \
         patch("recovery.tasks.random.random", return_value=0.0):  # force SUCCESS
        dispatch_scheduled_action(scheduled.id)

    txn.refresh_from_db()
    assert txn.status == Transaction.Status.RECOVERED
    assert Action.objects.filter(transaction=txn, action_type=Action.Type.VOICE, result=Action.Result.SUCCESS).exists()
