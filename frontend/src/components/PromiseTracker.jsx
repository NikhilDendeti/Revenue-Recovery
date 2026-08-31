import { useCallback, useEffect, useState } from "react";
import Icon from "./ui/Icon";
import Panel from "./ui/Surface";
import Badge from "./ui/Badge";
import EmptyState from "./ui/EmptyState";
import Skeleton, { LoadingRegion } from "./ui/Skeleton";
import { api } from "../lib/api";
import { inr, tone } from "../lib/format";
import { summarizePromises } from "../lib/promiseSummary";

/* Panel — promise-to-pay commitments, tracked from creation (the voice channel today)
 * through resolution (kept/broken). Self-fetching, matching ChainDrawer's
 * load/retry/loading contract: every asynchronous surface gets its own loading,
 * error-with-retry, and empty state rather than silently showing nothing.
 */

const STATUS_META = {
  pending: { label: "Pending", tone: "info", icon: "clock" },
  kept: { label: "Kept", tone: "ok", icon: "check" },
  broken: { label: "Broken", tone: "danger", icon: "block" },
};

function formatPromiseDate(value) {
  if (!value) return "—";
  const d = new Date(`${value}T00:00:00`);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

function CountBadge({ toneName, icon, value }) {
  return (
    <span className={`flex items-center gap-1 ${tone(toneName).text}`}>
      <Icon name={icon} size={11} />
      {value}
    </span>
  );
}

export default function PromiseTracker() {
  const [promises, setPromises] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Fetch only — no synchronous state change, matching every other self-fetching panel
  // (ChainDrawer's `load`). `retry` is the press-driven variant that shows loading again.
  const load = useCallback(() => {
    api
      .promisesToPay()
      .then((data) => {
        setPromises(data.results ?? data);
        setError(null);
      })
      .catch(() => setError("The promise-to-pay list couldn't be loaded. The backend may be unreachable."))
      .finally(() => setLoading(false));
  }, []);

  const retry = () => {
    setLoading(true);
    setError(null);
    load();
  };

  useEffect(() => {
    load();
  }, [load]);

  const counts = summarizePromises(promises);

  return (
    <Panel
      icon="phone"
      title="Promise Tracker"
      caption="Commitments elicited during a recovery attempt, tracked through to kept or broken"
      actions={
        <span className="tabular flex items-center gap-2 font-mono text-[0.625rem] text-fg-subtle">
          <CountBadge toneName="info" icon="clock" value={counts.pending} />
          <CountBadge toneName="ok" icon="check" value={counts.kept} />
          <CountBadge toneName="danger" icon="block" value={counts.broken} />
        </span>
      }
      className="h-panel"
      bodyClassName="flex flex-col"
    >
      <div className="min-h-0 flex-1 overflow-y-auto p-2 sm:p-2.5">
        {loading && promises.length === 0 ? (
          <LoadingRegion label="Loading promise-to-pay commitments…" className="space-y-2 p-1">
            {Array.from({ length: 3 }, (_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </LoadingRegion>
        ) : error ? (
          <EmptyState
            size="sm"
            variant="error"
            title="Couldn't load promises"
            description={error}
            action="Try again"
            onAction={retry}
          />
        ) : promises.length === 0 ? (
          <EmptyState
            size="sm"
            icon="phone"
            title="No promises yet"
            description="No customer has promised a payment date yet — trigger a voice recovery to see one tracked here."
          />
        ) : (
          <ul className="space-y-1.5">
            {promises.map((p) => {
              const meta = STATUS_META[p.status] || STATUS_META.pending;
              return (
                <li
                  key={p.id}
                  className="flex items-center gap-3 rounded-md border border-hairline bg-surface-2 px-3 py-2.5"
                >
                  <div className="min-w-0 flex-1">
                    <p className="tabular text-meta font-semibold text-fg">{inr(p.promised_amount)}</p>
                    <p className="mt-0.5 truncate text-[0.6875rem] text-fg-subtle">
                      Promised for {formatPromiseDate(p.promise_date)}
                    </p>
                  </div>
                  <Badge tone={meta.tone} icon={meta.icon} size="sm" className="shrink-0">
                    {meta.label}
                  </Badge>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </Panel>
  );
}
