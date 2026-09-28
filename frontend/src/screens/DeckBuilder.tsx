import { useEffect, useMemo, useRef, useState, type MouseEvent } from "react";

import {
  commitAllCards,
  commitCard,
  deleteSavedDeck,
  fetchCommunityDecks,
  fetchDeckOptions,
  saveDeck,
  updateDeckMeta,
} from "../api";
import { usePersistedState } from "../lib/persistentState";
import type { Card, CommunityDeck, CommunityDeckCard } from "../types";

interface SlotAnalysis extends CommunityDeckCard {
  card: Card | undefined;
  rawOwned: number;
  committedElsewhere: number;
  commitmentDetails: { deckName: string; qty: number }[];
  owned: number;
  missing: number;
}

interface DeckWithAnalysis extends CommunityDeck {
  slots: SlotAnalysis[];
  totalCards: number;
  ownedCards: number;
  canComplete: boolean;
  hasAny: boolean;
  isSaved: boolean;
}

const SECTION_ORDER = [
  "Commanders", "Legend", "Legends",
  "Mainboard", "Main", "Main Deck",
  "Runes", "Rune Pool", "Rune Deck",
  "Sideboard", "Side",
];

function sectionRank(section: string): number {
  const idx = SECTION_ORDER.findIndex(s => s.toLowerCase() === section.toLowerCase());
  return idx === -1 ? 50 : idx;
}

function analyze(
  deck: CommunityDeck,
  cardMap: Map<string, Card>,
  nameMap: Map<string, Card[]>,
  countAllVariants: boolean,
  allSavedDecks: CommunityDeck[] = [],
): DeckWithAnalysis {
  const isSaved = allSavedDecks.some(d => d.id === deck.id);

  const slots: SlotAnalysis[] = deck.cards.map(dc => {
    const card = dc.card_id ? cardMap.get(dc.card_id) : undefined;

    // Pool all printings of the same card name (handles runes from any set and alt arts)
    const cardsByName = nameMap.get(dc.card_name.toLowerCase()) ?? [];
    const rawOwned = cardsByName.length > 0
      ? cardsByName.reduce(
          (sum, c) => sum + c.count + (countAllVariants ? c.foil_count + (c.in_binder ? 1 : 0) : 0),
          0,
        )
      : card
        ? card.count + (countAllVariants ? card.foil_count + (card.in_binder ? 1 : 0) : 0)
        : 0;

    // For display: prefer the exact card, then the most-owned variant, then any variant
    const displayCard =
      card ??
      cardsByName.find(c => c.count > 0 || c.foil_count > 0 || c.in_binder) ??
      cardsByName[0];

    // Match committed-elsewhere by card name so cross-set printings (e.g. OGN vs UNL rune) link up
    const nameKey = dc.card_name.toLowerCase();
    const otherDecks = allSavedDecks.filter(d => d.id !== deck.id);
    const committedElsewhere = otherDecks
      .flatMap(d => d.cards)
      .filter(c => c.card_name.toLowerCase() === nameKey && (c.committed_quantity ?? 0) > 0)
      .reduce((sum, c) => sum + (c.committed_quantity ?? 0), 0);

    const commitmentDetails: { deckName: string; qty: number }[] = otherDecks.flatMap(d =>
      d.cards
        .filter(c => c.card_name.toLowerCase() === nameKey && (c.committed_quantity ?? 0) > 0)
        .map(c => ({ deckName: d.legend || d.name, qty: c.committed_quantity! })),
    );

    const owned = Math.max(0, rawOwned - committedElsewhere);
    return {
      ...dc,
      card: displayCard,
      rawOwned,
      committedElsewhere,
      commitmentDetails,
      owned,
      missing: Math.max(0, dc.quantity - owned),
    };
  });

  const mainSlots = slots.filter(
    s => !s.section.toLowerCase().includes("side") && !isIdentityCard(s),
  );
  const totalCards = mainSlots.reduce((n, s) => n + s.quantity, 0);
  const ownedCards = mainSlots.reduce((n, s) => n + Math.min(s.owned, s.quantity), 0);
  return {
    ...deck,
    slots,
    totalCards,
    ownedCards,
    canComplete: mainSlots.every(s => s.missing === 0),
    hasAny: mainSlots.some(s => s.owned > 0),
    isSaved,
  };
}

