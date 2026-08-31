"""The Diagnosis -> Decision graph. A LangGraph StateGraph, not a CrewAI crew — this
pipeline is a small, deterministic-shaped state machine (ingest -> diagnose -> decide),
which is exactly what LangGraph is good at: inspectable per-node state, easy to log,
easy to keep the Guardrail Enforcer (deterministic, no LLM) as a separate step outside
this graph entirely.

Runs synchronously inside a Celery task — never call this from a view or a Channels
consumer, an LLM round trip is seconds-to-tens-of-seconds and would stall the ASGI
event loop for every other dashboard viewer.
"""

from datetime import datetime, timezone as dt_timezone
from typing import TypedDict

from django.conf import settings
from langgraph.graph import END, StateGraph

from .llm import complete_json


_CODE_DIAGNOSES: dict[str, tuple[str, float, str]] = {
    "insufficient_funds": ("insufficient_funds", 0.82, "Card/UPI declined for insufficient funds — this failure class historically recovers well on a short delay retry."),
    "card_declined": ("card_declined", 0.78, "Card issuer declined the charge. Recoverable via a fresh attempt, but subject to the card-decline cooldown."),
    "card_expired": ("card_expired", 0.90, "The card on file has expired — a same-card retry cannot succeed; the customer needs a fresh payment method."),
    "authentication_failed": ("authentication_failed", 0.75, "Customer failed 3DS/OTP authentication on the attempt — a retry with a fresh authentication step is plausible."),
    "card_not_enrolled": ("card_not_enrolled", 0.80, "The card isn't enrolled for the authentication method Razorpay required — the same card will fail again; needs a fresh payment method."),
    "invalid_vpa": ("invalid_vpa", 0.85, "The UPI VPA entered doesn't resolve to a real handle — a data-entry error, not a transient failure."),
    "vpa_resolution_failed": ("vpa_resolution_failed", 0.65, "The VPA itself may be valid, but the PSP-side lookup failed transiently — worth retrying the same VPA, hence lower confidence than a confirmed-invalid VPA."),
    "bank_technical_error": ("technical_error", 0.65, "Provider-side (bank) technical failure, not a customer-caused decline — transient and often recoverable on retry."),
    "gateway_technical_error": ("technical_error", 0.65, "Provider-side (gateway) technical failure, not a customer-caused decline — transient and often recoverable on retry."),
    "issuer_technical_error": ("technical_error", 0.65, "Provider-side (issuer) technical failure, not a customer-caused decline — transient and often recoverable on retry."),
    "transaction_limit_exceeded": ("transaction_limit_exceeded", 0.80, "The instrument's transaction limit was exceeded — the same instrument will fail again; needs a fresh payment method or a lower amount."),
    "incorrect_cvv": ("incorrect_cvv", 0.75, "Customer entered the wrong CVV — a correctable input error, not an instrument problem."),
    "debit_instrument_blocked": ("debit_instrument_blocked", 0.80, "The debit instrument itself is blocked — a same-instrument retry cannot succeed; needs a fresh payment method."),
    "debit_instrument_inactive": ("debit_instrument_inactive", 0.80, "The debit instrument itself is inactive — a same-instrument retry cannot succeed; needs a fresh payment method."),
    "payment_timed_out": ("network_timeout", 0.55, "Payment attempt timed out before a definitive result — ambiguous signal, moderate confidence."),
    "request_timed_out": ("network_timeout", 0.55, "Request to the provider timed out before a definitive result — ambiguous signal, moderate confidence."),
    "payment_declined": ("payment_declined", 0.60, "Generic decline with no more specific reason attached — still a real, known code, so we act rather than treat it as wholly unclassified."),
    "payment_cancelled": ("payment_cancelled", 0.65, "Customer cancelled the payment attempt themselves — nothing wrong with the instrument, so the same order is worth retrying."),
    "payment_risk_check_failed": ("risk_check_failed", 0.85, "Razorpay's risk engine blocked the payment — this is a deliberate fraud/risk hold, not a technical or customer-caused failure, and must always escalate."),
    "reqauth_mandate_not_acknowledged": ("reqauth_mandate_not_acknowledged", 0.70, "The mandate's re-authorization request went unacknowledged by the customer's bank/app — re-driving registration is the only lever available."),
    "mandate_creation_failed": ("mandate_creation_failed", 0.70, "Mandate creation itself failed — there's no charge to retry, only re-registration."),
    "funds_blocked_by_mandate": ("funds_blocked_by_mandate", 0.65, "Funds were blocked under the mandate but the charge didn't complete — ambiguous enough to warrant re-driving registration rather than assuming a clean retry."),
    "recurring_payment_not_enabled": ("recurring_payment_not_enabled", 0.80, "Recurring payments aren't enabled for this instrument/merchant configuration — a registration link can't fix a configuration gap."),
}

