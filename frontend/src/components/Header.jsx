export default function Header({ connected, replaying, onReplay, onLogout }) {
  return (
    <header className="flex flex-wrap items-center justify-between gap-4 border-b border-line px-6 py-5 sm:px-10">
      <div>
        <p className="font-mono text-xs uppercase tracking-widest text-accent-ink">RecoverAI · Recovery Room</p>
        <h1 className="font-serif text-2xl font-semibold text-ink sm:text-3xl">Live recovery batch</h1>
      </div>
      <div className="flex items-center gap-4">
        <span className="flex items-center gap-2 font-mono text-xs text-ink-faint">
          <span
            className={`h-2 w-2 rounded-full ${connected ? "bg-accent" : "bg-danger"}`}
            aria-hidden="true"
          />
          {connected ? "live" : "disconnected"}
        </span>
        <button
          onClick={onReplay}
          disabled={replaying}
          className="rounded-md border border-accent bg-accent-soft px-4 py-2 font-sans text-sm font-medium text-accent-ink transition hover:bg-accent/20 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {replaying ? "Replaying…" : "Trigger batch replay"}
        </button>
        <button onClick={onLogout} className="font-mono text-xs text-ink-faint hover:text-ink">
          log out
        </button>
      </div>
    </header>
  );
}
