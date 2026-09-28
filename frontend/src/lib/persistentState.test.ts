import { afterEach, describe, expect, it, vi } from "vitest";

import { clearPersistedView, readPersisted, writePersisted } from "./persistentState";

/** Minimal sessionStorage stand-in — the test env is "node", so there is no
 * real one. Enumerable keys matter: clearPersistedView() walks Object.keys. */
function installStorage(overrides: Partial<Storage> = {}) {
  const store: Record<string, string> = {};
  const storage = {
    getItem: (k: string) => store[k] ?? null,
    setItem: (k: string, v: string) => {
      store[k] = v;
    },
    removeItem: (k: string) => {
      delete store[k];
    },
    ...overrides,
  };
  // Object.keys(sessionStorage) must yield the stored keys, as it does in a
  // browser, so proxy enumeration onto the backing record.
  const proxied = new Proxy(storage, {
    ownKeys: () => Object.keys(store),
    getOwnPropertyDescriptor: () => ({ enumerable: true, configurable: true }),
  });
  vi.stubGlobal("sessionStorage", proxied);
  return store;
}

afterEach(() => vi.unstubAllGlobals());

describe("readPersisted / writePersisted", () => {
  it("round-trips values under the riftbound.view. prefix", () => {
    const store = installStorage();
    writePersisted("collection.mine.search", "yasuo");
    expect(store["riftbound.view.collection.mine.search"]).toBe('"yasuo"');
    expect(readPersisted("collection.mine.search", "")).toBe("yasuo");
  });

  it("round-trips non-string values", () => {
    installStorage();
    writePersisted("collection.mine.rarity", ["epic", "rare"]);
    expect(readPersisted<string[]>("collection.mine.rarity", [])).toEqual(["epic", "rare"]);

    writePersisted("community.userId", 7);
    expect(readPersisted<number | null>("community.userId", null)).toBe(7);
  });

  it("falls back to the initial value when nothing is stored", () => {
    installStorage();
    expect(readPersisted("decks.tab", "community")).toBe("community");
  });

  it("falls back when the stored entry is corrupt", () => {
    const store = installStorage();
    store["riftbound.view.decks.tab"] = "{not json";
    expect(readPersisted("decks.tab", "community")).toBe("community");
  });

  it("rejects a restored value of the wrong shape", () => {
    const store = installStorage();
    // A stale string where the consumer expects string[] would crash .includes
    store["riftbound.view.collection.mine.rarity"] = '"epic"';
    expect(readPersisted<string[]>("collection.mine.rarity", [])).toEqual([]);
  });

  it("accepts any shape for a nullable slot", () => {
    installStorage();
    writePersisted("community.userId", 12);
    expect(readPersisted<number | null>("community.userId", null)).toBe(12);
  });

  it("degrades quietly when storage throws (Safari private mode)", () => {
    installStorage({
      setItem: () => {
        throw new Error("QuotaExceededError");
      },
      getItem: () => {
        throw new Error("SecurityError");
      },
    });
    expect(() => writePersisted("decks.tab", "saved")).not.toThrow();
    expect(readPersisted("decks.tab", "community")).toBe("community");
  });
});

describe("clearPersistedView", () => {
  it("drops view keys but leaves unrelated storage alone", () => {
    const store = installStorage();
    writePersisted("collection.mine.search", "yasuo");
    writePersisted("community.userId", 3);
    store["something.else"] = "keep me";

    clearPersistedView();

    expect(Object.keys(store)).toEqual(["something.else"]);
  });
});
