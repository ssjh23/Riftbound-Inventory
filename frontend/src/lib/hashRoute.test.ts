import { describe, expect, it } from "vitest";

import { DEFAULT_TAB, TABS, readTabFromHash, tabToHash } from "./hashRoute";

describe("readTabFromHash", () => {
  it("round-trips every tab through the hash", () => {
    for (const tab of TABS) {
      expect(readTabFromHash(tabToHash(tab))).toBe(tab);
    }
  });

  it("accepts a hash without the leading slash", () => {
    expect(readTabFromHash("#collection")).toBe("collection");
  });

  it("is case- and whitespace-insensitive", () => {
    expect(readTabFromHash("#/Decks")).toBe("decks");
    expect(readTabFromHash("#/ community ")).toBe("community");
  });

  it("returns null for an empty or absent hash so the caller can default", () => {
    expect(readTabFromHash("")).toBeNull();
    expect(readTabFromHash("#")).toBeNull();
    expect(readTabFromHash("#/")).toBeNull();
  });

  it("returns null for an unknown tab rather than rendering a blank shell", () => {
    expect(readTabFromHash("#/nope")).toBeNull();
    expect(readTabFromHash("#/collection/OGN")).toBeNull();
  });
});

describe("tabToHash", () => {
  it("produces a path-style fragment", () => {
    expect(tabToHash("collection")).toBe("#/collection");
    expect(tabToHash(DEFAULT_TAB)).toBe("#/overview");
  });
});
