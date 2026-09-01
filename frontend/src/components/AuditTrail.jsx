import Icon from "./ui/Icon";
import Panel from "./ui/Surface";
import Skeleton from "./ui/Skeleton";
import EmptyState from "./ui/EmptyState";
import { StatusBadge } from "./ui/Badge";
import { inr, kindMeta, statusMeta, tone } from "../lib/format";

const COLUMNS = ["Flow", "Customer", "Amount", "Status"];

function rowLabel(t) {
  const kind = kindMeta(t.kind);
  const status = statusMeta(t.status);
  return `${kind.label}: ${t.customer_name || t.customer_id}, ${inr(t.amount)}, ${status.label}. View reasoning chain.`;
}

function LoadingRows() {
  return (
    <div role="status" aria-busy="true" className="space-y-2 p-4">
      <span className="sr-only">Loading transactions…</span>
      {Array.from({ length: 6 }, (_, i) => (
        <div key={i} className="flex items-center gap-4">
          <Skeleton className="h-3.5 w-32" />
          <Skeleton className="h-3.5 flex-1" />
          <Skeleton className="h-3.5 w-24" />
          <Skeleton className="h-6 w-24" rounded="rounded-full" />
        </div>
      ))}
    </div>
  );
}

export default function AuditTrail({
  transactions,
  selectedId,
  onSelect,
  loading = false,
  error = null,
  onRetry,
  filtersActive = false,
  onClearFilters,
  totalCount = 0,
}) {
  const activate = (id) => onSelect?.(id);

  let body;
  if (loading && transactions.length === 0) {
    body = <LoadingRows />;
  } else if (error) {
    body = (
      <EmptyState
        variant="error"
        title="Couldn't load transactions"
        description={error}
        action={onRetry ? "Try again" : undefined}
        onAction={onRetry}
      />
    );
  } else if (transactions.length === 0) {
    body = filtersActive ? (
      <EmptyState
        icon="search"
        title="No transactions match these filters"
        description={`None of the ${totalCount} loaded transactions match your search and filters.`}
        action={onClearFilters ? "Clear filters" : undefined}
        onAction={onClearFilters}
      />
    ) : (
      <EmptyState
        icon="inbox"
        title="No transactions yet"
        description={
          import.meta.env.DEV
            ? "Seed the demo dataset on the backend, then trigger a batch replay to watch the agent work."
            : "Trigger a batch replay to watch the agent work."
        }
      />
    );
  } else {
    body = (
      <>
        <table className="hidden w-full border-collapse text-meta md:table">
          <caption className="sr-only">
            Transactions in this recovery batch. Select a row to open its reasoning chain.
          </caption>
          <thead className="sticky top-0 z-10 bg-surface-2">
            <tr className="border-b border-hairline-strong text-left">
              {COLUMNS.map((c) => (
                <th
                  key={c}
                  scope="col"
                  className={`px-4 py-2.5 text-caption uppercase text-fg-subtle ${c === "Amount" ? "text-right" : ""}`}
                >
                  {c}
                </th>
              ))}
              <th scope="col" className="w-10 px-2 py-2.5">
                <span className="sr-only">Open</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {transactions.map((t) => {
              const kind = kindMeta(t.kind);
              const selected = selectedId === t.id;
              return (
                <tr
                  key={t.id}
                  aria-current={selected ? "true" : undefined}
                  onClick={() => activate(t.id)}
                  className={`group cursor-pointer border-b border-hairline transition-colors duration-150 hover:bg-white/5 ${
                    selected ? "bg-brand-tint" : ""
                  }`}
                >
                  <td className="px-4 py-3">
                    <span className="flex items-center gap-2 text-fg-muted">
                      <Icon name={kind.icon} size={14} className="text-fg-subtle" />
                      {kind.label}
                    </span>
                  </td>
                  <td className="max-w-0 px-4 py-3">
                    <span className="block truncate text-fg">{t.customer_name || t.customer_id}</span>
                    {t.failure_code && (
                      <span className="block truncate font-mono text-[0.6875rem] text-fg-subtle">{t.failure_code}</span>
                    )}
                  </td>
                  <td className="tabular px-4 py-3 text-right font-semibold text-fg">{inr(t.amount)}</td>
                  <td className="px-4 py-3">
                    <StatusBadge status={t.status} />
                  </td>
                  <td className="px-2 py-3">
                    <button
                      type="button"
                      aria-label={rowLabel(t)}
                      onClick={(e) => {
                        e.stopPropagation();
                        activate(t.id);
                      }}
                      className="grid h-9 w-9 place-items-center rounded-full text-fg-subtle transition-colors hover:bg-white/8 hover:text-fg"
                    >
                      <Icon
                        name="chevronRight"
                        size={16}
                        className="transition-transform duration-200 group-hover:translate-x-0.5"
                      />
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>

        <ul className="space-y-2 p-3 md:hidden">
          {transactions.map((t) => {
            const kind = kindMeta(t.kind);
            const status = statusMeta(t.status);
            const selected = selectedId === t.id;
            return (
              <li key={t.id}>
                <button
                  type="button"
                  onClick={() => activate(t.id)}
                  aria-label={rowLabel(t)}
                  aria-current={selected ? "true" : undefined}
                  className={`relative w-full overflow-hidden rounded-lg border px-3.5 py-3 text-left transition-colors duration-200 ${
                    selected ? "border-brand bg-brand-tint" : "border-hairline bg-surface-3/50 hover:border-hairline-strong"
                  }`}
                >
                  <span aria-hidden="true" className={`absolute inset-y-0 left-0 w-0.5 ${tone(status.tone).solid}`} />
                  <span className="flex items-start justify-between gap-3">
                    <span className="min-w-0">
                      <span className="block truncate text-meta font-semibold text-fg">
                        {t.customer_name || t.customer_id}
                      </span>
                      <span className="mt-1 flex items-center gap-1.5 text-[0.6875rem] text-fg-subtle">
                        <Icon name={kind.icon} size={11} />
                        {kind.label}
                      </span>
                    </span>
                    <span className="tabular shrink-0 text-meta font-bold text-fg">{inr(t.amount)}</span>
                  </span>
                  <span className="mt-2.5 flex items-center justify-between gap-2">
                    <StatusBadge status={t.status} size="xs" />
                    {t.failure_code && (
                      <span className="truncate font-mono text-[0.625rem] text-fg-subtle">{t.failure_code}</span>
                    )}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      </>
    );
  }

  return (
    <Panel
      icon="list"
      title="Audit Trail"
      caption="Click any transaction — the full reasoning chain, end to end"
      actions={
        transactions.length > 0 ? (
          <span className="tabular text-[0.6875rem] text-fg-subtle">{transactions.length} shown</span>
        ) : null
      }
      bodyClassName="max-h-[32rem] overflow-y-auto"
    >
      {body}
    </Panel>
  );
}
