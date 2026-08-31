from unittest.mock import Mock, patch

import pytest
import requests

from recovery import razorpay_client as rc

pytestmark = pytest.mark.django_db


def _fail_if_called(*args, **kwargs):
    raise AssertionError("requests.post was called in simulated mode — it must not hit the network")


class TestErrorClassification:
    """A RazorpayError carries the HTTP status so the action layer can tell a 404
    (fall back to a fresh payment link) from a transient error (escalate)."""

    def test_post_raises_with_status_code_on_404(self):
        with patch.object(requests, "post", return_value=Mock(status_code=404, text="not found")):
            with pytest.raises(rc.RazorpayError) as excinfo:
                rc._post("/orders/order_missing", {})
        assert excinfo.value.status_code == 404
        assert rc.is_not_found(excinfo.value) is True

    def test_is_not_found_false_for_non_404_error(self):
        with patch.object(requests, "post", return_value=Mock(status_code=500, text="server error")):
            with pytest.raises(rc.RazorpayError) as excinfo:
                rc._post("/orders", {"amount": 100})
        assert excinfo.value.status_code == 500
        assert rc.is_not_found(excinfo.value) is False


@pytest.mark.usefixtures("no_razorpay_keys")
class TestSimulatedMode:
    def test_not_configured(self):
        assert rc._configured() is False

    def test_reopen_order_checkout_is_simulated(self):
        with patch.object(requests, "post", side_effect=_fail_if_called):
            resp = rc.reopen_order_checkout(None, 100000, "r1", "Test", "+919821123456")
        assert resp["simulated"] is True
        assert resp["short_url"].startswith("https://rzp.io/l/sim")

    def test_create_payment_link_is_simulated(self):
        with patch.object(requests, "post", side_effect=_fail_if_called):
            resp = rc.create_payment_link(100000, "desc", "Test", "+919821123456")
        assert resp["simulated"] is True
        assert resp["short_url"].startswith("https://rzp.io/l/sim")

    def test_create_registration_link_is_simulated(self):
        with patch.object(requests, "post", side_effect=_fail_if_called):
            resp = rc.create_registration_link(100000, "desc", "Test", "+919821123456", "test@example.test")
        assert resp["simulated"] is True

    def test_create_invoice_is_simulated(self):
        with patch.object(requests, "post", side_effect=_fail_if_called):
            resp = rc.create_invoice(100000, "desc", "Test", "+919821123456", expire_by=0)
        assert resp["simulated"] is True

    def test_resend_invoice_is_simulated(self):
        with patch.object(requests, "post", side_effect=_fail_if_called):
            resp = rc.resend_invoice("inv_fake")
        assert resp["simulated"] is True


class TestRegistrationLinkLivePayload:
    """Exercises `create_registration_link`'s live-mode body (the `_configured()` True
    branch) without a real network call — patches `_configured` directly rather than
    gating on real keys, since these assert on payload shape and the pre-flight guard,
    not on a real Razorpay response."""

    def test_blank_customer_email_raises_before_any_network_call(self):
        with patch.object(rc, "_configured", return_value=True):
            with patch.object(requests, "post", side_effect=_fail_if_called):
                with pytest.raises(rc.RazorpayError) as excinfo:
                    rc.create_registration_link(100000, "desc", "Test", "+919821123456", "")
        assert excinfo.value.status_code is None

    def test_live_payload_includes_email_zero_amount_and_subscription_registration(self):
        with patch.object(rc, "_configured", return_value=True):
            with patch.object(requests, "post", return_value=Mock(status_code=200, json=lambda: {"id": "reglink_x"})) as mock_post:
                rc.create_registration_link(100000, "desc", "Test", "+919821123456", "test@example.test")
        posted_body = mock_post.call_args.kwargs["json"]
        assert posted_body["amount"] == 0
        assert "subscription_registration" in posted_body
        assert posted_body["customer"]["email"] == "test@example.test"


class TestLiveMode:
    def test_create_and_cancel_a_real_payment_link(self, razorpay_live):
        resp = rc.create_payment_link(150000, "pytest live-mode smoke test", "Test Customer", "+919821123456")
        assert "simulated" not in resp
        assert resp["id"].startswith("plink_")
        assert resp["short_url"].startswith("https://rzp.io/")

        cancel = requests.post(
            f"https://api.razorpay.com/v1/payment_links/{resp['id']}/cancel",
            auth=(rc.settings.RAZORPAY_KEY_ID, rc.settings.RAZORPAY_KEY_SECRET),
            timeout=15,
        )
        assert cancel.status_code == 200
        assert cancel.json()["status"] == "cancelled"

    def test_reopen_order_checkout_issues_a_real_payment_link(self, razorpay_live):
        """After the live-mode rewrite, retry_order's call is identical in shape to a
        fresh payment link — no order-reopen endpoint is involved — so this asserts the
        same payment-link-shaped response `create_payment_link` produces, plus the
        `retried_order_id` provenance key."""
        resp = rc.reopen_order_checkout(
            "order_sim_does_not_exist", 150000, "pytest live-mode smoke test", "Test Customer", "+919821123456"
        )
        assert "simulated" not in resp
        assert resp["id"].startswith("plink_")
        assert resp["short_url"].startswith("https://rzp.io/")
        assert resp["retried_order_id"] == "order_sim_does_not_exist"

        cancel = requests.post(
            f"https://api.razorpay.com/v1/payment_links/{resp['id']}/cancel",
            auth=(rc.settings.RAZORPAY_KEY_ID, rc.settings.RAZORPAY_KEY_SECRET),
            timeout=15,
        )
        assert cancel.status_code == 200
        assert cancel.json()["status"] == "cancelled"

    def test_create_registration_link_against_live_api(self, razorpay_live):
        """Confirms the corrected payload (customer.email, subscription_registration,
        amount: 0) is accepted by Razorpay's real test-mode e-mandate registration
        endpoint — the `method`/`auth_type` values are a documented-safe guess per
        design.md's Open Questions, and this test is the mechanism meant to catch a
        wrong value. No cancellation call: Razorpay's subscription-registration
        auth-links API documents no cancel/expire endpoint for this artifact (unlike a
        Payment Link's `/cancel`), so none is attempted here — a deliberate omission,
        not an oversight."""
        resp = rc.create_registration_link(
            0,
            "pytest live-mode smoke test — registration link",
            "Test Customer",
            "+919821123456",
            "test@example.test",
        )
        assert "simulated" not in resp
        assert "short_url" in resp
