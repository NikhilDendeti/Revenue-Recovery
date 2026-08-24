const RULE_LABEL = {
  max_retry_attempts: "Max retry attempts",
  contact_frequency_cap: "Contact frequency cap",
  cooldown_between_retries: "Cooldown between retries",
  spend_ceiling: "Spend / action ceiling",
  confidence_floor: "Confidence floor",
  compliance_hours: "Compliance hours",
};

export default function GuardrailConsole({ events, onSelect }) {
  return (
    <section className="flex h-[520px] flex-col rounded-lg border border-line bg-console">
      <header className="border-b border-console-line/60 px-5 py-3">
        <h2 className="font-serif text-lg font-semibold text-ink">Guardrail Console</h2>
        <p className="font-mono text-[11px] text-ink-faint">Panel 2 · stopping rules and escalation logic, firing live</p>
      </header>
      <div className="flex-1 space-y-1 overflow-y-auto p-3 font-mono text-xs">
        {events.length === 0 && <p className="p-4 text-ink-faint">Waiting for the first guardrail check…</p>}
        {events.map((ev) => {
          const blocked = ev.rule_result === "blocked";
          return (
            <button
              key={ev._key}
              onClick={() => onSelect?.(ev.transaction_id)}
              className={`animate-tick-in flex w-full items-start gap-2 rounded px-3 py-2 text-left transition hover:bg-white/5 ${
                blocked ? "text-warn" : "text-ink-faint"
              }`}
            >
              <span className="mt-0.5 shrink-0">{blocked ? "⛔" : "·"}</span>
              <span className="min-w-0">
                <span className={blocked ? "text-warn" : "text-ink-soft"}>
                  {RULE_LABEL[ev.rule_name] || ev.rule_name}
                </span>
                <span className="text-ink-faint"> — {ev.detail}</span>
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
