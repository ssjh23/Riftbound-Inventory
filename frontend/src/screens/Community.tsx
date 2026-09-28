import { useEffect, useMemo, useState } from "react";

import { exportTradeRequest, fetchCommunityUsers, fetchUserCards } from "../api";
import { usePersistedState } from "../lib/persistentState";
import {
  selectionCount,
  selectionToItems,
  setSelection,
  type TradeSelectionMap,
} from "../lib/trade";
import type { Card, CommunityUser } from "../types";
import Collection from "./Collection";

export default function Community() {
  const [users, setUsers] = useState<CommunityUser[]>([]);
  const [usersError, setUsersError] = useState<string | null>(null);
  const [usersLoading, setUsersLoading] = useState(true);

  // Remember the drill-down across a reload by id rather than by object, so a
  // renamed user can never be restored under a stale name — the id is resolved
  // against a freshly fetched directory below.
  const [selectedId, setSelectedId] = usePersistedState<number | null>("community.userId", null);
  const [selected, setSelected] = useState<CommunityUser | null>(null);
  const [cards, setCards] = useState<Card[]>([]);
  const [cardsError, setCardsError] = useState<string | null>(null);
  const [cardsLoading, setCardsLoading] = useState(false);

  const [basket, setBasket] = useState<TradeSelectionMap>(new Map());
  const [exportText, setExportText] = useState<string | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    fetchCommunityUsers()
      .then((list) => {
        setUsers(list);
        // Restore the collection we were looking at before the tab was
        // reloaded. A user who has since disappeared just leaves us in the
        // directory. Runs once, on the initial fetch.
        setSelected((prev) => prev ?? list.find((u) => u.id === selectedId) ?? null);
      })
      .catch((e) => setUsersError(String(e)))
      .finally(() => setUsersLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- selectedId is the
    // persisted value read once at mount; re-running on every change would
    // refetch the directory each time the viewer opens a user.
  }, []);

  // Load the selected user's collection; drop stale responses if the viewer
  // clicks back to the directory (or onto someone else) mid-flight.
  useEffect(() => {
    if (!selected) return;
    let active = true;
    setCardsLoading(true);
    setCardsError(null);
    setCards([]);
    fetchUserCards(selected.id)
      .then((c) => active && setCards(c))
      .catch((e) => active && setCardsError(String(e)))
      .finally(() => active && setCardsLoading(false));
    return () => {
      active = false;
    };
  }, [selected]);

  const cardById = useMemo(() => new Map(cards.map((c) => [c.id, c])), [cards]);
  const basketTotal = selectionCount(basket);

  function openUser(u: CommunityUser) {
    setSelected(u);
    setSelectedId(u.id);
    setBasket(new Map()); // a basket only ever belongs to one collection
  }

  function backToDirectory() {
    setSelected(null);
    setSelectedId(null);
    setBasket(new Map());
  }

  async function doExport() {
    setExporting(true);
    setExportError(null);
    setCopied(false);
    try {
      const { text } = await exportTradeRequest(selected!.username, selectionToItems(basket));
      setExportText(text);
    } catch (e) {
      setExportError(String(e));
    } finally {
      setExporting(false);
    }
  }

  async function copyExport() {
    try {
      await navigator.clipboard.writeText(exportText ?? "");
      setCopied(true);
    } catch {
      // Clipboard access is blocked outside secure contexts — the text is
      // right there in the box, so just tell them to copy it by hand.
      setExportError("Couldn't reach the clipboard — select the text above and copy it.");
    }
  }

  if (selected) {
    return (
      <div className="community">
        <div className="viewing-banner">
          <button className="viewing-back" onClick={backToDirectory}>
            ← All users
          </button>
          <span className="viewing-eye" aria-hidden="true">
            👁
          </span>
          <span>
            Viewing <strong>{selected.username}</strong>
            {selected.is_self ? "'s (your) " : "'s "}
            collection — <span className="viewing-tag">view only</span>
          </span>
        </div>
        {cardsError && <div className="banner error">{cardsError}</div>}
        {cardsLoading ? (
          <p className="empty">Loading {selected.username}'s collection…</p>
        ) : (
          <div className="trade-layout">
            <div className="trade-main">
              <Collection
                cards={cards}
                persistKey="community"
                readOnly
                trade={{
                  selection: basket,
                  onChange: (card, finish, quantity) =>
                    setBasket((prev) =>
                      setSelection(
                        prev,
                        card.id,
                        finish,
                        quantity,
                        finish === "foil" ? card.foil_count : card.count,
                      ),
                    ),
                }}
              />
            </div>

            <aside className="trade-panel" aria-label="Trade request">
              <h3 className="trade-panel-title">
                Requesting from {selected.username}
                <span className="trade-panel-count">{basketTotal}</span>
              </h3>
              {basketTotal === 0 ? (
                <p className="trade-panel-empty">
                  Use the <span className="trade-panel-key">+</span> next to any count to ask for
                  copies. You can't request more than they own.
                </p>
              ) : (
                <ul className="trade-panel-list">
                  {[...basket.entries()].map(([cardId, entry]) => {
                    const card = cardById.get(cardId);
                    return (
                      <li key={cardId}>
                        <span className="trade-item-name" title={card?.name ?? cardId}>
                          {card?.name ?? cardId}
                        </span>
                        <span className="trade-item-qty">
                          {entry.normal > 0 && <span>{entry.normal}× normal</span>}
                          {entry.foil > 0 && <span className="foil">{entry.foil}× foil</span>}
                        </span>
                        <button
                          className="trade-item-remove"
                          aria-label={`Remove ${card?.name ?? cardId}`}
                          onClick={() =>
                            setBasket((prev) => {
                              const next = new Map(prev);
                              next.delete(cardId);
                              return next;
                            })
                          }
                        >
                          ×
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
              <div className="trade-panel-foot">
                <button onClick={() => setBasket(new Map())} disabled={basketTotal === 0}>
                  Clear
                </button>
                <button className="primary" onClick={doExport} disabled={basketTotal === 0 || exporting}>
                  {exporting ? "Building…" : "Export request"}
                </button>
              </div>
              {exportError && !exportText && <div className="banner error">{exportError}</div>}
            </aside>
          </div>
        )}

        {exportText !== null && (
          <div className="modal-backdrop" onClick={() => setExportText(null)}>
            <div
              className="modal-panel trade-export"
              role="dialog"
              aria-label="Exported trade request"
              onClick={(e) => e.stopPropagation()}
            >
              <h3>Trade request for {selected.username}</h3>
              <p className="modal-hint">
                Send this to {selected.username} — they can paste it straight into the
                “Import trade request” button on their own collection.
              </p>
              <textarea className="trade-textarea" readOnly value={exportText} rows={12} />
              {exportError && <div className="banner error">{exportError}</div>}
              <div className="modal-actions">
                <button onClick={() => setExportText(null)}>Close</button>
                <button className="primary" onClick={copyExport}>
                  {copied ? "Copied ✓" : "Copy to clipboard"}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="community">
      <div className="stats">
        {usersLoading ? "Loading collectors…" : `${users.length} collector${users.length === 1 ? "" : "s"} on this app`}
      </div>
      {usersError && <div className="banner error">{usersError}</div>}
      <div className="user-grid">
        {users.map((u) => (
          <button key={u.id} className="user-card" onClick={() => openUser(u)}>
            <span className="user-avatar" aria-hidden="true">
              {u.username.charAt(0).toUpperCase()}
            </span>
            <span className="user-card-body">
              <span className="user-name">
                {u.username}
                {u.is_self && <span className="user-self-tag">You</span>}
              </span>
              <span className="user-stats">
                {u.unique_cards} cards · {u.total_copies} copies
              </span>
            </span>
          </button>
        ))}
      </div>
      {!usersLoading && users.length === 0 && <p className="empty">No users yet.</p>}
    </div>
  );
}
