import { useCallback, useEffect, useId, useRef, useState } from "react";
import { api } from "../lib/api";
import Icon from "./ui/Icon";
import Button, { IconButton } from "./ui/Button";
import Badge, { StatusBadge } from "./ui/Badge";
import Skeleton, { SkeletonText } from "./ui/Skeleton";
import EmptyState from "./ui/EmptyState";
import {
  ACTION_RESULT_META,
  absoluteTime,
  actionIcon,
  actionLabel,
  actorMeta,
  guardrailResultMeta,
  humanize,
  inr,
  kindMeta,
  ruleLabel,
  timeAgo,
  tone,
} from "../lib/format";

const FOCUSABLE =
  'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),summary,[tabindex]:not([tabindex="-1"])';

const TABS = [
  { key: "timeline", label: "Timeline", icon: "activity", collection: "audit_entries" },
  { key: "diagnosis", label: "Diagnosis", icon: "bulb", collection: "diagnoses" },
  { key: "decision", label: "Decision", icon: "target", collection: "decisions" },
  { key: "actions", label: "Actions", icon: "zap", collection: "actions" },
  { key: "guardrails", label: "Guardrails", icon: "shield", collection: "guardrail_events" },
  { key: "scheduled", label: "Scheduled", icon: "clock", collection: "scheduled_actions" },
];

function Block({ children, className = "" }) {
  return <div className={`rounded-lg border border-hairline bg-surface-2 p-4 ${className}`}>{children}</div>;
}

function Meta({ label, value, mono = false }) {
  return (
    <div className="min-w-0">
      <p className="text-caption uppercase text-fg-subtle">{label}</p>
      <p className={`mt-0.5 truncate text-meta text-fg ${mono ? "font-mono" : ""}`}>{value}</p>
    </div>
  );
}

function Json({ data, label = "Raw payload" }) {
  return (
    <details className="group/j mt-3 rounded-md border border-hairline bg-console">
      <summary className="flex cursor-pointer list-none items-center gap-1.5 px-3 py-2 text-[0.6875rem] font-semibold tracking-wide text-fg-subtle uppercase transition-colors hover:text-fg">
        <Icon
          name="chevronRight"
          size={12}
          className="transition-transform duration-200 group-open/j:rotate-90"
        />
        {label}
      </summary>
      <pre className="max-h-64 overflow-auto border-t border-hairline px-3 py-2.5 font-mono text-[0.6875rem] leading-relaxed text-fg-muted">
        {JSON.stringify(data ?? {}, null, 2)}
      </pre>
    </details>
  );
}

