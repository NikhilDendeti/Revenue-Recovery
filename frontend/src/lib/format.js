export function inr(amount) {
  return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(
    Number(amount) || 0
  );
}

export function timeAgo(iso) {
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  return `${Math.floor(minutes / 60)}h ago`;
}

export const OUTCOME_STYLE = {
  recovered: { label: "Recovered", icon: "✅", cls: "text-accent-ink bg-accent-soft border-accent/40" },
  failed: { label: "Failed", icon: "❌", cls: "text-danger bg-danger-soft border-danger/40" },
  escalated: { label: "Escalated", icon: "⛔", cls: "text-danger bg-danger-soft border-danger/40" },
  held: { label: "Held", icon: "⏸", cls: "text-warn bg-warn-soft border-warn/40" },
};

export const STATUS_STYLE = {
  open: { label: "Open", cls: "text-ink-faint bg-ink-faint/10 border-line-strong" },
  processing: { label: "Processing", cls: "text-ink-soft bg-ink-soft/10 border-line-strong" },
  recovered: OUTCOME_STYLE.recovered,
  failed: OUTCOME_STYLE.failed,
  escalated: OUTCOME_STYLE.escalated,
  held: OUTCOME_STYLE.held,
};
