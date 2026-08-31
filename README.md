# RecoverAI

Autonomous revenue-recovery agent for the Razorpay AI Buildathon, Track 03. Detects
revenue at risk across four flows — payment degradation, subscription/mandate failure,
B2B receivables, and abandoned checkout — diagnoses the root cause, decides a bounded
intervention, enforces six deterministic guardrails, executes the action, tracks the
outcome through to a kept or broken promise, and logs every step to an append-only
audit trail — all watchable live on the **Recovery Room** dashboard.

## Stack

Django + DRF + Django Channels (WebSocket) + Celery + django-celery-beat on the
backend, with PostgreSQL + Redis in production and **no external services at all** in
local dev (SQLite + a filesystem-based Celery broker + a small DB-backed relay standing
in for Channels' Redis layer — see "Local dev needs nothing installed" below); a
LangGraph diagnosis→decision pipeline with a deterministic heuristic fallback; React +
Vite + Tailwind CSS v4 on the frontend, on a single cinematic dark design system with no
UI, icon, or animation dependencies.

**Nothing here needs real third-party credentials to run.** No `OPENAI_API_KEY`/
`ANTHROPIC_API_KEY` → the pipeline uses a rule-based diagnosis/decision fallback. No
`RAZORPAY_KEY_ID`/`RAZORPAY_KEY_SECRET` → every Razorpay call returns a realistic
simulated response. The full pipeline, guardrails, audit trail, and live dashboard all
work end-to-end offline. The dashboard itself does require logging in — one seeded
operator account you create locally (`seed_dashboard_user`, below), not a third-party
service.

## Prerequisites

- Python 3.11+ (tested on 3.13), Node 20+. That's it — no Docker, no database server,
  no Redis. (Optional: Postgres and/or Redis, only if you want to run against those
  instead of the local defaults — see below.)

## Run it locally

```bash
# 1. Backend
cd backend
python -m venv .venv
./.venv/Scripts/activate   # source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
cp .env.example .env
# set DASHBOARD_PASSWORD in .env before the next step — the command below refuses to
# run without one
python manage.py migrate               # creates backend/db.sqlite3
python manage.py seed_dashboard_user   # creates the one operator login the dashboard requires
python manage.py seed_data             # 68 synthetic records across all four flows
python manage.py createsuperuser       # optional, for /admin/

# 2. Run three backend processes (separate terminals)
daphne -b 127.0.0.1 -p 8000 config.asgi:application
celery -A config worker -l info --pool=solo   # --pool=solo is a Windows requirement; omit elsewhere
celery -A config beat -l info

# 3. Frontend (separate terminal)
cd frontend
npm install
npm run dev   # http://localhost:5173
```

### Local dev needs nothing installed

`DATABASE_URL`, `REDIS_URL`, and `CELERY_BROKER_URL` are all optional. Leave them
unset (the default in `.env.example`) and you get, with nothing else running:

- **Database**: a plain SQLite file (`backend/db.sqlite3`). The append-only audit-log
  guarantee (migration `0002`) is implemented natively for both SQLite and Postgres —
  it's not a Postgres-only guarantee that quietly disappears locally.
- **Celery broker**: `kombu`'s `filesystem://` transport — a local folder
  (`backend/.celery/queue`) standing in for a message broker. Staggered
  `apply_async(countdown=...)` scheduling still works (Celery implements that in the
  worker, not the broker), so a live batch replay climbs the ticker the same way it
  would against Redis.
- **Live dashboard events**: since the Celery worker (which pushes ticker/guardrail
  events) and Daphne (which serves the WebSocket) are separate processes, and an
  in-process channel layer can't bridge that, live events route through a small
  `BroadcastEvent` database table instead — `recovery/ws.py` writes to it,
  `RecoveryConsumer` polls it every ~300ms per connection. Not the audit log; purely
  transient, and never specially pruned.

Set `DATABASE_URL` and/or `REDIS_URL` (and `CELERY_BROKER_URL`) in `.env` to point at
real Postgres/Redis instead — every piece above switches to the standard
Postgres/`channels_redis`/Redis-broker path with no code change, useful for debugging
something backend-specific or mirroring production more closely. Production (Render)
always sets these, so it always takes the real Postgres/Redis path regardless of the
local default.

Open `http://localhost:5173`, log in with `DASHBOARD_USERNAME`/`DASHBOARD_PASSWORD`,
click **Trigger batch replay**, and watch the Recovery Ticker climb, the Guardrail
Console fire, and the Audit Trail populate live. Click any transaction row for its full
reasoning chain; a high-value overdue receivable (>₹40,000) gets a **🔊 trigger voice
showcase** button for the Hinglish voice moment — its promise-to-pay date lands in the
Promise Tracker, followed through to kept or broken.

### Quick smoke test without Celery

```bash
python manage.py seed_data
python manage.py replay_batch --sync   # runs the whole pipeline in-process, no worker needed
```

## Running tests

```bash
cd backend
pytest            # 186 tests: guardrails, the diagnosis/decision heuristic across all
                   # four flows, mandate-recovery sequencing, promise-to-pay tracking,
                   # the audit log's append-only DB trigger, the REST API, JWT auth
                   # (REST + WS), the WebSocket push path, the Celery task pipeline, and
                   # the backend's layer-boundary rules. Heuristic-path tests force the
                   # LLM call off (agents.pipeline.complete_json patched to None) so
                   # they're deterministic regardless of whether OPENAI_API_KEY is set in
                   # .env; a handful of exact-heuristic-output tests use the
                   # `heuristic_only` fixture instead and skip cleanly when a real key is
                   # configured.
```

Runs against whatever `DATABASE_URL`/`REDIS_URL` resolve to locally — SQLite by
default, no other service needed; pytest-django creates and drops a throwaway test
database automatically either way. One test (`test_contact_cap_race_...`) is skipped
on backends without row-level locking (SQLite) — it verifies a guarantee that only
applies where the app actually ships (Postgres, in production); see
`recovery/tests/test_guardrails.py` for why.

Everything runs fully offline except one test:
`recovery/tests/test_razorpay_client.py::TestLiveMode` makes one real call to
Razorpay's test-mode API (and cancels what it creates) — it runs automatically when
`RAZORPAY_KEY_ID`/`RAZORPAY_KEY_SECRET` are set in `.env`, and skips cleanly otherwise.
Everything else, including the rest of that same file, is mocked/simulated and never
touches the network.

## Project layout

```
backend/
  config/          settings, ASGI/WSGI, Celery app, URL root
  recovery/        models, DRF views/serializers, Channels consumer, guardrails,
                   Razorpay client, Celery tasks, seed/replay management commands.
                   Mid-migration to a layered interactor/storage/presenter/adapter
                   structure for the write path — see openspec/changes/ if you find
                   recovery/interfaces|adapters|interactors|storages|presenters/
                   only partly filled in; that's this refactor in progress, not drift.
  recovery/auth_middleware.py   Channels JWT auth middleware (WS)
  recovery/tests/  pytest suite for everything above
  agents/          the LangGraph Diagnosis -> Decision pipeline (+ heuristic fallback)
  agents/tests/    pytest suite for the pipeline heuristic
  pytest.ini, conftest.py   shared test config and fixtures
frontend/
  src/index.css       the design system — Tailwind v4 @theme tokens (colour, type,
                      radius, elevation, motion) + composite utilities. Every component
                      draws from here; no component defines its own palette.
  src/components/     Login, Dashboard, Header, MobileNav, Hero, Summary strip,
                      Search + filters, Content row (carousel), Transaction card,
                      Recovery Ticker, Guardrail Console, Promise Tracker, Audit Trail,
                      Chain dialog, Voice moment, Error boundary
  src/components/ui/  primitives — Button, Icon, Badge, Surface (Panel/Card), Skeleton,
                      EmptyState, Tooltip, Toast provider, Wordmark
  src/lib/            REST client + API base URL config, auth (JWT), WebSocket hook,
                      formatting + status descriptors, section/nav state, toast context,
                      promise-to-pay summary
render.yaml        Render Blueprint: web (Daphne) + worker + beat + Postgres + Redis
```

## What's real vs. simulated

- **Diagnosis/Decision**: a real LangGraph state machine. Reasoning is LLM-generated if
  an API key is set, otherwise a documented rule-based heuristic (`agents/pipeline.py`)
  — deliberately deterministic so the batch is reproducible during rehearsal.
- **Checkout drop-off detection**: unlike the other three flows, an abandoned checkout
  never produces a `failure_code` — nothing failed, it just never finished. Diagnosis
  instead keys off time-since-initiated, cart value, and last payment method
  (`agents/pipeline.py`). Razorpay has no "checkout abandoned" webhook; `seed_data` and
  the batch simulator model this ingestion path the same synthetic way they model the
  other three kinds.
- **Guardrails**: fully real, deterministic Python (`recovery/guardrails.py`) — never an
  LLM call. All six rules from the BRD are implemented and independently testable.
- **Audit log**: a real database-level `BEFORE UPDATE OR DELETE` trigger (migration
  `0002`, implemented natively for both SQLite and PostgreSQL) — append-only is
  enforced by the database, not just the ORM. Verified: a raw SQL `UPDATE` against
  `recovery_auditlogentry` is rejected on both backends.
- **Razorpay calls**: real HTTP calls to `api.razorpay.com` in test mode *if*
  `RAZORPAY_KEY_ID`/`SECRET` are set; otherwise a clearly-flagged simulated response
  (`recovery/razorpay_client.py`). There is no "retry a failed payment" endpoint —
  every action is a fresh payable artifact (Order re-attempt, Payment Link,
  Registration Link, Invoice reminder), matching what Razorpay's API actually exposes.
  **Seeded-data note**: `seed_data` generates synthetic `order_sim_...`/invoice IDs for
  realism; with real keys configured, the `retry_order` and `invoice_reminder` action
  paths would call Razorpay with those fake IDs and 404, since they were never created
  on Razorpay's side. The action layer handles this: a not-found (404) on those paths
  falls back to issuing a fresh Payment Link (`recovery/tasks.py::_execute_action`), so
  seeded data recovers cleanly against live keys instead of wedging the transaction. Any
  *other* API error (a transient 5xx/timeout) escalates the transaction to the human
  queue with an `action_failed` audit entry, rather than crashing the task and stranding
  it in `PROCESSING`.
- **Outcome (recovered vs. failed)**: since a batch replay has no real customer clicking
  "pay," the outcome is resolved probabilistically, weighted by diagnosis confidence
  (`recovery/tasks.py::_execute_action`) — an honest, documented synthetic-data model,
  not a claim of a real payment-capture callback.
- **Voice moment**: a simulated transcript + response, logged as a promise-to-pay. Swap
  in a real TTS/STT provider behind `recovery/tasks.py::trigger_voice_showcase` when
  ready — it's a 2-minute demo insert by design, not core infra.
- **Promise-to-pay resolution**: a promise created by the voice moment is swept
  periodically (`sweep_promises_to_pay`) once its promised date passes — kept if the
  transaction has recovered by then, otherwise broken. A broken promise routes back
  through the guardrail layer as an escalation, not a fresh nudge, so a customer who
  ghosts a commitment isn't just re-contacted by the same channel.
- **Auth**: fully real JWT (`djangorestframework-simplejwt`) on every REST endpoint and
  the WebSocket feed, backed by one seeded operator account — sized for a single-tenant
  dashboard, not a multi-user product. The Razorpay webhook endpoint is deliberately
  exempt (it's called by an external system, not a logged-in operator); real webhook
  signature verification is a separate, explicitly out-of-scope follow-up.

## Deploying

**Backend (Render)**: `render.yaml` defines the full Blueprint (web, worker, beat,
Postgres, Redis) — push to a repo connected to Render and it spins up as one unit.
Setting services up manually instead (three services pointed at the same repo,
Root Directory `backend`) works too — see the Start/Build commands in `render.yaml`.
Either way, set `DASHBOARD_USERNAME`/`DASHBOARD_PASSWORD`/`RAZORPAY_KEY_ID`/
`RAZORPAY_KEY_SECRET`/`SECRET_KEY` as env vars, and run `seed_dashboard_user` once
against the deployed database (Render's is separate from your local one) before the
login screen will accept anything.

**Frontend (Vercel or Netlify), separately** — it's never deployed alongside the
backend:

1. Import this repo, set the project **Root Directory** to `frontend`.
2. Set one build-time env var: `VITE_API_BASE_URL=https://<your-render-service>.onrender.com`
   (no trailing slash). Without this, the built frontend falls back to relative
   `/api` paths, which only work when frontend and backend share an origin — i.e.
   only in local dev, never once they're on separate domains.
3. Deploy. Note the resulting frontend URL (e.g. `https://your-app.vercel.app`).
4. Back on the Render **web** service, add that frontend URL to two separate env
   vars — both are required, they gate different things:
   - `CORS_ALLOWED_ORIGINS=https://your-app.vercel.app` (gates plain HTTP/REST requests)
   - `ALLOWED_HOSTS=.onrender.com,your-app.vercel.app` (gates the WebSocket handshake
     — Channels' origin check reads this, not `CORS_ALLOWED_ORIGINS`; CORS covers HTTP
     only, so REST can work while the WebSocket silently fails if this is missed)
