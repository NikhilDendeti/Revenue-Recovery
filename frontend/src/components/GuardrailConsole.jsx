import Icon from "./ui/Icon";
import Panel from "./ui/Surface";
import EmptyState from "./ui/EmptyState";
import Tooltip from "./ui/Tooltip";
import { RULE_HELP, guardrailResultMeta, ruleLabel, tone } from "../lib/format";

export default function GuardrailConsole({ events, onSelect }) {
  const blocked = events.filter((e) => e.rule_result === "blocked").length;

  return (
    <Panel
      icon="shield"
      title="Guardrail Console"
      caption="Deterministic stopping rules and escalation logic, firing live"
      actions={
        <span className="tabular flex items-center gap-2 font-mono text-[0.625rem] text-fg-subtle">
          <span className="flex items-center gap-1 text-warn-ink">
            <Icon name="block" size={11} />
            {blocked}
          </span>
          <span className="text-fg-subtle">/ {events.length}</span>
        </span>
      }
      className="h-panel"
      bodyClassName="flex flex-col bg-console"
    >
      <div className="min-h-0 flex-1 overflow-y-auto p-2 sm:p-2.5">
        {events.length === 0 ? (
          <EmptyState
            size="sm"
            icon="shield"
            title="No guardrail checks yet"
            description="Every stopping rule the agent evaluates — passed or blocked — is written here as it fires."
          />
        ) : (
          <ul className="space-y-0.5 font-mono">
            {events.map((ev) => {
              const meta = guardrailResultMeta(ev.rule_result);
              const c = tone(meta.tone);
              const isBlocked = ev.rule_result === "blocked";
              return (
                <li key={ev._key}>
                  <Tooltip label={RULE_HELP[ev.rule_name]} side="bottom" className="w-full">
                  <button
                    type="button"
                    onClick={() => onSelect?.(ev.transaction_id)}
                    aria-label={`${ruleLabel(ev.rule_name)} ${meta.label}: ${ev.detail}.${
                      RULE_HELP[ev.rule_name] ? ` ${RULE_HELP[ev.rule_name]}` : ""
                    } View reasoning chain.`}
                    className={`animate-tick-in flex w-full items-start gap-2.5 rounded-md px-2.5 py-2 text-left text-[0.75rem] leading-relaxed transition-colors duration-150 hover:bg-white/6 ${
                      isBlocked ? "bg-warn-tint/40" : ""
                    }`}
                  >
                    <span className={`mt-0.5 shrink-0 ${isBlocked ? c.text : "text-fg-faint"}`}>
                      <Icon name={isBlocked ? "block" : "check"} size={12} strokeWidth={2.2} />
                    </span>

                    <span className="min-w-0 flex-1">
                      <span
                        className={`mr-1.5 inline-block rounded px-1 py-px text-[0.5625rem] font-semibold tracking-wider uppercase ${
                          isBlocked ? "bg-warn/20 text-warn-ink" : "bg-white/8 text-fg-muted"
                        }`}
                      >
                        {isBlocked ? "blocked" : "pass"}
                      </span>
                      <span className={isBlocked ? "font-semibold text-warn-ink" : "text-fg-muted"}>
                        {ruleLabel(ev.rule_name)}
                      </span>
                      <span className="text-fg-subtle"> — {ev.detail}</span>
                    </span>
                  </button>
                  </Tooltip>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </Panel>
  );
}
