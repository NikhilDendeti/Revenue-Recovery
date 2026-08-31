import Icon from "./Icon";

/* Surfaces: the two container shapes the whole app is built from.
 * `Panel` is a titled region (ticker, console, audit trail).
 * `Card` is a plain elevated block (KPI tiles, chain sections, empty states).
 */

export function Card({ as: Tag = "div", elevated = false, interactive = false, className = "", children, ...rest }) {
  return (
    <Tag
      className={[
        "rounded-lg border border-hairline",
        elevated ? "bg-surface-3" : "bg-surface-2",
        "shadow-card",
        interactive
          ? "transition-[border-color,background-color,box-shadow,transform] duration-200 ease-standard hover:-translate-y-0.5 hover:border-hairline-strong hover:shadow-lift"
          : "",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
      {...rest}
    >
      {children}
    </Tag>
  );
}

export function PanelHeader({ icon, title, caption, actions, id }) {
  return (
    <header className="flex items-start justify-between gap-3 border-b border-hairline px-4 py-3.5 sm:px-5">
      <div className="min-w-0">
        <h2 id={id} className="flex items-center gap-2 text-h3 text-fg">
          {icon && <Icon name={icon} size={17} className="text-fg-subtle" />}
          <span className="truncate">{title}</span>
        </h2>
        {caption && <p className="mt-1 text-meta text-fg-subtle">{caption}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-1.5">{actions}</div>}
    </header>
  );
}

export default function Panel({ icon, title, caption, actions, className = "", bodyClassName = "", children, ...rest }) {
  const headingId = `panel-${String(title).toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
  return (
    <section
      aria-labelledby={headingId}
      className={`flex min-w-0 flex-col overflow-hidden rounded-xl border border-hairline bg-surface-2 shadow-card ${className}`}
      {...rest}
    >
      <PanelHeader icon={icon} title={title} caption={caption} actions={actions} id={headingId} />
      <div className={`min-h-0 flex-1 ${bodyClassName}`}>{children}</div>
    </section>
  );
}
