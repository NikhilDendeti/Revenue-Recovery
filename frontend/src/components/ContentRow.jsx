import { useCallback, useEffect, useRef, useState } from "react";
import Icon from "./ui/Icon";

/* A horizontally-scrollable row of cards.
 *
 * Scrolls by touch, by chevron, and by Tab (focusing a card scrolls it into
 * view). The row owns its overflow — the page body never scrolls sideways.
 */

export default function ContentRow({ title, caption, count, tone: toneClass = "bg-fg-subtle", children }) {
  const scroller = useRef(null);
  const [atStart, setAtStart] = useState(true);
  const [atEnd, setAtEnd] = useState(true);

  const sync = useCallback(() => {
    const el = scroller.current;
    if (!el) return;
    const max = el.scrollWidth - el.clientWidth;
    setAtStart(el.scrollLeft <= 4);
    setAtEnd(el.scrollLeft >= max - 4);
  }, []);

  useEffect(() => {
    const el = scroller.current;
    if (!el) return undefined;
    sync();
    el.addEventListener("scroll", sync, { passive: true });
    const observer = typeof ResizeObserver !== "undefined" ? new ResizeObserver(sync) : null;
    observer?.observe(el);
    return () => {
      el.removeEventListener("scroll", sync);
      observer?.disconnect();
    };
  }, [sync, count]);

  const page = (direction) => {
    const el = scroller.current;
    if (!el) return;
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    el.scrollBy({ left: direction * Math.max(240, el.clientWidth * 0.8), behavior: reduced ? "auto" : "smooth" });
  };

  return (
    <section className="group/row relative" aria-label={title}>
      <div className="mx-auto flex w-full max-w-[110rem] items-end justify-between gap-4 px-5 pb-3 sm:px-8 lg:px-10">
        <div className="min-w-0">
          <h3 className="flex items-center gap-2.5 text-h3 text-fg">
            <span aria-hidden="true" className={`h-3.5 w-1 rounded-full ${toneClass}`} />
            <span className="truncate">{title}</span>
            <span className="tabular shrink-0 rounded-full bg-surface-3 px-2 py-0.5 text-[0.6875rem] font-semibold text-fg-subtle">
              {count}
            </span>
          </h3>
          {caption && <p className="mt-1 truncate text-meta text-fg-subtle">{caption}</p>}
        </div>

        {/* Pointer-only paging controls. */}
        <div className="hidden shrink-0 items-center gap-1.5 opacity-0 transition-opacity duration-200 ease-standard group-hover/row:opacity-100 group-focus-within/row:opacity-100 md:flex">
          <button
            type="button"
            onClick={() => page(-1)}
            disabled={atStart}
            aria-label={`Scroll ${title} left`}
            className="grid h-9 w-9 place-items-center rounded-full border border-hairline-strong bg-surface-2/90 text-fg-muted backdrop-blur transition-colors hover:bg-surface-3 hover:text-fg disabled:pointer-events-none disabled:opacity-30"
          >
            <Icon name="chevronLeft" size={17} />
          </button>
          <button
            type="button"
            onClick={() => page(1)}
            disabled={atEnd}
            aria-label={`Scroll ${title} right`}
            className="grid h-9 w-9 place-items-center rounded-full border border-hairline-strong bg-surface-2/90 text-fg-muted backdrop-blur transition-colors hover:bg-surface-3 hover:text-fg disabled:pointer-events-none disabled:opacity-30"
          >
            <Icon name="chevronRight" size={17} />
          </button>
        </div>
      </div>

      <div className="relative mx-auto w-full max-w-[110rem]">
        {/* Edge fades, shown only where there is more content that way. */}
        <span
          aria-hidden="true"
          className={`pointer-events-none absolute inset-y-0 left-0 z-10 w-10 bg-gradient-to-r from-void to-transparent transition-opacity duration-200 ${
            atStart ? "opacity-0" : "opacity-100"
          }`}
        />
        <span
          aria-hidden="true"
          className={`pointer-events-none absolute inset-y-0 right-0 z-10 w-10 bg-gradient-to-l from-void to-transparent transition-opacity duration-200 ${
            atEnd ? "opacity-0" : "opacity-100"
          }`}
        />

        <div
          ref={scroller}
          role="group"
          aria-label={`${title} — scrollable row`}
          className="no-scrollbar flex w-full snap-x scroll-pl-5 gap-3 overflow-x-auto
            overflow-y-hidden overscroll-x-contain px-5 pt-1 pb-3 sm:scroll-pl-8 sm:gap-4 sm:px-8 lg:scroll-pl-10 lg:px-10"
        >
          {children}
        </div>
      </div>
    </section>
  );
}
