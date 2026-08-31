import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Header from "./Header";
import MobileNav from "./MobileNav";
import Hero from "./Hero";
import SummaryStrip from "./SummaryStrip";
import VoiceMoment from "./VoiceMoment";
import SearchFilterBar from "./SearchFilterBar";
import ContentRow from "./ContentRow";
import TransactionCard from "./TransactionCard";
import RecoveryTicker from "./RecoveryTicker";
import GuardrailConsole from "./GuardrailConsole";
import PromiseTracker from "./PromiseTracker";
import AuditTrail from "./AuditTrail";
import ChainDrawer from "./ChainDrawer";
import Skeleton from "./ui/Skeleton";
import EmptyState from "./ui/EmptyState";
import Wordmark from "./ui/Wordmark";
import { api } from "../lib/api";
import { useRecoveryRoom } from "../lib/useRecoveryRoom";
import { useToast } from "../lib/toastContext";
import { SECTION_IDS } from "../lib/sections";
import { STATUS_GROUPS, tone } from "../lib/format";
import { useActiveSection } from "../lib/useNavState";

function SectionHeading({ id, eyebrow, title, description, children }) {
  return (
    <div className="mx-auto flex w-full max-w-[110rem] flex-wrap items-end justify-between gap-4 px-5 sm:px-8 lg:px-10">
      <div className="min-w-0">
        <p className="text-caption uppercase text-brand-ink">{eyebrow}</p>
        <h2 id={id} className="mt-1.5 text-h1 text-fg">
          {title}
        </h2>
        {description && <p className="mt-2 max-w-2xl text-meta text-fg-subtle">{description}</p>}
      </div>
      {children}
    </div>
  );
}

function RowSkeleton() {
  return (
    <div className="mx-auto w-full max-w-[110rem] px-5 sm:px-8 lg:px-10">
      <Skeleton className="h-4 w-40" />
      <div className="no-scrollbar mt-4 flex gap-3 overflow-hidden sm:gap-4">
        {Array.from({ length: 5 }, (_, i) => (
          <Skeleton key={i} className="h-[13.5rem] w-60 shrink-0 sm:w-68" rounded="rounded-lg" />
        ))}
      </div>
    </div>
  );
}

const GROUP_TONE = { attention: "alert", inflight: "info", atrisk: "neutral", recovered: "ok" };