function Confidence({ value }) {
  const pct = Math.round(Math.max(0, Math.min(1, Number(value) || 0)) * 100);
  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between gap-3">
        <span className="text-caption uppercase text-fg-subtle">Confidence</span>
        <span className="tabular text-meta font-semibold text-fg">{pct}%</span>
      </div>
      <div
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Diagnosis confidence"
        className="h-1.5 overflow-hidden rounded-full bg-surface-4"
      >
        <div
          className={`h-full rounded-full ${pct >= 70 ? "bg-ok" : pct >= 40 ? "bg-warn" : "bg-alert"}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function TabEmpty({ what }) {
  return (
    <EmptyState
      size="sm"
      icon="inbox"
      title={`No ${what} recorded`}
      description={`This transaction has no ${what} in its chain — which is itself part of the record.`}
    />
  );
}

function Timeline({ entries }) {
  if (entries.length === 0) return <TabEmpty what="audit entries" />;
  return (
    <ol className="relative space-y-4 pl-6">
      <span aria-hidden="true" className="absolute top-1.5 bottom-1.5 left-[7px] w-px bg-hairline-strong" />
      {entries
        .slice()
        .reverse()
        .map((entry) => {
          const actor = actorMeta(entry.actor);
          return (
            <li key={entry.id} className="relative">
              <span
                aria-hidden="true"
                className={`absolute top-1.5 -left-6 h-[15px] w-[15px] rounded-full border-2 border-surface ${
                  tone(actor.tone).solid
                }`}
              />
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <Badge tone={actor.tone} icon={actor.icon} size="xs">
                  {actor.label}
                </Badge>
                <span className="text-meta font-semibold text-fg">{humanize(entry.event_type)}</span>
                <span className="ml-auto shrink-0 text-[0.6875rem] text-fg-subtle" title={absoluteTime(entry.timestamp)}>
                  {timeAgo(entry.timestamp)}
                </span>
              </div>
              <Json data={entry.payload} />
            </li>
          );
        })}
    </ol>
  );
}

function Diagnoses({ items }) {
  if (items.length === 0) return <TabEmpty what="diagnoses" />;
  return (
    <div className="space-y-3">
      {items.map((d) => (
        <Block key={d.id}>
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-caption uppercase text-fg-subtle">Root cause</p>
              <p className="mt-1 text-h3 text-fg">{humanize(d.root_cause)}</p>
            </div>
            <span className="shrink-0 text-[0.6875rem] text-fg-subtle">{timeAgo(d.agent_run_at)}</span>
          </div>
          <div className="mt-4 max-w-xs">
            <Confidence value={d.confidence} />
          </div>
          {d.reasoning_text && (
            <p className="mt-4 border-t border-hairline pt-3 text-meta leading-relaxed text-fg-muted">
              {d.reasoning_text}
            </p>
          )}
        </Block>
      ))}
    </div>
  );
}

function Decisions({ items }) {
  if (items.length === 0) return <TabEmpty what="decisions" />;
  return (
    <div className="space-y-3">
      {items.map((d) => (
        <Block key={d.id}>
          <div className="flex items-start justify-between gap-3">
            <div className="flex min-w-0 items-center gap-2.5">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand-tint text-brand-ink">
                <Icon name={actionIcon(d.chosen_action)} size={17} />
              </span>
              <div className="min-w-0">
                <p className="text-caption uppercase text-fg-subtle">Chosen action</p>
                <p className="mt-0.5 truncate text-h3 text-fg">{actionLabel(d.chosen_action)}</p>
              </div>
            </div>
            <span className="shrink-0 text-[0.6875rem] text-fg-subtle">{timeAgo(d.decided_at)}</span>
          </div>

          {d.reasoning_text && (
            <p className="mt-4 border-t border-hairline pt-3 text-meta leading-relaxed text-fg-muted">
              {d.reasoning_text}
            </p>
          )}

          {Array.isArray(d.guardrail_checks_passed) && d.guardrail_checks_passed.length > 0 && (
            <div className="mt-4">
              <p className="text-caption uppercase text-fg-subtle">Guardrails evaluated</p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {d.guardrail_checks_passed.map((check, i) => {
                  const isString = typeof check === "string";
                  const name = isString ? check : check?.rule_name;
                  const meta = guardrailResultMeta(isString ? "passed" : check?.rule_result);
                  return (
                    <Badge key={`${name ?? "rule"}-${i}`} tone={meta.tone} icon={meta.icon} size="xs">
                      {ruleLabel(name)}
                    </Badge>
                  );
                })}
              </div>
            </div>
          )}
        </Block>
      ))}
    </div>
  );
}

function Actions({ items }) {
  if (items.length === 0) return <TabEmpty what="executed actions" />;
  return (
    <div className="space-y-3">
      {items.map((a) => {
        const result = ACTION_RESULT_META[a.result] || { label: humanize(a.result), tone: "neutral", icon: "dot" };
        return (
          <Block key={a.id}>
            <div className="flex items-start justify-between gap-3">
              <div className="flex min-w-0 items-center gap-2.5">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-surface-4 text-fg-muted">
                  <Icon name={actionIcon(a.action_type)} size={17} />
                </span>
                <div className="min-w-0">
                  <p className="truncate text-h3 text-fg">{actionLabel(a.action_type)}</p>
                  <p className="mt-0.5 text-[0.6875rem] text-fg-subtle">{absoluteTime(a.executed_at)}</p>
                </div>
              </div>
              <Badge tone={result.tone} icon={result.icon} size="sm" className="shrink-0">
                {result.label}
              </Badge>
            </div>

            {Number(a.amount_recovered) > 0 && (
              <p className="tabular mt-3 flex items-center gap-2 rounded-md bg-ok-tint px-3 py-2 text-meta font-semibold text-ok-ink">
                <Icon name="trendingUp" size={14} />
                {inr(a.amount_recovered)} recovered
              </p>
            )}

            <Json data={a.api_response} label="Razorpay API response" />
          </Block>
        );
      })}
    </div>
  );
}

function Guardrails({ items }) {
  if (items.length === 0) return <TabEmpty what="guardrail events" />;
  return (
    <ul className="space-y-2">
      {items.map((g) => {
        const meta = guardrailResultMeta(g.rule_result);
        const c = tone(meta.tone);
        return (
          <li
            key={g.id}
            className="relative overflow-hidden rounded-lg border border-hairline bg-surface-2 py-3 pr-3.5 pl-4"
          >
            <span aria-hidden="true" className={`absolute inset-y-0 left-0 w-0.5 ${c.solid}`} />
            <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1.5">
              <Badge tone={meta.tone} icon={meta.icon} size="xs">
                {meta.label}
              </Badge>
              <span className="text-meta font-semibold text-fg">{ruleLabel(g.rule_name)}</span>
              <span className="ml-auto shrink-0 text-[0.6875rem] text-fg-subtle">{timeAgo(g.triggered_at)}</span>
            </div>
            <p className="mt-1.5 font-mono text-[0.75rem] leading-relaxed break-words text-fg-subtle">{g.detail}</p>
          </li>
        );
      })}
    </ul>
  );
}

function MandateSequenceProgress({ sequence }) {
  if (!sequence) {
    return (
      <div className="mb-3 flex items-center gap-2 rounded-lg border border-hairline bg-surface-2 px-3.5 py-2.5">
        <Icon name="clock" size={14} className="text-fg-subtle" />
        <span className="text-meta text-fg-muted">No active recovery sequence</span>
      </div>
    );
  }
  const badgeTone =
    sequence.status === "recovered"
      ? "ok"
      : sequence.status === "escalated"
        ? "alert"
        : sequence.status === "cancelled"
          ? "neutral"
          : "info";
  return (
    <div className="mb-3 flex items-center justify-between gap-3 rounded-lg border border-hairline bg-surface-2 px-3.5 py-2.5">
      <span className="text-meta font-semibold text-fg">
        Step {sequence.current_step + 1} of {sequence.total_steps}
      </span>
      <Badge tone={badgeTone} icon="clock" size="xs">
        {humanize(sequence.status)}
      </Badge>
    </div>
  );
}

function Scheduled({ items, mandateSequence }) {
  return (
    <div>
      <MandateSequenceProgress sequence={mandateSequence} />
      {items.length === 0 ? (
        <TabEmpty what="scheduled actions" />
      ) : (
        <div className="space-y-3">
          {items.map((s) => (
            <Block key={s.id}>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="truncate text-h3 text-fg">{actionLabel(s.action_type)}</p>
                  <p className="mt-1 text-meta text-fg-muted">{humanize(s.reason)}</p>
                </div>
                <Badge tone={s.status === "pending" ? "info" : "neutral"} icon="clock" size="sm" className="shrink-0">
                  {humanize(s.status)}
                </Badge>
              </div>
              <div className="mt-4 grid grid-cols-2 gap-4 border-t border-hairline pt-3">
                <Meta label="Runs after" value={absoluteTime(s.run_after)} />
                <Meta label="Created" value={absoluteTime(s.created_at)} />
              </div>
            </Block>
          ))}
        </div>
      )}
    </div>
  );
}

export default function ChainDrawer({ transactionId, onClose, onVoiceShowcase }) {
  const [chain, setChain] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState("timeline");
  const [copied, setCopied] = useState(false);

  const panelRef = useRef(null);
  const tablistRef = useRef(null);
  const titleId = useId();

  const load = useCallback(() => {
    if (!transactionId) return;
    api
      .transactionChain(transactionId)
      .then(setChain)
      .catch(() =>
        setError(
          import.meta.env.DEV
            ? "The reasoning chain couldn't be loaded. The backend may be unreachable."
            : "The reasoning chain couldn't be loaded."
        )
      )
      .finally(() => setLoading(false));
  }, [transactionId]);

  const retry = () => {
    setLoading(true);
    setError(null);
    load();
  };

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const background = [document.getElementById("main"), ...document.querySelectorAll("[data-app-chrome]")].filter(
      Boolean
    );
    background.forEach((el) => el.setAttribute("inert", ""));

    return () => {
      document.body.style.overflow = previous;
      background.forEach((el) => el.removeAttribute("inert"));
    };
  }, []);

  useEffect(() => {
    const opener = document.activeElement;
    panelRef.current?.focus();
    return () => {
      if (opener instanceof HTMLElement && document.contains(opener)) opener.focus();
    };
  }, []);

  const handleKeyDown = (e) => {
    if (e.key === "Escape") {
      e.stopPropagation();
      onClose();
      return;
    }
    if (e.key !== "Tab" || !panelRef.current) return;

    const nodes = Array.from(panelRef.current.querySelectorAll(FOCUSABLE)).filter(
      (el) => el.offsetWidth > 0 || el.offsetHeight > 0
    );
    if (nodes.length === 0) {
      e.preventDefault();
      return;
    }
    const first = nodes[0];
    const last = nodes[nodes.length - 1];
    if (e.shiftKey && (document.activeElement === first || document.activeElement === panelRef.current)) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  };

  const onTablistKeyDown = (e) => {
    const keys = ["ArrowLeft", "ArrowRight", "Home", "End"];
    if (!keys.includes(e.key)) return;
    e.preventDefault();
    const index = TABS.findIndex((t) => t.key === tab);
    let next = index;
    if (e.key === "ArrowLeft") next = (index - 1 + TABS.length) % TABS.length;
    if (e.key === "ArrowRight") next = (index + 1) % TABS.length;
    if (e.key === "Home") next = 0;
    if (e.key === "End") next = TABS.length - 1;
    setTab(TABS[next].key);
    tablistRef.current?.querySelectorAll('[role="tab"]')[next]?.focus();
  };

  const copyId = async () => {
    try {
      await navigator.clipboard?.writeText(transactionId);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
    }
  };

  if (!transactionId) return null;

  const kind = chain ? kindMeta(chain.kind) : null;
  const isHighValueReceivable = chain?.kind === "receivable" && Number(chain.amount) > 40000;
  const count = (key) => (Array.isArray(chain?.[key]) ? chain[key].length : 0);

  return (
    <div
      className="animate-fade-in fixed inset-0 z-70 flex items-end bg-void/75 backdrop-blur-sm sm:items-stretch sm:justify-end"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label="Reasoning chain"
        aria-labelledby={titleId}
        tabIndex={-1}
        onKeyDown={handleKeyDown}
        className="animate-slide-up-sheet flex h-[92dvh] max-h-full w-full flex-col overflow-hidden rounded-t-2xl border border-hairline-strong bg-surface shadow-modal outline-none
          sm:animate-slide-in-right sm:h-full sm:max-w-2xl sm:rounded-none sm:rounded-l-2xl sm:border-y-0 sm:border-r-0"
      >
        <header className="relative shrink-0 overflow-hidden border-b border-hairline">
          <span aria-hidden="true" className="cine-bg pointer-events-none absolute inset-0 opacity-60" />
          <div className="relative px-5 pt-4 pb-5 sm:px-6">
            <div className="flex items-start justify-between gap-3">
              <div className="flex min-w-0 items-center gap-1.5">
                <span className="truncate font-mono text-[0.6875rem] tracking-wide text-fg-subtle uppercase">
                  txn · {String(transactionId).slice(0, 8)}
                </span>
                <IconButton
                  icon={copied ? "check" : "copy"}
                  label={copied ? "Transaction id copied" : "Copy transaction id"}
                  size="sm"
                  onClick={copyId}
                  className="h-7 w-7 pointer-coarse:h-9 pointer-coarse:w-9"
                />
              </div>
              <IconButton icon="close" label="Close reasoning chain" size="sm" onClick={onClose} variant="subtle" />
            </div>

            {loading && !chain ? (
              <div className="mt-3 space-y-3">
                <Skeleton className="h-8 w-44" />
                <Skeleton className="h-5 w-64" rounded="rounded-full" />
              </div>
            ) : chain ? (
              <>
                <h2 id={titleId} className="tabular mt-2 text-h1 text-fg">
                  {inr(chain.amount)}
                </h2>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <StatusBadge status={chain.status} size="md" />
                  <Badge tone="neutral" icon={kind.icon} size="md">
                    {kind.label}
                  </Badge>
                  <span className="truncate text-meta text-fg-muted">{chain.customer_name || chain.customer_id}</span>
                </div>
                {isHighValueReceivable && onVoiceShowcase && (
                  <Button
                    size="sm"
                    variant="secondary"
                    icon="sound"
                    className="mt-4"
                    onClick={() => onVoiceShowcase(transactionId)}
                  >
                    Trigger Hinglish voice recovery
                  </Button>
                )}
              </>
            ) : (
              <h2 id={titleId} className="mt-2 text-h1 text-fg">
                Reasoning chain
              </h2>
            )}
          </div>
        </header>

        <div
          ref={tablistRef}
          role="tablist"
          aria-label="Reasoning chain sections"
          onKeyDown={onTablistKeyDown}
          className="no-scrollbar flex shrink-0 gap-1 overflow-x-auto border-b border-hairline bg-surface-2 px-3 sm:px-4"
        >
          {TABS.map((t) => {
            const active = tab === t.key;
            const n = count(t.collection);
            return (
              <button
                key={t.key}
                role="tab"
                type="button"
                id={`tab-${t.key}`}
                aria-selected={active}
                aria-controls={active ? `tabpanel-${t.key}` : undefined}
                tabIndex={active ? 0 : -1}
                onClick={() => setTab(t.key)}
                className={`relative flex shrink-0 items-center gap-1.5 px-3 py-3 text-meta font-semibold whitespace-nowrap transition-colors duration-200 ${
                  active ? "text-fg" : "text-fg-subtle hover:text-fg-muted"
                }`}
              >
                <Icon name={t.icon} size={14} />
                {t.label}
                {n > 0 && (
                  <span
                    className={`tabular rounded-full px-1.5 py-px text-[0.625rem] ${
                      active ? "bg-brand-tint text-brand-ink" : "bg-surface-4 text-fg-muted"
                    }`}
                  >
                    {n}
                  </span>
                )}
                {active && (
                  <span aria-hidden="true" className="absolute inset-x-2 -bottom-px h-0.5 rounded-full bg-brand" />
                )}
              </button>
            );
          })}
        </div>

        <div
          role="tabpanel"
          id={`tabpanel-${tab}`}
          aria-labelledby={`tab-${tab}`}
          tabIndex={0}
          className="min-h-0 flex-1 overflow-y-auto px-4 pt-4 pb-[calc(1rem+env(safe-area-inset-bottom,0px))]
            sm:px-5 sm:pt-5 sm:pb-[calc(1.25rem+env(safe-area-inset-bottom,0px))]"
        >
          {loading && !chain ? (
            <div role="status" aria-busy="true" className="space-y-4">
              <span className="sr-only">Loading reasoning chain…</span>
              {Array.from({ length: 3 }, (_, i) => (
                <div key={i} className="rounded-lg border border-hairline bg-surface-2 p-4">
                  <Skeleton className="h-3 w-28" />
                  <SkeletonText lines={2} className="mt-3" />
                </div>
              ))}
            </div>
          ) : error ? (
            <EmptyState
              variant="error"
              title="Couldn't load the reasoning chain"
              description={error}
              action="Try again"
              onAction={retry}
            />
          ) : chain ? (
            <>
              {tab === "timeline" && <Timeline entries={chain.audit_entries || []} />}
              {tab === "diagnosis" && <Diagnoses items={chain.diagnoses || []} />}
              {tab === "decision" && <Decisions items={chain.decisions || []} />}
              {tab === "actions" && <Actions items={chain.actions || []} />}
              {tab === "guardrails" && <Guardrails items={chain.guardrail_events || []} />}
              {tab === "scheduled" && (
                <Scheduled items={chain.scheduled_actions || []} mandateSequence={chain.mandate_sequence ?? null} />
              )}
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}
