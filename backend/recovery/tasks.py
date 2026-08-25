import logging
import random
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from agents.pipeline import run_pipeline

from . import razorpay_client, ws
from .analytics import compute_summary
from .guardrails import evaluate_guardrails
from .models import (
    Action,
    AuditLogEntry,
    Decision,
    Diagnosis,
    GuardrailEvent,
    ScheduledAction,
    Transaction,
)

logger = logging.getLogger(__name__)

DECISION_TO_ACTION_CHANNEL = {
    Decision.Action.RETRY_ORDER: Action.Type.RETRY,
    Decision.Action.NEW_PAYMENT_LINK: Action.Type.EMAIL,
    Decision.Action.REGISTRATION_LINK: Action.Type.EMAIL,
    Decision.Action.INVOICE_REMINDER: Action.Type.EMAIL,
    Decision.Action.VOICE_REMINDER: Action.Type.VOICE,
    Decision.Action.ESCALATE: Action.Type.ESCALATE,
}

# Actions whose Razorpay call targets a specific pre-existing artifact (an order to
# re-open, an invoice to re-notify). If that artifact 404s — the seed_data gap, or any
# stale id — we can recover by issuing a fresh payment link instead of escalating.
_FALLBACK_ACTIONS = {Decision.Action.RETRY_ORDER, Decision.Action.INVOICE_REMINDER}


def _audit(txn, event_type, actor, payload):
    entry = AuditLogEntry.objects.create(transaction=txn, event_type=event_type, actor=actor, payload=payload)
    ws.push(
        "audit",
        {
            "transaction_id": str(txn.id),
            "event_type": entry.event_type,
            "actor": entry.actor,
            "payload": entry.payload,
            "timestamp": entry.timestamp.isoformat(),
        },
    )
    return entry


def _push_ticker(txn, outcome, action_type=None):
    ws.push(
        "ticker",
        {
            "transaction_id": str(txn.id),
            "kind": txn.kind,
            "amount": float(txn.amount),
            "currency": txn.currency,
            "customer_id": txn.customer_id,
            "outcome": outcome,
            "action_type": action_type,
            "summary": compute_summary(),
        },
    )


def _call_razorpay(txn, action_type) -> dict:
    amount_paise = int(txn.amount * 100)
    label = f"RecoverAI recovery — {txn.id}"
    if action_type == Decision.Action.RETRY_ORDER:
        return razorpay_client.reopen_order_checkout(txn.razorpay_order_id, amount_paise, receipt=str(txn.id))
    if action_type == Decision.Action.NEW_PAYMENT_LINK:
        return razorpay_client.create_payment_link(amount_paise, label, txn.customer_name, txn.customer_phone)
    if action_type == Decision.Action.REGISTRATION_LINK:
        return razorpay_client.create_registration_link(amount_paise, label, txn.customer_name, txn.customer_phone)
    if action_type == Decision.Action.INVOICE_REMINDER:
        return razorpay_client.resend_invoice(txn.razorpay_order_id or "sim_invoice", medium="sms")
    return {"simulated": True, "note": "no Razorpay call for this action type"}


def _escalate(txn, *, reason, event_type, api_response) -> Action:
    """Resolve a transaction to the human queue. The single place a transaction becomes
    ESCALATED — reused by guardrail escalation, API-failure escalation, and the
    unexpected-error safety net — so all three write an ESCALATE Action, an audit entry,
    and an escalated ticker push consistently. event_type distinguishes why."""
    action = Action.objects.create(
        transaction=txn, action_type=Action.Type.ESCALATE, api_response=api_response, result=Action.Result.PENDING
    )
    txn.status = Transaction.Status.ESCALATED
    txn.save(update_fields=["status", "updated_at"])
    _audit(txn, event_type, AuditLogEntry.Actor.SYSTEM, {"reason": reason, "api_response": api_response})
    _push_ticker(txn, "escalated", Action.Type.ESCALATE)
    return action


def _escalate_api_failure(txn, action_type, err) -> Action:
    """A recovery action's Razorpay call failed unrecoverably (a transient/5xx error, or
    a 404 on an action with no fallback). Escalate with a distinct 'action_failed' event
    so the audit trail separates an API failure from a guardrail-driven escalation."""
    return _escalate(
        txn,
        reason=f"action '{action_type}' failed at the payment provider: {err}",
        event_type="action_failed",
        api_response={"error": str(err), "status_code": getattr(err, "status_code", None), "failed_action": action_type},
    )


def _escalate_on_unexpected_error(txn, err) -> Action:
    """Last-resort safety net for the pipeline tasks: any exception that isn't the
    Razorpay-failure path above still resolves the transaction to ESCALATED rather than
    leaving it stranded in PROCESSING (which the idempotency guard would then block from
    ever reprocessing)."""
    return _escalate(
        txn,
        reason=f"unexpected error during recovery execution: {err}",
        event_type="pipeline_error",
        api_response={"error": str(err), "error_type": type(err).__name__},
    )


