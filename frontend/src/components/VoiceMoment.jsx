export default function VoiceMoment({ moment, onDismiss }) {
  if (!moment) return null;
  return (
    <div className="mx-6 mb-2 rounded-lg border border-accent bg-accent-soft px-5 py-4 sm:mx-10">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="font-mono text-[11px] uppercase tracking-wide text-accent-ink">
            🔊 Hinglish voice recovery — signature moment
          </p>
          <p className="mt-2 font-sans text-sm text-ink">
            <span className="text-ink-faint">RecoverAI:</span> “{moment.transcript}”
          </p>
          <p className="mt-1 font-sans text-sm text-ink">
            <span className="text-ink-faint">Customer:</span> “{moment.customer_response}”
          </p>
          <p className="mt-2 font-mono text-xs text-accent-ink">
            Promise-to-pay logged for {moment.promise_to_pay_date}
          </p>
        </div>
        <button onClick={onDismiss} className="shrink-0 font-mono text-xs text-ink-faint hover:text-ink">
          dismiss
        </button>
      </div>
    </div>
  );
}
