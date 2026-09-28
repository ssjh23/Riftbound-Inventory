import { describe, expect, it } from "vitest";

import { formatPctChange, formatPrice, normalizeSeries, trendDirection } from "./price";

describe("formatPrice", () => {
  it("formats known currencies with their symbol and 2 decimals", () => {
    expect(formatPrice(1.5, "USD")).toBe("$1.50");
    expect(formatPrice(2, "EUR")).toBe("€2.00");
  });

  it("falls back to the currency code for unknown currencies", () => {
    expect(formatPrice(3, "JPY")).toBe("JPY 3.00");
  });

  it("renders null as an em dash", () => {
    expect(formatPrice(null)).toBe("—");
  });
});

describe("formatPctChange", () => {
  it("prefixes a plus sign on positive change, keeps minus on negative", () => {
    expect(formatPctChange(4.567)).toBe("+4.6%");
    expect(formatPctChange(-2.1)).toBe("-2.1%");
    expect(formatPctChange(0)).toBe("+0.0%");
  });

  it("renders null as an em dash", () => {
    expect(formatPctChange(null)).toBe("—");
  });
});

describe("trendDirection", () => {
  it("treats +/-0.5% as flat (noise), beyond that as up/down", () => {
    expect(trendDirection(0.4)).toBe("flat");
    expect(trendDirection(-0.4)).toBe("flat");
    expect(trendDirection(0.6)).toBe("up");
    expect(trendDirection(-0.6)).toBe("down");
    expect(trendDirection(null)).toBeNull();
  });
});

describe("normalizeSeries", () => {
  it("maps values to [0, 1] with min at 0 and max at 1", () => {
    expect(normalizeSeries([1, 2, 3])).toEqual([0, 0.5, 1]);
  });

  it("returns null with fewer than 2 usable points", () => {
    expect(normalizeSeries([])).toBeNull();
    expect(normalizeSeries([5])).toBeNull();
    expect(normalizeSeries([null, 5, null])).toBeNull();
  });

  it("maps a flat (all-equal) series to a flat 0.5 line, not NaN", () => {
    expect(normalizeSeries([2, 2, 2])).toEqual([0.5, 0.5, 0.5]);
  });

  it("places null points at the midline without breaking the scale of real ones", () => {
    expect(normalizeSeries([0, null, 10])).toEqual([0, 0.5, 1]);
  });
});
