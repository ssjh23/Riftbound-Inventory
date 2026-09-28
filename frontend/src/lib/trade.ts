import type { TradeItem } from "../types";

export type Finish = "normal" | "foil";

/** Copies of one card the viewer wants, split by finish — the two tallies are
 * independent, exactly as they are in the owner's inventory. */
export interface TradeSelection {
  normal: number;
  foil: number;
}

/** card_id → requested copies. */
export type TradeSelectionMap = Map<string, TradeSelection>;

/** Set one finish's requested quantity, clamped to what the owner actually
 * holds (you can never ask for more copies than are on their shelf). Returns a
 * new map so React sees the change; empty entries are dropped so the side list
 * and the tile highlight both fall away at zero. */
export function setSelection(
  map: TradeSelectionMap,
  cardId: string,
  finish: Finish,
  quantity: number,
  owned: number,
): TradeSelectionMap {
  const next = new Map(map);
  const current = next.get(cardId) ?? { normal: 0, foil: 0 };
  const clamped = Math.max(0, Math.min(quantity, Math.max(0, owned)));
  const entry = { ...current, [finish]: clamped };
  if (entry.normal === 0 && entry.foil === 0) {
    next.delete(cardId);
  } else {
    next.set(cardId, entry);
  }
  return next;
}

/** Total copies across every card and finish. */
export function selectionCount(map: TradeSelectionMap): number {
  let total = 0;
  for (const entry of map.values()) total += entry.normal + entry.foil;
  return total;
}

/** Flatten to the wire format, one item per card+finish, ids sorted so the
 * exported text is stable between runs. */
export function selectionToItems(map: TradeSelectionMap): TradeItem[] {
  const items: TradeItem[] = [];
  for (const cardId of [...map.keys()].sort()) {
    const entry = map.get(cardId)!;
    if (entry.normal > 0) items.push({ card_id: cardId, foil: false, quantity: entry.normal });
    if (entry.foil > 0) items.push({ card_id: cardId, foil: true, quantity: entry.foil });
  }
  return items;
}