function isIdentityCard(slot: SlotAnalysis): boolean {
  return slot.section === "Legend" && !slot.card_id;
}

function slotClass(slot: SlotAnalysis): string {
  if (isIdentityCard(slot)) return "deck-card-slot slot-identity";
  if (!slot.card_id || !slot.card) return "deck-card-slot slot-unknown";
  if (slot.missing === 0) return "deck-card-slot slot-owned";
  if (slot.owned > 0) return "deck-card-slot slot-partial";
  return "deck-card-slot slot-missing";
}

function slotStatus(slot: SlotAnalysis): string {
  if (isIdentityCard(slot)) return "–";
  if (!slot.card_id || !slot.card) return "?";
  if (slot.missing === 0) return "✓";
  return `${slot.owned}/${slot.quantity}`;
}

function deckToText(deck: DeckWithAnalysis): string {
  const sections = new Map<string, SlotAnalysis[]>();
  for (const slot of deck.slots) {
    if (!sections.has(slot.section)) sections.set(slot.section, []);
    sections.get(slot.section)!.push(slot);
  }
  const sorted = [...sections.entries()].sort((a, b) => sectionRank(a[0]) - sectionRank(b[0]));
  const lines: string[] = [];
  for (const [section, slots] of sorted) {
    lines.push(`${section}:`);
    for (const slot of slots) lines.push(`${slot.quantity} ${slot.card_name}`);
    lines.push("");
  }
  return lines.join("\n").trim();
}

function tooltipStyle(pos: { x: number; y: number }): React.CSSProperties {
  const W = 160;
  const H = Math.round(W * 1.45);
  const gap = 14;
  let left = pos.x + gap;
  if (left + W > window.innerWidth - 8) left = pos.x - W - gap;
  left = Math.max(8, left);
  let top = pos.y - H / 2;
  top = Math.max(8, Math.min(top, window.innerHeight - H - 8));
  return { left, top };
}

