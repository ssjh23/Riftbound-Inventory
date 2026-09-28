import { describe, expect, it } from "vitest";

import { computeSweepPortion, SHINE_DEFAULTS, sanitizeShineSettings } from "./shine";

describe("sanitizeShineSettings", () => {
  it("returns defaults when the input is empty or garbage", () => {
    expect(sanitizeShineSettings(null)).toEqual(SHINE_DEFAULTS);
    expect(sanitizeShineSettings("nope")).toEqual(SHINE_DEFAULTS);
    expect(sanitizeShineSettings({})).toEqual(SHINE_DEFAULTS);
  });

  it("clamps out-of-range and non-numeric values, keeps valid ones", () => {
    const s = sanitizeShineSettings({
      duration: 8, // in range, kept
      bandWidth: 999, // clamped down to max
      intensity: "bright", // wrong type, falls back to default
    });
    expect(s).toEqual({
      duration: 8,
      sweepSpeed: SHINE_DEFAULTS.sweepSpeed,
      bandWidth: 20,
      intensity: SHINE_DEFAULTS.intensity,
    });
  });

  it("clamps negative values up to the min", () => {
    expect(sanitizeShineSettings({ duration: -3 }).duration).toBe(1);
  });

  it("sanitizes the new sweepSpeed field the same way", () => {
    expect(sanitizeShineSettings({ sweepSpeed: 4 }).sweepSpeed).toBe(4);
    expect(sanitizeShineSettings({ sweepSpeed: 999 }).sweepSpeed).toBe(8); // max
    expect(sanitizeShineSettings({}).sweepSpeed).toBe(SHINE_DEFAULTS.sweepSpeed);
  });
});

describe("computeSweepPortion", () => {
  it("splits the cycle into sweep + symmetric pause", () => {
    const p = computeSweepPortion({
      ...SHINE_DEFAULTS,
      duration: 8,
      sweepSpeed: 2,
    });
    expect(p).toBe(0.25); // 2s of visible sweep in an 8s cycle
  });

  it("clamps to 1.0 when the sweep is longer than the cycle", () => {
    const p = computeSweepPortion({
      ...SHINE_DEFAULTS,
      duration: 3,
      sweepSpeed: 8,
    });
    expect(p).toBe(1);
  });
});
