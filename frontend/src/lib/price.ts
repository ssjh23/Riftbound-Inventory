/** Pure helpers for displaying price + trend data. Kept free of DOM/React so
 * they're trivially unit-testable, matching the rest of lib/. */

export type TrendDirection = "up" | "down" | "flat";

const CURRENCY_SYMBOL: Record<string, string> = { USD: "$", EUR: "€", GBP: "£" };

export function formatPrice(value: number | null, currency = "USD"): string {
  if (value === null) return "—";
  const symbol = CURRENCY_SYMBOL[currency] ?? `${currency} `;
  return `${symbol}${value.toFixed(2)}`;
}

export function formatPctChange(pct: number | null): string {
  if (pct === null) return "—";
  const sign = pct > 0 ? "+" : "";
  return `${sign}${pct.toFixed(1)}%`;
}

/** Flat within +/-0.5% reads as noise, not a real trend. */
export function trendDirection(pct: number | null): TrendDirection | null {
  if (pct === null) return null;
  if (pct > 0.5) return "up";
  if (pct < -0.5) return "down";
  return "flat";
}

/** Map a list of possibly-null values to [0, 1] (min -> 0, max -> 1) for
 * plotting, dropping nulls first. Returns null if fewer than 2 usable points
 * (a sparkline needs at least a start and an end). A flat series (all equal)
 * normalizes to a flat 0.5 line rather than dividing by zero. */
export function normalizeSeries(values: (number | null)[]): number[] | null {
  const present = values.filter((v): v is number => v !== null);
  if (present.length < 2) return null;
  const min = Math.min(...present);
  const max = Math.max(...present);
  if (max === min) return values.map(() => 0.5);
  return values.map((v) => (v === null ? 0.5 : (v - min) / (max - min)));
}