function DeckDetail({
  deck,
  onClose,
  onCommit,
  onCommitAll,
  onEdit,
  onMetaChange,
}: {
  deck: DeckWithAnalysis;
  onClose: () => void;
  onCommit?: (cardId: string, qty: number) => Promise<void>;
  onCommitAll?: (commit: boolean) => Promise<void>;
  onEdit?: (deck: DeckWithAnalysis) => void;
  onMetaChange?: (meta: { source_url: string | null }) => Promise<void>;
}) {
  const [hoveredCard, setHoveredCard] = useState<Card | null>(null);
  const [tooltipPos, setTooltipPos] = useState<{ x: number; y: number } | null>(null);
  const [pinnedCard, setPinnedCard] = useState<Card | null>(null);
  const [committingId, setCommittingId] = useState<string | null>(null);
  const [committingAll, setCommittingAll] = useState(false);
  const [sourceUrl, setSourceUrl] = useState(deck.source_url ?? "");
  const [urlSaved, setUrlSaved] = useState(false);

  // Clear preview state when a different deck is opened
  useEffect(() => {
    setPinnedCard(null);
    setHoveredCard(null);
    setTooltipPos(null);
  }, [deck.id]);

  // Sync source URL field when deck prop updates (e.g. after save)
  useEffect(() => {
    setSourceUrl(deck.source_url ?? "");
  }, [deck.source_url]);

  const handleSourceUrlBlur = async () => {
    if (!onMetaChange) return;
    const val = sourceUrl.trim();
    const current = deck.source_url ?? "";
    if (val === current) return;
    try {
      await onMetaChange({ source_url: val || null });
      setUrlSaved(true);
      setTimeout(() => setUrlSaved(false), 2000);
    } catch {
      setSourceUrl(current);
    }
  };

  const grouped = useMemo(() => {
    const map = new Map<string, SlotAnalysis[]>();
    for (const slot of deck.slots) {
      const key = slot.section;
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(slot);
    }
    return [...map.entries()].sort((a, b) => sectionRank(a[0]) - sectionRank(b[0]));
  }, [deck.slots]);

  const trackable = deck.slots.filter(s => !isIdentityCard(s));
  const ownedCount = trackable.reduce((n, s) => n + Math.min(s.owned, s.quantity), 0);
  const totalCount = trackable.reduce((n, s) => n + s.quantity, 0);
  const missingCount = trackable.reduce((n, s) => n + s.missing, 0);
  const unknownCount = trackable.filter(s => !s.card_id || !s.card).length;
  const totalCommitted = deck.slots.reduce((n, s) => n + (s.committed_quantity ?? 0), 0);

  const committableSlots = deck.slots.filter(s => s.card_id && !isIdentityCard(s));
  const allCommitted =
    committableSlots.length > 0 &&
    committableSlots.every(s => (s.committed_quantity ?? 0) > 0);

  const handleCommitAll = async () => {
    if (!onCommitAll) return;
    setCommittingAll(true);
    try {
      await onCommitAll(!allCommitted);
    } finally {
      setCommittingAll(false);
    }
  };

  const handleCommitClick = async (slot: SlotAnalysis, e: MouseEvent) => {
    e.stopPropagation();
    if (!slot.card_id || !onCommit) return;
    setCommittingId(slot.card_id);
    try {
      const currentCommitted = slot.committed_quantity ?? 0;
      const newQty = currentCommitted > 0 ? 0 : Math.min(slot.rawOwned, slot.quantity);
      await onCommit(slot.card_id, newQty);
    } finally {
      setCommittingId(null);
    }
  };

  return (
    <>
      <div className="deck-detail-overlay" onClick={onClose}>
        <div className="deck-detail" onClick={e => e.stopPropagation()}>
          <div className="deck-detail-header">
            <button className="deck-detail-close" onClick={onClose}>✕</button>
            <div className="deck-detail-title">{deck.legend || deck.name}</div>
            {deck.player && (
              <div className="deck-detail-sub">
                {deck.player} · #{deck.placement} · {deck.wins}W-{deck.losses}L
              </div>
            )}
            <div className="deck-detail-sub">
              {deck.tournament}{deck.date ? ` · ${deck.date}` : ""}
            </div>
            <div className="deck-detail-sub">
              {deck.sets.map(s => (
                <span key={s} className="set-tag">{s}</span>
              ))}
            </div>
          </div>

          <div className="deck-detail-summary">
            <span className="owned">✓ {ownedCount} owned</span>
            {missingCount > 0 && <span className="missing">✗ {missingCount} missing</span>}
            <span className="total">{totalCount} total</span>
            {totalCommitted > 0 && (
              <span className="committed-total">⚑ {totalCommitted} committed</span>
            )}
            {unknownCount > 0 && (
              <span className="deck-unknown-note">{unknownCount} not ingested</span>
            )}
            {deck.isSaved && onCommitAll && (
              <button
                className={`deck-commit-all-btn${allCommitted ? " committed" : ""}`}
                onClick={handleCommitAll}
                disabled={committingAll || committingId !== null || committableSlots.length === 0}
                title={allCommitted ? "Uncommit all cards from this deck" : "Commit all cards to this deck"}
              >
                {committingAll
                  ? "…"
                  : allCommitted
                    ? "🔒 Uncommit All"
                    : "🔓 Commit All"}
              </button>
            )}
          </div>

          {/* Pinned card panel — sits between summary and card list, large display */}
          {pinnedCard && (
            <div className="deck-card-pinned-panel">
              <button
                className="deck-card-pinned-close"
                onClick={() => setPinnedCard(null)}
              >
                ✕
              </button>
              <img
                src={pinnedCard.image_url}
                alt={pinnedCard.name}
                className="deck-card-pinned-img"
              />
              <div className="deck-card-pinned-name">{pinnedCard.name}</div>
            </div>
          )}

          <div className="deck-detail-cards">
            {grouped.map(([section, slots]) => (
              <div key={section}>
                <div className="deck-section-label">
                  {section} ({slots.reduce((n, s) => n + s.quantity, 0)})
                </div>
                {slots.map((slot, i) => (
                  <div key={i} className={slotClass(slot)}>
                    <span className="deck-card-qty">{slot.quantity}x</span>
                    <span
                      className="deck-card-name"
                      style={{ cursor: slot.card ? "pointer" : "default" }}
                      onMouseEnter={e => {
                        if (slot.card) {
                          setHoveredCard(slot.card);
                          setTooltipPos({ x: e.clientX, y: e.clientY });
                        }
                      }}
                      onMouseMove={e => {
                        if (slot.card) setTooltipPos({ x: e.clientX, y: e.clientY });
                      }}
                      onMouseLeave={() => {
                        setHoveredCard(null);
                        setTooltipPos(null);
                      }}
                      onClick={e => {
                        e.stopPropagation();
                        if (slot.card) {
                          setPinnedCard(p =>
                            p?.id === slot.card!.id ? null : slot.card!,
                          );
                        }
                      }}
                    >
                      {slot.card_name}
                    </span>
                    {slot.committedElsewhere > 0 && (
                      <span
                        className="deck-card-locked-elsewhere"
                        title={slot.commitmentDetails
                          .map(d => `${d.qty}x in "${d.deckName}"`)
                          .join(", ")}
                      >
                        ⚑{slot.committedElsewhere}
                      </span>
                    )}
                    <span className="deck-card-status">{slotStatus(slot)}</span>
                    {deck.isSaved && !isIdentityCard(slot) && slot.card_id && (
                      <button
                        className={`deck-card-commit${(slot.committed_quantity ?? 0) > 0 ? " committed" : ""}`}
                        title={
                          (slot.committed_quantity ?? 0) > 0
                            ? "Uncommit from this deck"
                            : "Commit copies to this deck"
                        }
                        disabled={
                          committingId !== null ||
                          (!slot.card && (slot.committed_quantity ?? 0) === 0)
                        }
                        onClick={e => handleCommitClick(slot, e)}
                      >
                        {(slot.committed_quantity ?? 0) > 0 ? "🔒" : "🔓"}
                      </button>
                    )}
                  </div>
                ))}
              </div>
            ))}
          </div>

          <div className="deck-attribution">
            <div className="deck-attribution-row">
              <span>
                {deck.source_url && !deck.isSaved ? (
                  <>Data from <a href={deck.source_url} target="_blank" rel="noopener noreferrer">{deck.source}</a></>
                ) : (
                  <>Source: {deck.source}</>
                )}
              </span>
              {deck.isSaved && onEdit && (
                <button className="deck-edit-btn" onClick={() => onEdit(deck)}>
                  Edit &amp; Fork
                </button>
              )}
            </div>
            {deck.isSaved && (
              <div className="deck-source-url-row">
                <span className="deck-source-url-label">Link</span>
                <input
                  className="deck-source-url-input"
                  type="url"
                  placeholder="Original post URL…"
                  value={sourceUrl}
                  onChange={e => setSourceUrl(e.target.value)}
                  onBlur={handleSourceUrlBlur}
                  onKeyDown={e => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }}
                />
                {sourceUrl && (
                  <a
                    href={sourceUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="deck-source-url-link"
                    title="Open link"
                  >
                    ↗
                  </a>
                )}
                {urlSaved && <span className="deck-url-saved-hint">✓</span>}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Hover tooltip — position:fixed, follows cursor, zero layout impact */}
      {hoveredCard && tooltipPos && !pinnedCard && (
        <div className="deck-card-hover-tooltip" style={tooltipStyle(tooltipPos)}>
          <img
            src={hoveredCard.image_url}
            alt={hoveredCard.name}
            className="deck-card-hover-tooltip-img"
          />
        </div>
      )}
    </>
  );
}

function DeckTile({
  deck,
  onClick,
  onDelete,
}: {
  deck: DeckWithAnalysis;
  onClick: () => void;
  onDelete?: () => void;
}) {
  const pct = deck.totalCards > 0 ? Math.round((deck.ownedCards / deck.totalCards) * 100) : 0;
  return (
    <div className="deck-tile" onClick={onClick}>
      {onDelete && (
        <button
          className="deck-tile-delete"
          title="Remove deck"
          onClick={e => { e.stopPropagation(); onDelete(); }}
        >
          ✕
        </button>
      )}
      {deck.legend_image_url ? (
        <div className="deck-tile-banner">
          <img src={deck.legend_image_url} alt={deck.legend} className="deck-tile-banner-img" />
          <div className="deck-tile-banner-overlay" />
          <div className="deck-tile-banner-label">
            <span className="deck-tile-banner-name">{deck.legend || deck.name}</span>
          </div>
        </div>
      ) : (
        <div className="deck-tile-body" style={{ paddingBottom: 0 }}>
          <div className="deck-tile-legend">{deck.legend || deck.name}</div>
        </div>
      )}
      <div className="deck-tile-body">
        {deck.player ? (
          <div className="deck-tile-meta">
            <strong>{deck.player}</strong> · #{deck.placement} · {deck.wins}W-{deck.losses}L
            <br />
            {deck.tournament}
            <br />
            {deck.date}
          </div>
        ) : (
          <div className="deck-tile-meta">
            {deck.tournament}
            {deck.date && <><br />{deck.date}</>}
          </div>
        )}
        {deck.sets.length > 0 && (
          <div className="set-tags">
            {deck.sets.map(s => (
              <span key={s} className="set-tag">{s}</span>
            ))}
          </div>
        )}
        <div className="deck-ownership">
          <div className="progress" style={{ flex: 1 }}>
            <div
              className={`progress-bar${deck.canComplete ? " complete" : ""}`}
              style={{ width: `${pct}%` }}
            />
          </div>
          <span>{deck.ownedCards}/{deck.totalCards}</span>
        </div>
      </div>
    </div>
  );
}

export default function DeckBuilder({
  cards,
  savedDecks,
  onSavedDecksChange,
  savedDecksLoaded,
}: {
  cards: Card[];
  savedDecks: CommunityDeck[];
  onSavedDecksChange: (decks: CommunityDeck[]) => void;
  savedDecksLoaded: boolean;
}) {
  // Sub-tab, selection and filters are remembered across a reload so a phone
  // discarding the backgrounded tab doesn't dump you back at the deck list.
  const [deckTab, setDeckTab] = usePersistedState<"community" | "saved">(
    "decks.tab",
    "community",
  );

  // Community — loads independently (can be slow)
  const [decks, setDecks] = useState<CommunityDeck[]>([]);
  const [configured, setConfigured] = useState(true);
  const [communityLoading, setCommunityLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [countAllVariants, setCountAllVariants] = useState(true);

  // Reactive selection: store only the ID, derive the analyzed deck from memo
  const [selectedId, setSelectedId] = usePersistedState<string | null>("decks.selectedId", null);

  const [search, setSearch] = usePersistedState("decks.search", "");
  const [setFilter, setSetFilter] = usePersistedState("decks.set", "");
  const [completionFilter, setCompletionFilter] = usePersistedState("decks.completion", "all");

  // Import is a modal wizard holding unsaved paste text — deliberately not
  // persisted, so it never reopens half-filled on return.
  const [importOpen, setImportOpen] = useState(false);
  const [importText, setImportText] = useState("");
  const [importFormat, setImportFormat] = useState<"piltover" | "riftbound_gg">("piltover");
  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const [isEditMode, setIsEditMode] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    // Community can be slow — load independently so saved tab is immediately usable
    fetchCommunityDecks()
      .then(({ configured: cfg, decks: d }) => {
        setConfigured(cfg);
        setDecks(d);
      })
      .catch(e => setError(String(e)))
      .finally(() => setCommunityLoading(false));

    fetchDeckOptions()
      .then(opts => setCountAllVariants(opts.count_all_variants))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (importOpen) textareaRef.current?.focus();
  }, [importOpen]);

  const cardMap = useMemo(() => {
    const normalizeId = (id: string) => {
      const parts = id.split("-");
      return parts.length > 2 && /^\d+$/.test(parts[parts.length - 1])
        ? parts.slice(0, -1).join("-")
        : id;
    };
    const map = new Map<string, Card>();
    for (const c of cards) {
      map.set(c.id, c);
      map.set(normalizeId(c.id), c);
    }
    return map;
  }, [cards]);

  // Map card name → all cards with that name (different sets, alt arts, showcases)
  const nameMap = useMemo(() => {
    const map = new Map<string, Card[]>();
    for (const c of cards) {
      const key = c.name.toLowerCase();
      const arr = map.get(key) ?? [];
      arr.push(c);
      map.set(key, arr);
    }
    return map;
  }, [cards]);

  const analyzed = useMemo(
    () => decks.map(d => analyze(d, cardMap, nameMap, countAllVariants, savedDecks)),
    [decks, cardMap, nameMap, countAllVariants, savedDecks],
  );

  const savedAnalyzed = useMemo(
    () => savedDecks.map(d => analyze(d, cardMap, nameMap, countAllVariants, savedDecks)),
    [savedDecks, cardMap, nameMap, countAllVariants],
  );

  // Reactive: auto-updates when savedDecks changes (e.g. after commit)
  const selected = useMemo(() => {
    if (!selectedId) return null;
    return (
      savedAnalyzed.find(d => d.id === selectedId) ??
      analyzed.find(d => d.id === selectedId) ??
      null
    );
  }, [selectedId, savedAnalyzed, analyzed]);

  const allCommunitySets = useMemo(
    () => [...new Set(decks.flatMap(d => d.sets))].sort(),
    [decks],
  );

  const filteredCommunity = useMemo(() => {
    let result = analyzed;
    if (search) {
      const q = search.toLowerCase();
      result = result.filter(
        d =>
          d.legend.toLowerCase().includes(q) ||
          d.player.toLowerCase().includes(q) ||
          d.tournament.toLowerCase().includes(q),
      );
    }
    if (setFilter) result = result.filter(d => d.sets.includes(setFilter));
    if (completionFilter === "complete") result = result.filter(d => d.canComplete);
    if (completionFilter === "partial") result = result.filter(d => d.hasAny && !d.canComplete);
    if (completionFilter === "missing") result = result.filter(d => !d.hasAny);
    return result;
  }, [analyzed, search, setFilter, completionFilter]);

  const filteredSaved = useMemo(() => {
    if (!search) return savedAnalyzed;
    const q = search.toLowerCase();
    return savedAnalyzed.filter(
      d =>
        d.legend.toLowerCase().includes(q) ||
        d.name.toLowerCase().includes(q),
    );
  }, [savedAnalyzed, search]);

  const handleImport = async () => {
    if (!importText.trim()) return;
    setImporting(true);
    setImportError(null);
    try {
      const deck = await saveDeck(importText, importFormat);
      onSavedDecksChange([deck, ...savedDecks]);
      setImportOpen(false);
      setImportText("");
      setDeckTab("saved");
      setSelectedId(deck.id);
    } catch (e) {
      setImportError(String(e));
    } finally {
      setImporting(false);
    }
  };

  const handleDelete = async (deck: DeckWithAnalysis) => {
    try {
      await deleteSavedDeck(deck.id);
      onSavedDecksChange(savedDecks.filter(d => d.id !== deck.id));
      if (selectedId === deck.id) setSelectedId(null);
    } catch {
      // silently ignore; the deck stays in list
    }
  };

  const handleCommit = async (cardId: string, qty: number) => {
    if (!selectedId) return;
    const updated = await commitCard(selectedId, cardId, qty);
    onSavedDecksChange(savedDecks.map(d => d.id === updated.id ? updated : d));
  };

  const handleCommitAll = async (commit: boolean) => {
    if (!selectedId) return;
    const updated = await commitAllCards(selectedId, commit);
    onSavedDecksChange(savedDecks.map(d => d.id === updated.id ? updated : d));
  };

  const handleEdit = (deck: DeckWithAnalysis) => {
    setImportText(deckToText(deck));
    setImportFormat("piltover");
    setImportError(null);
    setIsEditMode(true);
    setImportOpen(true);
  };

  const handleMetaChange = async (meta: { source_url: string | null }) => {
    if (!selectedId) return;
    const updated = await updateDeckMeta(selectedId, meta);
    onSavedDecksChange(savedDecks.map(d => d.id === updated.id ? updated : d));
  };

  const closeImportModal = () => {
    setImportOpen(false);
    setIsEditMode(false);
  };

  const FORMAT_PLACEHOLDERS: Record<string, string> = {
    piltover: "Legend:\n1 Legend Name\n\nChampion:\n1 Champion Card\n\nMainDeck:\n3 Card Name\n…",
    riftbound_gg: "1 Akali - Rogue Assassin (VEN-189)\n3 Shuriken Flip (VEN-140)\n6 Fury Rune (OGN-007a)\n…",
  };

  const importModal = importOpen && (
    <div className="deck-detail-overlay" onClick={closeImportModal}>
      <div className="import-modal" onClick={e => e.stopPropagation()}>
        <button className="deck-detail-close" onClick={closeImportModal}>✕</button>
        <h3 className="import-modal-title">
          {isEditMode ? "Edit Deck" : "Import Deck"}
        </h3>
        {isEditMode && (
          <p className="import-modal-hint">Saves as a new deck — original is unchanged.</p>
        )}

        <div className="import-source-row">
          <span className="import-source-label">Source</span>
          <div className="import-source-opts">
            <label className="import-source-opt">
              <input
                type="radio"
                name="importFormat"
                value="piltover"
                checked={importFormat === "piltover"}
                onChange={() => setImportFormat("piltover")}
              />
              Riftdeck / Piltover Archive
            </label>
            <label className="import-source-opt">
              <input
                type="radio"
                name="importFormat"
                value="riftbound_gg"
                checked={importFormat === "riftbound_gg"}
                onChange={() => setImportFormat("riftbound_gg")}
              />
              riftbound.gg
            </label>
          </div>
        </div>

        <textarea
          ref={textareaRef}
          className="import-textarea"
          value={importText}
          onChange={e => setImportText(e.target.value)}
          placeholder={FORMAT_PLACEHOLDERS[importFormat]}
          onKeyDown={e => { if (e.key === "Escape") closeImportModal(); }}
        />
        {importError && <div className="banner error" style={{ margin: "8px 0 0" }}>{importError}</div>}
        <div className="import-actions">
          <button onClick={closeImportModal}>Cancel</button>
          <button
            className="btn-primary"
            onClick={handleImport}
            disabled={importing || !importText.trim()}
          >
            {importing ? "Saving…" : isEditMode ? "Save as New Deck" : "Save to My Decks"}
          </button>
        </div>
      </div>
    </div>
  );

  return (
    <main className="deck-builder">
      <div className="deck-builder-titlebar">
        <h2 className="section-title">Decks</h2>
        <button className="btn-import" onClick={() => setImportOpen(true)}>Import Deck</button>
      </div>

      <div className="deck-inner-tabs">
        <button
          className={deckTab === "community" ? "deck-inner-tab active" : "deck-inner-tab"}
          onClick={() => setDeckTab("community")}
        >
          Community
          {communityLoading && <span className="deck-inner-tab-count">…</span>}
        </button>
        <button
          className={deckTab === "saved" ? "deck-inner-tab active" : "deck-inner-tab"}
          onClick={() => setDeckTab("saved")}
        >
          My Decks
          {!!savedDecksLoaded && savedDecks.length > 0 && (
            <span className="deck-inner-tab-count">{savedDecks.length}</span>
          )}
          {!savedDecksLoaded && <span className="deck-inner-tab-count">…</span>}
        </button>
      </div>

      {deckTab === "community" && (
        <>
          {!configured && (
            <div className="banner">
              <strong>TopDeck.gg API key required.</strong> Get a free key at{" "}
              <a href="https://topdeck.gg" target="_blank" rel="noopener noreferrer" style={{ color: "var(--blue)" }}>
                topdeck.gg
              </a>{" "}
              then set <code>RIFTBOUND_TOPDECK_KEY=&lt;your-key&gt;</code> and restart the backend.
            </div>
          )}
          {error && <div className="banner error">Failed to load decks: {error}</div>}
          {communityLoading ? (
            <p className="empty">Loading community decks…</p>
          ) : (
            <>
              <div className="filters">
                <input
                  placeholder="Search legend, player, tournament..."
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                />
                <select value={setFilter} onChange={e => setSetFilter(e.target.value)}>
                  <option value="">All sets</option>
                  {allCommunitySets.map(s => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
                <select value={completionFilter} onChange={e => setCompletionFilter(e.target.value)}>
                  <option value="all">All decks</option>
                  <option value="complete">Can complete</option>
                  <option value="partial">Partially owned</option>
                  <option value="missing">Missing all</option>
                </select>
              </div>
              <p className="stats">
                Showing {filteredCommunity.length} of {analyzed.length} decks
              </p>
              {filteredCommunity.length === 0 ? (
                <p className="empty">No decks match your filters.</p>
              ) : (
                <div className="deck-grid">
                  {filteredCommunity.map(deck => (
                    <DeckTile key={deck.id} deck={deck} onClick={() => setSelectedId(deck.id)} />
                  ))}
                </div>
              )}
            </>
          )}
        </>
      )}

      {deckTab === "saved" && (
        <>
          {!savedDecksLoaded ? (
            <p className="empty">Loading saved decks…</p>
          ) : filteredSaved.length === 0 && !search ? (
            <p className="empty">
              No saved decks yet.
              <br />
              Use "Import Deck" to paste a decklist and save it here.
            </p>
          ) : (
            <>
              <div className="filters">
                <input
                  placeholder="Search legend or name..."
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                />
              </div>
              {filteredSaved.length === 0 ? (
                <p className="empty">No saved decks match your search.</p>
              ) : (
                <div className="deck-grid">
                  {filteredSaved.map(deck => (
                    <DeckTile
                      key={deck.id}
                      deck={deck}
                      onClick={() => setSelectedId(deck.id)}
                      onDelete={() => handleDelete(deck)}
                    />
                  ))}
                </div>
              )}
            </>
          )}
        </>
      )}

      {importModal}
      {selected && (
        <DeckDetail
          deck={selected}
          onClose={() => setSelectedId(null)}
          onCommit={selected.isSaved ? handleCommit : undefined}
          onCommitAll={selected.isSaved ? handleCommitAll : undefined}
          onEdit={selected.isSaved ? handleEdit : undefined}
          onMetaChange={selected.isSaved ? handleMetaChange : undefined}
        />
      )}
    </main>
  );
}
