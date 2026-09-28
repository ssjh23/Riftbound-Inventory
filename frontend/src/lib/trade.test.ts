import { describe, expect, it } from "vitest";

import {
  selectionCount,
  selectionToItems,
  setSelection,
  type TradeSelectionMap,
} from "./trade";

const empty: TradeSelectionMap = new Map();

describe("setSelection", () => {
  it("adds a finish without touching the other", () => {
    const m = setSelection(setSelection(empty, "UNL-003", "normal", 2, 3), "UNL-003", "foil", 1, 1);
    expect(m.get("UNL-003")).toEqual({ normal: 2, foil: 1 });
  });

  it("never requests more copies than the owner holds", () => {
    const m = setSelection(empty, "UNL-003", "normal", 9, 3);
    expect(m.get("UNL-003")).toEqual({ normal: 3, foil: 0 });
  });

  it("clamps to zero rather than going negative", () => {
    const m = setSelection(empty, "UNL-003", "normal", -4, 3);
    expect(m.has("UNL-003")).toBe(false);
  });

  it("drops the card once both finishes are back to zero", () => {
    let m = setSelection(empty, "UNL-003", "normal", 2, 3);
    m = setSelection(m, "UNL-003", "foil", 1, 2);
    m = setSelection(m, "UNL-003", "normal", 0, 3);
    expect(m.get("UNL-003")).toEqual({ normal: 0, foil: 1 });
    m = setSelection(m, "UNL-003", "foil", 0, 2);
    expect(m.size).toBe(0);
  });

  it("returns a new map so React re-renders", () => {
    const m = setSelection(empty, "UNL-003", "normal", 1, 3);
    expect(m).not.toBe(empty);
    expect(empty.size).toBe(0);
  });
});

describe("selectionCount", () => {
  it("sums every finish of every card", () => {
    let m = setSelection(empty, "UNL-003", "normal", 2, 3);
    m = setSelection(m, "UNL-003", "foil", 1, 1);
    m = setSelection(m, "UNL-011", "normal", 3, 4);
    expect(selectionCount(m)).toBe(6);
  });

  it("is zero for an empty basket", () => {
    expect(selectionCount(empty)).toBe(0);
  });
});

describe("selectionToItems", () => {
  it("emits one item per card and finish, ids sorted", () => {
    let m = setSelection(empty, "UNL-011", "normal", 1, 2);
    m = setSelection(m, "UNL-003", "normal", 2, 3);
    m = setSelection(m, "UNL-003", "foil", 1, 1);
    expect(selectionToItems(m)).toEqual([
      { card_id: "UNL-003", foil: false, quantity: 2 },
      { card_id: "UNL-003", foil: true, quantity: 1 },
      { card_id: "UNL-011", foil: false, quantity: 1 },
    ]);
  });

  it("omits finishes with nothing requested", () => {
    const m = setSelection(empty, "UNL-003", "foil", 2, 2);
    expect(selectionToItems(m)).toEqual([{ card_id: "UNL-003", foil: true, quantity: 2 }]);
  });
});
