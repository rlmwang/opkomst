/**
 * Tests for the WhatsApp blast tool's frontend composable.
 *
 * The composable owns the page's connection state, polling
 * timers, and send/disconnect calls. It's the only piece of
 * frontend logic that touches both timers and the network, so a
 * regression here (e.g. heartbeat timer surviving disconnect) is
 * exactly the kind of bug a unit test should catch.
 *
 * The api client is mocked so no real fetch happens. Vue's
 * onBeforeUnmount needs an active component instance, so each
 * test runs the composable inside a tiny harness.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { type App, createApp, defineComponent, h } from "vue";
import * as apiClient from "@/api/client";

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

let app: App | null = null;

function withSetup<T>(fn: () => T): T {
  let result!: T;
  const Harness = defineComponent({
    setup() {
      result = fn();
      return () => h("div");
    },
  });
  app = createApp(Harness);
  app.mount(document.createElement("div"));
  return result;
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  app?.unmount();
  app = null;
});

describe("useWhatsApp", () => {
  it("starts disconnected and exposes refs", async () => {
    const { useWhatsApp } = await import("@/composables/useWhatsApp");
    const wa = withSetup(() => useWhatsApp());
    expect(wa.state.value).toBe("unknown");
    expect(wa.qr.value).toBeNull();
    expect(wa.pairingCode.value).toBeNull();
  });

  it("send() POSTs to /whatsapp/send and reports ok on success", async () => {
    const { useWhatsApp } = await import("@/composables/useWhatsApp");
    mockPost.mockResolvedValueOnce({});
    const wa = withSetup(() => useWhatsApp());
    const res = await wa.send("31612345678", "hi");
    expect(res).toEqual({ ok: true });
    expect(mockPost).toHaveBeenCalledWith("/api/v1/whatsapp/send", {
      number: "31612345678",
      text: "hi",
    });
  });

  it("send() reports {ok:false, error} when the call rejects", async () => {
    const { useWhatsApp } = await import("@/composables/useWhatsApp");
    mockPost.mockRejectedValueOnce(new Error("offline"));
    const wa = withSetup(() => useWhatsApp());
    const res = await wa.send("31612345678", "hi");
    expect(res.ok).toBe(false);
    expect(res.error).toContain("offline");
  });

  it("disconnect() calls /whatsapp/logout and clears the QR", async () => {
    const { useWhatsApp } = await import("@/composables/useWhatsApp");
    mockPost.mockResolvedValue({});
    const wa = withSetup(() => useWhatsApp());
    wa.qr.value = "data:foo";
    wa.pairingCode.value = "ABCD";
    await wa.disconnect();
    expect(mockPost).toHaveBeenCalledWith("/api/v1/whatsapp/logout", {});
    expect(wa.qr.value).toBeNull();
    expect(wa.pairingCode.value).toBeNull();
    expect(wa.state.value).toBe("close");
  });

  it("disconnect() swallows errors so the page never blocks on it", async () => {
    const { useWhatsApp } = await import("@/composables/useWhatsApp");
    mockPost.mockRejectedValueOnce(new Error("network"));
    const wa = withSetup(() => useWhatsApp());
    await expect(wa.disconnect()).resolves.toBeUndefined();
  });

  it("startPolling fires an immediate heartbeat and primes the QR", async () => {
    const { useWhatsApp } = await import("@/composables/useWhatsApp");
    mockPost.mockResolvedValue({ state: "close" });
    mockGet.mockResolvedValue({ qr: "data:bar", pairingCode: null });
    const wa = withSetup(() => useWhatsApp());
    wa.startPolling();
    // The heartbeat is dispatched synchronously; flush the promise
    // microtasks so the assertion sees the resolved state.
    await vi.runOnlyPendingTimersAsync();
    await Promise.resolve();
    expect(mockPost).toHaveBeenCalledWith("/api/v1/whatsapp/heartbeat", {});
    expect(mockGet).toHaveBeenCalledWith("/api/v1/whatsapp/qr");
    wa.stopPolling();
  });

  it("stopPolling clears the heartbeat interval", async () => {
    const { useWhatsApp } = await import("@/composables/useWhatsApp");
    mockPost.mockResolvedValue({ state: "close" });
    mockGet.mockResolvedValue({ qr: null, pairingCode: null });
    const wa = withSetup(() => useWhatsApp());
    wa.startPolling();
    mockPost.mockClear();
    wa.stopPolling();
    // 30 seconds of fake-clock advance: a still-running 15s timer
    // would have fired twice.
    await vi.advanceTimersByTimeAsync(30_000);
    expect(mockPost).not.toHaveBeenCalled();
  });
});
