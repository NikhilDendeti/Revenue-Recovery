"""Independent coverage for the promise-to-pay-tracking capability: the model itself,
its periodic sweep resolution, and the batch-summary kept-rate metric. Guardrail
interaction lives in test_guardrails.py (it exercises evaluate_guardrails directly);
the read-only API lives in test_api.py (it exercises the DRF viewset)."""

from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction as db_transaction
from django.utils import timezone

from recovery.analytics import compute_summary
from recovery.models import Action, AuditLogEntry, PromiseToPay, Transaction
from recovery.tasks import sweep_promises_to_pay

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("no_razorpay_keys")]


def test_promise_to_pay_records_its_defining_fields(make_transaction):
    txn = make_transaction(amount=1500)
    promise = PromiseToPay.objects.create(
        transaction=txn, promised_amount=txn.amount, promise_date=timezone.localdate() + timedelta(days=3),
        source=PromiseToPay.Source.VOICE,
    )

    promise.refresh_from_db()
    assert promise.transaction_id == txn.id
    assert promise.promised_amount == txn.amount
    assert promise.promise_date == timezone.localdate() + timedelta(days=3)
    assert promise.source == PromiseToPay.Source.VOICE
    assert promise.status == PromiseToPay.Status.PENDING


def test_second_pending_promise_for_same_transaction_is_rejected(make_transaction):
    txn = make_transaction()
    PromiseToPay.objects.create(
        transaction=txn, promised_amount=txn.amount, promise_date=timezone.localdate(), source=PromiseToPay.Source.VOICE
    )
    with pytest.raises(IntegrityError):
        with db_transaction.atomic():
            PromiseToPay.objects.create(
                transaction=txn, promised_amount=txn.amount, promise_date=timezone.localdate(),
                source=PromiseToPay.Source.VOICE,
            )
    assert PromiseToPay.objects.filter(transaction=txn).count() == 1


def test_sweep_marks_promise_kept_on_recovered_transaction(make_transaction):
    txn = make_transaction(customer_id="cust_kept")
    txn.status = Transaction.Status.RECOVERED
    txn.save(update_fields=["status"])
    promise = PromiseToPay.objects.create(
        transaction=txn, promised_amount=txn.amount, promise_date=timezone.localdate() - timedelta(days=1),
        source=PromiseToPay.Source.VOICE,
    )

    sweep_promises_to_pay()

    promise.refresh_from_db()
    assert promise.status == PromiseToPay.Status.KEPT


def test_sweep_marks_promise_broken_and_runs_guardrails_on_unresolved_transaction(make_transaction):
    txn = make_transaction(customer_id="cust_broken", failure_code="insufficient_funds", amount=500)
    assert txn.status == Transaction.Status.OPEN
    promise = PromiseToPay.objects.create(
        transaction=txn, promised_amount=txn.amount, promise_date=timezone.localdate() - timedelta(days=1),
        source=PromiseToPay.Source.VOICE,
    )

    sweep_promises_to_pay()

    promise.refresh_from_db()
    assert promise.status == PromiseToPay.Status.BROKEN
    assert AuditLogEntry.objects.filter(transaction=txn, event_type="promise_broken").exists()
    txn.refresh_from_db()
    assert txn.status == Transaction.Status.ESCALATED
    assert Action.objects.filter(transaction=txn, action_type=Action.Type.ESCALATE).exists()


def test_sweep_resolves_both_outcomes_correctly_in_one_run(make_transaction):
    kept_txn = make_transaction(customer_id="cust_sweep_kept")
    kept_txn.status = Transaction.Status.RECOVERED
    kept_txn.save(update_fields=["status"])
    kept_promise = PromiseToPay.objects.create(
        transaction=kept_txn, promised_amount=kept_txn.amount, promise_date=timezone.localdate() - timedelta(days=1),
        source=PromiseToPay.Source.VOICE,
    )

    broken_txn = make_transaction(customer_id="cust_sweep_broken", failure_code="insufficient_funds")
    broken_promise = PromiseToPay.objects.create(
        transaction=broken_txn, promised_amount=broken_txn.amount,
        promise_date=timezone.localdate() - timedelta(days=1), source=PromiseToPay.Source.VOICE,
    )

    sweep_promises_to_pay()

    kept_promise.refresh_from_db()
    broken_promise.refresh_from_db()
    assert kept_promise.status == PromiseToPay.Status.KEPT
    assert broken_promise.status == PromiseToPay.Status.BROKEN


def test_sweep_on_already_escalated_transaction_does_not_double_escalate(make_transaction):
    txn = make_transaction(customer_id="cust_already_escalated")
    txn.status = Transaction.Status.ESCALATED
    txn.save(update_fields=["status"])
    Action.objects.create(transaction=txn, action_type=Action.Type.ESCALATE, result=Action.Result.PENDING)
    promise = PromiseToPay.objects.create(
        transaction=txn, promised_amount=txn.amount, promise_date=timezone.localdate() - timedelta(days=1),
        source=PromiseToPay.Source.VOICE,
    )

    sweep_promises_to_pay()

    promise.refresh_from_db()
    assert promise.status == PromiseToPay.Status.BROKEN
    assert Action.objects.filter(transaction=txn, action_type=Action.Type.ESCALATE).count() == 1


def test_sweep_ignores_promises_not_yet_due(make_transaction):
    txn = make_transaction(customer_id="cust_not_due")
    promise = PromiseToPay.objects.create(
        transaction=txn, promised_amount=txn.amount, promise_date=timezone.localdate() + timedelta(days=1),
        source=PromiseToPay.Source.VOICE,
    )

    sweep_promises_to_pay()

    promise.refresh_from_db()
    assert promise.status == PromiseToPay.Status.PENDING


def test_promise_kept_rate_reflects_resolved_promises(make_transaction):
    txn1, txn2, txn3, txn4 = (make_transaction(customer_id=f"cust_rate_{i}") for i in range(4))
    PromiseToPay.objects.create(
        transaction=txn1, promised_amount=100, promise_date=timezone.localdate(),
        source=PromiseToPay.Source.VOICE, status=PromiseToPay.Status.KEPT,
    )
    PromiseToPay.objects.create(
        transaction=txn2, promised_amount=100, promise_date=timezone.localdate(),
        source=PromiseToPay.Source.VOICE, status=PromiseToPay.Status.KEPT,
    )
    PromiseToPay.objects.create(
        transaction=txn3, promised_amount=100, promise_date=timezone.localdate(),
        source=PromiseToPay.Source.VOICE, status=PromiseToPay.Status.BROKEN,
    )
    PromiseToPay.objects.create(
        transaction=txn4, promised_amount=100, promise_date=timezone.localdate(),
        source=PromiseToPay.Source.VOICE, status=PromiseToPay.Status.PENDING,
    )

    summary = compute_summary()

    assert summary["promise_kept_rate"] == pytest.approx(66.7, abs=0.1)


def test_promise_kept_rate_is_zero_with_no_resolved_promises(make_transaction):
    txn = make_transaction()
    PromiseToPay.objects.create(
        transaction=txn, promised_amount=100, promise_date=timezone.localdate(), source=PromiseToPay.Source.VOICE
    )

    summary = compute_summary()

    assert summary["promise_kept_rate"] == 0.0
