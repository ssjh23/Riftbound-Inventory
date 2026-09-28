/**
 * Foil-shine visual settings.
 *
 * The three values below map to CSS custom properties consumed by the
 * `.card-tile.shiny .card-art::before` shine pseudo-element. They are stored
 * in localStorage (per-browser preference, not part of the collection data
 * that lives in SQLite) and re-applied to `document.documentElement` on
 * startup and on every change.
 */

export interface ShineSettings {
  duration: number; // total seconds per cycle — how often a glint happens
  sweepSpeed: number; // seconds a single sweep pass takes — how fast the band moves
  bandWidth: number; // half-width of the shine band, in gradient percent
  intensity: number; // 0 = invisible, 1 = default, up to 1.5 = extra bright
}

export const SHINE_DEFAULTS: ShineSettings = {
  duration: 7,
  sweepSpeed: 2.5,
  bandWidth: 6,
  intensity: 1,
};

export const SHINE_LIMITS = {
  duration: { min: 1, max: 20, step: 0.5, label: "Interval between glints (s)" },
  sweepSpeed: { min: 0.3, max: 8, step: 0.1, label: "Sweep speed (s)" },
  bandWidth: { min: 1, max: 20, step: 0.5, label: "Band width (%)" },
  intensity: { min: 0, max: 1.5, step: 0.05, label: "Intensity" },
} as const;

const STORAGE_KEY = "riftbound.shine";

/** Clamp/validate a raw JSON blob into a safe ShineSettings, filling gaps
 * with defaults. Pure — safe to unit-test without a browser. */
export function sanitizeShineSettings(raw: unknown): ShineSettings {
  const src = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
  const pick = (key: keyof ShineSettings): number => {
    const v = src[key];
    const { min, max } = SHINE_LIMITS[key];
    if (typeof v !== "number" || !Number.isFinite(v)) return SHINE_DEFAULTS[key];
    return Math.min(max, Math.max(min, v));
  };
  return {
    duration: pick("duration"),
    sweepSpeed: pick("sweepSpeed"),
    bandWidth: pick("bandWidth"),
    intensity: pick("intensity"),
  };
}

export function loadShineSettings(): ShineSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return sanitizeShineSettings(raw ? JSON.parse(raw) : {});
  } catch {
    return { ...SHINE_DEFAULTS };
  }
}

export function saveShineSettings(s: ShineSettings): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(s));
  applyShineSettings(s);
}

/** Push the settings into CSS custom properties on `:root`, and generate the
 * `@keyframes shine-sweep` rule so that sweep speed can vary independently of
 * total cycle duration (keyframe percentages can't be CSS variables). */
export function applyShineSettings(s: ShineSettings): void {
  const root = document.documentElement.style;
  root.setProperty("--shine-duration", `${s.duration}s`);
  root.setProperty("--shine-band-width", `${s.bandWidth}%`);
  root.setProperty("--shine-intensity", `${s.intensity}`);

  // Fraction of the total cycle spent visibly sweeping — clamped so an
  // overlong sweep just becomes a continuous slide with no pause.
  const sweepPortion = Math.min(1, s.sweepSpeed / s.duration);
  const pauseHalf = (1 - sweepPortion) / 2;
  const start = (pauseHalf * 100).toFixed(2);
  const end = ((pauseHalf + sweepPortion) * 100).toFixed(2);
  const keyframes = `@keyframes shine-sweep {
    0%, ${start}% { background-position: 200% 0; }
    ${end}%, 100% { background-position: -100% 0; }
  }`;

  let style = document.getElementById("shine-keyframes") as HTMLStyleElement | null;
  if (!style) {
    style = document.createElement("style");
    style.id = "shine-keyframes";
    document.head.appendChild(style);
  }
  style.textContent = keyframes;
}

/** Compute the sweep portion (0-1) used by applyShineSettings — exposed for
 * testing so we can verify the pause/sweep math without a DOM. */
export function computeSweepPortion(s: ShineSettings): number {
  return Math.min(1, s.sweepSpeed / s.duration);
}
