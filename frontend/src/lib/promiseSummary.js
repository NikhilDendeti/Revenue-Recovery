/* Pure summarization of a promise-to-pay list, pulled out of PromiseTracker.jsx so the
 * counting logic (and the "no promises yet" condition it implies) can be unit-tested
 * without a DOM/JSX test runner — see promiseSummary.test.js. */

export function summarizePromises(promises) {
  const list = Array.isArray(promises) ? promises : [];
  const counts = { pending: 0, kept: 0, broken: 0 };
  for (const p of list) {
    if (p && Object.prototype.hasOwnProperty.call(counts, p.status)) {
      counts[p.status] += 1;
    }
  }
  return { ...counts, total: list.length };
}
