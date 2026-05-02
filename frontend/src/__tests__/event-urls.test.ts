import { describe, expect, it, vi } from "vitest";
import { eventQrUrl, publicEventUrl } from "@/lib/event-urls";

describe("eventQrUrl", () => {
  it("points at the QR SVG endpoint for the slug", () => {
    expect(eventQrUrl("abcd1234")).toBe("/api/v1/events/by-slug/abcd1234/qr.svg");
  });
});

describe("publicEventUrl", () => {
  it("composes the public sign-up URL from the current origin", () => {
    vi.stubGlobal("window", { location: { origin: "https://opkomst.nu" } });
    expect(publicEventUrl("xyz")).toBe("https://opkomst.nu/e/xyz");
    vi.unstubAllGlobals();
  });
});
