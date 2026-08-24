import { inr, timeAgo, OUTCOME_STYLE } from "../lib/format";

export default function RecoveryTicker({ ticks, onSelect }) {
  return (
    <section className="flex h-[520px] flex-col rounded-lg border border-line bg-paper-raised">
      <header className="border-b border-line px-5 py-3">
        <h2 className="font-serif text-lg font-semibold text-ink">Recovery Ticker</h2>
        <p className="font-mono text-[11px] text-ink-faint">Panel 1 · transaction-by-transaction, as the batch replays</p>
      </header>
      <div className="flex-1 space-y-1.5 overflow-y-auto p-3">
        {ticks.length === 0 && (
          <p className="p-4 font-mono text-xs text-ink-faint">
            Nothing yet — trigger a batch replay to watch it climb.
          </p>
        )}
        {ticks.map((t) => {
          const style = OUTCOME_STYLE[t.outcome] || OUTCOME_STYLE.held;
          return (
            <button
              key={t._key}
              onClick={() => onSelect?.(t.transaction_id)}
              className={`animate-tick-in flex w-full items-center justify-between gap-3 rounded-md border px-3 py-2 text-left text-sm transition hover:brightness-110 ${style.cls}`}
            >
              <span className="flex items-center gap-2 truncate">
                <span aria-hidden="true">{style.icon}</span>
                <span className="truncate font-sans">
                  {style.label} via {t.action_type || "—"}
                </span>
              </span>
              <span className="flex shrink-0 items-center gap-3 font-mono text-xs tabular-nums text-ink-faint">
                <span className={style.cls.split(" ")[0]}>{inr(t.amount)}</span>
                <span>{timeAgo(t._receivedAt)}</span>
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
