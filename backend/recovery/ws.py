from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings

GROUP = "recovery_room"


def push(event_type: str, payload: dict) -> None:
    """Fire-and-forget push to every connected Recovery Room dashboard. Called from
    Celery tasks (never from a view or consumer directly touching the ORM in-line).

    Two delivery paths, matching settings.CHANNELS_USE_REDIS:
    - Redis configured: normal Channels pub/sub via the channel layer.
    - No Redis (local-dev default): writes a BroadcastEvent row instead.
      RecoveryConsumer polls for it — see models.BroadcastEvent's docstring for why
      a channel layer alone can't do this when the publisher (a Celery worker) and
      the WebSocket server (Daphne) are different processes.
    """
    if settings.CHANNELS_USE_REDIS:
        layer = get_channel_layer()
        if layer is None:
            return
        async_to_sync(layer.group_send)(
            GROUP, {"type": "broadcast.event", "event_type": event_type, "payload": payload}
        )
    else:
        from .models import BroadcastEvent

        BroadcastEvent.objects.create(event_type=event_type, payload=payload)
