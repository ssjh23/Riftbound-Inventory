/**
 * View state that survives a page reload.
 *
 * Mobile browsers discard backgrounded tabs and re-run the document on return,
 * which wipes every `useState`. The auth token already survives (localStorage,
 * see auth.ts) but the view did not — so the app came back logged in on the
 * wrong screen, with filters and drill-downs reset.
 *
 * sessionStorage is the right store for this: it is scoped to the browser tab
 * and survives that tab being reloaded or discarded and restored, but a
 * brand-new tab starts clean. That is exactly the lifetime a filter or a
 * "which user am I browsing" selection should have — unlike the token, it
 * should not follow you into a fresh window.
 */

import { useEffect, useRef, useState } from "react";

const PREFIX = "riftbound.view.";

/** Same-shape check between a restored value and the default. Guards against a
 * stale entry of the wrong type crashing a consumer (e.g. a string where the
 * code expects `string[]` and calls `.includes`). */
function sameShape(restored: unknown, initial: unknown): boolean {
  if (Array.isArray(initial)) return Array.isArray(restored);
  if (initial === null) return true; // nullable slots (e.g. a selected id) accept anything
  return typeof restored === typeof initial;
}

export function readPersisted<T>(key: string, initial: T): T {
  try {
    const raw = sessionStorage.getItem(PREFIX + key);
    if (raw === null) return initial;
    const parsed = JSON.parse(raw) as unknown;
    return sameShape(parsed, initial) ? (parsed as T) : initial;
  } catch {
    return initial;
  }
}

export function writePersisted(key: string, value: unknown): void {
  try {
    sessionStorage.setItem(PREFIX + key, JSON.stringify(value));
  } catch {
    // Safari private mode throws on write, and the quota can fill. Losing
    // persistence is not worth breaking a render over — degrade to in-memory.
  }
}

/** Drop every persisted view value. Called on logout so one account's
 * drill-downs never greet the next login. */
export function clearPersistedView(): void {
  try {
    const stale = Object.keys(sessionStorage).filter((k) => k.startsWith(PREFIX));
    stale.forEach((k) => sessionStorage.removeItem(k));
  } catch {
    // Storage unavailable — nothing was persisted in the first place.
  }
}

/**
 * `useState`, but restored from and mirrored to sessionStorage.
 *
 * Pass `key: null` to opt out and behave as plain `useState`. That is what
 * keeps the three Collection render modes (your shelf, someone else's, trade)
 * from sharing one bucket of filters.
 */
export function usePersistedState<T>(
  key: string | null,
  initial: T,
): [T, React.Dispatch<React.SetStateAction<T>>] {
  const [value, setValue] = useState<T>(() => (key ? readPersisted(key, initial) : initial));

  // Skip the write on the first run: it would only re-save what we just read,
  // and for a null key there is nothing to write at all.
  const mounted = useRef(false);
  useEffect(() => {
    if (!mounted.current) {
      mounted.current = true;
      return;
    }
    if (key) writePersisted(key, value);
  }, [key, value]);

  return [value, setValue];
}
