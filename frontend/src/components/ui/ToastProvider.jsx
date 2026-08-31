import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ToastContext } from "../../lib/toastContext";
import { tone } from "../../lib/format";
import Icon from "./Icon";

/* Toasts.
 *
 * The app's one channel for "this happened" and "this failed" — the surfaces
 * that used to swallow rejections with `.catch(() => {})` route here instead.
 * Toasts announce politely, auto-dismiss, pause while hovered or focused, and
 * never steal focus.
 */

const TONE_ICON = { ok: "check", danger: "alert", alert: "alert", warn: "alert", info: "info", brand: "sparkle" };

function ToastItem({ toast, onDismiss, onPause, onResume }) {
  const isError = toast.tone === "danger" || toast.tone === "alert";
  const t = tone(toast.tone);

  return (
    <li
      role={isError ? "alert" : "status"}
      className={`animate-fade-up pointer-events-auto flex w-full items-start gap-3 rounded-lg border ${t.border}
        bg-surface-3/95 p-3.5 shadow-lift backdrop-blur-md sm:w-88`}
      onMouseEnter={onPause}
      onMouseLeave={onResume}
      onFocus={onPause}
      onBlur={onResume}
    >
      <span className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full ${t.bg} ${t.text}`}>
        <Icon name={TONE_ICON[toast.tone] || "info"} size={14} strokeWidth={2.1} />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-meta font-semibold text-fg">{toast.title}</p>
        {toast.description && <p className="mt-0.5 text-[0.8125rem] leading-snug text-fg-subtle">{toast.description}</p>}
      </div>
      <button
        type="button"
        onClick={onDismiss}
        aria-label={`Dismiss: ${toast.title}`}
        className="-m-1 shrink-0 rounded-full p-1.5 text-fg-faint transition-colors hover:bg-white/8 hover:text-fg"
      >
        <Icon name="close" size={14} />
      </button>
    </li>
  );
}

export default function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const timers = useRef(new Map());
  const seq = useRef(0);

  const dismiss = useCallback((id) => {
    const timer = timers.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timers.current.delete(id);
    }
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const schedule = useCallback(
    (id, duration) => {
      if (!duration) return;
      const existing = timers.current.get(id);
      if (existing) clearTimeout(existing);
      timers.current.set(
        id,
        setTimeout(() => dismiss(id), duration)
      );
    },
    [dismiss]
  );

  const push = useCallback(
    ({ title, description, tone: toneName = "info", duration = 5200 }) => {
      const id = ++seq.current;
      setToasts((prev) => [...prev.slice(-3), { id, title, description, tone: toneName, duration }]);
      schedule(id, duration);
      return id;
    },
    [schedule]
  );

  // Clear every pending timer if the provider unmounts.
  useEffect(() => {
    const pending = timers.current;
    return () => {
      pending.forEach((timer) => clearTimeout(timer));
      pending.clear();
    };
  }, []);

  const value = useMemo(
    () => ({
      push,
      dismiss,
      success: (title, description) => push({ title, description, tone: "ok" }),
      error: (title, description) => push({ title, description, tone: "danger", duration: 8000 }),
      info: (title, description) => push({ title, description, tone: "info" }),
    }),
    [push, dismiss]
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
      <ul
        aria-live="polite"
        aria-label="Notifications"
        className="pointer-events-none fixed inset-x-3 top-3 z-[100] flex flex-col gap-2.5
          sm:inset-x-auto sm:top-auto sm:right-5 sm:bottom-5 sm:items-end"
      >
        {toasts.map((t) => (
          <ToastItem
            key={t.id}
            toast={t}
            onDismiss={() => dismiss(t.id)}
            onPause={() => {
              const timer = timers.current.get(t.id);
              if (timer) {
                clearTimeout(timer);
                timers.current.delete(t.id);
              }
            }}
            onResume={() => schedule(t.id, t.duration)}
          />
        ))}
      </ul>
    </ToastContext.Provider>
  );
}
