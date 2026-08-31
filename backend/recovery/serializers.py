from rest_framework import serializers

from .models import (
    Action,
    AuditLogEntry,
    Decision,
    Diagnosis,
    GuardrailEvent,
    PromiseToPay,
    ScheduledAction,
    Transaction,
)


class DiagnosisSerializer(serializers.ModelSerializer):
    class Meta:
        model = Diagnosis
        fields = ["id", "root_cause", "confidence", "reasoning_text", "agent_run_at"]


class DecisionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Decision
        fields = ["id", "chosen_action", "reasoning_text", "guardrail_checks_passed", "decided_at"]


class ActionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Action
        fields = ["id", "action_type", "executed_at", "api_response", "result", "amount_recovered"]


class GuardrailEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = GuardrailEvent
        fields = ["id", "rule_name", "rule_result", "detail", "triggered_at"]


class ScheduledActionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScheduledAction
        fields = ["id", "action_type", "reason", "run_after", "status", "created_at"]


class PromiseToPaySerializer(serializers.ModelSerializer):
    class Meta:
        model = PromiseToPay
        fields = ["id", "transaction", "promised_amount", "promise_date", "source", "status", "created_at"]


class AuditLogEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLogEntry
        fields = ["id", "transaction", "event_type", "actor", "payload", "timestamp"]


class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = [
            "id", "kind", "amount", "currency", "customer_id", "customer_name", "customer_phone",
            "merchant_id", "failure_code", "razorpay_order_id", "status", "created_at", "updated_at",
        ]


class TransactionChainSerializer(serializers.ModelSerializer):
    """The full click-through reasoning chain for Panel 3 of the Recovery Room."""

    diagnoses = DiagnosisSerializer(many=True, read_only=True)
    decisions = DecisionSerializer(many=True, read_only=True)
    actions = ActionSerializer(many=True, read_only=True)
    guardrail_events = GuardrailEventSerializer(many=True, read_only=True)
    audit_entries = AuditLogEntrySerializer(many=True, read_only=True)
    scheduled_actions = ScheduledActionSerializer(many=True, read_only=True)

    class Meta:
        model = Transaction
        fields = [
            "id", "kind", "amount", "currency", "customer_id", "customer_name", "customer_phone",
            "merchant_id", "failure_code", "razorpay_order_id", "status", "created_at", "updated_at",
            "diagnoses", "decisions", "actions", "guardrail_events", "audit_entries", "scheduled_actions",
        ]
