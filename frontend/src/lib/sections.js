/* The dashboard's four in-page sections. Shared by the desktop header nav,
 * the mobile bottom nav, and the IntersectionObserver that tracks which one is
 * in view — one list, so the two navs can never drift apart.
 */

export const SECTIONS = [
  { id: "overview", label: "Overview", icon: "home" },
  { id: "transactions", label: "Transactions", icon: "layers" },
  { id: "live", label: "Live", icon: "activity" },
  { id: "audit", label: "Audit", icon: "list" },
];

export const SECTION_IDS = SECTIONS.map((s) => s.id);

/** The one search input the header and the filter bar both drive. */
export const SEARCH_INPUT_ID = "transaction-search";
