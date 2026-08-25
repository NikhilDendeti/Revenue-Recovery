## 1. Structured not-found signal from the Razorpay client

- [x] 1.1 Give `RazorpayError` a `status_code` attribute populated in `razorpay_client._post` from the HTTP response, and add an `is_not_found(err)` helper (True when `status_code == 404`). Verify: a unit test where a mocked 404 response raises `RazorpayError` with `status_code == 404` and `is_not_found()` returns True.

## 2. Action-layer failure handling in `_execute_action`

- [x] 2.1 Wrap the `_call_razorpay` call; on a non-not-found `RazorpayError`, resolve the transaction to `ESCALATED`, append a distinct `action_failed` audit entry (failing action + error detail), and push an `escalated` ticker event. Verify: a test forcing a 5xx `RazorpayError` leaves the transaction `ESCALATED` (never `PROCESSING`), with a new `action_failed` audit row and a ticker push (spec: API-failure escalation recorded distinctly; non-not-found error does not trigger fallback).
- [x] 2.2 On a not-found `RazorpayError` for `retry_order` / `invoice_reminder`, fall back to `create_payment_link`, note the artifact substitution in the audit payload, and continue to the normal recovered/failed outcome. Verify: tests forcing a 404 on each of `retry_order` and `invoice_reminder` show a fresh payment link issued and a recovered-or-failed (not escalated) outcome (spec: not-found falls back to a fresh artifact).
- [x] 2.3 If the fallback `create_payment_link` call itself raises, escalate instead. Verify: a test where both the original call and the fallback raise leaves the transaction `ESCALATED`, not `PROCESSING`.

## 3. Pipeline-task safety net (never stuck in `PROCESSING`)

- [x] 3.1 Wrap the body of `process_transaction_event` so any otherwise-unhandled exception moves the transaction out of `PROCESSING` to `ESCALATED` with an audit entry. Verify: a test that makes the pipeline raise (e.g. patch `run_pipeline` to throw) ends the transaction `ESCALATED`, not `PROCESSING` (spec: unexpected error still resolves the transaction).
- [x] 3.2 Apply the same guard to `dispatch_scheduled_action`. Verify: a test where the dispatched execution raises ends the transaction `ESCALATED`, not left mid-execution (spec: unexpected error still resolves the transaction).

## 4. Regression and documentation

- [x] 4.1 Run the full backend suite (`pytest`). Verify: every previously-passing test still passes and the one SQLite-skipped test remains the only skip — confirming simulated (no-keys) mode behavior is byte-for-byte unchanged.
- [x] 4.2 Update the known-gap wording in `README.md` ("What's real vs. simulated") and `CLAUDE.md` (the architectural-invariant note) to reflect that a stale/404 order or invoice id now falls back to a fresh payment link rather than wedging the transaction. Verify: neither file still describes an unfixed 404 wedge as a live known gap.
