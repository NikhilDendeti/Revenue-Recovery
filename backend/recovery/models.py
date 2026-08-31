import uuid

from django.db import models


class Transaction(models.Model):
    """A single unit of at-risk revenue — the BRD's three flows are three Kind values
    sharing one pipeline (detect -> diagnose -> decide -> act -> track -> audit)."""

    class Kind(models.TextChoices):
        PAYMENT_DEGRADATION = "payment_degradation", "Payment degradation"
        SUBSCRIPTION_FAILURE = "subscription_failure", "Subscription failure"
        RECEIVABLE = "receivable", "B2B receivable"
        CHECKOUT_DROPOFF = "checkout_dropoff", "Checkout drop-off"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        PROCESSING = "processing", "Processing"
        RECOVERED = "recovered", "Recovered"
        ESCALATED = "escalated", "Escalated"
        HELD = "held", "Held"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=32, choices=Kind.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="INR")
    customer_id = models.CharField(max_length=64, db_index=True)
    customer_name = models.CharField(max_length=128, blank=True)
    customer_phone = models.CharField(max_length=20, blank=True)
    customer_email = models.EmailField(blank=True)
    merchant_id = models.CharField(max_length=64, default="demo_merchant")
    failure_code = models.CharField(max_length=64, blank=True)
    razorpay_order_id = models.CharField(max_length=64, blank=True)
    checkout_initiated_at = models.DateTimeField(null=True, blank=True)
    last_payment_method = models.CharField(max_length=32, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["customer_id", "created_at"])]

    def __str__(self):
        return f"{self.kind} · {self.currency} {self.amount} · {self.customer_id}"


class Diagnosis(models.Model):
    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name="diagnoses")
    root_cause = models.CharField(max_length=128)
    confidence = models.FloatField()
    reasoning_text = models.TextField()
    agent_run_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-agent_run_at"]


class Decision(models.Model):
    class Action(models.TextChoices):
        RETRY_ORDER = "retry_order", "Re-attempt same order"
        NEW_PAYMENT_LINK = "new_payment_link", "Issue fresh payment link"
        REGISTRATION_LINK = "registration_link", "Send registration link"
        INVOICE_REMINDER = "invoice_reminder", "Resend invoice reminder"
        VOICE_REMINDER = "voice_reminder", "Hinglish voice reminder"
        ESCALATE = "escalate", "Escalate to human queue"
        HOLD = "hold", "Hold — guardrail cooldown"

    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name="decisions")
    chosen_action = models.CharField(max_length=32, choices=Action.choices)
    reasoning_text = models.TextField()
    guardrail_checks_passed = models.JSONField(default=list)
    decided_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-decided_at"]


