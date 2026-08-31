import Icon from "./Icon";

/* Buttons.
 *
 * Every variant implements hover / focus-visible / active / disabled, and the
 * focus ring comes from the global :focus-visible rule so it can never be
 * styled away. On coarse pointers every size grows to the 44px touch minimum.
 */

const BASE =
  "relative inline-flex items-center justify-center gap-2 rounded-full font-semibold " +
  "whitespace-nowrap select-none transition-[background-color,color,border-color,box-shadow,transform] " +
  "duration-200 ease-standard active:scale-[0.975] " +
  "disabled:pointer-events-none disabled:opacity-45 disabled:saturate-50 disabled:active:scale-100";

const VARIANTS = {
  // Hover deepens rather than brightens: white on --color-brand-hover is only
  // 3.69:1, so a "lighter on hover" primary would fail AA exactly while the
  // pointer is on it. The lift + glow carry the interaction feedback instead.
  primary: "bg-brand text-white shadow-glow hover:bg-brand-strong hover:shadow-lift",
  secondary: "border border-white/15 bg-white/10 text-fg hover:border-white/25 hover:bg-white/18",
  outline: "border border-hairline-strong bg-transparent text-fg-muted hover:border-fg-subtle hover:bg-surface-3 hover:text-fg",
  ghost: "bg-transparent text-fg-muted hover:bg-white/8 hover:text-fg",
  danger: "border border-danger/50 bg-danger-tint text-danger-ink hover:border-danger hover:bg-danger/25",
  subtle: "bg-surface-3 text-fg-muted hover:bg-surface-4 hover:text-fg",
};

const SIZES = {
  sm: "h-9 px-3.5 text-meta pointer-coarse:h-11 pointer-coarse:px-4",
  md: "h-11 px-5 text-meta",
  lg: "h-12 px-7 text-body",
};

export function Spinner({ size = 14, className = "" }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      className={`animate-spin shrink-0 ${className}`}
      aria-hidden="true"
      focusable="false"
    >
      <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeOpacity="0.28" strokeWidth="2.5" />
      <path d="M21 12a9 9 0 0 0-9-9" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
    </svg>
  );
}

export default function Button({
  variant = "primary",
  size = "md",
  icon,
  iconRight,
  loading = false,
  disabled = false,
  className = "",
  children,
  type = "button",
  ...rest
}) {
  return (
    <button
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={`${BASE} ${VARIANTS[variant] || VARIANTS.primary} ${SIZES[size] || SIZES.md} ${className}`}
      {...rest}
    >
      {loading ? <Spinner /> : icon ? <Icon name={icon} size={size === "lg" ? 18 : 16} /> : null}
      {children}
      {iconRight && !loading ? <Icon name={iconRight} size={size === "lg" ? 18 : 16} /> : null}
    </button>
  );
}

const ICON_SIZES = {
  sm: "h-9 w-9 pointer-coarse:h-11 pointer-coarse:w-11",
  md: "h-11 w-11",
  lg: "h-12 w-12",
};

/** Icon-only button. `label` is required — it becomes the accessible name. */
export function IconButton({
  icon,
  label,
  variant = "ghost",
  size = "md",
  loading = false,
  disabled = false,
  className = "",
  type = "button",
  ...rest
}) {
  return (
    <button
      type={type}
      aria-label={label}
      title={label}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={`${BASE} ${VARIANTS[variant] || VARIANTS.ghost} ${ICON_SIZES[size] || ICON_SIZES.md} p-0 ${className}`}
      {...rest}
    >
      {loading ? <Spinner size={16} /> : <Icon name={icon} size={size === "sm" ? 16 : 18} />}
    </button>
  );
}
