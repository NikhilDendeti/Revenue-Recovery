import { inr } from "../lib/format";

function Tile({ label, value, accent }) {
  return (
    <div className="rounded-lg border border-line bg-paper-raised px-5 py-4">
      <p className="font-sans text-[11px] uppercase tracking-wide text-ink-faint">{label}</p>
      <p className={`mt-1 font-mono text-2xl font-semibold tabular-nums ${accent || "text-ink"}`}>{value}</p>
    </div>
  );
}

export default function SummaryStrip({ summary }) {
  if (!summary) {
    return <div className="px-6 py-4 font-mono text-sm text-ink-faint sm:px-10">Loading summary…</div>;
  }
  return (
    <div className="grid grid-cols-2 gap-3 px-6 py-5 sm:grid-cols-4 sm:px-10">
      <Tile label="Recovered" value={inr(summary.recovered_total)} accent="text-accent-ink" />
      <Tile label="At risk (batch total)" value={inr(summary.at_risk_total)} />
      <Tile label="Recovery rate" value={`${summary.recovery_rate}%`} />
      <Tile
        label={`Escalated · Held · Failed`}
        value={`${summary.escalated_count} · ${summary.held_count} · ${summary.failed_count}`}
        accent="text-warn"
      />
    </div>
  );
}
