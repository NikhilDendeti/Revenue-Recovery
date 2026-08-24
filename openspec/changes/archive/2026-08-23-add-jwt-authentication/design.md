## Context

See proposal.md - Why. Today: no `INSTALLED_APPS` entry or settings touch auth at all;
`REST_FRAMEWORK` has no `DEFAULT_AUTHENTICATION_CLASSES`/`DEFAULT_PERMISSION_CLASSES`
(DRF defaults to `AllowAny`); Channels' `AllowedHostsOriginValidator` is the *only*
gate on the WebSocket, and it checks origin, not identity. The React app has no auth
state at all — every `fetch` and the `WebSocket` constructor call are unauthenticated.

## Goals / Non-Goals

**Goals**: require a valid credential for every REST read/write and for the WS feed;
keep the webhook path open (it's not a browser session); keep setup scriptable (no
manual admin-panel account creation); keep the frontend's UX close to what it is today
— one login screen, then the same dashboard.

**Non-Goals**: multi-user accounts, roles/permissions beyond "authenticated or not",
password reset flows, Razorpay webhook signature verification (a separate, real
follow-up — noted in proposal.md as explicitly out of scope), mid-connection WS token
refresh (a WS connection accepted at connect time stays open even if the access token
subsequently expires — acceptable for an operator dashboard where a stale live feed on
an already-open tab is a minor inconvenience, not a security exposure, since the
connection was authenticated when it was established).

## Decisions

**`djangorestframework-simplejwt`, not Django's session auth or a hand-rolled token
scheme.** It's the standard DRF-ecosystem choice, needs no CSRF dance across the
frontend's separate origin (unlike session cookies), and its `AccessToken` class is
directly reusable for the Channels middleware below — one token format, two transports.

**One seeded operator account via a management command, not a registration/signup
flow.** This is a single-operator dashboard (see proposal.md - Why); building
multi-user registration would be solving a problem this app doesn't have. The seed
command is idempotent (`update_or_create`-style: creates on first run, updates the
password on a later run with a changed `DASHBOARD_PASSWORD`) so it's safe to re-run in
any environment, including on every deploy.

**WS auth via a `?token=` query parameter and a custom Channels middleware, not
Channels' session-based `AuthMiddlewareStack`.** The browser `WebSocket` constructor
cannot set an `Authorization` header, and the app has no session/cookie auth to hang
`AuthMiddlewareStack` off in the first place. The new `JWTAuthMiddleware` parses the
query string, validates the token via simplejwt's `AccessToken` (same validation path
DRF's `JWTAuthentication` uses), and sets `scope["user"]`; `RecoveryConsumer.connect()`
closes the connection (code 4401) if that resolves to `AnonymousUser`. Token-in-URL is
a known trade-off (query strings can end up in server logs) — acceptable here since
the token is short-lived and this is a local/single-operator deployment, not handling
third-party credentials; noted for anyone hardening this further.

**Frontend: a login gate in `App.jsx`, not a router.** The app is a single dashboard
page — there's nothing to route to. `App.jsx` renders `<Login>` when
`auth.isAuthenticated()` is false and the dashboard otherwise; `api.js` centralizes
the `Authorization` header and a single refresh-on-401 retry (one retry, then force
re-login on a second 401 — avoids a refresh-retry loop if the refresh token itself has
expired).

## Risks / Trade-offs

- [Existing anonymous API/WS access breaks for anyone with the old frontend build or a
  saved bookmark/script] → intentional and stated as **BREAKING** in the proposal;
  this is exactly the gap being closed.
- [Token-in-query-string for WS can appear in access logs] → see the WS-auth decision
  above; mitigated by short access-token lifetime, not eliminated.
- [Single shared operator account means no per-action attribution beyond what the
  audit log already records via `actor=agent|system|human`] → unchanged from today;
  out of scope to add per-user attribution for a single-operator app.

## Migration Plan

1. Backend: install dependency, add settings/urls/middleware, ship the seed command.
2. Run `python manage.py seed_dashboard_user` once per environment (local, and again
   after deploying, since Render's database is separate from the local one) — document
   in README as a required setup step, alongside `migrate` and `seed_data`.
3. Frontend: ship the login screen and authenticated API/WS clients in the same
   change, so there's no window where the backend requires auth but the frontend
   doesn't send it.

No data migration — this only adds Django's built-in `auth_user`/token tables (already
present via `django.contrib.auth`, already in `INSTALLED_APPS`) and one new user row.

## Open Questions

None.
