from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .analytics import compute_summary
from .models import (
    Action as ActionModel,
    AuditLogEntry,
    Decision,
    Diagnosis,
    GuardrailEvent,
    PromiseToPay,
    ScheduledAction,
    Transaction,
)
from .serializers import (
    ActionSerializer,
    AuditLogEntrySerializer,
    DecisionSerializer,
    DiagnosisSerializer,
    GuardrailEventSerializer,
    PromiseToPaySerializer,
    ScheduledActionSerializer,
    TransactionChainSerializer,
    TransactionSerializer,
)
from .tasks import process_transaction_event, replay_batch, trigger_voice_showcase

WEBHOOK_KIND_MAP = {
    "payment.failed": Transaction.Kind.PAYMENT_DEGRADATION,
    "subscription.pending": Transaction.Kind.SUBSCRIPTION_FAILURE,
    "subscription.halted": Transaction.Kind.SUBSCRIPTION_FAILURE,
    "invoice.expired": Transaction.Kind.RECEIVABLE,
    # NOT a real Razorpay webhook event — Razorpay does not emit a checkout-abandonment
    # notification. This exists purely so the same simulated-webhook ingestion path the
    # other three kinds already use (the batch simulator, this endpoint) can also create
    # checkout_dropoff transactions. The at-risk window (settings.CHECKOUT_DROPOFF_AT_RISK_HOURS)
    # is the producing system's responsibility to enforce before firing this event — it is
    # not re-validated here, matching how e.g. "invoice.expired" is trusted as already-expired.
    "checkout.abandoned": Transaction.Kind.CHECKOUT_DROPOFF,
}


class TransactionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Transaction.objects.all()
    serializer_class = TransactionSerializer
    filterset_fields = ["kind", "status"]

    def get_serializer_class(self):
        if self.action == "chain":
            return TransactionChainSerializer
        return TransactionSerializer

    @action(detail=True, methods=["get"])
    def chain(self, request, pk=None):
        txn = self.get_object()
        return Response(self.get_serializer(txn).data)

    @action(detail=True, methods=["post"], url_path="voice-showcase")
    def voice_showcase(self, request, pk=None):
        txn = self.get_object()
        trigger_voice_showcase.delay(str(txn.id))
        return Response({"queued": True}, status=status.HTTP_202_ACCEPTED)


class DiagnosisViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Diagnosis.objects.all()
    serializer_class = DiagnosisSerializer
    filterset_fields = ["transaction"]


class DecisionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Decision.objects.all()
    serializer_class = DecisionSerializer
    filterset_fields = ["transaction", "chosen_action"]


class ActionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ActionModel.objects.all()
    serializer_class = ActionSerializer
    filterset_fields = ["transaction", "action_type", "result"]


class GuardrailEventViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = GuardrailEvent.objects.all()
    serializer_class = GuardrailEventSerializer
    filterset_fields = ["transaction", "rule_name", "rule_result"]


class ScheduledActionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ScheduledAction.objects.all()
    serializer_class = ScheduledActionSerializer
    filterset_fields = ["transaction", "status"]


class PromiseToPayViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = PromiseToPay.objects.all()
    serializer_class = PromiseToPaySerializer
    filterset_fields = ["status", "transaction"]


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """List/retrieve only — never expose update/delete on audit endpoints, matching
    the append-only DB constraint on AuditLogEntry itself."""

    queryset = AuditLogEntry.objects.all()
    serializer_class = AuditLogEntrySerializer
    filterset_fields = ["transaction", "event_type", "actor"]


class SummaryView(APIView):
    def get(self, request):
        return Response(compute_summary())


class BatchReplayView(APIView):
    """POST triggers a live, staggered replay of every OPEN transaction — the demo's
    'don't pre-run it' moment. Idempotent: transactions already past OPEN are skipped
    inside process_transaction_event, so calling this twice mid-flight is harmless."""

    def post(self, request):
        result = replay_batch.delay()
        return Response({"queued": True, "task_id": result.id}, status=status.HTTP_202_ACCEPTED)


class WebhookView(APIView):
    """Simulated Razorpay webhook ingestion. Accepts {"event": "...", "payload": {...}}
    shaped like a real Razorpay webhook body, maps it to a Transaction, and enqueues
    the diagnose -> decide -> guardrail -> act pipeline.

    Deliberately exempt from the dashboard's JWT auth: the caller here is an external
    system (Razorpay, or the batch simulator), not a logged-in operator — a JWT is the
    wrong mechanism for it. The correct mechanism is verifying Razorpay's own webhook
    signature (X-Razorpay-Signature + a webhook secret), which this endpoint does not
    yet do — that's a real follow-up, explicitly out of scope for the auth change that
    added this AllowAny.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        event = request.data.get("event")
        payload = request.data.get("payload", {})
        kind = WEBHOOK_KIND_MAP.get(event)
        if kind is None:
            return Response({"error": f"unrecognized event '{event}'"}, status=status.HTTP_400_BAD_REQUEST)

        # checkout_dropoff-only signals: an ISO datetime string (or absent -> None) and a
        # free-text payment method (or absent -> ""). Harmless no-ops for the other three
        # kinds, which never populate them.
        checkout_initiated_at = None
        raw_checkout_initiated_at = payload.get("checkout_initiated_at")
        if raw_checkout_initiated_at:
            checkout_initiated_at = parse_datetime(raw_checkout_initiated_at)
            if checkout_initiated_at and timezone.is_naive(checkout_initiated_at):
                checkout_initiated_at = timezone.make_aware(checkout_initiated_at)

        txn = Transaction.objects.create(
            kind=kind,
            amount=payload.get("amount", 0),
            currency=payload.get("currency", "INR"),
            customer_id=payload.get("customer_id", "unknown_customer"),
            customer_name=payload.get("customer_name", ""),
            customer_phone=payload.get("customer_phone", ""),
            customer_email=payload.get("customer_email", ""),
            failure_code=payload.get("failure_code", ""),
            razorpay_order_id=payload.get("order_id", ""),
            checkout_initiated_at=checkout_initiated_at,
            last_payment_method=payload.get("last_payment_method", ""),
        )
        process_transaction_event.delay(str(txn.id))
        return Response(TransactionSerializer(txn).data, status=status.HTTP_201_CREATED)
