"""The Diagnosis -> Decision graph. A LangGraph StateGraph, not a CrewAI crew — this
pipeline is a small, deterministic-shaped state machine (ingest -> diagnose -> decide),
which is exactly what LangGraph is good at: inspectable per-node state, easy to log,
easy to keep the Guardrail Enforcer (deterministic, no LLM) as a separate step outside
this graph entirely.

Runs synchronously inside a Celery task — never call this from a view or a Channels
consumer, an LLM round trip is seconds-to-tens-of-seconds and would stall the ASGI
event loop for every other dashboard viewer.
"""

from typing import TypedDict

from langgraph.graph import END, StateGraph

from .llm import complete_json

# --- heuristic fallback tables (used whenever no LLM key is configured, or the call fails) ---

_DIAGNOSIS_RULES = [
    ("insufficient_funds", "insufficient_funds", 0.82, "Card/UPI declined for insufficient funds — this failure class historically recovers well on a short delay retry."),
    # "expired" is checked before "card_declined" deliberately: a code containing both
    # (e.g. seed data's "card_declined_expired") is a more specific, more actionable
    # diagnosis as an expired card than as a generic decline — a same-card retry
    # cannot succeed on an expired card, so it needs to route to a fresh payment link,
    # not the card-decline retry/cooldown path. First-match-wins over a substring scan
    # means list order encodes specificity; keep the more specific pattern first.
    ("expired", "card_expired", 0.90, "The card on file has expired — a same-card retry cannot succeed; the customer needs a fresh payment method."),
    ("card_declined", "card_declined", 0.78, "Card issuer declined the charge. Recoverable via a fresh attempt, but subject to the card-decline cooldown."),
    ("timeout", "network_timeout", 0.55, "Payment attempt timed out before a definitive result — ambiguous signal, moderate confidence."),
    ("network", "network_timeout", 0.55, "Network-level failure during the attempt — ambiguous signal, moderate confidence."),
    ("mandate", "mandate_charge_failed", 0.75, "Recurring mandate charge failed — Razorpay is likely already auto-retrying on its fixed schedule."),
]

_KIND_DEFAULTS = {
    "payment_degradation": ("payment_declined", 0.60, "Generic payment failure with no specific failure code — treating as a standard decline."),
    "subscription_failure": ("mandate_charge_failed", 0.65, "Subscription charge failed — Razorpay's own retry schedule applies; recovery here means driving re-authorization."),
    "receivable": ("invoice_overdue", 0.88, "B2B invoice has aged past its due date with no payment received."),
}


def _heuristic_diagnosis(txn: dict) -> dict:
    code = (txn.get("failure_code") or "").lower()
    for needle, root_cause, confidence, reasoning in _DIAGNOSIS_RULES:
        if needle in code:
            return {"root_cause": root_cause, "confidence": confidence, "reasoning_text": reasoning}
    if not code:
        # No failure code at all is itself a weak signal — keep confidence low so the
        # confidence-floor guardrail has a real, honest chance to fire in the demo.
        return {"root_cause": "unknown", "confidence": 0.35, "reasoning_text": "No failure code present and no rule matched — root cause is genuinely unclear."}
    root_cause, confidence, reasoning = _KIND_DEFAULTS.get(txn["kind"], ("unknown", 0.35, "Unrecognized failure pattern."))
    return {"root_cause": root_cause, "confidence": confidence, "reasoning_text": reasoning}


# Payment-degradation root causes route to Order re-attempt or a fresh Payment Link —
# there's a real order_id to reopen. Subscription-failure root causes ALWAYS route to
# registration_link regardless of root cause: Razorpay already auto-retries a failed
# mandate charge on its own fixed schedule, and there's no API to force an out-of-band
# retry — the only actionable lever a subscription-context transaction has is driving
# re-authorization. Collapsing this into one table keyed by root_cause alone (the
# original version of this function) would let a subscription transaction diagnosed as
# "card_declined" pick retry_order, which assumes an Order-reopen flow that doesn't
# apply to recurring billing — exactly the kind of Razorpay-API mistake this build is
# supposed to avoid.
_PAYMENT_DEGRADATION_ACTIONS = {
    "insufficient_funds": "retry_order",
    "card_declined": "retry_order",
    "network_timeout": "retry_order",
    "card_expired": "new_payment_link",
    "payment_declined": "new_payment_link",
}
_SUBSCRIPTION_RETRIABLE_ROOT_CAUSES = {"card_declined", "insufficient_funds", "mandate_charge_failed"}

_REASONING = {
    "retry_order": "Root cause is retriable on the same order intent — re-opening Checkout rather than inventing a retry call that doesn't exist.",
    "new_payment_link": "Same card/order can't be reused — issuing a fresh payable artifact instead.",
    "registration_link": "This is a subscription/mandate context: Razorpay's own auto-retry schedule already governs the charge and there's no API to force a retry — driving re-authorization is the actionable lever.",
    "invoice_reminder": "Overdue receivable — nudging via the existing invoice's reminder channel before escalating to a higher-touch channel.",
}


def _heuristic_decision(txn: dict, diagnosis: dict) -> dict:
    root_cause = diagnosis["root_cause"]
    if diagnosis["confidence"] < 0.60 or root_cause == "unknown":
        return {"chosen_action": "escalate", "reasoning_text": "Diagnosis confidence too low to act autonomously — routing to human review rather than guessing with money."}

    if txn["kind"] == "subscription_failure":
        action = "registration_link" if root_cause in _SUBSCRIPTION_RETRIABLE_ROOT_CAUSES else "escalate"
    elif txn["kind"] == "receivable":
        action = "invoice_reminder" if root_cause == "invoice_overdue" else "escalate"
    else:
        action = _PAYMENT_DEGRADATION_ACTIONS.get(root_cause, "escalate")

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
            "string), confidence (float 0-1), reasoning_text (one or two sentences)."
        ),
        user_prompt=f"Transaction: {txn}",
    )
    diagnosis = llm_result if llm_result and {"root_cause", "confidence", "reasoning_text"} <= llm_result.keys() else _heuristic_diagnosis(txn)
    return {"diagnosis": diagnosis}


def _decide_node(state: PipelineState) -> PipelineState:
    txn, diagnosis = state["transaction"], state["diagnosis"]
    llm_result = complete_json(
        system_prompt=(
            "You are the Decision Agent in a revenue-recovery pipeline. Given a transaction "
            "and its diagnosis, choose ONE action from: retry_order, new_payment_link, "
            "registration_link, invoice_reminder, escalate. Return JSON with exactly these "
            "keys: chosen_action, reasoning_text. Note: there is no API to force-retry a "
            "specific failed payment or a halted subscription — never choose an action that "
            "assumes one exists."
        ),
        user_prompt=f"Transaction: {txn}\nDiagnosis: {diagnosis}",
    )
    valid_actions = {"retry_order", "new_payment_link", "registration_link", "invoice_reminder", "escalate"}
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
    customer_name) — the graph is intentionally decoupled from the Django ORM."""
    return compiled_pipeline.invoke({"transaction": transaction_fields})
