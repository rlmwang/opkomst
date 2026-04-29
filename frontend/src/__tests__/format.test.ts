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

  it("never displays seconds — events are scheduled to the minute", () => {
    // The default ``toLocaleString`` returns ``27-04-2026 18:00:00``
    // for nl-NL — that trailing ``:00`` is noise. Pin it out.
    const nl = formatDateTime("2026-04-27T18:00:00", "nl");
    const en = formatDateTime("2026-04-27T18:00:00", "en");
    expect(nl).not.toMatch(/:\d{2}:\d{2}/);
    expect(en).not.toMatch(/:\d{2}:\d{2}/);
    // Sanity: minutes are still rendered.
    expect(nl).toMatch(/18:00/);
    expect(en).toMatch(/18:00/);
  });

  it("formats nl as 27-04-2026, 18:00 (snapshot)", () => {
    expect(formatDateTime("2026-04-27T18:00:00", "nl")).toBe("27-04-2026, 18:00");
  });

  it("formats en as 27/04/2026, 18:00 (snapshot)", () => {
    expect(formatDateTime("2026-04-27T18:00:00", "en")).toBe(
      "27/04/2026, 18:00",
    );
  });
});

describe("formatTimeRange snapshots", () => {
  it("nl: 18:00 — 20:00", () => {
    expect(formatTimeRange("2026-04-27T18:00:00", "2026-04-27T20:00:00", "nl")).toBe(
      "18:00 — 20:00",
    );
  });

  it("en: 18:00 — 20:00", () => {
    expect(formatTimeRange("2026-04-27T18:00:00", "2026-04-27T20:00:00", "en")).toBe(
      "18:00 — 20:00",
    );
  });
});
