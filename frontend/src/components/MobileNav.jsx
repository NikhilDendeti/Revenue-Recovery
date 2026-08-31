import Icon from "./ui/Icon";
import { SECTIONS } from "../lib/sections";
import { scrollToSection } from "../lib/useNavState";

/* Touch navigation.
 *
 * A bottom bar rather than a hamburger drawer: navigation stays visible, the
 * targets sit where a thumb actually reaches, and the active section is
 * readable without opening anything. `<main>` carries matching bottom padding
 * (`pb-safe-nav`) so nothing ever hides underneath it.
 */

export default function MobileNav({ activeSection }) {
  return (
    <nav
      data-app-chrome
      aria-label="Dashboard sections (mobile)"
      className="pb-safe fixed inset-x-0 bottom-0 z-50 border-t border-hairline bg-void/95 backdrop-blur-xl lg:hidden"
    >
      <ul className="mx-auto flex max-w-lg items-stretch">
        {SECTIONS.map((s) => {
          const active = activeSection === s.id;
          return (
            <li key={s.id} className="flex-1">
              <button
                type="button"
                onClick={() => scrollToSection(s.id)}
                aria-current={active ? "true" : undefined}
                className={`relative flex h-16 w-full flex-col items-center justify-center gap-1 transition-colors duration-200 ${
                  active ? "text-brand-ink" : "text-fg-subtle"
                }`}
              >
                {active && (
                  <span aria-hidden="true" className="absolute inset-x-6 top-0 h-0.5 rounded-full bg-brand" />
                )}
                <Icon name={s.icon} size={19} strokeWidth={active ? 2.1 : 1.75} />
                <span className={`text-[0.6875rem] ${active ? "font-semibold" : "font-medium"}`}>{s.label}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