_DIAGNOSIS_RULES = [
    ("insufficient_funds", "insufficient_funds", 0.82, "Card/UPI declined for insufficient funds — this failure class historically recovers well on a short delay retry."),
    ("expired", "card_expired", 0.90, "The card on file has expired — a same-card retry cannot succeed; the customer needs a fresh payment method."),
    ("card_declined", "card_declined", 0.78, "Card issuer declined the charge. Recoverable via a fresh attempt, but subject to the card-decline cooldown."),
    ("timeout", "network_timeout", 0.55, "Payment attempt timed out before a definitive result — ambiguous signal, moderate confidence."),
    ("timed_out", "network_timeout", 0.55, "Payment attempt timed out before a definitive result — ambiguous signal, moderate confidence."),
    ("network", "network_timeout", 0.55, "Network-level failure during the attempt — ambiguous signal, moderate confidence."),
    ("mandate", "mandate_charge_failed", 0.75, "Recurring mandate charge failed — Razorpay is likely already auto-retrying on its fixed schedule."),
]

_KIND_DEFAULTS = {
    "payment_degradation": ("payment_declined", 0.55, "Generic payment failure with no specific failure code — treating as a standard decline."),
    "subscription_failure": ("mandate_charge_failed", 0.65, "Subscription charge failed — Razorpay's own retry schedule applies; recovery here means driving re-authorization."),
    "receivable": ("invoice_overdue", 0.88, "B2B invoice has aged past its due date with no payment received."),
}


def _hours_since(iso_or_dt) -> float:
    """Hours elapsed since `iso_or_dt` (an ISO-8601 string, a datetime, or None). Missing
    or unparseable input returns +inf — no time signal at all is treated as "long ago"
    rather than guessing recency, so it lands in the same honest low-confidence territory
    as any other genuinely unclear signal."""
    if iso_or_dt is None:
        return float("inf")
    if isinstance(iso_or_dt, datetime):
        dt = iso_or_dt
    else:
        try:
            dt = datetime.fromisoformat(str(iso_or_dt))
        except ValueError:
            return float("inf")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=dt_timezone.utc)
    return (datetime.now(dt_timezone.utc) - dt).total_seconds() / 3600.0


def _heuristic_checkout_dropoff_diagnosis(txn: dict) -> dict:
    hours_since_initiated = _hours_since(txn.get("checkout_initiated_at"))
    amount = txn.get("amount") or 0
    method_attempted = bool(txn.get("last_payment_method"))

    if hours_since_initiated <= 2 and amount >= settings.HIGH_VALUE_CART_INR and method_attempted:
        return {
            "root_cause": "high_value_recent_dropoff",
            "confidence": 0.85,
            "reasoning_text": "Recent, high-value cart with a payment method already attempted — the highest-intent signal, worth the fastest, most confident nudge.",
        }
    if hours_since_initiated <= 2 and method_attempted:
        return {
            "root_cause": "recent_dropoff_payment_attempted",
            "confidence": 0.80,
            "reasoning_text": "Customer was mid-payment very recently — a short recall window while intent is still fresh.",
        }
    if hours_since_initiated <= 24 and method_attempted:
        return {
            "root_cause": "short_window_dropoff",
            "confidence": 0.68,
            "reasoning_text": "Still same-day, but intent has cooled somewhat since the payment attempt.",
        }
    if not method_attempted:
        return {
            "root_cause": "browse_abandonment",
            "confidence": 0.45,
            "reasoning_text": "Never attempted a payment method at all — weaker purchase intent than a mid-payment drop-off.",
        }
    if hours_since_initiated <= 72:
        return {
            "root_cause": "aging_dropoff",
            "confidence": 0.55,
            "reasoning_text": "Multi-day-old drop-off — still plausible to recover, but confidence honestly sits near the floor.",
        }
    return {
        "root_cause": "cold_dropoff",
        "confidence": 0.32,
        "reasoning_text": "Past a week old — treated like any other genuinely low-confidence diagnosis.",
    }


