import asyncio
import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings

from .models import BroadcastEvent
from .ws import GROUP

POLL_INTERVAL_SECONDS = 0.3


class RecoveryConsumer(AsyncWebsocketConsumer):
    """One channel, typed messages — the Ticker, Guardrail Console and Audit Trail all
    subscribe to the same group and route by `type` client-side. Simpler than one
    consumer per panel, and just as live.

    Delivery mechanism depends on settings.CHANNELS_USE_REDIS: real Channels group
    pub/sub when Redis is configured, or a short-interval poll of BroadcastEvent when
    it isn't — see recovery/ws.py and models.BroadcastEvent for why."""

    async def connect(self):
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close(code=4401)
            return
        await self.accept()
        if settings.CHANNELS_USE_REDIS:
            await self.channel_layer.group_add(GROUP, self.channel_name)
        else:
            self._last_broadcast_id = await self._latest_broadcast_id()
            self._poll_task = asyncio.ensure_future(self._poll_loop())

    async def disconnect(self, code):
        if settings.CHANNELS_USE_REDIS:
            await self.channel_layer.group_discard(GROUP, self.channel_name)
        else:
            poll_task = getattr(self, "_poll_task", None)
            if poll_task:
                poll_task.cancel()
                try:
                    await poll_task
                except asyncio.CancelledError:
                    pass

    async def broadcast_event(self, event):
        """Channel-layer delivery path (Redis mode) — group_send lands here."""
        await self.send(text_data=json.dumps({"type": event["event_type"], "payload": event["payload"]}))

    async def _poll_loop(self):
        try:
            while True:
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                for event_type, payload, event_id in await self._new_broadcast_events():
                    await self.send(text_data=json.dumps({"type": event_type, "payload": payload}))
                    self._last_broadcast_id = event_id
        except asyncio.CancelledError:
            pass

    @database_sync_to_async
    def _latest_broadcast_id(self):
        return BroadcastEvent.objects.order_by("-id").values_list("id", flat=True).first() or 0

    @database_sync_to_async
    def _new_broadcast_events(self):
        return list(
            BroadcastEvent.objects.filter(id__gt=self._last_broadcast_id)
            .order_by("id")
            .values_list("event_type", "payload", "id")
        )