def _execute_action(txn, action_type, diagnosis_confidence) -> Action:
    if action_type == Decision.Action.ESCALATE:
        # ESCALATE's _call_razorpay returns a static dict and never hits the network,
        # so it can't raise — no guard needed here.
        return _escalate(
            txn,
            reason="guardrail escalation or low-confidence decision",
            event_type="escalated",
            api_response=_call_razorpay(txn, action_type),
        )

    channel = DECISION_TO_ACTION_CHANNEL.get(action_type, Action.Type.ESCALATE)
    fallback_note = None
    try:
        api_response = _call_razorpay(txn, action_type)
    except razorpay_client.RazorpayError as err:
        # A 404 on retry_order/invoice_reminder means the stored order/invoice id doesn't
        # exist at Razorpay (the seed_data gap, or any stale id) — recover by issuing a
        # fresh payment link. Any other API error has no safe fallback: escalate.
        if razorpay_client.is_not_found(err) and action_type in _FALLBACK_ACTIONS:
            try:
                api_response = razorpay_client.create_payment_link(
                    int(txn.amount * 100), f"RecoverAI recovery — {txn.id}", txn.customer_name, txn.customer_phone
                )
            except razorpay_client.RazorpayError as fallback_err:
                return _escalate_api_failure(txn, action_type, fallback_err)
            channel = Action.Type.EMAIL  # a payment link is a contact-channel artifact, not a same-order retry
            fallback_note = {
                "fallback_from": action_type,
                "reason": "original payable artifact not found (404) — issued a fresh payment link instead",
                "original_error": str(err),
            }
        else:
            return _escalate_api_failure(txn, action_type, err)

    if fallback_note is not None:
        api_response = {**api_response, "_recoverai_fallback": fallback_note}

    # Synthetic outcome model: a payable artifact was created (order / link / invoice)
    # but nothing forces the customer to pay it — there's no real customer in a batch
    # replay. We resolve the outcome probabilistically, weighted by diagnosis
    # confidence, so the ticker's ₹ recovered number is an honest function of the
    # synthetic dataset's designed distribution, not a hard-coded demo path.
    recovered = random.random() < min(0.95, max(0.05, diagnosis_confidence))
    result = Action.Result.SUCCESS if recovered else Action.Result.FAILED
    amount_recovered = txn.amount if recovered else 0

    action = Action.objects.create(
        transaction=txn, action_type=channel, api_response=api_response, result=result, amount_recovered=amount_recovered
    )
    txn.status = Transaction.Status.RECOVERED if recovered else Transaction.Status.FAILED
    txn.save(update_fields=["status", "updated_at"])
    _audit(
        txn, "action_executed", AuditLogEntry.Actor.AGENT,
        {"action_type": channel, "result": result, "api_response": api_response, "amount_recovered": float(amount_recovered)},
    )
    _push_ticker(txn, "recovered" if recovered else "failed", channel)
    return action


@shared_task
def process_transaction_event(transaction_id):
    try:
        txn = Transaction.objects.get(id=transaction_id)
    except Transaction.DoesNotExist:
        logger.warning("process_transaction_event: transaction %s no longer exists", transaction_id)
        return

    if txn.status != Transaction.Status.OPEN:
        return  # idempotency guard — a duplicate webhook/dispatch must not reprocess

    txn.status = Transaction.Status.PROCESSING
    txn.save(update_fields=["status", "updated_at"])
    _audit(
        txn, "detected", AuditLogEntry.Actor.SYSTEM,
        {"kind": txn.kind, "failure_code": txn.failure_code, "amount": float(txn.amount)},
    )

    try:
        _run_recovery_pipeline(txn)
    except Exception as err:
        # Safety net: an unexpected failure (not the Razorpay-failure path, which
        # _execute_action already resolves) must never leave the transaction wedged in
        # PROCESSING — the idempotency guard above would then block it forever.
        logger.exception("process_transaction_event: pipeline failed for %s", txn.id)
        _escalate_on_unexpected_error(txn, err)


