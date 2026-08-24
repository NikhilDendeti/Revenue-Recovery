import { inr, STATUS_STYLE } from "../lib/format";

const KIND_LABEL = {
  payment_degradation: "Payment degradation",
  subscription_failure: "Subscription failure",
  receivable: "B2B receivable",
};

export default function AuditTrail({ transactions, selectedId, onSelect }) {
  return (
    <section className="rounded-lg border border-line bg-paper-raised">
      <header className="border-b border-line px-5 py-3">
        <h2 className="font-serif text-lg font-semibold text-ink">Audit Trail</h2>
        <p className="font-mono text-[11px] text-ink-faint">
          Panel 3 · click any transaction — judges can pick any one themselves
        </p>
      </header>
      <div className="max-h-[420px] overflow-auto">
        <table className="w-full min-w-[640px] border-collapse text-sm">
          <thead className="sticky top-0 bg-paper-raised">
            <tr className="border-b border-line-strong text-left font-sans text-[11px] uppercase tracking-wide text-ink-faint">
              <th className="px-4 py-2">Flow</th>
              <th className="px-4 py-2">Customer</th>
              <th className="px-4 py-2 text-right">Amount</th>
              <th className="px-4 py-2">Status</th>
            </tr>
          </thead>
          <tbody>
            {transactions.map((t) => {
              const status = STATUS_STYLE[t.status] || STATUS_STYLE.open;
              return (
                <tr
                  key={t.id}
                  tabIndex={0}
                  role="button"
                  aria-label={`View reasoning chain for ${t.customer_name || t.customer_id}, ${inr(t.amount)}`}
                  onClick={() => onSelect(t.id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      onSelect(t.id);
                    }
                  }}
                  className={`cursor-pointer border-b border-line font-sans text-ink-soft transition outline-none hover:bg-white/5 focus-visible:bg-white/5 focus-visible:ring-1 focus-visible:ring-accent ${
                    selectedId === t.id ? "bg-accent-soft" : ""
                  }`}
                >
                  <td className="px-4 py-2">{KIND_LABEL[t.kind]}</td>
                  <td className="px-4 py-2">{t.customer_name || t.customer_id}</td>
                  <td className="px-4 py-2 text-right font-mono tabular-nums">{inr(t.amount)}</td>
                  <td className="px-4 py-2">
                    <span className={`rounded-full border px-2 py-0.5 font-mono text-[11px] ${status.cls}`}>
                      {status.label}
                    </span>
                  </td>
                </tr>
              );
            })}
            {transactions.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-6 text-center font-mono text-xs text-ink-faint">
                  No transactions yet — seed the demo dataset on the backend first.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
