from unittest.mock import patch

import pytest
import requests

from recovery import razorpay_client as rc

pytestmark = pytest.mark.django_db


def _fail_if_called(*args, **kwargs):
    raise AssertionError("requests.post was called in simulated mode — it must not hit the network")


@pytest.mark.usefixtures("no_razorpay_keys")
class TestSimulatedMode:
    def test_not_configured(self):
        assert rc._configured() is False

    def test_reopen_order_checkout_is_simulated(self):
        with patch.object(requests, "post", side_effect=_fail_if_called):
            resp = rc.reopen_order_checkout(None, 100000, receipt="r1")
        assert resp["simulated"] is True
        assert resp["id"].startswith("sim_order_")

    def test_create_payment_link_is_simulated(self):
        with patch.object(requests, "post", side_effect=_fail_if_called):
            resp = rc.create_payment_link(100000, "desc", "Test", "+919821123456")
        assert resp["simulated"] is True
        assert resp["short_url"].startswith("https://rzp.io/l/sim")

    def test_create_registration_link_is_simulated(self):
        with patch.object(requests, "post", side_effect=_fail_if_called):
            resp = rc.create_registration_link(100000, "desc", "Test", "+919821123456")
        assert resp["simulated"] is True

    def test_create_invoice_is_simulated(self):
        with patch.object(requests, "post", side_effect=_fail_if_called):
            resp = rc.create_invoice(100000, "desc", "Test", "+919821123456", expire_by=0)
        assert resp["simulated"] is True

    def test_resend_invoice_is_simulated(self):
        with patch.object(requests, "post", side_effect=_fail_if_called):
            resp = rc.resend_invoice("inv_fake")
        assert resp["simulated"] is True


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
