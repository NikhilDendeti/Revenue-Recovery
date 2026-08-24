"""JWT auth for the WebSocket connection.

Channels' own AuthMiddlewareStack is session/cookie based, and this app has no
session auth at all — the browser's native WebSocket constructor can't set an
Authorization header either. So the access token travels as a `?token=` query
parameter and gets validated here, on connect, using the same simplejwt AccessToken
class DRF's JWTAuthentication uses for the REST API — one token format, two
transports. See openspec/changes/add-jwt-authentication/design.md for the trade-offs
(token-in-URL, no mid-connection refresh) this accepts.
"""

from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken


@database_sync_to_async
def _resolve_user(token_str):
    from django.contrib.auth import get_user_model

    try:
        validated = AccessToken(token_str)
        user_id = validated["user_id"]
    except TokenError:
        return AnonymousUser()

    try:
        return get_user_model().objects.get(pk=user_id)
    except get_user_model().DoesNotExist:
        return AnonymousUser()


class JWTAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        query_string = scope.get("query_string", b"").decode()
        token = parse_qs(query_string).get("token", [None])[0]
        scope["user"] = await _resolve_user(token) if token else AnonymousUser()
        return await super().__call__(scope, receive, send)
