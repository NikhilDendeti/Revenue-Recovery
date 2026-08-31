import { useState } from "react";

const SIDES = {
  top: "bottom-full left-1/2 mb-2 -translate-x-1/2",
  bottom: "top-full left-1/2 mt-2 -translate-x-1/2",
  left: "right-full top-1/2 mr-2 -translate-y-1/2",
  right: "left-full top-1/2 ml-2 -translate-y-1/2",
};

export default function Tooltip({ label, side = "top", children, className = "" }) {
  const [dismissed, setDismissed] = useState(false);

  if (!label) return children;

  return (
    <span
      className={`group/tt relative inline-flex ${className}`}
      onMouseEnter={() => setDismissed(false)}
      onMouseLeave={() => setDismissed(false)}
      onKeyDown={(e) => {
        if (e.key === "Escape") setDismissed(true);
      }}
    >
      {children}
      <span className="sr-only"> — {label}</span>
      <span
        role="tooltip"
        aria-hidden="true"
        className={`pointer-events-none absolute z-50 w-max max-w-[min(16rem,72vw)] rounded-md border border-hairline-strong
          bg-surface-4 px-2.5 py-1.5 text-[0.6875rem] leading-snug font-medium text-fg shadow-lift
          opacity-0 transition-opacity duration-150 ease-standard
          group-hover/tt:opacity-100 group-focus-within/tt:opacity-100
          ${dismissed ? "!opacity-0" : ""} ${SIDES[side] || SIDES.top}`}
      >
        {label}
      </span>
    </span>
  );
}
