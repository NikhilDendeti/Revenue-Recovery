import Button from "./ui/Button";
import Icon from "./ui/Icon";
import Skeleton from "./ui/Skeleton";
import { inr, inrCompact } from "../lib/format";
import { scrollToSection } from "../lib/useNavState";

/* The billboard.
 *
 * Leads with the one number an operator wants first (value recovered) and the
 * one action they take (replay the batch). Everything else on this surface is
 * context for those two things.
 */

function Stat({ icon, label, value, tone = "text-fg" }) {
  return (
    <div className="flex items-center gap-2.5">
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-hairline bg-surface-2/80 text-fg-subtle">
        <Icon name={icon} size={15} />
      </span>
      <span className="min-w-0">
        <span className="block text-caption uppercase text-fg-subtle">{label}</span>
        <span className={`tabular block text-meta font-semibold ${tone}`}>{value}</span>
      </span>
    </div>
  );
}

export default function Hero({ summary, connected, replaying, onReplay }) {
  const rate = summary ? Math.max(0, Math.min(100, Number(summary.recovery_rate) || 0)) : 0;
  const attention = summary ? summary.escalated_count + summary.held_count + summary.failed_count : 0;

  return (
    <section
      id="overview"
      data-section
      aria-labelledby="hero-heading"
      className="cine-bg grain relative isolate overflow-hidden"
    >
      <div aria-hidden="true" className="scrim-b pointer-events-none absolute inset-0" />
      <div aria-hidden="true" className="scrim-l pointer-events-none absolute inset-0 hidden lg:block" />

      <div className="relative mx-auto flex min-h-[clamp(28rem,70vh,42rem)] w-full max-w-[110rem] flex-col justify-end px-5 pt-28 pb-10 sm:px-8 sm:pt-32 lg:px-10 lg:pb-14">
        <div className="max-w-3xl">
          {/* Live state + batch context */}
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
            <span
              className={`inline-flex items-center gap-2 rounded-full border px-2.5 py-1 text-caption uppercase ${
                connected ? "border-brand/45 bg-brand-tint text-brand-ink" : "border-hairline-strong bg-surface-2 text-fg-subtle"
              }`}
            >
              <span
                aria-hidden="true"
                className={`h-1.5 w-1.5 rounded-full ${connected ? "animate-live-pulse bg-brand" : "bg-fg-faint"}`}
              />
              {connected ? "Live" : "Offline"}
            </span>
            <span className="text-caption uppercase text-fg-subtle">Recovery Room · batch in progress</span>
          </div>

          <h1 id="hero-heading" className="sr-only">
            Recovery Room overview
          </h1>

          {/* The headline figure */}
          <p className="mt-5 text-caption uppercase text-fg-subtle">Revenue recovered</p>
          {summary ? (
            <p className="tabular mt-1.5 text-display text-fg">{inrCompact(summary.recovered_total)}</p>
          ) : (
            <Skeleton className="mt-2 h-[clamp(2.5rem,7vw,4.25rem)] w-[min(20rem,80%)]" rounded="rounded-lg" />
          )}
          {summary ? (
            <p className="tabular mt-1 font-mono text-meta text-fg-subtle">
              {inr(summary.recovered_total)} across {summary.recovered_count} of {summary.processed_count} processed
            </p>
          ) : (
            <Skeleton className="mt-2 h-4 w-64" />
          )}

          {/* Recovery-rate meter */}
          <div className="mt-7 max-w-md">
            <div className="mb-2 flex items-baseline justify-between gap-3">
              <span className="text-caption uppercase text-fg-subtle">Recovery rate</span>
              <span className="tabular text-meta font-semibold text-ok-ink">{summary ? `${summary.recovery_rate}%` : "—"}</span>
            </div>
            <div
              role="progressbar"
              aria-valuenow={summary ? rate : undefined}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label="Recovery rate"
              className="h-1.5 w-full overflow-hidden rounded-full bg-surface-3"
            >
              <div
                className="h-full rounded-full bg-gradient-to-r from-ok/70 to-ok transition-[width] duration-700 ease-out-expo"
                style={{ width: `${rate}%` }}
              />
            </div>
          </div>

          {/* Actions */}
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Button size="lg" icon={replaying ? undefined : "play"} loading={replaying} onClick={onReplay}>
              {replaying ? "Replaying batch…" : "Trigger batch replay"}
            </Button>
            <Button size="lg" variant="secondary" icon="list" onClick={() => scrollToSection("audit")}>
              Open audit trail
            </Button>
          </div>

          {/* Supporting figures */}
          <div className="mt-9 flex flex-wrap gap-x-8 gap-y-4">
            {summary ? (
              <>
                <Stat icon="wallet" label="At risk (batch)" value={inr(summary.at_risk_total)} />
                <Stat icon="layers" label="Transactions" value={`${summary.total_count} detected`} />
                <Stat
                  icon="alert"
                  label="Needs attention"
                  value={`${attention} open item${attention === 1 ? "" : "s"}`}
                  tone={attention > 0 ? "text-alert-ink" : "text-fg"}
                />
              </>
            ) : (
              Array.from({ length: 3 }, (_, i) => (
                <div key={i} className="flex items-center gap-2.5">
                  <Skeleton className="h-8 w-8" rounded="rounded-full" />
                  <div className="space-y-1.5">
                    <Skeleton className="h-2.5 w-20" />
                    <Skeleton className="h-3 w-24" />
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
