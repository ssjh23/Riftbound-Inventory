import { describe, expect, it } from "vitest";

import { computeAchievements } from "./achievements";

function card(overrides: Partial<{
  set_code: string;
  rarity: string;
  count: number;
  foil_count: number;
  in_binder: boolean;
  limit: number;
}> = {}) {
  return {
    set_code: "AAA",
    rarity: "Common",
    count: 0,
    foil_count: 0,
    in_binder: false,
    limit: 3,
    ...overrides,
  };
}

describe("computeAchievements — completion", () => {
  it("uses the 'Archivist' family name, reused globally and per set", () => {
    const cards = [
      card({ set_code: "AAA", count: 3 }), // owned
      card({ set_code: "AAA" }),
      card({ set_code: "AAA" }),
      card({ set_code: "AAA" }),
      card({ set_code: "AAA", rarity: "Showcase" }), // excluded from base math
    ];
    const ach = computeAchievements(cards);

    const global = ach.find((a) => a.id === "completion-global-collector")!;
    expect(global.title).toBe("Archivist");
    expect(global).toMatchObject({ current: 1, target: 4, tier: "bronze" }); // 25%

    const setA = ach.find((a) => a.id === "completion-set-AAA-collector")!;
    expect(setA.title).toBe("AAA: Archivist");
    expect(setA).toMatchObject({ current: 1, target: 4, tier: "bronze" });
  });

  it("reaches Prismatic at 100% base completion, ignoring Showcase ownership", () => {
    const cards = [
      card({ set_code: "BBB", count: 1 }),
      card({ set_code: "BBB", count: 1 }),
      card({ set_code: "BBB", rarity: "Showcase" }), // deliberately NOT owned
    ];
    const ach = computeAchievements(cards);
    const setB = ach.find((a) => a.id === "completion-set-BBB-collector")!;
    expect(setB).toMatchObject({ current: 2, target: 2, tier: "prismatic" });
  });

  it("steps through Bronze/Silver/Gold/Prismatic at the 25/50/75/100 thresholds", () => {
    const mk = (owned: number, total: number) => {
      const cards = Array.from({ length: total }, (_, i) =>
        card({ set_code: "CCC", count: i < owned ? 1 : 0 }),
      );
      return computeAchievements(cards).find((a) => a.id === "completion-set-CCC-collector")!;
    };
    expect(mk(0, 4).tier).toBeNull();
    expect(mk(1, 4).tier).toBe("bronze");
    expect(mk(2, 4).tier).toBe("silver");
    expect(mk(3, 4).tier).toBe("gold");
    expect(mk(4, 4).tier).toBe("prismatic");
  });

  it("'First Pull' and 'Capped Out' are single-tier (Bronze only) starter achievements", () => {
    const cards = [card({ set_code: "AAA", count: 1, limit: 3 })];
    const ach = computeAchievements(cards);
    const firstPull = ach.find((a) => a.id === "completion-global-first-card")!;
    expect(firstPull.title).toBe("First Pull");
    expect(firstPull.tier).toBe("bronze");
    const cappedOut = ach.find((a) => a.id === "completion-global-first-playset")!;
    expect(cappedOut.title).toBe("Capped Out");
    expect(cappedOut.tier).toBeNull();

    const complete = computeAchievements([card({ set_code: "AAA", count: 3, limit: 3 })]);
    expect(complete.find((a) => a.id === "completion-global-first-playset")!.tier).toBe("bronze");
  });

  it("a binder-only card (no physical copies) still counts as collected", () => {
    const cards = [card({ set_code: "AAA", in_binder: true })];
    const ach = computeAchievements(cards);
    expect(ach.find((a) => a.id === "completion-global-first-card")!.tier).toBe("bronze");
  });
});

describe("computeAchievements — rarity chaser", () => {
  it("uses the Rare Seeker / Epic Vanguard / Prism Chaser family names", () => {
    const cards = [
      card({ set_code: "AAA", rarity: "Rare", foil_count: 1 }),
      card({ set_code: "AAA", rarity: "Epic", foil_count: 1 }),
      card({ set_code: "AAA", rarity: "Showcase", foil_count: 1 }),
    ];
    const ach = computeAchievements(cards);
    expect(ach.find((a) => a.id === "rarity-global-rare")!.title).toBe("Rare Seeker");
    expect(ach.find((a) => a.id === "rarity-global-epic")!.title).toBe("Epic Vanguard");
    expect(ach.find((a) => a.id === "rarity-global-showcase")!.title).toBe("Prism Chaser");
    expect(ach.find((a) => a.id === "rarity-set-AAA-rare")!.title).toBe("AAA: Rare Seeker");
  });

  it("tiers rarity-chaser achievements the same way, split global vs per-set", () => {
    const cards = [
      card({ set_code: "AAA", rarity: "Rare", foil_count: 1 }), // owned
      card({ set_code: "AAA", rarity: "Rare" }), // not owned
      card({ set_code: "BBB", rarity: "Rare", foil_count: 1 }), // owned
      card({ set_code: "BBB", rarity: "Rare" }), // not owned
    ];
    const ach = computeAchievements(cards);

    const globalRare = ach.find((a) => a.id === "rarity-global-rare")!;
    expect(globalRare).toMatchObject({ current: 2, target: 4, tier: "silver" }); // 50%

    const setARare = ach.find((a) => a.id === "rarity-set-AAA-rare")!;
    expect(setARare).toMatchObject({ current: 1, target: 2, tier: "silver" }); // 50%
  });

  it("omits a rarity achievement entirely when a scope has none of that rarity", () => {
    const cards = [card({ set_code: "AAA", rarity: "Common" })]; // no Epic anywhere
    const ach = computeAchievements(cards);
    expect(ach.find((a) => a.id === "rarity-global-epic")).toBeUndefined();
    expect(ach.find((a) => a.id === "rarity-set-AAA-epic")).toBeUndefined();
  });

  it("reaches Prismatic once every card of that rarity is owned", () => {
    const cards = [card({ set_code: "AAA", rarity: "Epic", count: 1 })];
    const ach = computeAchievements(cards);
    expect(ach.find((a) => a.id === "rarity-global-epic")!.tier).toBe("prismatic");
  });
});
