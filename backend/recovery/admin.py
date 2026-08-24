from django.contrib import admin

from .models import (
    Action,
    AuditLogEntry,
    ContactCooldown,
    Decision,
    Diagnosis,
    GuardrailEvent,
    ScheduledAction,
    Transaction,
)


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("id", "kind", "amount", "currency", "customer_id", "status", "created_at")
    list_filter = ("kind", "status")
    search_fields = ("customer_id", "id")


@admin.register(Diagnosis)
class DiagnosisAdmin(admin.ModelAdmin):
    list_display = ("transaction", "root_cause", "confidence", "agent_run_at")


@admin.register(Decision)
class DecisionAdmin(admin.ModelAdmin):
    list_display = ("transaction", "chosen_action", "decided_at")


@admin.register(ScheduledAction)
class ScheduledActionAdmin(admin.ModelAdmin):
    list_display = ("transaction", "action_type", "run_after", "status")
    list_filter = ("status",)


@admin.register(Action)
class ActionAdmin(admin.ModelAdmin):
    list_display = ("transaction", "action_type", "result", "amount_recovered", "executed_at")
    list_filter = ("action_type", "result")


@admin.register(GuardrailEvent)
class GuardrailEventAdmin(admin.ModelAdmin):
    list_display = ("transaction", "rule_name", "rule_result", "triggered_at")
    list_filter = ("rule_name", "rule_result")


@admin.register(ContactCooldown)
class ContactCooldownAdmin(admin.ModelAdmin):
    list_display = ("customer_id", "last_contacted_at")


@admin.register(AuditLogEntry)
class AuditLogEntryAdmin(admin.ModelAdmin):
    list_display = ("transaction", "event_type", "actor", "timestamp")
    list_filter = ("event_type", "actor")

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
