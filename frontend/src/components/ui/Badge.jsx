import Icon from "./Icon";
import { statusMeta, tone } from "../../lib/format";

const SIZES = {
  xs: "h-5 gap-1 px-1.5 text-[0.625rem]",
  sm: "h-6 gap-1.5 px-2 text-[0.6875rem]",
  md: "h-7 gap-1.5 px-2.5 text-meta",
};

export default function Badge({ tone: toneName = "neutral", icon, size = "sm", className = "", children, ...rest }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border font-semibold tracking-wide ${
        tone(toneName).chip
      } ${SIZES[size] || SIZES.sm} ${className}`}
      {...rest}
    >
      {icon && <Icon name={icon} size={size === "md" ? 13 : 11} strokeWidth={2.1} />}
      <span className="truncate">{children}</span>
    </span>
  );
}

export function StatusBadge({ status, size = "sm", short = false, className = "" }) {
  const meta = statusMeta(status);
  return (
    <Badge tone={meta.tone} icon={meta.icon} size={size} className={className}>
      {short ? meta.short : meta.label}
    </Badge>
  );
}

export function Dot({ tone: toneName = "neutral", pulse = false, className = "" }) {
  return (
    <span
      aria-hidden="true"
      className={`inline-block h-2 w-2 shrink-0 rounded-full ${tone(toneName).solid} ${
        pulse ? "animate-live-pulse" : ""
      } ${className}`}
    />
  );
}
