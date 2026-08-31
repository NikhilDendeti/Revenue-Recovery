import Icon from "./ui/Icon";
import Skeleton from "./ui/Skeleton";
import { Card } from "./ui/Surface";
import { inr, tone } from "../lib/format";

/* The KPI rail — four figures, read straight off the existing /summary/
 * payload. No field here is new; nothing extra is requested from the server.
 */

function Tile({ icon, label, value, detail, toneName = "neutral" }) {
  const t = tone(toneName);
  return (
    <Card className="relative overflow-hidden p-4 sm:p-5">
      <span aria-hidden="true" className={`absolute inset-x-0 top-0 h-px ${t.solid} opacity-60`} />
      <div className="flex items-start justify-between gap-3">
        <p className="text-caption uppercase text-fg-subtle">{label}</p>
        <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${t.bg} ${t.text}`}>
          <Icon name={icon} size={14} />
        </span>
      </div>
      <p className="tabular mt-3 text-h2 font-bold text-fg">{value}</p>
      {detail && <p className="mt-1 text-[0.75rem] leading-snug text-fg-subtle">{detail}</p>}
    </Card>
  );
}

function TileSkeleton() {
  return (
    <Card className="p-4 sm:p-5">
      <div className="flex items-start justify-between gap-3">
        <Skeleton className="h-2.5 w-24" />
        <Skeleton className="h-7 w-7" rounded="rounded-full" />
      </div>
      <Skeleton className="mt-3.5 h-6 w-28" />
      <Skeleton className="mt-2.5 h-2.5 w-32" />
    </Card>
  );
}

export default function SummaryStrip({ summary }) {
  return (
    <div className="mx-auto w-full max-w-[110rem] px-5 sm:px-8 lg:px-10">
      <div
        role={summary ? undefined : "status"}
        aria-busy={summary ? undefined : "true"}
        className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4"
      >
        {summary ? (
          <>
            <Tile
              icon="trendingUp"
              toneName="ok"
              label="Recovered"
              value={inr(summary.recovered_total)}
              detail={`${summary.recovered_count} transaction${summary.recovered_count === 1 ? "" : "s"} closed`}
            />
            <Tile
              icon="wallet"
              toneName="info"
              label="At risk"
              value={inr(summary.at_risk_total)}
              detail={`${summary.total_count} detected in this batch`}
            />
            <Tile
              icon="target"
              toneName="brand"
              label="Recovery rate"
              value={`${summary.recovery_rate}%`}
              detail={`${summary.processed_count} processed so far`}
            />
            <Tile
              icon="alert"
              toneName={summary.escalated_count + summary.held_count + summary.failed_count > 0 ? "alert" : "neutral"}
              label="Escalated · Held · Failed"
              value={`${summary.escalated_count} · ${summary.held_count} · ${summary.failed_count}`}
              detail="Escalated to a human, held by a guardrail, or not recovered"
            />
          </>
        ) : (
          <>
            <span className="sr-only">Loading recovery summary…</span>
            {Array.from({ length: 4 }, (_, i) => (
              <TileSkeleton key={i} />
            ))}
          </>
        )}
      </div>
    </div>
  );
}