class ScheduledAction(models.Model):
    """A cooldown/delayed action, e.g. 'retry in 48h'. Modeled as a row + a periodic
    Beat sweeper (recovery.tasks.sweep_scheduled_actions) rather than a raw Celery ETA
    task, so it survives worker restarts and stays inspectable in the admin."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        DISPATCHED = "dispatched", "Dispatched"
        CANCELLED = "cancelled", "Cancelled"

    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name="scheduled_actions")
    action_type = models.CharField(max_length=32)
    reason = models.CharField(max_length=64, blank=True)
    run_after = models.DateTimeField(db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["transaction"],
                condition=models.Q(status="pending"),
                name="one_pending_scheduled_action_per_txn",
            )
        ]


class PromiseToPay(models.Model):
    """A customer's committed payment date, elicited during a recovery attempt (the
    voice channel today; a manual B2B follow-up in future). Modeled as a row + a
    periodic Beat sweeper (recovery.tasks.sweep_promises_to_pay), the same
    "row + sweep" shape as ScheduledAction, rather than living only as unstructured
    audit-log payload text."""

    class Source(models.TextChoices):
        VOICE = "voice", "Voice"
        MANUAL = "manual", "Manual"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        KEPT = "kept", "Kept"
        BROKEN = "broken", "Broken"

    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name="promises")
    promised_amount = models.DecimalField(max_digits=12, decimal_places=2)
    promise_date = models.DateField()
    source = models.CharField(max_length=16, choices=Source.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["transaction"],
                condition=models.Q(status="pending"),
                name="one_pending_promise_to_pay_per_txn",
            )
        ]


class Action(models.Model):
    class Type(models.TextChoices):
        RETRY = "retry", "Retry"
        EMAIL = "email", "Email"
        WHATSAPP = "whatsapp", "WhatsApp"
        VOICE = "voice", "Voice"
        ESCALATE = "escalate", "Escalate"

    class Result(models.TextChoices):
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"
        PENDING = "pending", "Pending"
        SIMULATED = "simulated", "Simulated"

    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name="actions")
    action_type = models.CharField(max_length=16, choices=Type.choices)
    executed_at = models.DateTimeField(auto_now_add=True)
    api_response = models.JSONField(default=dict)
    result = models.CharField(max_length=16, choices=Result.choices)
    amount_recovered = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        ordering = ["-executed_at"]


class GuardrailEvent(models.Model):
    class Result(models.TextChoices):
        PASSED = "passed", "Passed"
        BLOCKED = "blocked", "Blocked"

    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name="guardrail_events")
    rule_name = models.CharField(max_length=64)
    rule_result = models.CharField(max_length=16, choices=Result.choices)
    detail = models.TextField(blank=True)
    triggered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-triggered_at"]


class ContactCooldown(models.Model):
    """Backs the '1 nudge / 24h / customer' guardrail. Checked and updated inside a
    single select_for_update() transaction — a naive read-then-write races under
    concurrent Celery tasks."""

    customer_id = models.CharField(max_length=64, unique=True)
    last_contacted_at = models.DateTimeField()


class AuditLogEntry(models.Model):
    """Append-only event ledger. The save()/delete() guards below are the layer judges
    never see; the layer that actually matters is the BEFORE UPDATE OR DELETE trigger
    added in migration 0002 — that's what makes 'append-only' true against raw SQL or
    a stray admin action, not just against this ORM code."""

    class Actor(models.TextChoices):
        AGENT = "agent", "Agent"
        SYSTEM = "system", "System"
        HUMAN = "human", "Human"

    # PROTECT, not CASCADE: a cascaded delete would issue a bulk DELETE against this
    # table, and the append-only trigger (migration 0002) would reject it anyway —
    # better to fail fast and obviously (ProtectedError) than abort mid-transaction on
    # a trigger exception. A Transaction with audit history genuinely cannot be deleted.
    transaction = models.ForeignKey(Transaction, on_delete=models.PROTECT, related_name="audit_entries")
    event_type = models.CharField(max_length=64)
    actor = models.CharField(max_length=16, choices=Actor.choices)
    payload = models.JSONField(default=dict)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-timestamp"]

    def save(self, *args, **kwargs):
        if self.pk:
            raise PermissionError("audit_log is append-only — updates are not permitted")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("audit_log is append-only — deletes are not permitted")


class BroadcastEvent(models.Model):
    """The cross-process relay used in place of Channels' Redis pub/sub when
    settings.CHANNELS_USE_REDIS is False (the local-dev default). recovery.ws.push()
    writes a row here; RecoveryConsumer polls for rows newer than its own connect-time
    watermark and forwards each one to its client. Both the Celery worker (publisher)
    and Daphne (the WebSocket server) already share this database regardless of broker
    choice, so this reuses the one cross-process channel that was always there rather
    than adding a new one. Not the audit log: purely transient plumbing, safe to grow
    and never specially pruned."""

    event_type = models.CharField(max_length=32)
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)


class MandateSequence(models.Model):
    """Tracks a subscription_failure transaction through the fixed 3-step
    nudge-then-escalate cadence: step 0 - registration-link nudge (today's existing
    behavior, unchanged), step 1 - a follow-up nudge on a different channel
    (voice_reminder) after a configurable delay if the customer hasn't recovered, step
    2 - escalate to the human queue if still unresolved. Created once, lazily, the
    moment a subscription_failure transaction's first Decision resolves to
    registration_link without an immediate guardrail escalation — an immediately
    escalated transaction is never sequenced. Each step transition is chained as a
    ScheduledAction row (reason="mandate_sequence_step"), the same DB-backed,
    Beat-swept pattern recovery.tasks.sweep_scheduled_actions already sweeps for
    cooldown/retry — never a raw multi-day Celery ETA task — so the cadence survives a
    worker restart."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        RECOVERED = "recovered", "Recovered"
        ESCALATED = "escalated", "Escalated"
        CANCELLED = "cancelled", "Cancelled"

    transaction = models.OneToOneField(Transaction, on_delete=models.CASCADE, related_name="mandate_sequence")
    current_step = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
