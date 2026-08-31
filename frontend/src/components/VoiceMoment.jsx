import Icon from "./ui/Icon";
import Button, { IconButton } from "./ui/Button";

function Wave() {
  return (
    <span aria-hidden="true" className="flex h-6 items-center gap-[3px]">
      {[0, 1, 2, 3, 4].map((i) => (
        <span
          key={i}
          className="animate-wave block w-[3px] origin-center rounded-full bg-brand-ink"
          style={{ height: "100%", animationDelay: `${i * 110}ms` }}
        />
      ))}
    </span>
  );
}

function Line({ speaker, text, isAgent }) {
  return (
    <p className="text-meta leading-relaxed">
      <span className={`font-semibold ${isAgent ? "text-brand-ink" : "text-fg-subtle"}`}>{speaker}:</span>{" "}
      <span className="text-fg">“{text}”</span>
    </p>
  );
}

export default function VoiceMoment({ moment, onDismiss, onSelect }) {
  if (!moment) return null;

  return (
    <div className="mx-auto w-full max-w-[110rem] px-5 sm:px-8 lg:px-10">
      <section
        aria-label="Hinglish voice recovery"
        className="animate-fade-up relative overflow-hidden rounded-xl border border-brand/45 bg-surface-2 shadow-glow"
      >
        <span
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 bg-gradient-to-r from-brand-tint-strong via-brand-tint to-transparent"
        />

        <div className="relative flex flex-col gap-4 p-4 sm:flex-row sm:items-start sm:p-5">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-brand text-white shadow-glow">
            <Icon name="sound" size={20} />
          </span>

          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
              <p className="text-caption uppercase text-brand-ink">Hinglish voice recovery · live</p>
              <Wave />
            </div>

            <div className="mt-3 space-y-1.5">
              <Line speaker="RecoverAI" text={moment.transcript} isAgent />
              <Line speaker="Customer" text={moment.customer_response} />
            </div>

            <div className="mt-4 flex flex-wrap items-center gap-2.5">
              <span className="inline-flex items-center gap-1.5 rounded-full border border-ok/45 bg-ok-tint px-2.5 py-1 text-[0.75rem] font-semibold text-ok-ink">
                <Icon name="calendar" size={13} />
                Promise to pay · {moment.promise_to_pay_date}
              </span>
              {onSelect && moment.transaction_id && (
                <Button variant="ghost" size="sm" iconRight="arrowRight" onClick={() => onSelect(moment.transaction_id)}>
                  View chain
                </Button>
              )}
            </div>
          </div>

          <IconButton
            icon="close"
            label="Dismiss voice recovery"
            size="sm"
            variant="ghost"
            onClick={onDismiss}
            className="absolute top-3 right-3 sm:static"
          />
        </div>
      </section>
    </div>
  );
}
