/**
 * The WhatsApp blast tool's connection.
 *
 * It owns the page's connection state, the polling timers, and the send
 * and disconnect calls. It is the only piece of frontend logic that
 * touches both timers and the network, so a regression here, a
 * heartbeat surviving a disconnect say, is exactly what a unit test is
 * for.
 *
 * The api client is mocked, so nothing is fetched. The composable tears
 * its timers down in an effect and an effect needs an owner, so each
 * test runs it inside an effect root.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as apiClient from "@/api/client";
import { inEffect } from "@/__tests__/effect-root.svelte";

vi.mock("@/api/client", () => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  patch: vi.fn(),
  del: vi.fn(),
  getToken: vi.fn(() => null),
  setToken: vi.fn(),
  clearToken: vi.fn(),
  ApiError: class ApiError extends Error {},
}));

const mockGet = vi.mocked(apiClient.get);
const mockPost = vi.mocked(apiClient.post);

/** The composable, inside an owner, with the body run against it. */
async function withWhatsApp<T>(body: (wa: WhatsApp) => T | Promise<T>): Promise<T> {
  const { whatsApp } = await import("@/composables/useWhatsApp.svelte");
  return inEffect(() => body(whatsApp()));
}
type WhatsApp = Awaited<ReturnType<typeof import("@/composables/useWhatsApp.svelte").whatsApp>>;

beforeEach(() => {
  vi.clearAllMocks();
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("whatsApp", () => {
  it("starts disconnected and knows nothing yet", async () => {
    await withWhatsApp((wa) => {
      expect(wa.state).toBe("unknown");
      expect(wa.qr).toBeNull();
      expect(wa.pairingCode).toBeNull();
    });
  });

  it("send posts to /whatsapp/send and reports ok on success", async () => {
    mockPost.mockResolvedValueOnce({});
    const res = await withWhatsApp((wa) => wa.send("31612345678", "hi"));
    expect(res).toEqual({ ok: true });
    expect(mockPost).toHaveBeenCalledWith("/api/v1/whatsapp/send", {
      number: "31612345678",
      text: "hi",
    });
  });

  it("send reports the error when the call rejects", async () => {
    mockPost.mockRejectedValueOnce(new Error("offline"));
    const res = await withWhatsApp((wa) => wa.send("31612345678", "hi"));
    expect(res.ok).toBe(false);
    expect(res.error).toContain("offline");
  });

  it("disconnect calls /whatsapp/logout and clears the QR", async () => {
    mockPost.mockResolvedValue({});
    mockGet.mockResolvedValue({ qr: "data:foo", pairingCode: "ABCD" });
    await withWhatsApp(async (wa) => {
      // The QR arrives the only way it ever does, from the endpoint.
      await wa.fetchQr();
      expect(wa.qr).toBe("data:foo");

      await wa.disconnect();
      expect(mockPost).toHaveBeenCalledWith("/api/v1/whatsapp/logout", {});
      expect(wa.qr).toBeNull();
      expect(wa.pairingCode).toBeNull();
      expect(wa.state).toBe("close");
    });
  });

  it("disconnect swallows errors, so the page never blocks on it", async () => {
    mockPost.mockRejectedValueOnce(new Error("network"));
    await withWhatsApp(async (wa) => {
      await expect(wa.disconnect()).resolves.toBeUndefined();
    });
  });

  it("startPolling fires an immediate heartbeat and primes the QR", async () => {
    mockPost.mockResolvedValue({ state: "close" });
    mockGet.mockResolvedValue({ qr: "data:bar", pairingCode: null });
    await withWhatsApp(async (wa) => {
      wa.startPolling();
      // The heartbeat goes out synchronously; the microtasks it queued
      // have to settle before the assertion sees the state.
      await vi.runOnlyPendingTimersAsync();
      await Promise.resolve();
      expect(mockPost).toHaveBeenCalledWith("/api/v1/whatsapp/heartbeat", {});
      expect(mockGet).toHaveBeenCalledWith("/api/v1/whatsapp/qr");
      wa.stopPolling();
    });
  });

  it("stopPolling clears the heartbeat", async () => {
    mockPost.mockResolvedValue({ state: "close" });
    mockGet.mockResolvedValue({ qr: null, pairingCode: null });
    await withWhatsApp(async (wa) => {
      wa.startPolling();
      mockPost.mockClear();
      wa.stopPolling();
      // Thirty seconds of fake clock: a heartbeat still running would
      // have gone out several times.
      await vi.advanceTimersByTimeAsync(30_000);
      expect(mockPost).not.toHaveBeenCalled();
    });
  });
});
