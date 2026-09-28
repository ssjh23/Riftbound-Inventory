import type {
  Card,
  CardPrice,
  CommunityDeck,
  CommunityUser,
  DeckOptions,
  LimitRules,
  PriceHistory,
  PriceStatus,
  TradeItem,
  TradePreview,
} from "./types";
import { clearToken, getToken } from "./auth";

/** Called when an authenticated request comes back 401. App registers its
 * logout handler here so an expired session re-renders to Login in place.
 * This used to be a `location.reload()`, which threw away the whole document —
 * and with it the current screen, every filter and any un-flushed edit. */
let onSessionExpired: () => void = () => {};

export function setSessionExpiredHandler(fn: () => void): void {
  onSessionExpired = fn;
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const authHeader: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
  const resp = await fetch(url, {
    ...init,
    headers: { ...(init?.headers ?? {}), ...authHeader },
  });
  if (resp.status === 401) {
    // Only bounce if we actually presented a token: a 401 on an already
    // unauthenticated call means nothing expired, so there is no session to end.
    if (token) {
      clearToken();
      onSessionExpired();
    }
    throw new Error("Session expired");
  }
  if (!resp.ok) {
    throw new Error(`${init?.method ?? "GET"} ${url} failed: ${resp.status}`);
  }
  return resp.json() as Promise<T>;
}

export function fetchCards(): Promise<Card[]> {
  return request<Card[]>("/api/cards");
}

export function increment(cardId: string, delta = 1, foil = false): Promise<Card> {
  return request<Card>(
    `/api/inventory/${encodeURIComponent(cardId)}/increment?delta=${delta}&foil=${foil}`,
    { method: "POST" },
  );
}

export function patchInventory(
  cardId: string,
  body: {
    count?: number;
    foil_count?: number;
    in_binder?: boolean;
    binder_foil?: boolean;
    limit_override?: number | null;
  },
  /** Let the request outlive the page being frozen or unloaded — used when
   * flushing debounced count edits as the phone backgrounds the tab. A plain
   * fetch would be cancelled; sendBeacon can't carry the auth header. */
  keepalive = false,
): Promise<Card> {
  return request<Card>(`/api/inventory/${encodeURIComponent(cardId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    keepalive,
  });
}

/** Everyone registered on this instance, for the community directory. */
export function fetchCommunityUsers(): Promise<CommunityUser[]> {
  return request<CommunityUser[]>("/api/community/users");
}

/** Another user's collection — same shape as fetchCards(), but read-only:
 * there is no write endpoint that targets a user other than yourself. */
export function fetchUserCards(userId: number): Promise<Card[]> {
  return request<Card[]>(`/api/community/users/${userId}/cards`);
}

/** Render the selected cards as the shareable trade-request text. The format
 * is owned by the backend so the writer and the parser can't drift apart. */
export function exportTradeRequest(toUsername: string, items: TradeItem[]): Promise<{ text: string }> {
  return request<{ text: string }>("/api/trades/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ to_username: toUsername, items }),
  });
}

/** Parse a pasted request and price it against your own shelves. Read-only. */
export function previewTradeRequest(text: string): Promise<TradePreview> {
  return request<TradePreview>("/api/trades/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
}

/** Apply the confirmed quantities to your own counts. */
export function fulfilTradeRequest(items: TradeItem[]): Promise<{ applied: number; cards: Card[] }> {
  return request<{ applied: number; cards: Card[] }>("/api/trades/fulfil", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ items }),
  });
}

export function fetchRules(): Promise<LimitRules> {
  return request<LimitRules>("/api/settings/limits");
}

export function saveRules(rules: LimitRules): Promise<LimitRules> {
  return request<LimitRules>("/api/settings/limits", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(rules),
  });
}

export function exportBackup(): Promise<unknown> {
  return request<unknown>("/api/backup/export");
}

export function importBackup(payload: unknown): Promise<{ applied: number; skipped: number }> {
  return request("/api/backup/import", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

/** Download the Excel backup/template as a Blob, so the caller can save it. */
export async function exportExcel(): Promise<{ blob: Blob; filename: string }> {
  const resp = await fetch("/api/backup/excel");
  if (!resp.ok) throw new Error(`GET /api/backup/excel failed: ${resp.status}`);
  // Prefer the filename the backend suggests; fall back to a date-stamped one.
  const disp = resp.headers.get("Content-Disposition") ?? "";
  const match = /filename="([^"]+)"/.exec(disp);
  const filename = match?.[1] ?? `riftbound-collection-${new Date().toISOString().slice(0, 10)}.xlsx`;
  return { blob: await resp.blob(), filename };
}

export function importExcel(file: File): Promise<{ applied: number; skipped: number }> {
  const form = new FormData();
  form.append("file", file, file.name);
  return request("/api/backup/excel", { method: "POST", body: form });
}

export function fetchPrice(cardId: string): Promise<CardPrice> {
  return request<CardPrice>(`/api/prices/${encodeURIComponent(cardId)}`);
}

export function fetchPriceHistory(cardId: string, days = 30): Promise<PriceHistory> {
  return request<PriceHistory>(
    `/api/prices/${encodeURIComponent(cardId)}/history?days=${days}`,
  );
}

/** Batched current prices for a set of cards, e.g. everything on screen —
 * never triggers a live refresh, so this is always cheap to call. */
export function fetchPriceSummary(cardIds: string[]): Promise<CardPrice[]> {
  if (cardIds.length === 0) return Promise.resolve([]);
  const ids = cardIds.map(encodeURIComponent).join(",");
  return request<CardPrice[]>(`/api/prices/summary?ids=${ids}`);
}

export function fetchPriceStatus(): Promise<PriceStatus> {
  return request<PriceStatus>("/api/prices/status");
}

export function fetchCommunityDecks(): Promise<{ configured: boolean; decks: CommunityDeck[] }> {
  return request<{ configured: boolean; decks: CommunityDeck[] }>("/api/decks/community");
}

export function importDeck(text: string): Promise<CommunityDeck> {
  return request<CommunityDeck>("/api/decks/import", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
}

export function fetchSavedDecks(): Promise<CommunityDeck[]> {
  return request<CommunityDeck[]>("/api/decks/saved");
}

export function saveDeck(text: string, format: string): Promise<CommunityDeck> {
  return request<CommunityDeck>("/api/decks/saved", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, format }),
  });
}

export function updateDeckMeta(
  deckId: string,
  meta: { source_url: string | null },
): Promise<CommunityDeck> {
  return request<CommunityDeck>(`/api/decks/saved/${encodeURIComponent(deckId)}/meta`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(meta),
  });
}

export function commitAllCards(deckId: string, commit: boolean): Promise<CommunityDeck> {
  return request<CommunityDeck>(`/api/decks/saved/${encodeURIComponent(deckId)}/commit-all`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ commit }),
  });
}

export function commitCard(deckId: string, cardId: string, quantity: number): Promise<CommunityDeck> {
  return request<CommunityDeck>(`/api/decks/saved/${encodeURIComponent(deckId)}/commit`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ card_id: cardId, quantity }),
  });
}

export function deleteSavedDeck(id: string): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(`/api/decks/saved/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

export function fetchDeckOptions(): Promise<DeckOptions> {
  return request<DeckOptions>("/api/settings/deck-options");
}

export function saveDeckOptions(opts: DeckOptions): Promise<DeckOptions> {
  return request<DeckOptions>("/api/settings/deck-options", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(opts),
  });
}
