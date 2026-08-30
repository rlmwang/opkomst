/**
 * The guard, and specifically ``requiresWhatsApp``: a typed URL for
 * ``/admin/whatsapp`` has to land back on ``/event`` when the account
 * is not allowed the tool, even for an admin who would otherwise pass
 * ``requiresAdmin``.
 *
 * The api client is mocked, so the guard's ``/auth/me`` never reaches
 * the network. The router and the session are module state, so each
 * test imports them fresh.
 */
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
  vi.resetModules();
  vi.clearAllMocks();
  vi.mocked(apiClient.getToken).mockReturnValue("tok");
});

afterEach(() => {
  // The URL is where the router starts, so it is put back between
  // tests or the next one replays the last one's navigation.
  window.history.replaceState({}, "", "/");
});

/** Start the router as this account, and go to ``path``. Answers with
 *  where it actually landed. */
async function goAs(user: Record<string, unknown>, path: string): Promise<string> {
  vi.mocked(apiClient.get).mockImplementation(async (asked: string) => {
    if (asked === "/api/v1/auth/me") return user;
    throw new Error(`unexpected GET ${asked}`);
  });
  const { routes } = await import("@/router/routes");
  const { go, route, startRouter } = await import("@/router/navigation.svelte");
  await startRouter(routes);
  await go(path);
  return route.path;
}

// Each test resets the module registry and imports the router again,
// which transforms every page it reaches. Under a parallel suite load
// that pushes past the 5s default; in isolation these run in well under
// a second, so the allowance is headroom rather than a real wait.
describe("the guard on /admin/whatsapp", { timeout: 30_000 }, () => {
  it("sends an admin to /event when the tool is not open to the account", async () => {
    const landed = await goAs({ ...adminUser, whatsapp_available: false }, "/admin/whatsapp");
    expect(landed).toBe("/event");
  });

  it("admits an admin when it is", async () => {
    const landed = await goAs({ ...adminUser, whatsapp_available: true }, "/admin/whatsapp");
    expect(landed).toBe("/admin/whatsapp");
  });

  it("sends an organiser to /event on requiresAdmin, before the tool is even asked about", async () => {
    const landed = await goAs(
      { ...adminUser, role: "organiser", whatsapp_available: true },
      "/admin/whatsapp",
    );
    expect(landed).toBe("/event");
  });
});
