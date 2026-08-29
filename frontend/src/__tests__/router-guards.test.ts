/**
 * Router-guard behaviour. Specifically the ``requiresWhatsApp``
 * meta added for ``/admin/whatsapp``: a direct URL poke must
 * redirect to ``/event`` when the auth store reports the
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
  tenant_kind: "organisation",
  participant_cap: null,
  participant_mail: true,
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

// Each test does ``vi.resetModules()`` + a dynamic ``import("@/router/index")``,
// which under parallel suite load can occasionally push past Vitest's 5s
// default. Tests pass in well under a second in isolation, so the timeout
// is just headroom — and 15s of it was not enough on a pre-push, where
// this runs beside the backend suite, the production build and Playwright
// all at once. It took 18.6s there and blocked the push.
describe("router guards: requiresWhatsApp", { timeout: 30_000 }, () => {
  it("redirects to /event when whatsappAvailable is false", async () => {
    const { useAuthStore } = await import("@/stores/auth");
    const router = await loadRouter();
    const store = useAuthStore();
    store.user = { ...adminUser, whatsapp_available: false };
    store.loaded = true;

    await router.push("/admin/whatsapp");
    expect(router.currentRoute.value.path).toBe("/event");
  });

  it("admits admins to /admin/whatsapp when whatsappAvailable is true", async () => {
    const { useAuthStore } = await import("@/stores/auth");
    const router = await loadRouter();
    const store = useAuthStore();
    store.user = { ...adminUser, whatsapp_available: true };
    store.loaded = true;

    await router.push("/admin/whatsapp");
    expect(router.currentRoute.value.path).toBe("/admin/whatsapp");
  });

  it("non-admin trying to reach /admin/whatsapp lands on /event via requiresAdmin (not requiresWhatsApp)", async () => {
    const { useAuthStore } = await import("@/stores/auth");
    const router = await loadRouter();
    const store = useAuthStore();
    store.user = { ...adminUser, role: "organiser", whatsapp_available: true };
    store.loaded = true; // whatsapp would pass on its own

    await router.push("/admin/whatsapp");
    expect(router.currentRoute.value.path).toBe("/event");
  });
});
