## Why

Every REST endpoint and the WebSocket feed are currently wide open — no credential is
required to read the transaction list, the full audit trail (customer IDs, reasoning,
Razorpay responses), or trigger a batch replay / voice showcase. That's an acceptable
local-dev posture but a real gap the moment this gets a public Render URL, which the
project's own `render.yaml` and README deployment section already anticipate. This
change closes it with JWT auth, sized for what this app actually is — a single-tenant
operator dashboard, not a multi-user product — rather than building out full user
registration.

## What Changes

- Add `djangorestframework-simplejwt`; every REST endpoint requires a valid JWT by
  default (`IsAuthenticated`), obtained via `POST /api/auth/token/` and refreshed via
  `POST /api/auth/token/refresh/`. **BREAKING**: existing anonymous API access stops
  working — the frontend and any external client must authenticate.
- Exception: `POST /api/webhooks/razorpay/` stays open (`AllowAny`) — it's called by
  an external system (Razorpay / the batch simulator), not a logged-in dashboard user,
  and JWT is the wrong mechanism for it. (Verifying Razorpay's own webhook signature
  is the correct mechanism there and is explicitly out of scope for this change.)
- The WebSocket endpoint (`/ws/recovery/`) now requires the same JWT, passed as a
  `?token=` query parameter (browsers can't set custom headers on a native WebSocket
  handshake) and validated by a new Channels auth middleware; an unauthenticated or
  invalid token gets the connection closed rather than accepted.
- One seedable operator account, not user registration: a management command
  (`seed_dashboard_user`) creates/updates a single Django user from
  `DASHBOARD_USERNAME`/`DASHBOARD_PASSWORD` env vars.
- Frontend gains a minimal login screen (username/password → stores the JWT pair in
  `localStorage`), attaches `Authorization: Bearer <access>` to every API call with
  refresh-on-401, and appends the access token to the WebSocket URL.

## Capabilities

### New Capabilities
- `dashboard-authentication`: JWT-based access control for the REST API and the
  WebSocket feed, backed by a single seeded operator account.

### Modified Capabilities
(none — no existing capability has a baseline spec covering "who can call the API,"
so this is additive)

## Impact

- New backend dependency: `djangorestframework-simplejwt`.
- `backend/config/settings.py`: REST_FRAMEWORK auth/permission defaults, `SIMPLE_JWT`
  config, new `DASHBOARD_USERNAME`/`DASHBOARD_PASSWORD` env vars.
- `backend/config/urls.py`: two new auth endpoints.
- `backend/recovery/views.py`: `WebhookView` explicitly opted back out of the new
  default permission.
- New: `backend/recovery/auth_middleware.py` (Channels JWT middleware),
  `backend/recovery/management/commands/seed_dashboard_user.py`.
- `backend/config/asgi.py`, `backend/recovery/consumers.py`: WS auth wiring.
- `frontend/src/lib/auth.js` (new), `frontend/src/lib/api.js`,
  `frontend/src/lib/useRecoveryRoom.js`, `frontend/src/App.jsx`,
  `frontend/src/components/Login.jsx` (new), `frontend/src/components/Header.jsx`
  (logout).
- `backend/.env.example`, `README.md`: document the new setup step.
