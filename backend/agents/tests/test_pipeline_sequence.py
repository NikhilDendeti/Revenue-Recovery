"""add-mandate-recovery-sequence: step-aware decision routing for a subscription_failure
transaction re-entering the pipeline mid-cadence (sequence_step), plus voice_reminder
becoming a valid LLM decision action.

These patch agents.pipeline.complete_json directly (matching the convention already used
in recovery/tests/test_tasks.py) rather than relying on the heuristic_only fixture, so
they run deterministically regardless of whether a real LLM key is configured in this
environment.
"""

from unittest.mock import patch

from agents.pipeline import run_pipeline


def _txn(**overrides):
    base = dict(
        kind="subscription_failure",
        amount=1000.0,
        currency="INR",
        failure_code="card_declined",
        customer_id="cust_seq",
    )
    base.update(overrides)
    return base


def test_sequence_step_none_or_zero_behaves_like_todays_existing_mapping():
    with patch("agents.pipeline.complete_json", return_value=None):
        none_result = run_pipeline(_txn())
        zero_result = run_pipeline(_txn(sequence_step=0))
    assert none_result["decision"]["chosen_action"] == "registration_link"
    assert zero_result["decision"]["chosen_action"] == "registration_link"


def test_sequence_step_1_retriable_routes_to_voice_reminder_not_registration_link():
    with patch("agents.pipeline.complete_json", return_value=None):
        result = run_pipeline(_txn(sequence_step=1))
    assert result["decision"]["chosen_action"] == "voice_reminder"


def test_sequence_step_2_always_escalates_even_for_high_confidence_retriable_diagnosis():
    with patch("agents.pipeline.complete_json", return_value=None):
        result = run_pipeline(_txn(failure_code="insufficient_funds", sequence_step=2))
    assert result["diagnosis"]["confidence"] >= 0.60
    assert result["diagnosis"]["root_cause"] in {"insufficient_funds"}
    assert result["decision"]["chosen_action"] == "escalate"


def test_llm_voice_reminder_now_accepted_as_valid_decision_action():
    """voice_reminder used to be absent from _decide_node's valid_actions set and the
    system prompt's action list, so an LLM choosing it would have been silently
    coerced to the heuristic fallback. It's now accepted straight from the LLM."""
    llm_decision = {"chosen_action": "voice_reminder", "reasoning_text": "LLM chose the follow-up channel."}
    with patch("agents.pipeline.complete_json", side_effect=[None, llm_decision]):
        result = run_pipeline(_txn(sequence_step=1))
    assert result["decision"] == llm_decision
