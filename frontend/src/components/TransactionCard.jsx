import Icon from "./ui/Icon";
import { StatusBadge } from "./ui/Badge";
import { inr, kindMeta, statusMeta, tone } from "../lib/format";

/* The poster card.
 *
 * The whole card is one button, so everything the desktop hover reveals is
 * also reachable with a tap or the Enter key — the reveal is emphasis, never
 * the only route to something.
 */

export default function TransactionCard({ transaction, selected = false, onSelect }) {
  const status = statusMeta(transaction.status);
  const kind = kindMeta(transaction.kind);
  const t = tone(status.tone);
  const customer = transaction.customer_name || transaction.customer_id;

  return (
    <button
      type="button"
      onClick={() => onSelect?.(transaction.id)}
      aria-current={selected ? "true" : undefined}
      aria-label={`${kind.label}: ${customer}, ${inr(transaction.amount)}, ${status.label}. View reasoning chain.`}
      className={`group relative w-60 shrink-0 snap-start overflow-hidden rounded-lg border text-left
        transition-[transform,border-color,box-shadow] duration-300 ease-out-expo
        hover:-translate-y-1 hover:shadow-lift sm:w-68
        ${selected ? "border-brand shadow-glow" : "border-hairline hover:border-hairline-strong"}`}
    >
      {/* Poster */}
      <div className={`relative h-32 overflow-hidden ${t.bg}`}>
        <span
          aria-hidden="true"
          className="absolute inset-0 bg-gradient-to-br from-transparent via-surface-2/40 to-surface-2"
        />
        <Icon
          name={kind.icon}
          size={116}
          strokeWidth={1}
          aria-hidden="true"
          className={`absolute -right-6 -bottom-7 opacity-[0.14] transition-transform duration-500 ease-out-expo group-hover:scale-110 ${t.text}`}
        />
        <span aria-hidden="true" className={`absolute inset-x-0 top-0 h-0.5 ${t.solid}`} />

        <span className="absolute top-3 left-3">
          <StatusBadge status={transaction.status} size="xs" short />
        </span>

        <p className="tabular absolute right-3.5 bottom-3 left-3.5 truncate text-h2 font-bold text-fg">
          {inr(transaction.amount)}
        </p>

        {/* Hover emphasis — a visual affordance, not a nested control. */}
        <span
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 flex items-end justify-center bg-void/55 pb-4 opacity-0
            transition-opacity duration-300 ease-standard group-hover:opacity-100 group-focus-visible:opacity-100"
        >
          <span className="flex translate-y-2 items-center gap-1.5 rounded-full bg-brand px-3.5 py-1.5 text-[0.6875rem] font-semibold text-white shadow-glow transition-transform duration-300 ease-out-expo group-hover:translate-y-0 group-focus-visible:translate-y-0">
            <Icon name="play" size={12} />
            View chain
          </span>
        </span>
      </div>

      {/* Body */}
      <div className="border-t border-hairline bg-surface-2 p-3.5">
        <p className="truncate text-meta font-semibold text-fg">{customer}</p>
        <div className="mt-2 flex items-center gap-2">
          <span className="flex min-w-0 items-center gap-1.5 text-[0.6875rem] text-fg-subtle">
            <Icon name={kind.icon} size={12} />
            <span className="truncate">{kind.short}</span>
          </span>
          {transaction.failure_code && (
            <span className="ml-auto max-w-[55%] shrink-0 truncate rounded bg-surface-3 px-1.5 py-0.5 font-mono text-[0.625rem] text-fg-subtle">
              {transaction.failure_code}
            </span>
          )}
        </div>
      </div>

      {/* In-flight indicator */}
      {transaction.status === "processing" && (
        <span aria-hidden="true" className="absolute inset-x-0 bottom-0 h-0.5 overflow-hidden bg-surface-3">
          <span className="shimmer block h-full w-full bg-info/40" />
        </span>
      )}
    </button>
  );
}
