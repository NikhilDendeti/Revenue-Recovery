from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("transactions", views.TransactionViewSet, basename="transaction")
router.register("diagnoses", views.DiagnosisViewSet, basename="diagnosis")
router.register("decisions", views.DecisionViewSet, basename="decision")
router.register("actions", views.ActionViewSet, basename="action")
router.register("guardrail-events", views.GuardrailEventViewSet, basename="guardrail-event")
router.register("scheduled-actions", views.ScheduledActionViewSet, basename="scheduled-action")
router.register("promises-to-pay", views.PromiseToPayViewSet, basename="promise-to-pay")
router.register("audit-log", views.AuditLogViewSet, basename="audit-log")

urlpatterns = [
    path("", include(router.urls)),
    path("summary/", views.SummaryView.as_view(), name="summary"),
    path("batch/replay/", views.BatchReplayView.as_view(), name="batch-replay"),
    path("webhooks/razorpay/", views.WebhookView.as_view(), name="webhook-razorpay"),
]
