export interface TokenOut {
  access_token: string;
  token_type: string;
  username: string;
}

export interface Card {
  id: string;
  name: string;
  set_code: string;
  number: string;
  rarity: string;
  domain: string;
  card_type: string;
  image_url: string;
  count: number; // non-foil copies
  foil_count: number; // foil copies
  in_binder: boolean; // marked present in the collector's binder
  binder_foil: boolean; // the binder copy is a foil
  limit: number;
  limit_override: number | null;
}

export interface CommunityUser {
  id: number;
  username: string;
  unique_cards: number; // distinct cards owned (incl. binder-only)
  total_copies: number; // physical copies, foil + non-foil
  is_self: boolean;
}

/** One card+finish the requester wants from someone else's collection. */
export interface TradeItem {
  card_id: string;
  foil: boolean;
  quantity: number;
}

export interface TradePreviewLine {
  card_id: string;
  card_name: string;
  image_url: string | null; // null when the card id isn't in the catalog
  foil: boolean;
  requested: number;
  current_count: number; // owner's count for this finish, before the trade
  resulting_count: number; // what it becomes if fulfilled in full
  known: boolean;
  sufficient: boolean;
}

export interface TradePreview {
  from_username: string | null;
  to_username: string | null;
  lines: TradePreviewLine[];
  warnings: string[];
}

export interface LimitRules {
  type_limits: Record<string, number>;
  rarity_caps_enabled: boolean;
  rarity_caps: Record<string, number>;
  showcase_cap_enabled: boolean;
  fallback_limit: number;
}

export interface CardPrice {
  card_id: string;
  configured: boolean; // false when no pricing API key is set server-side
  market_price: number | null;
  low_price: number | null;
  foil_market_price: number | null;
  foil_low_price: number | null;
  currency: string;
  updated_at: string | null;
  stale: boolean;
  pct_change_7d: number | null;
  pct_change_30d: number | null;
}

export interface PriceHistoryPoint {
  date: string;
  market_price: number | null;
  foil_market_price: number | null;
}

export interface PriceHistory {
  card_id: string;
  points: PriceHistoryPoint[];
}

export interface CommunityDeckCard {
  card_id: string | null;
  card_name: string;
  quantity: number;
  section: string;
  committed_quantity?: number;
}

export interface CommunityDeck {
  id: string;
  name: string;
  legend: string;
  legend_image_url: string | null;
  player: string;
  placement: number;
  wins: number;
  losses: number;
  tournament: string;
  source: string;
  source_url: string | null;
  date: string;
  sets: string[];
  cards: CommunityDeckCard[];
}

export interface PriceStatus {
  configured: boolean;
  requests_used_today: number;
  daily_budget: number;
  stale_hours: number;
}

export interface DeckOptions {
  count_all_variants: boolean;
}
