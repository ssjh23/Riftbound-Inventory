/**
 * Top-level tab routing via `location.hash`.
 *
 * The tab lives in the URL (`/#/collection`) rather than in React state alone,
 * so it survives a document reload. That matters most on phones: mobile
 * browsers discard backgrounded tabs to reclaim memory, and returning to one
 * re-runs the document from scratch — which used to drop the user back on
 * Overview. It also makes the device back button step between tabs instead of
 * leaving the app.
 *
 * The hash never reaches the server, so no dev-server or nginx config is
 * involved. Kept here rather than in App.tsx so it can be unit-tested without
 * pulling in every screen.
 */

export type Tab = "overview" | "collection" | "achievements" | "settings" | "decks" | "community";

export const TABS: Tab[] = ["overview", "collection", "achievements", "settings", "decks", "community"];

export const TAB_LABELS: Record<Tab, string> = {
  overview: "Overview",
  collection: "Collection",
  achievements: "Achievements",
  settings: "Settings",
  decks: "Decks",
  community: "Community",
};

export const DEFAULT_TAB: Tab = "overview";

/** `"#/collection"` → `"collection"`. Anything unrecognised (empty hash, a
 * stale link, a typo) yields null so the caller can fall back to the default
 * rather than rendering a blank shell. */
export function readTabFromHash(hash: string): Tab | null {
  const slug = hash.replace(/^#\/?/, "").trim().toLowerCase();
  return (TABS as string[]).includes(slug) ? (slug as Tab) : null;
}

/** `"collection"` → `"#/collection"`. */
export function tabToHash(tab: Tab): string {
  return `#/${tab}`;
}