export default function Dashboard({ onLogout }) {
  const { summary, ticks, guardrails, voiceMoment, setVoiceMoment, connected, error: summaryError } = useRecoveryRoom();
  const toast = useToast();

  const [transactions, setTransactions] = useState([]);
  const [txLoading, setTxLoading] = useState(true);
  const [txError, setTxError] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [replaying, setReplaying] = useState(false);

  const [query, setQuery] = useState("");
  const [kinds, setKinds] = useState([]);
  const [statuses, setStatuses] = useState([]);

  const activeSection = useActiveSection(SECTION_IDS);
  const reportedSummaryError = useRef(false);

  // Fetch only — no synchronous state change, so the mount effect and the
  // ticker-driven refresh below never restart a render pass. `retryTransactions`
  // is the variant that shows the loading state, and it only runs from a press.
  const refreshTransactions = useCallback(() => {
    api
      .transactions()
      .then((data) => {
        setTransactions(data.results ?? data);
        setTxError(null);
      })
      .catch(() => setTxError("The backend didn't return the transaction list. It may be unreachable."))
      .finally(() => setTxLoading(false));
  }, []);

  const retryTransactions = () => {
    setTxLoading(true);
    setTxError(null);
    refreshTransactions();
  };

  useEffect(() => {
    refreshTransactions();
  }, [refreshTransactions]);


  // Cheap live refresh: re-pull the transaction table whenever a new ticker event
  // lands, so the Audit Trail panel's status column stays in sync with the ticker.
  // Keyed on the newest tick, not the list length — length pins at MAX_FEED and the
  // effect would then stop firing for the rest of the session.
  const newestTick = ticks[0]?._key;
  useEffect(() => {
    if (newestTick) refreshTransactions();
  }, [newestTick, refreshTransactions]);

  // Surface a summary failure once, rather than swallowing it.
  useEffect(() => {
    if (summaryError && !reportedSummaryError.current) {
      reportedSummaryError.current = true;
      toast.error("Recovery summary unavailable", summaryError);
    }
    if (!summaryError) reportedSummaryError.current = false;
  }, [summaryError, toast]);

  const handleReplay = async () => {
    setReplaying(true);
    try {
      await api.replayBatch();
      toast.success("Batch replay queued", "Recovery events will land in the ticker as each transaction is worked.");
    } catch {
      toast.error("Couldn't trigger the replay", "The backend rejected the request or is unreachable.");
      setReplaying(false);
      return;
    }
    setTimeout(() => setReplaying(false), 2000);
  };

  const handleVoiceShowcase = (id) => {
    api
      .voiceShowcase(id)
      .then(() => toast.success("Voice recovery queued", "The Hinglish call will appear as soon as it completes."))
      .catch(() => toast.error("Couldn't queue the voice recovery", "The backend rejected the request or is unreachable."));
  };

  const clearFilters = () => {
    setQuery("");
    setKinds([]);
    setStatuses([]);
  };

  const toggle = (setter) => (value) =>
    setter((prev) => (prev.includes(value) ? prev.filter((v) => v !== value) : [...prev, value]));

  const filtersActive = Boolean(query) || kinds.length > 0 || statuses.length > 0;

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return transactions.filter((t) => {
      if (kinds.length > 0 && !kinds.includes(t.kind)) return false;
      if (statuses.length > 0 && !statuses.includes(t.status)) return false;
      if (!q) return true;
      return [t.customer_name, t.customer_id, t.failure_code, t.razorpay_order_id, t.id]
        .filter(Boolean)
        .some((field) => String(field).toLowerCase().includes(q));
    });
  }, [transactions, kinds, statuses, query]);

  const groups = useMemo(
    () =>
      STATUS_GROUPS.map((g) => ({ ...g, items: filtered.filter((t) => g.statuses.includes(t.status)) })).filter(
        (g) => g.items.length > 0
      ),
    [filtered]
  );

  return (
    <div className="min-h-screen">
      <a
        href="#main"
        className="sr-only rounded-full focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-110 focus:bg-brand focus:px-4 focus:py-2.5 focus:text-meta focus:font-semibold focus:text-white"
      >
        Skip to main content
      </a>

      <Header
        connected={connected}
        replaying={replaying}
        onReplay={handleReplay}
        onLogout={onLogout}
        query={query}
        onQuery={setQuery}
        activeSection={activeSection}
      />

      <main id="main" tabIndex={-1} className="pb-safe-nav outline-none lg:pb-14">
        <Hero summary={summary} connected={connected} replaying={replaying} onReplay={handleReplay} />

        <div className="relative z-10 -mt-4 space-y-10 sm:-mt-6 sm:space-y-14">
          <SummaryStrip summary={summary} />

          <VoiceMoment moment={voiceMoment} onDismiss={() => setVoiceMoment(null)} onSelect={setSelectedId} />

          {/* Transactions */}
          <section id="transactions" data-section aria-labelledby="transactions-heading" className="space-y-5">
            <SectionHeading
              id="transactions-heading"
              eyebrow="Revenue at risk"
              title="Transactions"
              description="Grouped by what needs you first. Every card opens the agent's full reasoning chain."
            />

            <SearchFilterBar
              query={query}
              onQuery={setQuery}
              kinds={kinds}
              onToggleKind={toggle(setKinds)}
              statuses={statuses}
              onToggleStatus={toggle(setStatuses)}
              onClear={clearFilters}
              resultCount={filtered.length}
              totalCount={transactions.length}
            />

            {txLoading && transactions.length === 0 ? (
              <div className="space-y-8">
                <RowSkeleton />
                <RowSkeleton />
              </div>
            ) : txError ? (
              <div className="mx-auto w-full max-w-[110rem] px-5 sm:px-8 lg:px-10">
                <div className="rounded-xl border border-hairline bg-surface-2">
                  <EmptyState
                    variant="error"
                    title="Couldn't load transactions"
                    description={txError}
                    action="Try again"
                    onAction={retryTransactions}
                  />
                </div>
              </div>
            ) : groups.length === 0 ? (
              <div className="mx-auto w-full max-w-[110rem] px-5 sm:px-8 lg:px-10">
                <div className="rounded-xl border border-hairline bg-surface-2">
                  {filtersActive ? (
                    <EmptyState
                      icon="search"
                      title="Nothing matches these filters"
                      description={`None of the ${transactions.length} loaded transactions match your search and filters.`}
                      action="Clear filters"
                      onAction={clearFilters}
                    />
                  ) : (
                    <EmptyState
                      icon="inbox"
                      title="No transactions detected yet"
                      description="Seed the demo dataset on the backend, then trigger a batch replay to watch the agent work through it."
                    />
                  )}
                </div>
              </div>
            ) : (
              <div className="space-y-8">
                {groups.map((g) => (
                  <ContentRow
                    key={g.key}
                    title={g.title}
                    caption={g.caption}
                    count={g.items.length}
                    tone={tone(GROUP_TONE[g.key]).solid}
                  >
                    {g.items.map((t) => (
                      <TransactionCard
                        key={t.id}
                        transaction={t}
                        selected={selectedId === t.id}
                        onSelect={setSelectedId}
                      />
                    ))}
                  </ContentRow>
                ))}
              </div>
            )}
          </section>

          {/* Live panels */}
          <section id="live" data-section aria-labelledby="live-heading" className="space-y-5">
            <SectionHeading
              id="live-heading"
              eyebrow="Watch it work"
              title="Live"
              description="The ticker is what the agent did. The console is what the guardrails allowed it to do."
            />
            <div className="mx-auto grid w-full max-w-[110rem] gap-4 px-5 sm:px-8 lg:grid-cols-2 lg:px-10">
              <RecoveryTicker ticks={ticks} onSelect={setSelectedId} connected={connected} />
              <GuardrailConsole events={guardrails} onSelect={setSelectedId} />
            </div>
            <div className="mx-auto w-full max-w-[110rem] px-5 sm:px-8 lg:px-10">
              <PromiseTracker />
            </div>
          </section>

          {/* Audit trail */}
          <section id="audit" data-section aria-labelledby="audit-heading" className="space-y-5">
            <SectionHeading
              id="audit-heading"
              eyebrow="Append-only record"
              title="Audit trail"
              description="Every transaction in the batch. Pick any one — the chain behind it is written, not reconstructed."
            />
            <div className="mx-auto w-full max-w-[110rem] px-5 sm:px-8 lg:px-10">
              <AuditTrail
                transactions={filtered}
                selectedId={selectedId}
                onSelect={setSelectedId}
                loading={txLoading}
                error={txError}
                onRetry={retryTransactions}
                filtersActive={filtersActive}
                onClearFilters={clearFilters}
                totalCount={transactions.length}
              />
            </div>
          </section>

          <footer className="mx-auto w-full max-w-[110rem] px-5 pt-4 sm:px-8 lg:px-10">
            <div className="flex flex-col gap-4 border-t border-hairline pt-7 sm:flex-row sm:items-center sm:justify-between">
              <Wordmark size="sm" />
              <p className="text-[0.75rem] text-fg-subtle">
                Detect → diagnose → decide → act (bounded) → track → audit. Built for the Razorpay AI Buildathon, Track 03.
              </p>
            </div>
          </footer>
        </div>
      </main>

      <MobileNav activeSection={activeSection} />

      {selectedId && (
        <ChainDrawer
          key={selectedId}
          transactionId={selectedId}
          onClose={() => setSelectedId(null)}
          onVoiceShowcase={handleVoiceShowcase}
        />
      )}
    </div>
  );
}
