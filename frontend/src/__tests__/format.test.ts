import { describe, expect, it } from "vitest";
import { formatDate, formatDateTime, formatTimeRange, localeTag } from "@/lib/format";

describe("localeTag", () => {
  it("maps en to en-GB so dates render in DMY order", () => {
    expect(localeTag("en")).toBe("en-GB");
  });

  it("maps anything else to nl-NL", () => {
    expect(localeTag("nl")).toBe("nl-NL");
    expect(localeTag("de")).toBe("nl-NL");
  });
});

describe("formatDate", () => {
  it("renders a long Dutch date for nl", () => {
    const out = formatDate("2026-04-27T18:00:00", "nl");
    expect(out).toContain("april");
    expect(out).toContain("27");
    expect(out).toContain("2026");
  });

  it("renders an English long date for en", () => {
    const out = formatDate("2026-04-27T18:00:00", "en");
    expect(out).toContain("April");
    expect(out).toContain("2026");
  });
});

describe("formatTimeRange", () => {
  it("returns a hh:mm — hh:mm range", () => {
    const out = formatTimeRange("2026-04-27T18:00:00", "2026-04-27T20:00:00", "nl");
    expect(out).toMatch(/\d{2}:\d{2}\s+[—-]\s+\d{2}:\d{2}/);
  });
});

describe("formatDateTime", () => {
  it("returns a non-empty string", () => {
    expect(formatDateTime("2026-04-27T18:00:00", "nl")).not.toBe("");
  });
});
