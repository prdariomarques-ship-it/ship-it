import { describe, expect, it } from "vitest";

import {
  formatDateTime,
  formatDuration,
  formatNumber,
  formatPercent,
  formatRelativeTime,
  formatUptime,
} from "@/lib/format";

describe("formatRelativeTime", () => {
  it("returns em-dash for null/undefined", () => {
    expect(formatRelativeTime(null)).toBe("—");
    expect(formatRelativeTime(undefined)).toBe("—");
  });

  it("returns 'agora' for very recent timestamps", () => {
    const now = new Date().toISOString();
    expect(formatRelativeTime(now)).toBe("agora");
  });

  it("formats minutes ago", () => {
    const tenMinAgo = new Date(Date.now() - 10 * 60_000).toISOString();
    expect(formatRelativeTime(tenMinAgo)).toBe("10min atrás");
  });

  it("formats hours ago", () => {
    const threeHoursAgo = new Date(Date.now() - 3 * 3_600_000).toISOString();
    expect(formatRelativeTime(threeHoursAgo)).toBe("3h atrás");
  });
});

describe("formatDuration", () => {
  it("returns em-dash for null/undefined", () => {
    expect(formatDuration(null)).toBe("—");
    expect(formatDuration(undefined)).toBe("—");
  });

  it("formats sub-second durations as ms", () => {
    expect(formatDuration(0.25)).toBe("250ms");
  });

  it("formats sub-minute durations with one decimal", () => {
    expect(formatDuration(4.2)).toBe("4.2s");
  });

  it("formats multi-minute durations", () => {
    expect(formatDuration(125)).toBe("2min 5s");
  });
});

describe("formatUptime", () => {
  it("formats minutes only when under an hour", () => {
    expect(formatUptime(300)).toBe("5min");
  });

  it("formats hours and minutes", () => {
    expect(formatUptime(3 * 3600 + 15 * 60)).toBe("3h 15min");
  });

  it("formats days and hours", () => {
    expect(formatUptime(2 * 86400 + 4 * 3600)).toBe("2d 4h");
  });
});

describe("formatNumber", () => {
  it("returns em-dash for null/undefined", () => {
    expect(formatNumber(null)).toBe("—");
    expect(formatNumber(undefined)).toBe("—");
  });

  it("formats with pt-BR thousands separators", () => {
    expect(formatNumber(12345)).toBe("12.345");
  });
});

describe("formatPercent", () => {
  it("returns em-dash for null/undefined", () => {
    expect(formatPercent(null)).toBe("—");
  });

  it("formats with one decimal place", () => {
    expect(formatPercent(42.567)).toBe("42.6%");
  });
});

describe("formatDateTime", () => {
  it("returns em-dash for null/undefined", () => {
    expect(formatDateTime(null)).toBe("—");
  });

  it("returns a non-empty formatted string for a valid date", () => {
    expect(formatDateTime("2026-01-01T12:00:00Z").length).toBeGreaterThan(0);
  });
});
