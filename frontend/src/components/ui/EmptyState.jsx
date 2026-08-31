import Icon from "./Icon";
import Button from "./Button";

export default function EmptyState({
  icon = "inbox",
  title,
  description,
  action,
  onAction,
  variant = "empty",
  size = "md",
  className = "",
}) {
  const isError = variant === "error";
  const pad = size === "sm" ? "px-5 py-8" : "px-6 py-12";

  return (
    <div
      role={isError ? "alert" : undefined}
      className={`flex flex-col items-center justify-center text-center ${pad} ${className}`}
    >
      <span
        className={`mb-4 flex h-12 w-12 items-center justify-center rounded-full border ${
          isError ? "border-alert/40 bg-alert-tint text-alert-ink" : "border-hairline bg-surface-3 text-fg-subtle"
        }`}
      >
        <Icon name={isError ? "alert" : icon} size={22} />
      </span>
      <p className="text-h3 text-fg">{title}</p>
      {description && <p className="mt-1.5 max-w-sm text-meta text-fg-subtle">{description}</p>}
      {action && onAction && (
        <Button
          variant={isError ? "danger" : "outline"}
          size="sm"
          icon={isError ? "refresh" : undefined}
          className="mt-5"
          onClick={onAction}
        >
          {action}
        </Button>
      )}
    </div>
  );
}
