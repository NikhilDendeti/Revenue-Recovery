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
