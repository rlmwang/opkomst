/**
 * The header's help group: Rondleiding is offered on a page that has a
 * tour, to an approved account that is not still picking chapters.
 */
import { cleanup, render } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as apiClient from "@/api/client";
import AppHeader from "@/components/AppHeader.svelte";

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

const here = { path: "/event", meta: {} as Record<string, unknown>, ready: true, params: {} };
vi.mock("@/router/navigation.svelte", () => ({
  get route() {
    return here;
  },
  go: vi.fn(),
}));

const BASE = {
  id: "u1",
  email: "a@b.c",
  name: "A",
  role: "organiser",
  is_approved: true,
  tenant_kind: "organisation",
  chapters: [{ id: "c1", name: "Amsterdam" }],
  participant_mail: true,
};

async function signedInAs(user: Record<string, unknown>) {
  const store = await import("@/stores/auth.svelte");
  vi.mocked(apiClient.getToken).mockReturnValue("tok");
  vi.mocked(apiClient.get).mockImplementation(async (path: string) => {
    if (path === "/api/v1/auth/me") return user;
    return { count: 0 };
  });
  await store.fetchMe();
}

async function openMenu(): Promise<string[]> {
  const { container } = render(AppHeader);
  const trigger = container.querySelector(".menu-trigger") as HTMLButtonElement;
  trigger.click();
  await new Promise((r) => setTimeout(r, 0));
  return Array.from(document.body.querySelectorAll(".nav-menu .menu-item")).map(
    (b) => b.textContent?.trim() ?? "",
  );
}

beforeEach(() => {
  here.path = "/event";
});
afterEach(async () => {
  cleanup();
  const { logout } = await import("@/stores/auth.svelte");
  logout();
});

describe("the header's help group", () => {
  it("offers Rondleiding on a list page to an approved member", async () => {
    await signedInAs(BASE);
    const items = await openMenu();
    expect(items).toContain("Rondleiding");
    expect(items.indexOf("Rondleiding")).toBe(items.indexOf("Uitloggen") - 1);
  });

  it("does not offer it to a member still picking chapters", async () => {
    await signedInAs({ ...BASE, chapters: [] });
    expect(await openMenu()).not.toContain("Rondleiding");
  });

  it("does not offer it on a page that has no tour", async () => {
    here.path = "/";
    await signedInAs(BASE);
    expect(await openMenu()).not.toContain("Rondleiding");
  });

  it("starts the page's tour when pressed", async () => {
    await signedInAs(BASE);
    const newButton = document.createElement("button");
    document.body.append(newButton);
    const { register } = await import("@/tours/anchors.svelte");
    register("list.new", newButton);
    await openMenu();
    const item = Array.from(document.body.querySelectorAll<HTMLButtonElement>(".nav-menu .menu-item")).find(
      (b) => b.textContent?.trim() === "Rondleiding",
    );
    item?.click();
    const { tour } = await import("@/stores/tour.svelte");
    expect(tour.id).toBe("lijst");
    expect(tour.product).toBe("event");
  });
});
