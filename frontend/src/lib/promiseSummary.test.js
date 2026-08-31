// Uses Node's built-in test runner (node:test / node:assert) — no test framework
// (vitest/jest/@testing-library) exists anywhere in this repo yet, so this covers the
// PromiseTracker panel's counting logic (extracted into promiseSummary.js precisely so
// it's testable without a JSX-capable DOM test runner) without introducing one.
// Run with: node --test src/lib/promiseSummary.test.js

import assert from "node:assert/strict";
import { test } from "node:test";

import { summarizePromises } from "./promiseSummary.js";

test("summarizePromises counts pending, kept, and broken correctly", () => {
  const promises = [
    { id: 1, status: "pending" },
    { id: 2, status: "kept" },
    { id: 3, status: "kept" },
    { id: 4, status: "broken" },
  ];

  const counts = summarizePromises(promises);

  assert.deepEqual(counts, { pending: 1, kept: 2, broken: 1, total: 4 });
});

test("summarizePromises returns all-zero counts for an empty list (the empty-state case)", () => {
  const counts = summarizePromises([]);

  assert.deepEqual(counts, { pending: 0, kept: 0, broken: 0, total: 0 });
  assert.equal(counts.total, 0);
});

test("summarizePromises tolerates a missing/non-array input", () => {
  assert.deepEqual(summarizePromises(undefined), { pending: 0, kept: 0, broken: 0, total: 0 });
});

test("summarizePromises ignores an entry with an unrecognized status rather than throwing", () => {
  const counts = summarizePromises([{ id: 1, status: "unknown" }, { id: 2, status: "kept" }]);

  assert.deepEqual(counts, { pending: 0, kept: 1, broken: 0, total: 2 });
});
