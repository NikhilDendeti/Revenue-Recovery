import { useEffect, useRef, useState } from "react";
import Icon from "./ui/Icon";
import Button, { IconButton } from "./ui/Button";
import Wordmark from "./ui/Wordmark";
import { SECTIONS, SEARCH_INPUT_ID } from "../lib/sections";
import { scrollToSection, useScrolled } from "../lib/useNavState";

function OperatorMenu({ connected, onLogout }) {
  const [open, setOpen] = useState(false);
  const wrapper = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const onDown = (e) => {
      if (!wrapper.current?.contains(e.target)) setOpen(false);
    };
    const onKey = (e) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={wrapper} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="true"
        aria-expanded={open}
        aria-label="Operator menu"
        className="grid h-10 w-10 place-items-center rounded-full border border-hairline-strong bg-surface-3 text-fg-muted transition-colors duration-200 hover:border-fg-faint hover:text-fg pointer-coarse:h-11 pointer-coarse:w-11"
      >
        <Icon name="user" size={17} />
      </button>

      {open && (
        <div
          aria-label="Operator"
          className="animate-scale-in absolute right-0 z-50 mt-2 w-60 origin-top-right overflow-hidden rounded-xl border border-hairline-strong bg-surface-2 shadow-modal"
        >
          <div className="border-b border-hairline px-4 py-3">
            <p className="text-meta font-semibold text-fg">Operator session</p>
            <p className="mt-1 flex items-center gap-1.5 text-[0.75rem] text-fg-subtle">
              <span
                aria-hidden="true"
                className={`h-1.5 w-1.5 rounded-full ${connected ? "bg-ok" : "bg-fg-faint"}`}
              />
              {connected ? "Live feed connected" : "Live feed disconnected"}
            </p>
          </div>
          <button
            type="button"
            onClick={() => {
              setOpen(false);
              onLogout();
            }}
            className="flex w-full items-center gap-2.5 px-4 py-3 text-left text-meta text-fg-muted transition-colors hover:bg-white/6 hover:text-fg"
          >
            <Icon name="logout" size={16} />
            Log out
          </button>
        </div>
      )}
    </div>
  );
}

export default function Header({ connected, replaying, onReplay, onLogout, query, onQuery, activeSection }) {
  const scrolled = useScrolled(28);
  const [searchOpen, setSearchOpen] = useState(false);
  const searchRef = useRef(null);

  useEffect(() => {
    if (searchOpen) searchRef.current?.focus();
  }, [searchOpen]);

  const jumpToSearch = () => {
    scrollToSection("transactions");
    setTimeout(() => document.getElementById(SEARCH_INPUT_ID)?.focus(), 320);
  };

  return (
    <header
      data-app-chrome
      className={`fixed inset-x-0 top-0 z-50 transition-[background-color,border-color,box-shadow] duration-300 ease-standard ${
        scrolled
          ? "border-b border-hairline bg-void/92 shadow-card backdrop-blur-xl"
          : "border-b border-transparent bg-gradient-to-b from-void/90 via-void/45 to-transparent"
      }`}
    >
      <div className="mx-auto flex h-16 w-full max-w-[110rem] items-center gap-2 px-5 sm:h-18 sm:gap-3 sm:px-8 lg:px-10">
        <button
          type="button"
          onClick={() => scrollToSection("overview")}
          aria-label="RecoverAI — back to overview"
          className="shrink-0 rounded-lg"
        >
          <span className="sm:hidden">
            <Wordmark size="sm" />
          </span>
          <span className="hidden sm:block">
            <Wordmark size="md" />
          </span>
        </button>

        <nav aria-label="Dashboard sections" className="ml-4 hidden items-center gap-0.5 lg:flex">
          {SECTIONS.map((s) => {
            const active = activeSection === s.id;
            return (
              <button
                key={s.id}
                type="button"
                onClick={() => scrollToSection(s.id)}
                aria-current={active ? "true" : undefined}
                className={`relative rounded-md px-3 py-2 text-meta font-medium transition-colors duration-200 ${
                  active ? "text-fg" : "text-fg-subtle hover:text-fg-muted"
                }`}
              >
                {s.label}
                {active && (
                  <span aria-hidden="true" className="absolute inset-x-2.5 -bottom-0.5 h-0.5 rounded-full bg-brand" />
                )}
              </button>
            );
          })}
        </nav>

        <div className="ml-auto flex shrink-0 items-center gap-1.5 sm:gap-2.5">
          <div className="hidden items-center lg:flex">
            {searchOpen ? (
              <div className="relative">
                <label htmlFor="header-search" className="sr-only">
                  Search transactions
                </label>
                <Icon
                  name="search"
                  size={15}
                  className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-fg-subtle"
                />
                <input
                  id="header-search"
                  ref={searchRef}
                  type="search"
                  value={query}
                  onChange={(e) => onQuery(e.target.value)}
                  onBlur={() => {
                    if (!query) setSearchOpen(false);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Escape") {
                      onQuery("");
                      setSearchOpen(false);
                    }
                    if (e.key === "Enter") scrollToSection("transactions");
                  }}
                  placeholder="Search transactions…"
                  className="h-10 w-64 rounded-full border border-hairline-strong bg-surface-2 pr-3 pl-9 text-meta text-fg placeholder:text-fg-subtle focus:border-brand [&::-webkit-search-cancel-button]:appearance-none"
                />
              </div>
            ) : (
              <IconButton icon="search" label="Search transactions" size="sm" onClick={() => setSearchOpen(true)} />
            )}
          </div>
          <span className="lg:hidden">
            <IconButton icon="search" label="Search transactions" size="sm" onClick={jumpToSearch} />
          </span>

          <span
            className={`hidden items-center gap-1.5 rounded-full border px-2.5 py-1 text-[0.625rem] font-semibold tracking-wide uppercase sm:inline-flex ${
              connected ? "border-brand/45 bg-brand-tint text-brand-ink" : "border-hairline-strong bg-surface-3 text-fg-subtle"
            }`}
          >
            <span
              aria-hidden="true"
              className={`h-1.5 w-1.5 rounded-full ${connected ? "animate-live-pulse bg-brand" : "bg-fg-faint"}`}
            />
            {connected ? "Live" : "Offline"}
          </span>

          <span className="hidden sm:block">
            <Button size="sm" icon={replaying ? undefined : "play"} loading={replaying} onClick={onReplay}>
              {replaying ? "Replaying…" : "Replay batch"}
            </Button>
          </span>
          <span className="sm:hidden">
            <IconButton
              icon="play"
              label={replaying ? "Batch replay in progress" : "Trigger batch replay"}
              size="sm"
              variant="primary"
              loading={replaying}
              onClick={onReplay}
            />
          </span>

          <OperatorMenu connected={connected} onLogout={onLogout} />
        </div>
      </div>
    </header>
  );
}
