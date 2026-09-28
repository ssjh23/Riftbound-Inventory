import { describe, expect, it } from "vitest";

import {
  collectionStats,
  compareRarity,
  completionStatus,
  dashboardStats,
  isFoilOnly,
  progressPct,
  setBreakdown,
} from "./collection";

describe("compareRarity", () => {
  it("orders by game progression, not alphabetically", () => {
    const shuffled = ["Showcase", "Common", "Rare", "Uncommon", "Epic"];
    expect([...shuffled].sort(compareRarity)).toEqual([
      "Common", "Uncommon", "Rare", "Epic", "Showcase",
    ]);
  });

  it("puts unrecognized rarities after all known ones", () => {
    const withUnknown = ["Epic", "Mythic", "Common"];
    expect([...withUnknown].sort(compareRarity)).toEqual(["Common", "Epic", "Mythic"]);
  });
});

describe("isFoilOnly", () => {
  it("treats Rare and above as foil-only, Common/Uncommon as not", () => {
    expect(isFoilOnly("Common")).toBe(false);
    expect(isFoilOnly("uncommon")).toBe(false);
    expect(isFoilOnly("Rare")).toBe(true);
    expect(isFoilOnly("Epic")).toBe(true);
    expect(isFoilOnly("Showcase")).toBe(true);
  });
});


describe("completionStatus", () => {
  it("maps count/limit to the four states", () => {
    expect(completionStatus(0, 3)).toBe("missing");
    expect(completionStatus(1, 3)).toBe("partial");
    expect(completionStatus(3, 3)).toBe("complete");
    expect(completionStatus(4, 3)).toBe("overflow"); // trade fodder
  });

  it("treats a zero limit as nothing-to-collect", () => {
    expect(completionStatus(0, 0)).toBe("complete");
    expect(completionStatus(2, 0)).toBe("overflow");
  });
});

describe("progressPct", () => {
  it("caps at 100 and never divides by zero", () => {
    expect(progressPct(1, 3)).toBe(33);
    expect(progressPct(5, 3)).toBe(100);
    expect(progressPct(0, 0)).toBe(100);
  });
});

describe("collectionStats", () => {
  it("counts complete cards and total copies including foils", () => {
    const stats = collectionStats([
      { count: 2, foil_count: 1, limit: 3 }, // 3 total -> complete
      { count: 1, foil_count: 0, limit: 3 },
      { count: 0, foil_count: 0, limit: 1 },
    ]);
    expect(stats).toEqual({ total: 3, complete: 1, owned: 4 });
  });
});

describe("dashboardStats", () => {
  it("treats binder as collected but not toward playsets", () => {
    const stats = dashboardStats([
      { count: 2, foil_count: 1, in_binder: false, limit: 3, rarity: "Common" }, // playset complete
      { count: 4, foil_count: 0, in_binder: false, limit: 3, rarity: "Rare" }, // over limit
      { count: 0, foil_count: 0, in_binder: true, limit: 3, rarity: "Epic" }, // binder-only
      { count: 0, foil_count: 0, in_binder: false, limit: 1, rarity: "Common" }, // missing
    ]);
    expect(stats).toEqual({
      totalCopies: 7, // binder adds no copies
      uniqueOwned: 3, // the binder card counts as collected
      totalUnique: 4,
      overallPct: 75,
      playsetsComplete: 2, // binder card excluded
    });
  });

  it("excludes Showcase cards from every count", () => {
    const stats = dashboardStats([
      { count: 3, foil_count: 0, in_binder: false, limit: 3, rarity: "Rare" }, // base
      { count: 0, foil_count: 0, in_binder: false, limit: 3, rarity: "Rare" }, // base, missing
      { count: 2, foil_count: 1, in_binder: false, limit: 3, rarity: "Showcase" }, // excluded
      { count: 5, foil_count: 0, in_binder: true, limit: 1, rarity: "showcase" }, // case-insensitive
    ]);
    expect(stats).toEqual({
      totalCopies: 3, // Showcase copies not counted
      uniqueOwned: 1,
      totalUnique: 2, // only the two base cards
      overallPct: 50,
      playsetsComplete: 1,
    });
  });

  it("handles an empty collection without dividing by zero", () => {
    expect(dashboardStats([])).toEqual({
      totalCopies: 0,
      uniqueOwned: 0,
      totalUnique: 0,
      overallPct: 0,
      playsetsComplete: 0,
    });
  });
});

describe("setBreakdown", () => {
  it("counts foil-only and binder-only cards as owned, excludes Showcase", () => {
    const rows = setBreakdown([
      { set_code: "UNL", count: 0, foil_count: 0, in_binder: false, rarity: "Common" },
      { set_code: "OGN", count: 2, foil_count: 0, in_binder: false, rarity: "Rare" },
      { set_code: "OGN", count: 0, foil_count: 0, in_binder: true, rarity: "Epic" }, // binder
      { set_code: "UNL", count: 0, foil_count: 1, in_binder: false, rarity: "Rare" }, // foil-only
      { set_code: "OGN", count: 4, foil_count: 0, in_binder: false, rarity: "Showcase" }, // out
    ]);
    expect(rows).toEqual([
      { setCode: "OGN", owned: 2, total: 2, pct: 100 }, // Showcase omitted
      { setCode: "UNL", owned: 1, total: 2, pct: 50 },
    ]);
  });
});
