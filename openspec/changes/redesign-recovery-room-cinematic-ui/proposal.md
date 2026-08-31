## Why

The Recovery Room dashboard is the product's whole demo surface — a judge watches this
screen, not the Celery logs — but its UI is a thin, unstyled scaffold: a muted green/paper
palette left over from an early draft, three stacked panels labelled "Panel 1 / Panel 2 /
Panel 3", no hero, no search, no filters, no loading or error states, and a mobile
experience that is the desktop layout squeezed down. Concretely, today:

- **There is no design system.** Colours, radii, shadows, and spacing are ad-hoc Tailwind
  utilities repeated per component; two panels are hard-coded to `h-[520px]` regardless of
  viewport, so on a short laptop the page scrolls twice and on mobile the panels dominate.
- **The Audit Trail table sets `min-w-[640px]`** inside an `overflow-auto` div — on a phone
  the primary data surface is a horizontally-scrolling table, which is the single worst
  responsive defect in the app.
- **The reasoning chain is under-served.** `GET /transactions/:id/chain/` already returns
  `diagnoses`, `decisions`, `actions`, `guardrail_events`, and `scheduled_actions`, and the
  drawer renders **only** `audit_entries` as raw `JSON.stringify` dumps. The single most
  important story the product tells — *why* the agent did what it did — is presented as a
  wall of JSON.
- **Failures are invisible.** `Dashboard`, `useRecoveryRoom`, and the voice-showcase call
  all swallow errors with `.catch(() => {})`. A backend that is down looks identical to a
  backend with no data. There are no skeletons either, so first paint is a blank frame.
- **Accessibility is partial.** The Audit Trail rows have focus handling, but the drawer is
  a `div` with a click-to-close backdrop — no dialog role, no focus trap, no Escape — the
  ticker/console rows have no accessible names, there is no skip link, and status is
  communicated by colour plus an emoji rather than a durable text label.
- **Leftover template assets** (`public/icons.svg` with Bluesky/Discord/GitHub logos,
  a purple Vite favicon) still ship, and `index.html` loads a serif display face that the
  UI never justifies.

## What Changes

Replace the ad-hoc styling with a **single cinematic dark design system** and rebuild every
screen and component on top of it. The visual direction is streaming-platform grade —
near-black grounds, charcoal elevation tiers, a strategically-used red accent, cinematic
gradient overlays, poster-style cards, and disciplined typography — applied to *this*
product's domain rather than copying a media catalogue.

- **Design system** (`src/index.css`): one token layer for colour, elevation, typography
  scale, radii, shadows, motion, and breakpoints, exposed as Tailwind v4 `@theme` tokens so
  every component draws from the same source. Brand red is reserved for primary actions,
  active navigation, and the live indicator; **transaction status keeps its own
  semantically-distinct palette** so a recovery outcome is never confused with a CTA.
- **Component primitives** (`src/components/ui/`): `Button`, `Badge`, `Card`, `Skeleton`,
  `EmptyState`, `Tooltip`, `IconButton`, `Icon`, and a `Toast` provider — so buttons, pills,
  and surfaces stop being re-invented per screen.
- **Navigation**: a sticky header that is transparent over the hero and solidifies on
  scroll, with a wordmark, section navigation with an active red indicator, an expanding
  search field, a live/disconnected status pill, the primary replay CTA, and an operator
  menu. **A separate bottom navigation bar for touch viewports**, with full-size touch
  targets and safe-area padding — not the desktop header scaled down.
- **Hero**: a cinematic billboard leading with recovered value, batch context, a recovery-
  rate meter, a primary red CTA (trigger batch replay) and a secondary outline CTA.
- **Content rows**: transactions are grouped into horizontally-scrollable rows by
  operational state (needs attention / in flight / at risk / recovered), rendered as
  poster-style cards with a desktop hover reveal, keyboard and chevron scrolling, scroll
  snapping, and edge fades — the streaming "row" pattern mapped onto recovery triage.
- **Search & filters**: client-side search across customer, id, and failure code, plus flow
  and status filter chips. **No new API calls and no query-parameter changes.**
- **Live panels**: the Recovery Ticker and Guardrail Console are rebuilt on the design
  system with outcome colour rails, accessible names, and fluid heights instead of a fixed
  `520px`.
- **Audit Trail**: a premium data table on desktop that **becomes a stacked card list below
  the table breakpoint**, removing the horizontal-scroll defect.
- **Reasoning-chain detail**: the drawer becomes a proper modal dialog (role, labelled,
  focus-trapped, Escape-closable, scroll-locked) with a tabbed view that finally surfaces
  the diagnosis, decision, actions, guardrail events, and scheduled actions the API already
  returns, alongside a readable timeline with collapsible payloads.
- **States**: skeleton loaders for the hero, KPI rail, rows, table, and drawer; designed
  empty states per surface; and **visible error surfacing** — the swallowed `.catch(() => {})`
  paths raise a toast and an inline retry affordance instead of failing silently.
- **Motion & accessibility**: standardised transitions, hover/focus/active/disabled states
  on every interactive element, a visible red focus ring, a skip link, semantic landmarks,
  status conveyed by icon **and** text label, and a global `prefers-reduced-motion` opt-out.
- **Assets**: replace the leftover Vite template `icons.svg`/`favicon.svg` with an on-brand
  inline icon set and favicon, and swap the unused serif face for a single display/body sans.

## Capabilities

### New Capabilities
- `recovery-room-ui`: The presentation and interaction contract for the Recovery Room
  operator dashboard — its design system, navigation model, live panels, transaction
  browsing, reasoning-chain detail view, loading/empty/error states, responsive behaviour,
  and accessibility guarantees.

### Modified Capabilities
<!-- None. `dashboard-authentication` keeps its existing requirements: the login screen is
     restyled, but its behaviour (token storage, refresh, session-expiry handling) is
     untouched. -->

## Impact

- **Code**: `frontend/index.html`, `frontend/src/index.css`, every file under
  `frontend/src/components/`, `frontend/src/lib/format.js`, plus new
  `frontend/src/components/ui/*` (primitives + `ToastProvider`),
  `frontend/src/lib/toastContext.js`, `frontend/src/lib/sections.js`, and
  `frontend/src/lib/useNavState.js`. `frontend/public/` template assets replaced.
  Responsive branching is CSS-only — no JS media-query hook was needed.
- **Not touched**: the entire `backend/`. No REST endpoint, WebSocket message type, payload
  field, migration, or Celery task changes. `src/lib/api.js`, `src/lib/auth.js`, and
  `src/lib/config.js` keep their current contracts; `useRecoveryRoom` keeps its return
  shape and WebSocket behaviour, gaining only error state alongside it.
- **Behaviour preserved**: JWT login/refresh/session-expiry, the WebSocket ticker/guardrail/
  voice feed, batch replay, the voice showcase trigger, chain fetch-on-select, and the
  `MAX_FEED` buffer all keep working exactly as they do now.
- **Dependencies**: **none added.** The redesign is Tailwind v4 tokens, hand-authored SVG
  icons, and CSS — no icon package, no animation library, no component kit.
- **Risk**: presentation-layer only; rollback is a plain revert of `frontend/`.
