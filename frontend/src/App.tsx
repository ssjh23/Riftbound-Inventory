import { useCallback, useEffect, useMemo, useState } from "react";

import { fetchCards, fetchSavedDecks, setSessionExpiredHandler } from "./api";
import { clearToken, getToken, getUsername } from "./auth";
import {
  DEFAULT_TAB,
  TAB_LABELS,
  TABS,
  readTabFromHash,
  tabToHash,
  type Tab,
} from "./lib/hashRoute";
import { clearPersistedView } from "./lib/persistentState";
import { applyShineSettings, loadShineSettings } from "./lib/shine";
import Achievements from "./screens/Achievements";
import Collection, { type CollectionPreset } from "./screens/Collection";
import Community from "./screens/Community";
import Dashboard from "./screens/Dashboard";
import DeckBuilder from "./screens/DeckBuilder";
import Login from "./screens/Login";
import Settings from "./screens/Settings";
import type { Card, CommunityDeck } from "./types";

// Apply the user's saved shine tuning to :root as soon as the module loads,
// so the CSS variables are in place before the first paint.
applyShineSettings(loadShineSettings());

export default function App() {
  const [username, setUsername] = useState<string | null>(() =>
    getToken() ? getUsername() : null,
  );
  // The URL is the source of truth for the tab, so a reload — including the
  // one a phone performs after discarding a backgrounded tab — comes back on
  // the same screen. See lib/hashRoute.ts.
  const [tab, setTab] = useState<Tab>(() => readTabFromHash(location.hash) ?? DEFAULT_TAB);
  const [cards, setCards] = useState<Card[]>([]);
  const [preset, setPreset] = useState<CollectionPreset | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [savedDecks, setSavedDecks] = useState<CommunityDeck[]>([]);
  const [savedDecksLoaded, setSavedDecksLoaded] = useState(false);

  // tab → URL. Clicking a tab pushes a history entry, so the device back
  // button steps between tabs instead of leaving the app; the first render
  // only normalises a bare "/" and uses replaceState so there is no empty
  // entry to step back through.
  useEffect(() => {
    const target = tabToHash(tab);
    if (location.hash === target) return;
    if (readTabFromHash(location.hash) === null) {
      history.replaceState(null, "", target);
    } else {
      location.hash = target;
    }
  }, [tab]);

  // URL → tab, for back/forward and hand-edited links.
  useEffect(() => {
    const onHashChange = () => setTab(readTabFromHash(location.hash) ?? DEFAULT_TAB);
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  // An expired token now drops us to Login in place rather than reloading the
  // document, so view state (and the tab) survives re-authenticating.
  useEffect(() => setSessionExpiredHandler(handleLogout), []);

  const reload = useCallback(() => {
    if (!getToken()) return;
    fetchCards()
      .then((c) => {
        setCards(c);
        setError(null);
      })
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(reload, [reload, username]);

  // Fetch saved decks once on login; kept here so Collection can read commitments.
  useEffect(() => {
    if (!username) return;
    fetchSavedDecks()
      .then(setSavedDecks)
      .catch(() => {})
      .finally(() => setSavedDecksLoaded(true));
  }, [username]);

  // card_id → list of {deckName, qty} for every committed slot across all saved decks
  const commitmentMap = useMemo(() => {
    const map = new Map<string, { deckName: string; qty: number }[]>();
    for (const deck of savedDecks) {
      for (const card of deck.cards) {
        if (card.card_id && (card.committed_quantity ?? 0) > 0) {
          const entry = map.get(card.card_id) ?? [];
          entry.push({ deckName: deck.legend || deck.name, qty: card.committed_quantity! });
          map.set(card.card_id, entry);
        }
      }
    }
    return map;
  }, [savedDecks]);

  // Patch a single card in place so +/- clicks don't refetch the whole list.
  const updateCard = useCallback((card: Card) => {
    setCards((prev) => prev.map((c) => (c.id === card.id ? card : c)));
  }, []);

  // Dashboard "View missing" jumps to the Collection tab pre-filtered.
  const viewSetMissing = useCallback((setCode: string) => {
    setPreset({ set: setCode, owned: "missing" });
    setTab("collection");
  }, []);

  function handleLogin(name: string) {
    setUsername(name);
    setCards([]);
  }

  function handleLogout() {
    clearToken();
    // Persisted filters and drill-downs belong to the account that set them.
    clearPersistedView();
    setTab(DEFAULT_TAB);
    setUsername(null);
    setCards([]);
    setSavedDecks([]);
    setSavedDecksLoaded(false);
    setError(null);
  }

  if (!username) {
    return <Login onLogin={handleLogin} />;
  }

  return (
    <div className="app">
      <header>
        <h1>Riftbound Inventory</h1>
        <nav>
          {TABS.map((t) => (
            <button
              key={t}
              className={tab === t ? "tab active" : "tab"}
              onClick={() => setTab(t)}
            >
              {TAB_LABELS[t]}
            </button>
          ))}
        </nav>
        <div className="user-badge">
          <span>
            Logged in as <strong>{username}</strong>
          </span>
          <button onClick={handleLogout}>Log out</button>
        </div>
      </header>
      {error && <div className="banner error">{error} — is the backend running?</div>}
      {tab === "overview" && <Dashboard cards={cards} onViewSet={viewSetMissing} />}
      {tab === "collection" && (
        <Collection
          cards={cards}
          onCardChange={updateCard}
          preset={preset}
          commitmentMap={commitmentMap}
          persistKey="mine"
        />
      )}
      {tab === "achievements" && <Achievements cards={cards} />}
      {tab === "settings" && <Settings onRulesChanged={reload} />}
      {tab === "decks" && (
        <DeckBuilder
          cards={cards}
          savedDecks={savedDecks}
          onSavedDecksChange={setSavedDecks}
          savedDecksLoaded={savedDecksLoaded}
        />
      )}
      {tab === "community" && <Community />}
    </div>
  );
}
