import Icon from "./ui/Icon";
import Button from "./ui/Button";
import { KIND_FILTERS, STATUS_FILTERS } from "../lib/format";
import { SEARCH_INPUT_ID } from "../lib/sections";

function Chip({ active, onClick, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`inline-flex h-9 shrink-0 items-center gap-1.5 rounded-full border px-3.5 text-[0.8125rem] font-medium
        transition-[background-color,border-color,color] duration-200 ease-standard pointer-coarse:h-11
        ${
          active
            ? "border-brand/60 bg-brand-tint text-brand-ink"
            : "border-hairline bg-surface-2 text-fg-muted hover:border-hairline-strong hover:text-fg"
        }`}
    >
      {active && <Icon name="check" size={12} strokeWidth={2.4} />}
      {children}
    </button>
  );
}

export default function SearchFilterBar({
  query,
  onQuery,
  kinds,
  onToggleKind,
  statuses,
  onToggleStatus,
  onClear,
  resultCount,
  totalCount,
}) {
  const searchId = SEARCH_INPUT_ID;
  const activeCount = kinds.length + statuses.length + (query ? 1 : 0);

  return (
    <div className="mx-auto w-full max-w-[110rem] px-5 sm:px-8 lg:px-10">
      <div className="flex flex-col gap-3 rounded-xl border border-hairline bg-surface-2/70 p-3 backdrop-blur-sm sm:p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="relative min-w-0 flex-1">
            <label htmlFor={searchId} className="sr-only">
              Search transactions by customer, id, or failure code
            </label>
            <Icon
              name="search"
              size={16}
              className="pointer-events-none absolute top-1/2 left-3.5 -translate-y-1/2 text-fg-subtle"
            />
            <input
              id={searchId}
              type="search"
              value={query}
              onChange={(e) => onQuery(e.target.value)}
              placeholder="Search customer, transaction id, or failure code…"
              className="h-11 w-full rounded-full border border-hairline bg-void/60 pr-11 pl-10 text-meta text-fg
                placeholder:text-fg-subtle transition-colors duration-200 hover:border-hairline-strong focus:border-brand
                [&::-webkit-search-cancel-button]:appearance-none"
            />
            {query && (
              <button
                type="button"
                onClick={() => onQuery("")}
                aria-label="Clear search"
                className="absolute top-1/2 right-1.5 grid h-8 w-8 -translate-y-1/2 place-items-center rounded-full text-fg-subtle transition-colors hover:bg-white/8 hover:text-fg"
              >
                <Icon name="close" size={14} />
              </button>
            )}
          </div>

          <div className="flex items-center justify-between gap-3 sm:justify-end">
            <p aria-live="polite" className="tabular text-meta text-fg-subtle">
              {resultCount === totalCount ? (
                <>
                  <span className="font-semibold text-fg">{totalCount}</span> transactions
                </>
              ) : (
                <>
                  <span className="font-semibold text-fg">{resultCount}</span> of {totalCount}
                </>
              )}
            </p>
            {activeCount > 0 && (
              <Button variant="ghost" size="sm" icon="close" onClick={onClear}>
                Clear {activeCount === 1 ? "filter" : `${activeCount} filters`}
              </Button>
            )}
          </div>
        </div>

        <div className="no-scrollbar -mx-1 flex items-center gap-2 overflow-x-auto px-1 pb-0.5">
          <span className="shrink-0 pr-1 text-caption uppercase text-fg-subtle">Flow</span>
          {KIND_FILTERS.map((f) => (
            <Chip key={f.value} active={kinds.includes(f.value)} onClick={() => onToggleKind(f.value)}>
              {f.label}
            </Chip>
          ))}
          <span aria-hidden="true" className="mx-1 h-5 w-px shrink-0 bg-hairline-strong" />
          <span className="shrink-0 pr-1 text-caption uppercase text-fg-subtle">Status</span>
          {STATUS_FILTERS.map((f) => (
            <Chip key={f.value} active={statuses.includes(f.value)} onClick={() => onToggleStatus(f.value)}>
              {f.label}
            </Chip>
          ))}
        </div>
      </div>
    </div>
  );
}
