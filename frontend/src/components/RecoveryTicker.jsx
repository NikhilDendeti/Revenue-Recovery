import Icon from "./ui/Icon";
import Panel from "./ui/Surface";
import EmptyState from "./ui/EmptyState";
import { actionLabel, inr, kindMeta, statusMeta, timeAgo, tone } from "../lib/format";

function LiveState({ connected }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-1 text-[0.625rem] font-semibold tracking-wide uppercase ${
        connected ? "border-brand/45 bg-brand-tint text-brand-ink" : "border-hairline-strong bg-surface-3 text-fg-subtle"
      }`}
    >
      <span
        aria-hidden="true"
        className={`h-1.5 w-1.5 rounded-full ${connected ? "animate-live-pulse bg-brand" : "bg-fg-faint"}`}
      />
      {connected ? "Live" : "Offline"}
    </span>
  );
}

export default function RecoveryTicker({ ticks, onSelect, connected = false }) {
  return (
    <Panel
      icon="activity"
      title="Recovery Ticker"
      caption="Transaction by transaction, as the batch replays"
      actions={<LiveState connected={connected} />}
      className="h-panel"
      bodyClassName="flex flex-col"
    >
      {!connected && ticks.length > 0 && (
        <p className="flex items-center gap-2 border-b border-hairline bg-surface-3/60 px-4 py-2 text-[0.75rem] text-fg-subtle">
          <Icon name="wifiOff" size={13} />
          Live feed disconnected — showing the events already received.
        </p>
      )}

      <div className="min-h-0 flex-1 space-y-1.5 overflow-y-auto p-2.5 sm:p-3">
        {ticks.length === 0 ? (
          <EmptyState
            size="sm"
            icon="activity"
            title={connected ? "Waiting for the first event" : "Not connected yet"}
            description={
              connected
                ? "Trigger a batch replay and every recovery decision lands here as it happens."
                : "Once the live connection is up, recovery events stream into this panel."
            }
          />
        ) : (
          ticks.map((t) => {
            const meta = statusMeta(t.outcome);
            const c = tone(meta.tone);
            const kind = kindMeta(t.kind);
            return (
              <button
                key={t._key}
                type="button"
                onClick={() => onSelect?.(t.transaction_id)}
                aria-label={`${meta.label} — ${kind.label} for ${t.customer_id}, ${inr(t.amount)} via ${actionLabel(
                  t.action_type
                )}. View reasoning chain.`}
                className="animate-tick-in group relative flex w-full items-center gap-3 overflow-hidden rounded-lg border border-hairline bg-surface-3/50 py-2.5 pr-3 pl-3.5 text-left transition-colors duration-200 ease-standard hover:border-hairline-strong hover:bg-surface-3"
              >
                <span aria-hidden="true" className={`absolute inset-y-0 left-0 w-0.5 ${c.solid}`} />

                <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${c.bg} ${c.text}`}>
                  <Icon name={meta.icon} size={14} strokeWidth={2.1} />
                </span>

                <span className="min-w-0 flex-1">
                  <span className="flex items-baseline gap-2">
                    <span className={`text-meta font-semibold ${c.text}`}>{meta.label}</span>
                    <span className="truncate text-[0.75rem] text-fg-subtle">via {actionLabel(t.action_type)}</span>
                  </span>
                  <span className="mt-0.5 flex items-center gap-1.5 text-[0.6875rem] text-fg-subtle">
                    <Icon name={kind.icon} size={11} />
                    <span className="truncate font-mono">{t.customer_id}</span>
                  </span>
                </span>

                <span className="flex shrink-0 flex-col items-end">
                  <span className={`tabular text-meta font-semibold ${c.text}`}>{inr(t.amount)}</span>
                  <span className="tabular text-[0.6875rem] text-fg-subtle">{timeAgo(t._receivedAt)}</span>
                </span>
              </button>
            );
          })
        )}
      </div>
    </Panel>
  );
}
