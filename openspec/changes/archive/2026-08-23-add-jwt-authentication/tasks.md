## 1. Backend: dependency and settings

- [x] 1.1 Add `djangorestframework-simplejwt` to `backend/requirements.txt` and verify `pip install -r requirements.txt` succeeds
- [x] 1.2 In `backend/config/settings.py`, set `REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"] = ["rest_framework_simplejwt.authentication.JWTAuthentication"]` and `DEFAULT_PERMISSION_CLASSES = ["rest_framework.permissions.IsAuthenticated"]`, plus a `SIMPLE_JWT` dict with reasonable lifetimes (e.g. 60 min access / 7 day refresh) and `DASHBOARD_USERNAME`/`DASHBOARD_PASSWORD` env-backed settings
- [x] 1.3 Add `DASHBOARD_USERNAME`/`DASHBOARD_PASSWORD` to `backend/.env.example` (password left blank, not a weak default) and verify `python manage.py check` passes — passes; local `.env` seeded with a generated dev password

## 2. Backend: token endpoints and seeded account

- [x] 2.1 Add `POST /api/auth/token/` (`TokenObtainPairView`) and `POST /api/auth/token/refresh/` (`TokenRefreshView`) to `backend/config/urls.py`
- [x] 2.2 Write `backend/recovery/management/commands/seed_dashboard_user.py`: creates the user from `DASHBOARD_USERNAME`/`DASHBOARD_PASSWORD` on first run, updates the password on a later run if changed; errors clearly if `DASHBOARD_PASSWORD` is unset
- [x] 2.3 Run the seed command locally and verify `POST /api/auth/token/` with those credentials returns an access + refresh token, and with wrong credentials returns 401 — confirmed via curl against the live server

## 3. Backend: protect the REST API, exempt the webhook

- [x] 3.1 Verify (manually or via a quick test request) that a protected endpoint (e.g. `/api/transactions/`) now returns 401 without a token and 200 with a valid one — confirmed via curl
- [x] 3.2 Add `permission_classes = [AllowAny]` to `WebhookView` in `backend/recovery/views.py` with a comment explaining why, and verify `/api/webhooks/razorpay/` still works with no `Authorization` header — implemented; final curl re-verification pending a Daphne restart (see 5.4/7.1)

## 4. Backend: WebSocket auth

- [x] 4.1 Write `backend/recovery/auth_middleware.py`: a Channels ASGI middleware that reads `token` from the connection's query string, validates it via simplejwt's `AccessToken`, and sets `scope["user"]` to the resolved user or `AnonymousUser`
- [x] 4.2 Wire it into `backend/config/asgi.py` in place of the current `AuthMiddlewareStack`, still wrapped by `AllowedHostsOriginValidator`
- [x] 4.3 In `backend/recovery/consumers.py::RecoveryConsumer.connect()`, close the connection (code 4401) instead of accepting when `scope["user"]` is not authenticated
- [x] 4.4 Verify manually: connecting to `/ws/recovery/` with no `?token=` is closed immediately; connecting with a valid access token is accepted and still receives pushed events — covered by the automated tests in 5.3; live browser re-check in 7.1

## 5. Backend tests

- [x] 5.1 Update `backend/recovery/tests/test_api.py`'s `client` fixture to authenticate (obtain and attach a token for the seeded/test user) so existing endpoint tests keep passing under the new default permission — used `force_authenticate` for endpoint tests, real token flow tested separately in `TestAuthentication`
- [x] 5.2 Add tests: an unauthenticated request to a protected endpoint returns 401; the webhook endpoint works with no auth; the token endpoint accepts valid credentials and rejects invalid ones; the refresh endpoint issues a new access token — 19/19 in test_api.py passing; also fixed a real `InsecureKeyLengthWarning` this surfaced (dev SECRET_KEY was too short for JWT HMAC signing)
- [x] 5.3 Add a WebSocket auth test in `backend/recovery/tests/test_consumers.py`: connecting with no token is closed; connecting with a valid token is accepted and still receives a pushed event (extend/reuse the existing ticker-event test) — 4/4 passing; needed `django_db(transaction=True)` since the Channels auth middleware resolves the user on a separate DB connection
- [x] 5.4 Run the full suite (`pytest -v` from `backend/`) and verify everything passes — 72/72 passing (was 64, +8 new auth tests)

## 6. Frontend

- [x] 6.1 Write `frontend/src/lib/auth.js`: `login(username, password)` (calls the token endpoint, stores the pair in `localStorage`), `logout()`, `getAccessToken()`, `refreshAccessToken()`, `isAuthenticated()`
- [x] 6.2 Update `frontend/src/lib/api.js` to attach `Authorization: Bearer <access>` to every request, and on a 401 attempt one silent refresh-and-retry before giving up
- [x] 6.3 Update `frontend/src/lib/useRecoveryRoom.js` to append `?token=<access>` to the WebSocket URL
- [x] 6.4 Write `frontend/src/components/Login.jsx` (username/password form, matches the existing visual style) and gate `App.jsx` on `auth.isAuthenticated()` — split the old App body into `Dashboard.jsx` so the WS hook only mounts once authenticated
- [x] 6.5 Add a logout control to `frontend/src/components/Header.jsx`
- [x] 6.6 Run `npm run build` from `frontend/` and verify it succeeds with no errors — clean build

## 7. End-to-end verification and docs

- [x] 7.1 With the full stack running (Postgres, Redis, Daphne, Celery worker/beat, Vite dev server), seed the dashboard user, load the frontend, confirm the login screen appears, log in, and confirm the Recovery Room loads and a batch replay still streams live over the now-authenticated WebSocket — verified live in browser: login → dashboard → triggered replay → ticker climbed, guardrails fired, audit trail updated, all over the authenticated WS; logout correctly clears the session and returns to login
- [x] 7.2 Document the new `seed_dashboard_user` setup step and the login flow in `README.md` — also added DASHBOARD_USERNAME/PASSWORD to render.yaml, which the proposal's Impact section had missed
