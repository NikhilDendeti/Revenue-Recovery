"""Adapter tests — the translation layers between this app and the outside world."""

from unittest import mock

import pytest

from .. import razorpay_client
from ..adapters.razorpay_gateway import RazorpayGateway
from ..adapters.runtime import SystemRandomness
from ..domain_rules import resolve_outcome
from ..exceptions import GatewayArtifactNotFound, GatewayError


class TestRazorpayGatewayTranslation:
    """A 404 means "that artifact isn't there, issue a fresh one"; anything else means
    "escalate". Getting this mapping wrong either strands transactions or spams payment
    links, so it is worth pinning precisely."""

    def test_a_404_becomes_a_not_found_domain_error(self):
        err = razorpay_client.RazorpayError("gone", status_code=404)
        with mock.patch.object(razorpay_client, "reopen_order_checkout", side_effect=err):
            with pytest.raises(GatewayArtifactNotFound):
                RazorpayGateway().reopen_order_checkout("order_x", 100, "receipt")

    def test_a_500_becomes_a_generic_gateway_error(self):
        err = razorpay_client.RazorpayError("boom", status_code=500)
        with mock.patch.object(razorpay_client, "resend_invoice", side_effect=err):
            with pytest.raises(GatewayError) as caught:
                RazorpayGateway().resend_invoice("inv_x")
        assert not isinstance(caught.value, GatewayArtifactNotFound)

    def test_a_not_found_error_is_catchable_as_a_gateway_error(self):
        """Callers that don't care about the distinction get to write one except clause."""
        assert issubclass(GatewayArtifactNotFound, GatewayError)

    def test_a_non_provider_exception_passes_through_untouched(self):
        """The pipeline's safety net distinguishes "the provider said no" from "something
        unexpected broke". Wrapping a RuntimeError here would blur that."""
        with mock.patch.object(razorpay_client, "create_payment_link", side_effect=RuntimeError("kaboom")):
            with pytest.raises(RuntimeError):
                RazorpayGateway().create_payment_link(100, "d", "n", "p")

    def test_the_provider_function_is_resolved_at_call_time(self):
        """Binding these at import would make every existing mock.patch in the suite
        silently ineffective."""
        with mock.patch.object(razorpay_client, "create_payment_link", return_value={"id": "patched"}):
            assert RazorpayGateway().create_payment_link(100, "d", "n", "p") == {"id": "patched"}


class TestSeededRandomness:
    def test_unseeded_draws_are_in_range(self):
        rng = SystemRandomness(seed=None)
        draws = [rng.uniform(str(i)) for i in range(50)]
        assert all(0.0 <= d < 1.0 for d in draws)
        assert len(set(draws)) > 40, "unseeded draws should not repeat"

    def test_a_seed_makes_the_same_key_reproducible(self):
        a = SystemRandomness(seed="demo").uniform("txn-1")
        b = SystemRandomness(seed="demo").uniform("txn-1")
        assert a == b

    def test_a_seed_still_produces_a_distribution_across_transactions(self):
        """The regression this exists for: seeding one `random.Random(seed)` per built
        dependency graph returns the *first* value of the stream every time, so every
        transaction draws the same constant and a seeded replay silently becomes a ~100%
        recovery rate. A "run it twice, compare the counts" check passes that happily."""
        rng = SystemRandomness(seed="demo")
        draws = [rng.uniform(f"txn-{i}") for i in range(200)]
        assert len(set(draws)) > 50, "a seeded run collapsed to a near-constant draw"

    def test_a_seeded_replay_does_not_recover_everything(self):
        """The same bug, stated in the terms that matter on stage."""
        rng = SystemRandomness(seed="demo")
        outcomes = [resolve_outcome(0.82, rng.uniform(f"txn-{i}")) for i in range(200)]
        recovered = sum(outcomes)
        assert 0 < recovered < 200, "seeded outcomes must still vary"
        assert 0.70 < recovered / 200 < 0.94, f"expected ~82% recovery, got {recovered / 200:.0%}"

    def test_reproducibility_does_not_depend_on_processing_order(self):
        """Celery staggers the replay across however many workers are running, so a seed
        that only reproduces under serial execution reproduces nothing in practice."""
        keys = [f"txn-{i}" for i in range(20)]
        forward = {k: SystemRandomness(seed="demo").uniform(k) for k in keys}
        backward = {k: SystemRandomness(seed="demo").uniform(k) for k in reversed(keys)}
        assert forward == backward

    def test_different_seeds_give_different_boards(self):
        a = [SystemRandomness(seed="one").uniform(f"t{i}") for i in range(20)]
        b = [SystemRandomness(seed="two").uniform(f"t{i}") for i in range(20)]
        assert a != b
