import pytest
from rest_framework.test import APIClient

from recovery.models import AuditLogEntry, Decision, Diagnosis, GuardrailEvent, Transaction

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("no_razorpay_keys")]


@pytest.fixture
def client(dashboard_user):
    """Authenticated by default — these tests exercise endpoint behavior, not the
    auth mechanism itself (see TestAuthentication below for that)."""
    c = APIClient()
    c.force_authenticate(user=dashboard_user)
    return c


def _record(make_transaction):
    txn = make_transaction(failure_code="insufficient_funds", amount=1000)
    Diagnosis.objects.create(transaction=txn, root_cause="insufficient_funds", confidence=0.82, reasoning_text="t")
    Decision.objects.create(transaction=txn, chosen_action="retry_order", reasoning_text="t")
    GuardrailEvent.objects.create(transaction=txn, rule_name="spend_ceiling", rule_result="passed", detail="ok")
    AuditLogEntry.objects.create(transaction=txn, event_type="detected", actor="system", payload={"a": 1})
    return txn


# --- read endpoints ---


def test_transaction_list(client, make_transaction):
    _record(make_transaction)
    resp = client.get("/api/transactions/")
    assert resp.status_code == 200
    assert resp.json()["count"] == 1


def test_transaction_chain_returns_full_reasoning_chain(client, make_transaction):
    txn = _record(make_transaction)
    resp = client.get(f"/api/transactions/{txn.id}/chain/")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["diagnoses"]) == 1
    assert len(body["decisions"]) == 1
    assert len(body["guardrail_events"]) == 1
    assert len(body["audit_entries"]) == 1


def test_summary_endpoint(client, make_transaction):
    _record(make_transaction)
    resp = client.get("/api/summary/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_count"] == 1
    assert "recovery_rate" in body


def test_guardrail_events_list(client, make_transaction):
    _record(make_transaction)
    resp = client.get("/api/guardrail-events/")
    assert resp.status_code == 200
    assert resp.json()["count"] == 1


def test_scheduled_actions_list_empty(client):
    resp = client.get("/api/scheduled-actions/")
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


# --- audit log: read-only ---


def test_audit_log_list_and_retrieve(client, make_transaction):
    txn = _record(make_transaction)
    entry = AuditLogEntry.objects.get(transaction=txn)

    list_resp = client.get("/api/audit-log/")
    assert list_resp.status_code == 200
    assert list_resp.json()["count"] == 1

    detail_resp = client.get(f"/api/audit-log/{entry.id}/")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["event_type"] == "detected"


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_audit_log_write_methods_are_rejected(client, make_transaction, method):
    txn = _record(make_transaction)
    entry = AuditLogEntry.objects.get(transaction=txn)
    before_count = AuditLogEntry.objects.count()

    if method in {"put", "patch", "delete"}:
        resp = getattr(client, method)(f"/api/audit-log/{entry.id}/", {"event_type": "tampered"}, format="json")
    else:
        resp = client.post("/api/audit-log/", {"event_type": "forged", "actor": "human"}, format="json")

    assert resp.status_code == 405
    assert AuditLogEntry.objects.count() == before_count
    entry.refresh_from_db()
    assert entry.event_type == "detected"


# --- batch replay + webhook ingestion ---


def test_batch_replay_trigger_is_accepted(client, make_transaction):
    make_transaction(failure_code="insufficient_funds")
    resp = client.post("/api/batch/replay/", {}, format="json")
    assert resp.status_code == 202
    assert resp.json()["queued"] is True


def test_webhook_payment_failed_creates_transaction(client):
    resp = client.post(
        "/api/webhooks/razorpay/",
        {
            "event": "payment.failed",
            "payload": {
                "amount": 1200,
                "currency": "INR",
                "customer_id": "cust_webhook",
                "failure_code": "insufficient_funds",
            },
        },
        format="json",
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["kind"] == Transaction.Kind.PAYMENT_DEGRADATION
    assert Transaction.objects.filter(customer_id="cust_webhook").exists()


def test_webhook_unrecognized_event_is_rejected(client):
    resp = client.post("/api/webhooks/razorpay/", {"event": "not.a.real.event", "payload": {}}, format="json")
    assert resp.status_code == 400


# --- authentication ---


class TestAuthentication:
    def test_protected_endpoint_without_token_is_rejected(self):
        resp = APIClient().get("/api/transactions/")
        assert resp.status_code == 401

    def test_webhook_works_with_no_authentication_at_all(self):
        """The webhook is intentionally exempt — see WebhookView's docstring."""
        resp = APIClient().post(
            "/api/webhooks/razorpay/",
            {"event": "payment.failed", "payload": {"amount": 500, "customer_id": "cust_unauth_webhook"}},
            format="json",
        )
        assert resp.status_code == 201
        assert Transaction.objects.filter(customer_id="cust_unauth_webhook").exists()

    def test_token_endpoint_valid_credentials(self, dashboard_user):
        resp = APIClient().post(
            "/api/auth/token/", {"username": "test_operator", "password": "test-password-123"}, format="json"
        )
        assert resp.status_code == 200
        assert "access" in resp.json() and "refresh" in resp.json()

    def test_token_endpoint_invalid_credentials(self, dashboard_user):
        resp = APIClient().post(
            "/api/auth/token/", {"username": "test_operator", "password": "wrong-password"}, format="json"
        )
        assert resp.status_code == 401

    def test_refresh_endpoint_issues_new_access_token(self, dashboard_user):
        obtain = APIClient().post(
            "/api/auth/token/", {"username": "test_operator", "password": "test-password-123"}, format="json"
        )
        refresh_token = obtain.json()["refresh"]

        resp = APIClient().post("/api/auth/token/refresh/", {"refresh": refresh_token}, format="json")
        assert resp.status_code == 200
        assert "access" in resp.json()

    def test_valid_token_grants_access(self, dashboard_user):
        obtain = APIClient().post(
            "/api/auth/token/", {"username": "test_operator", "password": "test-password-123"}, format="json"
        )
        access_token = obtain.json()["access"]

        resp = APIClient().get("/api/transactions/", HTTP_AUTHORIZATION=f"Bearer {access_token}")
        assert resp.status_code == 200
