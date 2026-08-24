import pytest
from django.conf import settings


@pytest.fixture
def make_transaction(db):
    """Factory fixture — create a Transaction with sensible defaults, overridable."""
    from recovery.models import Transaction

    def _make(**kwargs):
        defaults = dict(
            kind=Transaction.Kind.PAYMENT_DEGRADATION,
            amount=1000,
            currency="INR",
            customer_id="cust_test_default",
            customer_name="Test Customer",
            customer_phone="+919821123456",
            failure_code="card_declined",
        )
        defaults.update(kwargs)
        return Transaction.objects.create(**defaults)

    return _make


@pytest.fixture
def heuristic_only():
    """Skip when an LLM key is configured — the pipeline heuristic fallback is only
    exercised (and only asserted on exact output) when no LLM is in the loop."""
    if settings.OPENAI_API_KEY or settings.ANTHROPIC_API_KEY:
        pytest.skip("OPENAI_API_KEY/ANTHROPIC_API_KEY configured — heuristic fallback is not exercised")


@pytest.fixture
def razorpay_live():
    """Skip the test cleanly when no real Razorpay credentials are configured."""
    if not (settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET):
        pytest.skip("RAZORPAY_KEY_ID/RAZORPAY_KEY_SECRET not configured — skipping live Razorpay test")


@pytest.fixture
def dashboard_user(db):
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_user(username="test_operator", password="test-password-123")


@pytest.fixture
def no_razorpay_keys(settings):
    """Force simulated mode regardless of what's in .env — keeps tests that aren't
    specifically about the live Razorpay integration deterministic and network-free."""
    settings.RAZORPAY_KEY_ID = ""
    settings.RAZORPAY_KEY_SECRET = ""