def _heuristic_diagnosis(txn: dict) -> dict:
    if txn["kind"] == "checkout_dropoff":
        return _heuristic_checkout_dropoff_diagnosis(txn)
    code = (txn.get("failure_code") or "").lower()
    if code in _CODE_DIAGNOSES:
        root_cause, confidence, reasoning = _CODE_DIAGNOSES[code]
        return {"root_cause": root_cause, "confidence": confidence, "reasoning_text": reasoning}
    for needle, root_cause, confidence, reasoning in _DIAGNOSIS_RULES:
        if needle in code:
            return {"root_cause": root_cause, "confidence": confidence, "reasoning_text": reasoning}
    if not code:
        return {"root_cause": "unknown", "confidence": 0.35, "reasoning_text": "No failure code present and no rule matched — root cause is genuinely unclear."}
    root_cause, confidence, reasoning = _KIND_DEFAULTS.get(txn["kind"], ("unknown", 0.35, "Unrecognized failure pattern."))
    return {"root_cause": root_cause, "confidence": confidence, "reasoning_text": reasoning}


_PAYMENT_DEGRADATION_ACTIONS = {
    "insufficient_funds": "retry_order",
    "card_declined": "retry_order",
    "network_timeout": "retry_order",
    "card_expired": "new_payment_link",
    "payment_declined": "new_payment_link",
    "authentication_failed": "retry_order",
    "card_not_enrolled": "new_payment_link",
    "invalid_vpa": "new_payment_link",
    "vpa_resolution_failed": "retry_order",
    "technical_error": "retry_order",
    "transaction_limit_exceeded": "new_payment_link",
    "incorrect_cvv": "retry_order",
    "debit_instrument_blocked": "new_payment_link",
    "debit_instrument_inactive": "new_payment_link",
    "payment_cancelled": "retry_order",
}
_SUBSCRIPTION_RETRIABLE_ROOT_CAUSES = {
    "card_declined", "insufficient_funds", "mandate_charge_failed",
    "authentication_failed", "card_not_enrolled", "invalid_vpa", "vpa_resolution_failed",
    "technical_error", "transaction_limit_exceeded", "incorrect_cvv",
    "debit_instrument_blocked", "debit_instrument_inactive",
    "reqauth_mandate_not_acknowledged", "mandate_creation_failed", "funds_blocked_by_mandate",
}

_REASONING = {
    "retry_order": "Root cause is retriable on the same order intent — re-opening Checkout rather than inventing a retry call that doesn't exist.",
    "new_payment_link": "Same card/order can't be reused — issuing a fresh payable artifact instead.",
    "registration_link": "This is a subscription/mandate context: Razorpay's own auto-retry schedule already governs the charge and there's no API to force a retry — driving re-authorization is the actionable lever.",
    "voice_reminder": "Step 2 of the mandate recovery cadence: the registration-link nudge went unanswered, so this re-approaches the customer on a different channel before the cadence's final escalation step.",
    "invoice_reminder": "Overdue receivable — nudging via the existing invoice's reminder channel before escalating to a higher-touch channel.",
}


def _heuristic_decision(txn: dict, diagnosis: dict) -> dict:
    root_cause = diagnosis["root_cause"]
    if diagnosis["confidence"] < 0.60 or root_cause == "unknown":
        return {"chosen_action": "escalate", "reasoning_text": "Diagnosis confidence too low to act autonomously — routing to human review rather than guessing with money."}

    if txn["kind"] == "subscription_failure":
        sequence_step = txn.get("sequence_step")
        if sequence_step == 2:
            action = "escalate"
        elif sequence_step == 1:
            action = "voice_reminder" if root_cause in _SUBSCRIPTION_RETRIABLE_ROOT_CAUSES else "escalate"
        else:
            action = "registration_link" if root_cause in _SUBSCRIPTION_RETRIABLE_ROOT_CAUSES else "escalate"
    elif txn["kind"] == "receivable":
        action = "invoice_reminder" if root_cause == "invoice_overdue" else "escalate"
    elif txn["kind"] == "checkout_dropoff":
        action = "new_payment_link"
    else:
        action = _PAYMENT_DEGRADATION_ACTIONS.get(root_cause, "escalate")

    if txn["kind"] == "checkout_dropoff":
        reasoning = "Customer never completed Checkout — there's no failed payment to retry, so a fresh payment link recaptures the cart."
    else:
        reasoning = _REASONING.get(action, "No confident action mapping for this flow — escalating.")
    return {"chosen_action": action, "reasoning_text": reasoning}


