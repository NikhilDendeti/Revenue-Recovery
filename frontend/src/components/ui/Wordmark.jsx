/* The brand lockup: a red mark carrying the recovery loop, plus the wordmark.
 * Identical everywhere it appears — login, header, mobile nav.
 */

const SIZES = {
  sm: { tile: "h-7 w-7 rounded-md", glyph: 16, text: "text-[0.9375rem]" },
  md: { tile: "h-9 w-9 rounded-lg", glyph: 20, text: "text-[1.0625rem]" },
  lg: { tile: "h-12 w-12 rounded-xl", glyph: 26, text: "text-[1.5rem]" },
};

export default function Wordmark({ size = "md", showText = true, className = "" }) {
  const s = SIZES[size] || SIZES.md;

  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`}>
      <span className={`grid shrink-0 place-items-center bg-brand shadow-glow ${s.tile}`}>
        <svg viewBox="0 0 64 64" width={s.glyph} height={s.glyph} aria-hidden="true" focusable="false">
          <path
            d="M32 14a18 18 0 1 1-15.59 9"
            fill="none"
            stroke="#fff"
            strokeWidth="7"
            strokeLinecap="round"
          />
          <path d="M27 6.5 40 14 27 21.5Z" fill="#fff" />
        </svg>
      </span>
      {showText && (
        <span className={`font-display font-extrabold tracking-[-0.045em] uppercase ${s.text}`}>
          <span className="text-fg">Recover</span>
          <span className="text-brand-ink">AI</span>
        </span>
      )}
      {!showText && <span className="sr-only">RecoverAI</span>}
    </span>
  );
}
