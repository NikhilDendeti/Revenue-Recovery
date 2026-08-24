import pytest
from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator
from rest_framework_simplejwt.tokens import AccessToken

from config.asgi import application
from recovery import ws as ws_module

pytestmark = pytest.mark.django_db(transaction=True)
# transaction=True, not the default rolled-back transaction: the Channels auth
# middleware resolves the user via database_sync_to_async, which runs on a separate
# DB connection/thread — it can't see a user created inside the default test
# transaction, since that transaction is never actually committed. Same root cause
# and same fix as the concurrency test in test_guardrails.py.


@pytest.fixture
def ws_url(dashboard_user):
    token = str(AccessToken.for_user(dashboard_user))
    return f"/ws/recovery/?token={token}"


@pytest.mark.asyncio
async def test_connection_without_token_is_closed():
    communicator = WebsocketCommunicator(application, "/ws/recovery/", headers=[(b"origin", b"http://localhost")])
    connected, _ = await communicator.connect()
    assert connected is False


@pytest.mark.asyncio
async def test_connection_with_invalid_token_is_closed():
    communicator = WebsocketCommunicator(
        application, "/ws/recovery/?token=not-a-real-token", headers=[(b"origin", b"http://localhost")]
    )
    connected, _ = await communicator.connect()
    assert connected is False


@pytest.mark.asyncio
async def test_ticker_event_reaches_a_connected_client(ws_url):
    communicator = WebsocketCommunicator(application, ws_url, headers=[(b"origin", b"http://localhost")])
    connected, _ = await communicator.connect()
    assert connected is True

    payload = {"transaction_id": "abc-123", "outcome": "recovered", "amount": 1200.0}
    await sync_to_async(ws_module.push)("ticker", payload)

    message = await communicator.receive_json_from(timeout=5)
    assert message == {"type": "ticker", "payload": payload}

    await communicator.disconnect()


@pytest.mark.asyncio
async def test_guardrail_event_reaches_a_connected_client(ws_url):
    communicator = WebsocketCommunicator(application, ws_url, headers=[(b"origin", b"http://localhost")])
    connected, _ = await communicator.connect()
    assert connected is True

    payload = {"transaction_id": "abc-123", "rule_name": "confidence_floor", "rule_result": "blocked"}
    await sync_to_async(ws_module.push)("guardrail", payload)

    message = await communicator.receive_json_from(timeout=5)
    assert message == {"type": "guardrail", "payload": payload}

    await communicator.disconnect()