class PipelineState(TypedDict, total=False):
    transaction: dict
    diagnosis: dict
    decision: dict


def _diagnose_node(state: PipelineState) -> PipelineState:
    txn = state["transaction"]
    llm_result = complete_json(
        system_prompt=(
            "You are the Diagnosis Agent in a revenue-recovery pipeline. Given a failed "
            "transaction, return JSON with exactly these keys: root_cause (short snake_case "
            "string), confidence (float 0-1), reasoning_text (one or two sentences). "
            "Note: a checkout_dropoff transaction has no failure code by design — Checkout "
            "was never completed, it never failed — so reason over elapsed time since "
            "checkout_initiated_at, the cart's amount, and last_payment_method instead."
        ),
        user_prompt=f"Transaction: {txn}",
    )
    diagnosis = llm_result if llm_result and {"root_cause", "confidence", "reasoning_text"} <= llm_result.keys() else _heuristic_diagnosis(txn)
    return {"diagnosis": diagnosis}


def _decide_node(state: PipelineState) -> PipelineState:
    txn, diagnosis = state["transaction"], state["diagnosis"]
    sequence_step = txn.get("sequence_step")
    step_note = (
        f"\nThis transaction is at step {sequence_step} of a 3-step mandate recovery "
        "cadence — pick the step-appropriate action (a later step uses a different "
        "channel, or escalates outright) rather than repeating the first nudge."
        if sequence_step not in (None, 0)
        else ""
    )
    llm_result = complete_json(
        system_prompt=(
            "You are the Decision Agent in a revenue-recovery pipeline. Given a transaction "
            "and its diagnosis, choose ONE action from: retry_order, new_payment_link, "
            "registration_link, invoice_reminder, voice_reminder, escalate. Return JSON with "
            "exactly these keys: chosen_action, reasoning_text. Note: there is no API to "
            "force-retry a specific failed payment or a halted subscription — never choose an "
            "action that assumes one exists. A checkout_dropoff transaction has no order to "
            "retry — prefer new_payment_link."
        ),
        user_prompt=f"Transaction: {txn}\nDiagnosis: {diagnosis}{step_note}",
    )
    valid_actions = {
        "retry_order", "new_payment_link", "registration_link", "invoice_reminder",
        "voice_reminder", "escalate",
    }
    decision = (
        llm_result
        if llm_result and llm_result.get("chosen_action") in valid_actions and "reasoning_text" in llm_result
        else _heuristic_decision(txn, diagnosis)
    )
    return {"decision": decision}


_graph = StateGraph(PipelineState)
_graph.add_node("diagnose", _diagnose_node)
_graph.add_node("decide", _decide_node)
_graph.set_entry_point("diagnose")
_graph.add_edge("diagnose", "decide")
_graph.add_edge("decide", END)
compiled_pipeline = _graph.compile()


def run_pipeline(transaction_fields: dict) -> PipelineState:
    """transaction_fields: a plain dict (kind, amount, currency, failure_code, customer_id,
    customer_name, sequence_step) — the graph is intentionally decoupled from the Django
    ORM. sequence_step is optional (defaults to None via .get() wherever it's read) and
    only meaningful for a subscription_failure transaction re-entering the pipeline
    mid-cadence (add-mandate-recovery-sequence): None/0 = the first nudge (today's
    existing behavior), 1 = the follow-up nudge on a different channel, 2 = the
    cadence's own terminal escalate step."""
    return compiled_pipeline.invoke({"transaction": transaction_fields})
