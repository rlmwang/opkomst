/**
 * Router-guard behaviour. Specifically the ``requiresWhatsApp``
 * meta added for ``/admin/whatsapp``: a direct URL poke must
 * redirect to ``/events`` when the auth store reports the
 * WhatsApp tool isn't configured, even though the user is an
 * admin and would otherwise pass ``requiresAdmin``.
 *
 * The api client is mocked so ``auth.fetchMe`` doesn't try to
 * hit the network during the guard's eager-load branch.
 */

import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
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

const adminUser = {
  id: "u1",
  email: "a@b",
  name: "A",
  role: "admin" as const,
  is_approved: true,
  chapters: [],
  created_at: "2026-01-01T00:00:00Z",
};

beforeEach(() => {
  setActivePinia(createPinia());
  vi.clearAllMocks();
  vi.mocked(apiClient.getToken).mockReturnValue("tok");
});

afterEach(() => {
  // Reset the URL between tests so the router doesn't replay
  // previous navigations.
  window.history.replaceState({}, "", "/");
});

async function loadRouter() {
  // Bypass the module cache so the router picks up the per-test
  // pinia instance and mock state.
  vi.resetModules();
  const mod = await import("@/router/index");
  return mod.default;
}

describe("router guards: requiresWhatsApp", () => {
  it("redirects to /events when whatsappAvailable is false", async () => {
    const { useAuthStore } = await import("@/stores/auth");
    const router = await loadRouter();
    const store = useAuthStore();
    store.user = { ...adminUser };
    store.loaded = true;
    store.whatsappAvailable = false;

    await router.push("/admin/whatsapp");
    expect(router.currentRoute.value.path).toBe("/events");
  });

  it("admits admins to /admin/whatsapp when whatsappAvailable is true", async () => {
    const { useAuthStore } = await import("@/stores/auth");
    const router = await loadRouter();
    const store = useAuthStore();
    store.user = { ...adminUser };
    store.loaded = true;
    store.whatsappAvailable = true;

    await router.push("/admin/whatsapp");
    expect(router.currentRoute.value.path).toBe("/admin/whatsapp");
  });

  it("non-admin trying to reach /admin/whatsapp lands on /events via requiresAdmin (not requiresWhatsApp)", async () => {
    const { useAuthStore } = await import("@/stores/auth");
    const router = await loadRouter();
    const store = useAuthStore();
    store.user = { ...adminUser, role: "organiser" };
    store.loaded = true;
    store.whatsappAvailable = true; // would pass on its own

    await router.push("/admin/whatsapp");
    expect(router.currentRoute.value.path).toBe("/events");
  });
});
