"""If a fake drifts from its interface, every use-case test built on it becomes a test of
something that cannot exist in production. ABCs catch that at instantiation — these tests
just make the failure land here, once, instead of in ten unrelated tests."""

from ...interfaces import (
    ClockInterface,
    DiagnosisPipelineInterface,
    PaymentGatewayInterface,
    RandomnessInterface,
    RecoveryRoomPresenterInterface,
    StorageInterface,
    TaskQueueInterface,
)
from ..fakes import (
    FakeClock,
    FakeGateway,
    FakePipeline,
    FakePresenter,
    FakeRandomness,
    FakeStorage,
    FakeTaskQueue,
    make_transaction,
)


def test_every_fake_implements_its_port():
    assert isinstance(FakeStorage(), StorageInterface)
    assert isinstance(FakeGateway(), PaymentGatewayInterface)
    assert isinstance(FakePipeline(), DiagnosisPipelineInterface)
    assert isinstance(FakeTaskQueue(), TaskQueueInterface)
    assert isinstance(FakeClock(), ClockInterface)
    assert isinstance(FakeRandomness(), RandomnessInterface)
    assert isinstance(FakePresenter(), RecoveryRoomPresenterInterface)


def test_fake_storage_enforces_the_idempotency_guard():
    """The guard that stops a duplicate webhook reprocessing a transaction — the fake has
    to model it, or a use-case test would never exercise the branch."""
    open_txn = make_transaction(id="t1", status="open")
    storage = FakeStorage(transactions=[open_txn])

    claimed = storage.claim_open_transaction("t1")
    assert claimed.status == "processing"

    from ...exceptions import TransactionNotOpen
    try:
        storage.claim_open_transaction("t1")
    except TransactionNotOpen as err:
        assert err.status == "processing"
    else:
        raise AssertionError("second claim should have raised TransactionNotOpen")


def test_fake_gateway_raises_once_then_succeeds():
    """`raises` models the 404-then-fallback shape: the first call fails, the payment-link
    retry after it succeeds."""
    from ...exceptions import GatewayArtifactNotFound

    gateway = FakeGateway(raises=GatewayArtifactNotFound("gone"))
    try:
        gateway.reopen_order_checkout("order_x", 100, "receipt")
    except GatewayArtifactNotFound:
        pass
    else:
        raise AssertionError("first call should have raised")

    assert gateway.create_payment_link(100, "d", "n", "p")["id"] == "sim_fake_001"
    assert gateway.called == ["reopen_order_checkout", "create_payment_link"]
