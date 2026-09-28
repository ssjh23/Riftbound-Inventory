export type CompletionStatus = "missing" | "partial" | "complete" | "overflow";

// Canonical rarity progression (not alphabetical) — used to order the rarity
// filter and anywhere else rarities are listed together.
const RARITY_ORDER = ["Common", "Uncommon", "Rare", "Epic", "Showcase"];

/** Sort comparator: known rarities follow RARITY_ORDER; anything unrecognized
 * (a future rarity we haven't special-cased yet) sorts after all known ones,
 * alphabetically among themselves, so it's never silently dropped. */
export function compareRarity(a: string, b: string): number {
  const ia = RARITY_ORDER.indexOf(a);
  const ib = RARITY_ORDER.indexOf(b);
  if (ia === -1 && ib === -1) return a.localeCompare(b);
  if (ia === -1) return 1;
  if (ib === -1) return -1;
  return ia - ib;
}

export function completionStatus(count: number, limit: number): CompletionStatus {
  if (limit <= 0) return count > 0 ? "overflow" : "complete";
  if (count === 0) return "missing";
  if (count < limit) return "partial";
  if (count === limit) return "complete";
  return "overflow";
}

export function progressPct(count: number, limit: number): number {
  if (limit <= 0) return 100;
  return Math.min(100, Math.round((count / limit) * 100));
}

export function collectionStats(
  cards: { count: number; foil_count: number; limit: number }[],
) {
  const complete = cards.filter((c) => {
    const s = completionStatus(c.count + c.foil_count, c.limit);
    return s !== "missing" && s !== "partial";
  }).length;
  const owned = cards.reduce((sum, c) => sum + c.count + c.foil_count, 0);
  return { total: cards.length, complete, owned };
}

interface CountLimit {
  count: number;
  foil_count: number;
  in_binder: boolean;
  limit: number;
  rarity: string;
}

// "Collected" = you have it: a physical copy (any finish) or it's in the binder.
export function isCollected(c: { count: number; foil_count: number; in_binder: boolean }) {
  return c.count + c.foil_count > 0 || c.in_binder;
}

// Rare and above are printed only as foils, so those cards have no non-foil
// counter — everything that isn't Common or Uncommon is foil-only.
const NON_FOIL_RARITIES = new Set(["common", "uncommon"]);
export function isFoilOnly(rarity: string): boolean {
  return !NON_FOIL_RARITIES.has(rarity.trim().toLowerCase());
}

// Showcase cards are bonus/variant printings, not part of the base set — they
// are excluded from overview progress counts so the dashboard shows how close
// you are to completing the "real" collection.
export function isShowcase(rarity: string): boolean {
  return rarity.trim().toLowerCase() === "showcase";
}


export interface DashboardStats {
  totalCopies: number; // every copy owned, across all cards
  uniqueOwned: number; // distinct cards with at least one copy
  totalUnique: number; // cards in the database
  overallPct: number; // uniqueOwned / totalUnique, 0–100
  playsetsComplete: number; // cards owned up to (or beyond) their limit
}

export function dashboardStats(cards: CountLimit[]): DashboardStats {
  // Showcase cards are variant printings and don't count toward base-set
  // completion — the overview measures progress on the collectible core.
  const base = cards.filter((c) => !isShowcase(c.rarity));
  const totalUnique = base.length;
  const uniqueOwned = base.filter(isCollected).length; // binder counts as collected
  const totalCopies = base.reduce((sum, c) => sum + c.count + c.foil_count, 0);
  // Playsets are physical copies vs the limit — the binder flag is excluded.
  const playsetsComplete = base.filter(
    (c) => c.limit > 0 && c.count + c.foil_count >= c.limit,
  ).length;
  const overallPct = totalUnique === 0 ? 0 : Math.round((uniqueOwned / totalUnique) * 100);
  return { totalCopies, uniqueOwned, totalUnique, overallPct, playsetsComplete };
}

export interface SetProgress {
  setCode: string;
  owned: number; // distinct cards owned in the set
  total: number; // distinct cards in the set
  pct: number; // 0–100
}

export function setBreakdown(
  cards: {
    set_code: string;
    count: number;
    foil_count: number;
    in_binder: boolean;
    rarity: string;
  }[],
): SetProgress[] {
  // Match dashboardStats: Showcase cards don't count toward set completion.
  const base = cards.filter((c) => !isShowcase(c.rarity));
  const bySet = new Map<string, { owned: number; total: number }>();
  for (const c of base) {
    const s = bySet.get(c.set_code) ?? { owned: 0, total: 0 };
    s.total += 1;
    if (isCollected(c)) s.owned += 1;
    bySet.set(c.set_code, s);
  }
  return [...bySet.entries()]
    .map(([setCode, { owned, total }]) => ({
      setCode,
      owned,
      total,
      pct: total === 0 ? 0 : Math.round((owned / total) * 100),
    }))
    .sort((a, b) => a.setCode.localeCompare(b.setCode));
}
