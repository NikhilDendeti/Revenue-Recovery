export function inr(amount) {
  return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(
    Number(amount) || 0
  );
}

export function inrCompact(amount) {
  const n = Number(amount) || 0;
  const abs = Math.abs(n);
  if (abs >= 1e7) return `₹${(n / 1e7).toFixed(abs >= 1e8 ? 0 : 2)}Cr`;
  if (abs >= 1e5) return `₹${(n / 1e5).toFixed(abs >= 1e6 ? 0 : 2)}L`;
  if (abs >= 1e3) return `₹${(n / 1e3).toFixed(abs >= 1e4 ? 0 : 1)}K`;
  return inr(n);
}

export function timeAgo(iso) {
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export function absoluteTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });
}

export function humanize(value) {
  if (!value) return "—";
  const text = String(value).replace(/[_-]+/g, " ").trim();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export const TONE = {
  brand: {
    text: "text-brand-ink",
    bg: "bg-brand-tint",
    border: "border-brand/45",
    solid: "bg-brand",
    rail: "bg-brand",
    chip: "bg-brand-tint text-brand-ink border-brand/45",
  },
  ok: {
    text: "text-ok-ink",
    bg: "bg-ok-tint",
    border: "border-ok/45",
    solid: "bg-ok",
    rail: "bg-ok",
    chip: "bg-ok-tint text-ok-ink border-ok/45",
  },
  danger: {
    text: "text-danger-ink",
    bg: "bg-danger-tint",
    border: "border-danger/45",
    solid: "bg-danger",
    rail: "bg-danger",
    chip: "bg-danger-tint text-danger-ink border-danger/45",
  },
  alert: {
    text: "text-alert-ink",
    bg: "bg-alert-tint",
    border: "border-alert/45",
    solid: "bg-alert",
    rail: "bg-alert",
    chip: "bg-alert-tint text-alert-ink border-alert/45",
  },
  warn: {
    text: "text-warn-ink",
    bg: "bg-warn-tint",
    border: "border-warn/45",
    solid: "bg-warn",
    rail: "bg-warn",
    chip: "bg-warn-tint text-warn-ink border-warn/45",
  },
  info: {
    text: "text-info-ink",
    bg: "bg-info-tint",
    border: "border-info/45",
    solid: "bg-info",
    rail: "bg-info",
    chip: "bg-info-tint text-info-ink border-info/45",
  },
  neutral: {
    text: "text-neutral-ink",
    bg: "bg-neutral-tint",
    border: "border-neutral/45",
    solid: "bg-neutral",
    rail: "bg-neutral",
    chip: "bg-neutral-tint text-neutral-ink border-neutral/45",
  },
};

export function tone(name) {
  return TONE[name] || TONE.neutral;
}

export const STATUS_META = {
  open: { label: "Open", short: "Open", tone: "neutral", icon: "dot", blurb: "Detected, not yet picked up" },
  processing: { label: "Processing", short: "In flight", tone: "info", icon: "activity", blurb: "The agent is working it" },
  recovered: { label: "Recovered", short: "Recovered", tone: "ok", icon: "check", blurb: "Payment collected" },
  failed: { label: "Failed", short: "Failed", tone: "danger", icon: "close", blurb: "Acted, customer did not pay" },
  escalated: { label: "Escalated", short: "Escalated", tone: "alert", icon: "escalate", blurb: "Handed to a human" },
  held: { label: "Held", short: "Held", tone: "warn", icon: "pause", blurb: "Guardrail is holding the action" },
};

export function statusMeta(status) {
  return STATUS_META[status] || STATUS_META.open;
}

export const STATUS_GROUPS = [
  {
    key: "attention",
    title: "Needs your attention",
    caption: "Escalated, held, or failed — a human decision is the next step",
    statuses: ["escalated", "held", "failed"],
  },
  {
    key: "inflight",
    title: "In flight",
    caption: "The agent is diagnosing, deciding, or acting right now",
    statuses: ["processing"],
  },
  {
    key: "atrisk",
    title: "At risk",
    caption: "Detected revenue waiting on the next replay",
    statuses: ["open"],
  },
  {
    key: "recovered",
    title: "Recovered",
    caption: "Closed out — money back in the merchant's account",
    statuses: ["recovered"],
  },
];

export const KIND_META = {
  payment_degradation: { label: "Payment degradation", short: "Payment", icon: "card" },
  subscription_failure: { label: "Subscription failure", short: "Subscription", icon: "repeat" },
  receivable: { label: "B2B receivable", short: "Receivable", icon: "invoice" },
  checkout_dropoff: { label: "Checkout drop-off", short: "Drop-off", icon: "cart" },
};

export function kindMeta(kind) {
  return KIND_META[kind] || { label: humanize(kind), short: humanize(kind), icon: "card" };
}

export const KIND_FILTERS = [
  { value: "payment_degradation", label: "Payment" },
  { value: "subscription_failure", label: "Subscription" },
  { value: "receivable", label: "Receivable" },
  { value: "checkout_dropoff", label: "Drop-off" },
];

export const STATUS_FILTERS = [
  { value: "open", label: "Open" },
  { value: "processing", label: "Processing" },
  { value: "recovered", label: "Recovered" },
  { value: "held", label: "Held" },
  { value: "escalated", label: "Escalated" },
  { value: "failed", label: "Failed" },
];

export const ACTION_LABEL = {
  retry_order: "Re-attempt same order",
  new_payment_link: "Fresh payment link",
  registration_link: "Registration link",
  invoice_reminder: "Invoice reminder",
  voice_reminder: "Hinglish voice reminder",
  escalate: "Escalate to human queue",
  hold: "Hold — guardrail cooldown",
  retry: "Payment retry",
  email: "Email",
  whatsapp: "WhatsApp",
  voice: "Voice call",
};

export const ACTION_ICON = {
  retry_order: "repeat",
  new_payment_link: "card",
  registration_link: "external",
  invoice_reminder: "invoice",
  voice_reminder: "sound",
  escalate: "escalate",
  hold: "pause",
  retry: "repeat",
  email: "invoice",
  whatsapp: "phone",
  voice: "sound",
};

export function actionIcon(value) {
  return ACTION_ICON[value] || "zap";
}

export function actionLabel(value) {
  return ACTION_LABEL[value] || humanize(value);
}

export const ACTION_RESULT_META = {
  success: { label: "Success", tone: "ok", icon: "check" },
  failed: { label: "Failed", tone: "danger", icon: "close" },
  pending: { label: "Pending", tone: "info", icon: "clock" },
  simulated: { label: "Simulated", tone: "neutral", icon: "beaker" },
};

export const RULE_LABEL = {
  max_retry_attempts: "Max retry attempts",
  contact_frequency_cap: "Contact frequency cap",
  cooldown_between_retries: "Cooldown between retries",
  spend_ceiling: "Spend / action ceiling",
  confidence_floor: "Confidence floor",
  compliance_hours: "Compliance hours",
};

export const RULE_HELP = {
  max_retry_attempts: "Caps how many times one transaction may be retried before it must go to a human.",
  contact_frequency_cap: "Stops the agent contacting the same customer more than once in 24 hours.",
  cooldown_between_retries: "Forces a wait after a card decline instead of retrying immediately.",
  spend_ceiling: "Blocks any action on a transaction above the per-action value ceiling.",
  confidence_floor: "Requires the diagnosis to clear a confidence threshold before acting.",
  compliance_hours: "Restricts B2B outreach to permitted business hours.",
};

export function ruleLabel(name) {
  return RULE_LABEL[name] || humanize(name);
}

export const GUARDRAIL_RESULT_META = {
  blocked: { label: "Blocked", tone: "warn", icon: "block" },
  passed: { label: "Passed", tone: "ok", icon: "check" },
};

export function guardrailResultMeta(result) {
  return GUARDRAIL_RESULT_META[result] || { label: humanize(result), tone: "neutral", icon: "dot" };
}

export const ACTOR_META = {
  agent: { label: "Agent", icon: "bot", tone: "brand" },
  system: { label: "System", icon: "cog", tone: "neutral" },
  human: { label: "Human", icon: "user", tone: "info" },
};

export function actorMeta(actor) {
  return ACTOR_META[actor] || { label: humanize(actor), icon: "cog", tone: "neutral" };
}

function pill(meta) {
  return { label: meta.label, icon: meta.icon, tone: meta.tone, cls: tone(meta.tone).chip };
}

export const OUTCOME_STYLE = {
  recovered: pill(STATUS_META.recovered),
  failed: pill(STATUS_META.failed),
  escalated: pill(STATUS_META.escalated),
  held: pill(STATUS_META.held),
};

export const STATUS_STYLE = {
  open: pill(STATUS_META.open),
  processing: pill(STATUS_META.processing),
  recovered: OUTCOME_STYLE.recovered,
  failed: OUTCOME_STYLE.failed,
  escalated: OUTCOME_STYLE.escalated,
  held: OUTCOME_STYLE.held,
};
