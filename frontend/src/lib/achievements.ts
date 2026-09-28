/**
 * Achievement definitions and progress computation.
 *
 * Derived entirely from the already-loaded card list (the same data the
 * Overview dashboard uses) — no backend storage needed. Two families:
 *
 *   - "completion": percentage of the BASE set owned. Showcase cards are
 *     excluded, matching the Overview dashboard's definition of "complete"
 *     (lib/collection.ts's dashboardStats/setBreakdown). Reaching 100% is
 *     the "base set complete" milestone — it does not require any Showcase
 *     cards.
 *   - "rarity": collecting cards of a single rarity (Rare / Epic / Showcase)
 *     — the chase collectors actually care about, since those rarities are
 *     foil-only prints (see isFoilOnly in collection.ts).
 *
 * Each family is split into "global" (across every set combined) and "set"
 * (one set at a time) achievements, per set code.
 *
 * Rather than one achievement per percentage checkpoint, each achievement
 * carries a single progressive badge tier — Bronze (25%+), Silver (50%+),
 * Gold (75%+), Prismatic (100%) — computed from current/target. A handful
 * of one-shot starter achievements (first card, first playset) only ever
 * reach Bronze, since they have no meaningful further tiers.
 */

import { isCollected, isShowcase } from "./collection";

export type AchievementCategory = "completion" | "rarity";
export type AchievementScope = "global" | "set";
export type BadgeTier = "bronze" | "silver" | "gold" | "prismatic";

export interface Achievement {
  id: string;
  category: AchievementCategory;
  scope: AchievementScope;
  setCode: string | null; // null for global achievements
  title: string;
  description: string;
  current: number;
  target: number;
  tier: BadgeTier | null; // null = not yet unlocked (no badge)
}

interface MiniCard {
  set_code: string;
  rarity: string;
  count: number;
  foil_count: number;
  in_binder: boolean;
  limit: number;
}

const CHASE_RARITIES = ["Rare", "Epic", "Showcase"] as const;

// Flavor names, one per achievement family, reused for both the global and
// per-set version (the per-set title is just `${setLabel}: ${name}`, and the
// UI's section headers already communicate which scope you're looking at).
const COMPLETION_NAME = "Archivist";
const RARITY_NAME: Record<(typeof CHASE_RARITIES)[number], string> = {
  Rare: "Rare Seeker",
  Epic: "Epic Vanguard",
  Showcase: "Prism Chaser",
};

/** Bronze at 25%, Silver at 50%, Gold at 75%, Prismatic at 100%. */
function tierFor(current: number, target: number): BadgeTier | null {
  if (target <= 0) return null;
  const pct = (current / target) * 100;
  if (pct >= 100) return "prismatic";
  if (pct >= 75) return "gold";
  if (pct >= 50) return "silver";
  if (pct >= 25) return "bronze";
  return null;
}

function matchesRarity(card: MiniCard, rarity: string): boolean {
  return card.rarity.trim().toLowerCase() === rarity.toLowerCase();
}

function completionAchievements(
  cards: MiniCard[],
  scope: AchievementScope,
  setCode: string | null,
  setLabel: string,
): Achievement[] {
  const base = cards.filter((c) => !isShowcase(c.rarity));
  const owned = base.filter(isCollected).length;
  const total = base.length;
  const idPrefix = scope === "global" ? "completion-global" : `completion-set-${setCode}`;

  const collector: Achievement = {
    id: `${idPrefix}-collector`,
    category: "completion",
    scope,
    setCode,
    title: scope === "global" ? COMPLETION_NAME : `${setLabel}: ${COMPLETION_NAME}`,
    description:
      scope === "global"
        ? "Own the base cards across every set. Showcase cards are not required for Prismatic."
        : `Own ${setLabel}'s base cards. Showcase cards are not required for Prismatic.`,
    current: owned,
    target: total,
    tier: tierFor(owned, total),
  };

  if (scope !== "global") return [collector];

  const firstCardOwned = cards.some(isCollected); // any rarity counts
  const firstPlayset = cards.some((c) => c.limit > 0 && c.count + c.foil_count >= c.limit);
  return [
    {
      id: "completion-global-first-card",
      category: "completion",
      scope: "global",
      setCode: null,
      title: "First Pull",
      description: "Add your first card to the collection.",
      current: firstCardOwned ? 1 : 0,
      target: 1,
      tier: firstCardOwned ? "bronze" : null,
    },
    {
      id: "completion-global-first-playset",
      category: "completion",
      scope: "global",
      setCode: null,
      title: "Capped Out",
      description: "Complete the full copy limit for any one card.",
      current: firstPlayset ? 1 : 0,
      target: 1,
      tier: firstPlayset ? "bronze" : null,
    },
    collector,
  ];
}

function rarityAchievements(
  cards: MiniCard[],
  scope: AchievementScope,
  setCode: string | null,
  setLabel: string,
): Achievement[] {
  const idPrefix = scope === "global" ? "rarity-global" : `rarity-set-${setCode}`;
  return CHASE_RARITIES.map((rarity) => {
    const inRarity = cards.filter((c) => matchesRarity(c, rarity));
    const owned = inRarity.filter(isCollected).length;
    const total = inRarity.length;
    return {
      id: `${idPrefix}-${rarity.toLowerCase()}`,
      category: "rarity" as const,
      scope,
      setCode,
      title:
        scope === "global"
          ? RARITY_NAME[rarity]
          : `${setLabel}: ${RARITY_NAME[rarity]}`,
      description:
        scope === "global"
          ? `Collect ${rarity} cards across all sets.`
          : `Collect ${rarity} cards in ${setLabel}.`,
      current: owned,
      target: total,
      tier: tierFor(owned, total),
    };
    // Sets/scopes with zero cards of a rarity (e.g. no Showcase prints yet)
    // don't get a hollow achievement for it.
  }).filter((a) => a.target > 0);
}

export function computeAchievements(cards: MiniCard[]): Achievement[] {
  const setCodes = [...new Set(cards.map((c) => c.set_code))].sort();
  const out: Achievement[] = [];

  out.push(...completionAchievements(cards, "global", null, "All sets"));
  out.push(...rarityAchievements(cards, "global", null, "All sets"));

  for (const setCode of setCodes) {
    const setCards = cards.filter((c) => c.set_code === setCode);
    out.push(...completionAchievements(setCards, "set", setCode, setCode));
    out.push(...rarityAchievements(setCards, "set", setCode, setCode));
  }
  return out;
}