def _run_recovery_pipeline(txn):
    result = run_pipeline(
        {
            "kind": txn.kind,
            "amount": float(txn.amount),
            "currency": txn.currency,
            "failure_code": txn.failure_code,
            "customer_id": txn.customer_id,
        }
    )
    diag_data, dec_data = result["diagnosis"], result["decision"]

    diagnosis = Diagnosis.objects.create(
        transaction=txn,
        root_cause=diag_data["root_cause"],
        confidence=diag_data["confidence"],
        reasoning_text=diag_data["reasoning_text"],
    )
    _audit(
        txn, "diagnosed", AuditLogEntry.Actor.AGENT,
        {"root_cause": diagnosis.root_cause, "confidence": diagnosis.confidence, "reasoning": diagnosis.reasoning_text},
    )

    decision = Decision.objects.create(
        transaction=txn, chosen_action=dec_data["chosen_action"], reasoning_text=dec_data["reasoning_text"]
    )
    _audit(
        txn, "decided", AuditLogEntry.Actor.AGENT,
        {"chosen_action": decision.chosen_action, "reasoning": decision.reasoning_text},
    )

    verdict = evaluate_guardrails(txn, diagnosis, decision)
    recent_checks = list(
        GuardrailEvent.objects.filter(transaction=txn).order_by("-triggered_at")[:6].values("rule_name", "rule_result")
    )
    decision.guardrail_checks_passed = recent_checks
    decision.save(update_fields=["guardrail_checks_passed"])

    for ev in GuardrailEvent.objects.filter(transaction=txn).order_by("-triggered_at")[:6]:
        ws.push(
            "guardrail",
            {"transaction_id": str(txn.id), "rule_name": ev.rule_name, "rule_result": ev.rule_result, "detail": ev.detail},
        )

    if verdict.escalate:
        _execute_action(txn, Decision.Action.ESCALATE, diagnosis.confidence)
        return

    if not verdict.cleared:
        ScheduledAction.objects.update_or_create(
            transaction=txn,
            status=ScheduledAction.Status.PENDING,
            defaults={"action_type": decision.chosen_action, "reason": verdict.hold_reason, "run_after": verdict.hold_until},
        )
        txn.status = Transaction.Status.HELD
        txn.save(update_fields=["status", "updated_at"])
        _audit(
            txn, "held", AuditLogEntry.Actor.SYSTEM,
            {"reason": verdict.hold_reason, "run_after": verdict.hold_until.isoformat()},
        )
        _push_ticker(txn, "held", decision.chosen_action)
        return

    _execute_action(txn, decision.chosen_action, diagnosis.confidence)


@shared_task
def sweep_scheduled_actions():
    """Celery Beat, every 30s. Picks up due ScheduledAction rows — the cooldown and
    48h-retry guardrails both flow through here, never through a raw multi-day ETA
    task, so a worker restart mid-cooldown can't silently drop the retry."""
    due = ScheduledAction.objects.filter(status=ScheduledAction.Status.PENDING, run_after__lte=timezone.now())
    dispatched = 0
    for scheduled in due:
        scheduled.status = ScheduledAction.Status.DISPATCHED
        scheduled.save(update_fields=["status"])
        dispatch_scheduled_action.delay(scheduled.id)
        dispatched += 1
    return {"dispatched": dispatched}


@shared_task
def dispatch_scheduled_action(scheduled_action_id):
    try:
        scheduled = ScheduledAction.objects.select_related("transaction").get(id=scheduled_action_id)
    except ScheduledAction.DoesNotExist:
        return
    txn = scheduled.transaction
    try:
        confidence = txn.diagnoses.latest("agent_run_at").confidence
    except Diagnosis.DoesNotExist:
        confidence = 0.5

    _audit(
        txn, "scheduled_action_dispatched", AuditLogEntry.Actor.SYSTEM,
        {"reason": scheduled.reason, "action_type": scheduled.action_type},
    )
    try:
        _execute_action(txn, scheduled.action_type, confidence)
    except Exception as err:
        # Same safety net as process_transaction_event: a delayed action that fails
        # unexpectedly must resolve the transaction, not leave it mid-execution.
        logger.exception("dispatch_scheduled_action: execution failed for %s", txn.id)
        _escalate_on_unexpected_error(txn, err)


@shared_task
def replay_batch():
    """Walks every OPEN transaction and staggers its processing so the Recovery Room
    ticker climbs transaction-by-transaction instead of jumping straight to a final
    number — this is the 'don't pre-run it, trigger it live' demo requirement."""
    open_ids = list(
        Transaction.objects.filter(status=Transaction.Status.OPEN).order_by("created_at").values_list("id", flat=True)
    )
    stagger = settings.REPLAY_STAGGER_SECONDS
    for i, txn_id in enumerate(open_ids):
        process_transaction_event.apply_async(args=[str(txn_id)], countdown=i * stagger)
    return {"queued": len(open_ids)}


@shared_task
def trigger_voice_showcase(transaction_id):
    """The signature Hinglish voice moment — one high-value overdue receivable, a
    simulated TTS call, logged as a promise-to-pay. A 2-minute demo insert, not
    infrastructure: swap the simulated response for a real TTS/STT pass when a
    provider key is wired up."""
    txn = Transaction.objects.get(id=transaction_id)
    transcript = f"Namaste, aapka invoice ₹{txn.amount:,.0f} ka due hai, kya hum abhi payment link bhej sakte hain?"
    customer_response = "Haan bhej dijiye, main 3 din mein pay kar dunga."
    promise_date = (timezone.now() + timedelta(days=3)).date().isoformat()

    Action.objects.create(
        transaction=txn,
        action_type=Action.Type.VOICE,
        api_response={"simulated": True, "transcript": transcript, "customer_response": customer_response},
        result=Action.Result.SIMULATED,
    )
    _audit(
        txn, "voice_promise_to_pay", AuditLogEntry.Actor.AGENT,
        {"transcript": transcript, "customer_response": customer_response, "promise_to_pay_date": promise_date},
    )
    ws.push(
        "voice",
        {
            "transaction_id": str(txn.id),
            "transcript": transcript,
            "customer_response": customer_response,
            "promise_to_pay_date": promise_date,
        },
    )
    return {"promise_to_pay_date": promise_date}
