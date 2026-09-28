import { useEffect, useMemo, useRef, useState } from "react";

import { patchInventory } from "../api";
import MultiSelect from "../components/MultiSelect";
import TradeImport from "../components/TradeImport";
import { usePersistedState } from "../lib/persistentState";
import type { Finish, TradeSelectionMap } from "../lib/trade";
import {
  collectionStats,
  compareRarity,
  completionStatus,
  isCollected,
  isFoilOnly,
  progressPct,
} from "../lib/collection";
import type { Card } from "../types";

const STATUS_LABEL: Record<string, string> = {
  missing: "Missing",
  binder: "In binder ✓",
  partial: "Collecting",
  complete: "Complete ✓",
  overflow: "Extras — trade fodder",
};

export interface CollectionPreset {
  set?: string;
  owned?: string;
}

/** A +/- click that hasn't been PATCHed yet. Everything the save needs is held
 * here rather than captured in the timer closure, so the edit can also be
 * flushed from outside — on unmount, or when the page is about to be frozen. */
interface PendingEdit {
  card: Card; // pre-click card, for reverting on a failed save
  foil: boolean;
  count: number; // target count
  timer: ReturnType<typeof setTimeout>;
}

export default function Collection({
  cards,
  onCardChange,
  preset,
  commitmentMap,
  readOnly = false,
  trade,
  persistKey,
}: {
  cards: Card[];
  onCardChange?: (card: Card) => void;
  preset?: CollectionPreset | null;
  commitmentMap?: Map<string, { deckName: string; qty: number }[]>;
  /** Someone else's collection: counts, binder flags and limits are display
   * only. No mutating handler is wired up, so nothing here can PATCH. */
  readOnly?: boolean;
  /** Trade-request mode: each finish gets a stepper for asking the owner for
   * copies, capped at what they hold. Only meaningful alongside readOnly. */
  trade?: {
    selection: TradeSelectionMap;
    onChange: (card: Card, finish: Finish, quantity: number) => void;
  };
  /** Namespace for remembering the filters across a reload. Each render mode
   * gets its own, so browsing someone else's shelf doesn't inherit the filters
   * you set on your own. Omit to opt out of persistence entirely. */
  persistKey?: string;
}) {
  const slot = (name: string) => (persistKey ? `collection.${persistKey}.${name}` : null);
  const [search, setSearch] = usePersistedState(slot("search"), "");
  const [setFilter, setSetFilter] = usePersistedState(slot("set"), "");
  const [typeFilter, setTypeFilter] = usePersistedState(slot("type"), "");
  const [rarityFilter, setRarityFilter] = usePersistedState<string[]>(slot("rarity"), []);
  const [ownedFilter, setOwnedFilter] = usePersistedState(slot("owned"), "");
  // Deliberately not persisted — a modal that reopens itself on return is
  // disorienting, and it holds no user input.
  const [zoomed, setZoomed] = useState<Card | null>(null);

  // Close the zoomed image with Escape.
  useEffect(() => {
    if (!zoomed) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setZoomed(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [zoomed]);

  // Apply a preset handed in from the dashboard (e.g. "OGN missing cards").
  useEffect(() => {
    if (!preset) return;
    setSetFilter(preset.set ?? "");
    setOwnedFilter(preset.owned ?? "");
  }, [preset]);

  const sets = useMemo(() => [...new Set(cards.map((c) => c.set_code))].sort(), [cards]);
  const types = useMemo(() => [...new Set(cards.map((c) => c.card_type))].sort(), [cards]);
  const rarities = useMemo(
    () => [...new Set(cards.map((c) => c.rarity))].sort(compareRarity),
    [cards],
  );

  const visible = cards.filter((c) => {
    if (search && !c.name.toLowerCase().includes(search.toLowerCase())) return false;
    if (setFilter && c.set_code !== setFilter) return false;
    if (typeFilter && c.card_type !== typeFilter) return false;
    if (rarityFilter.length > 0 && !rarityFilter.includes(c.rarity)) return false;
    if (ownedFilter === "owned" && !isCollected(c)) return false;
    if (ownedFilter === "missing" && isCollected(c)) return false;
    return true;
  });

  const stats = collectionStats(cards);

  // key = `${cardId}:${"foil"|"normal"}`
  const pending = useRef<Map<string, PendingEdit>>(new Map());

  const emit = (card: Card) => onCardChange?.(card);

  /** Send one debounced edit now, whether its timer has fired or not. */
  const flush = async (key: string, keepalive: boolean) => {
    const p = pending.current.get(key);
    if (!p) return;
    clearTimeout(p.timer);
    pending.current.delete(key);
    try {
      const body = p.foil ? { foil_count: p.count } : { count: p.count };
      emit(await patchInventory(p.card.id, body, keepalive));
    } catch (e) {
      emit(p.card); // revert to pre-click state on network error
      console.error("Failed to save inventory change:", e);
    }
  };

  const flushAll = (keepalive: boolean) => {
    [...pending.current.keys()].forEach((key) => void flush(key, keepalive));
  };

  // Hold the latest flusher so the listeners below — registered once — never
  // fire a stale closure.
  const flushAllRef = useRef(flushAll);
  useEffect(() => {
    flushAllRef.current = flushAll;
  });

  // Flush pending saves rather than dropping them. Backgrounding the phone (or
  // just switching tabs) inside the 600 ms debounce window used to discard the
  // click silently. `keepalive` lets the PATCH outlive the page being frozen —
  // a plain fetch would be cancelled, and sendBeacon can't carry the auth
  // header. `visibilitychange` is the signal that actually fires on iOS;
  // `beforeunload` does not.
  useEffect(() => {
    const onVisibility = () => {
      if (document.visibilityState === "hidden") flushAllRef.current(true);
    };
    const onPageHide = () => flushAllRef.current(true);
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("pagehide", onPageHide);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("pagehide", onPageHide);
      flushAllRef.current(false); // leaving the tab in-app: an ordinary fetch survives
    };
  }, []);

  const bump = (card: Card, delta: number, foil = false) => {
    const key = `${card.id}:${foil ? "foil" : "normal"}`;

    // Use the in-flight target if the user clicked faster than React re-rendered.
    const base = pending.current.get(key)?.count ?? (foil ? card.foil_count : card.count);
    const newCount = Math.max(0, base + delta);

    // Instant optimistic update — no network wait.
    emit({
      ...card,
      count:      foil ? card.count  : newCount,
      foil_count: foil ? newCount    : card.foil_count,
    });

    // Debounce: cancel previous timer, restart. Fires one PATCH after 600 ms idle.
    const prev = pending.current.get(key);
    if (prev) clearTimeout(prev.timer);

    const timer = setTimeout(() => void flush(key, false), 600);
    pending.current.set(key, { card, foil, count: newCount, timer });
  };

  const toggleBinder = (card: Card) => {
    const next = !card.in_binder;
    // A foil-only (Rare+) binder copy is necessarily foil, so the single "In
    // binder" checkbox also drives binder_foil for those cards.
    const body = isFoilOnly(card.rarity)
      ? { in_binder: next, binder_foil: next }
      : { in_binder: next };
    patchInventory(card.id, body).then(emit).catch(console.error);
  };

  // Backend enforces the coupling (foil ⇒ in binder), so a single-field patch
  // is enough — the response reflects both flags.
  const toggleBinderFoil = (card: Card) =>
    patchInventory(card.id, { binder_foil: !card.binder_foil })
      .then(emit)
      .catch(console.error);

  const editLimit = (card: Card) => {
    const raw = window.prompt(
      `Limit override for ${card.name} (blank = use rules, currently ${card.limit})`,
      card.limit_override?.toString() ?? "",
    );
    if (raw === null) return;
    const override = raw.trim() === "" ? null : Math.max(0, parseInt(raw, 10) || 0);
    patchInventory(card.id, { limit_override: override })
      .then(emit)
      .catch(console.error);
  };

  return (
    <main>
      <div className="collection-toolbar">
        <div className="stats">
          {stats.owned} cards owned · {stats.complete}/{stats.total} complete
        </div>
        {/* Only your own collection can hand cards over. */}
        {!readOnly && <TradeImport onApplied={(updated) => updated.forEach(emit)} />}
      </div>
      <div className="filters">
        <input
          placeholder="Search cards…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select value={setFilter} onChange={(e) => setSetFilter(e.target.value)}>
          <option value="">All sets</option>
          {sets.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}>
          <option value="">All types</option>
          {types.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
        <MultiSelect
          label="All rarities"
          options={rarities}
          values={rarityFilter}
          onChange={setRarityFilter}
        />
        <select value={ownedFilter} onChange={(e) => setOwnedFilter(e.target.value)}>
          <option value="">All cards</option>
          <option value="owned">Owned</option>
          <option value="missing">Missing</option>
        </select>
      </div>
      <div className="grid">
        {visible.map((card) => {
          const total = card.count + card.foil_count;
          const collected = isCollected(card);
          const shiny = card.foil_count > 0 || card.binder_foil;
          const foilOnly = isFoilOnly(card.rarity); // Rare+ have no non-foil printing
          // Playset status is copies-vs-limit; a binder-only card is collected
          // but shows as "In binder", never as a completed playset.
          const status =
            total > 0
              ? completionStatus(total, card.limit)
              : card.in_binder
                ? "binder"
                : "missing";
          const picked = trade?.selection.get(card.id);
          const pickedTotal = (picked?.normal ?? 0) + (picked?.foil ?? 0);
          return (
            <div
              key={card.id}
              className={`card-tile ${status} ${collected ? "" : "unowned"} ${
                shiny ? `shiny rarity-${card.rarity.toLowerCase()}` : ""
              } ${pickedTotal > 0 ? "requested" : ""}`}
            >
              <div className="card-art">
                <img
                  src={card.image_url}
                  alt={card.name}
                  loading="lazy"
                  className="card-img"
                  onClick={() => setZoomed(card)}
                  title="Click to enlarge"
                />
                {pickedTotal > 0 && (
                  <span
                    className="card-trade-badge"
                    title={`Requesting ${picked!.normal} normal, ${picked!.foil} foil`}
                  >
                    ⇄ {pickedTotal}
                  </span>
                )}
                {commitmentMap?.has(card.id) && (
                  <span
                    className="card-committed-badge"
                    title={commitmentMap.get(card.id)!
                      .map(d => `${d.qty}× in "${d.deckName}"`)
                      .join(", ")}
                  >
                    *
                  </span>
                )}
              </div>
              <div className="card-info">
                <div className="card-name" title={card.name}>{card.name}</div>
                <div className="card-meta">
                  {card.set_code} #{card.number} · {card.rarity}
                </div>
                <div className="progress">
                  <div
                    className={`progress-bar ${status}`}
                    style={{ width: `${progressPct(total, card.limit)}%` }}
                  />
                </div>
                <div className={`count-rows ${readOnly ? "read-only" : ""}`}>
                  {!foilOnly && (
                    <div className="card-row">
                      <span className="count-label">Normal</span>
                      {!readOnly && (
                        <button onClick={() => bump(card, -1)} disabled={card.count === 0}>−</button>
                      )}
                      <span
                        className="count"
                        onClick={readOnly ? undefined : () => editLimit(card)}
                        title={readOnly ? undefined : "Click to override limit"}
                      >
                        {card.count} / {card.limit}
                      </span>
                      {!readOnly && <button onClick={() => bump(card, 1)}>+</button>}
                      {trade && card.count > 0 && (
                        <span className="trade-stepper" title="Copies to request">
                          <button
                            onClick={() => trade.onChange(card, "normal", (picked?.normal ?? 0) - 1)}
                            disabled={(picked?.normal ?? 0) === 0}
                            aria-label={`Request one fewer ${card.name}`}
                          >
                            −
                          </button>
                          <span className="trade-qty">{picked?.normal ?? 0}</span>
                          <button
                            onClick={() => trade.onChange(card, "normal", (picked?.normal ?? 0) + 1)}
                            disabled={(picked?.normal ?? 0) >= card.count}
                            aria-label={`Request one more ${card.name}`}
                          >
                            +
                          </button>
                        </span>
                      )}
                    </div>
                  )}
                  <div className="card-row foil">
                    <span className="count-label">Foil</span>
                    {!readOnly && (
                      <button onClick={() => bump(card, -1, true)} disabled={card.foil_count === 0}>−</button>
                    )}
                    {/* Foil-only cards have no Normal row, so the limit lives here. */}
                    {foilOnly ? (
                      <span
                        className={readOnly ? "count" : "count editable"}
                        onClick={readOnly ? undefined : () => editLimit(card)}
                        title={readOnly ? undefined : "Click to override limit"}
                      >
                        {card.foil_count} / {card.limit}
                      </span>
                    ) : (
                      <span className="count">{card.foil_count}</span>
                    )}
                    {!readOnly && <button onClick={() => bump(card, 1, true)}>+</button>}
                    {trade && card.foil_count > 0 && (
                      <span className="trade-stepper" title="Foil copies to request">
                        <button
                          onClick={() => trade.onChange(card, "foil", (picked?.foil ?? 0) - 1)}
                          disabled={(picked?.foil ?? 0) === 0}
                          aria-label={`Request one fewer foil ${card.name}`}
                        >
                          −
                        </button>
                        <span className="trade-qty">{picked?.foil ?? 0}</span>
                        <button
                          onClick={() => trade.onChange(card, "foil", (picked?.foil ?? 0) + 1)}
                          disabled={(picked?.foil ?? 0) >= card.foil_count}
                          aria-label={`Request one more foil ${card.name}`}
                        >
                          +
                        </button>
                      </span>
                    )}
                  </div>
                </div>
                <div className="binder-row">
                  <label className="binder-toggle" title="Marked as collected, but not counted toward playset limits">
                    <input
                      type="checkbox"
                      checked={card.in_binder}
                      disabled={readOnly}
                      onChange={readOnly ? undefined : () => toggleBinder(card)}
                      readOnly={readOnly}
                    />
                    In binder
                  </label>
                  {/* Foil-only (Rare+) binder copies are always foil, so no
                      separate checkbox — "In binder" implies foil for them. */}
                  {!foilOnly && (
                    <label className="binder-toggle" title="The binder copy is a foil — marks it in the binder and adds the shimmer">
                      <input
                        type="checkbox"
                        checked={card.binder_foil}
                        disabled={readOnly}
                        onChange={readOnly ? undefined : () => toggleBinderFoil(card)}
                        readOnly={readOnly}
                      />
                      Foil
                    </label>
                  )}
                </div>
                <div className={`status ${status}`}>{STATUS_LABEL[status]}</div>
              </div>
            </div>
          );
        })}
      </div>
      {visible.length === 0 && <p className="empty">No cards match the filters.</p>}

      {zoomed && (
        <div
          className="lightbox"
          role="dialog"
          aria-label={`${zoomed.name} enlarged`}
          onClick={() => setZoomed(null)}
        >
          <button className="lightbox-close" aria-label="Close" onClick={() => setZoomed(null)}>
            ×
          </button>
          <figure
            className={`lightbox-figure ${
              zoomed.foil_count > 0 || zoomed.binder_foil
                ? `shiny rarity-${zoomed.rarity.toLowerCase()}`
                : ""
            }`}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="lightbox-art">
              <img src={zoomed.image_url} alt={zoomed.name} />
            </div>
            <figcaption>
              {zoomed.name} · {zoomed.set_code} #{zoomed.number} · {zoomed.rarity}
            </figcaption>
          </figure>
        </div>
      )}
    </main>
  );
}
