import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { inr, STATUS_STYLE } from "../lib/format";

const ACTOR_ICON = { agent: "🤖", system: "⚙️", human: "🧑" };

export default function ChainDrawer({ transactionId, onClose, onVoiceShowcase }) {
  const [chain, setChain] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!transactionId) return;
    setLoading(true);
    api
      .transactionChain(transactionId)
      .then(setChain)
      .finally(() => setLoading(false));
  }, [transactionId]);

  if (!transactionId) return null;
  const status = chain ? STATUS_STYLE[chain.status] || STATUS_STYLE.open : null;
  const isHighValueReceivable = chain?.kind === "receivable" && Number(chain.amount) > 40000;

  return (
    <div className="fixed inset-0 z-30 flex justify-end bg-black/50" onClick={onClose}>
      <aside
        onClick={(e) => e.stopPropagation()}
        className="h-full w-full max-w-lg overflow-y-auto border-l border-line-strong bg-paper-raised p-6"
      >
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <p className="font-mono text-[11px] text-ink-faint">TXN · {transactionId.slice(0, 8)}</p>
            <h3 className="font-serif text-xl font-semibold text-ink">{chain ? inr(chain.amount) : "…"}</h3>
          </div>
          <button onClick={onClose} className="font-mono text-xs text-ink-faint hover:text-ink">
            close ✕
          </button>
        </div>

        {loading && <p className="font-mono text-xs text-ink-faint">Loading reasoning chain…</p>}

        {chain && (
          <>
            <div className="mb-5 flex items-center gap-2">
              <span className={`rounded-full border px-2 py-0.5 font-mono text-[11px] ${status.cls}`}>{status.label}</span>
              <span className="font-mono text-[11px] text-ink-faint">{chain.customer_name || chain.customer_id}</span>
              {isHighValueReceivable && onVoiceShowcase && (
                <button
                  onClick={() => onVoiceShowcase(transactionId)}
                  className="ml-auto rounded border border-accent px-2 py-1 font-mono text-[11px] text-accent-ink hover:bg-accent-soft"
                >
                  🔊 trigger voice showcase
                </button>
              )}
            </div>

            <ol className="space-y-3 border-l border-line-strong pl-4">
              {chain.audit_entries
                .slice()
                .reverse()
                .map((entry) => (
                  <li key={entry.id} className="relative">
                    <span className="absolute -left-[21px] top-1 h-2 w-2 rounded-full bg-accent" />
                    <p className="font-mono text-[11px] uppercase tracking-wide text-ink-faint">
                      {ACTOR_ICON[entry.actor]} {entry.event_type.replace(/_/g, " ")}
                    </p>
                    <pre className="mt-1 overflow-x-auto rounded bg-console p-2 font-mono text-[11px] text-ink-soft">
{JSON.stringify(entry.payload, null, 2)}
                    </pre>
                  </li>
                ))}
            </ol>
          </>
        )}
      </aside>
    </div>
  );
}
