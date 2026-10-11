/**
 * The tour's state (``stores/tour.svelte``): it survives a navigation
 * through session storage, goes with the session on sign-out, and a
 * per-page tour resolves its list when it starts.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { register, resetAnchors } from "@/tours/anchors.svelte";

vi.mock("@/api/client", () => ({
  get: vi.fn(),
  post: vi.fn(),
  getToken: vi.fn(() => null),
  setToken: vi.fn(),
  clearToken: vi.fn(),
  ApiError: class ApiError extends Error {},
}));

const KEY = "rsp:tour";

beforeEach(() => {
  sessionStorage.clear();
  resetAnchors();
});
afterEach(async () => {
  const { stop } = await import("@/stores/tour.svelte");
  stop();
});

function el(): HTMLElement {
  const node = document.createElement("button");
  document.body.append(node);
  return node;
}

describe("the tour store", () => {
  it("writes every change to session storage under the app's prefix", async () => {
    const { start, next, tour } = await import("@/stores/tour.svelte");
    expect(start("welkom", "/")).toBe(true);
    const stored = JSON.parse(sessionStorage.getItem(KEY) ?? "null");
    expect(stored.tour).toBe("welkom");
    expect(stored.index).toBe(0);
    next();
    expect(JSON.parse(sessionStorage.getItem(KEY) ?? "null").index).toBe(1);
    expect(tour.index).toBe(1);
  });

  it("ends and clears the key on stop, and returns focus to the opener", async () => {
    const { start, stop, tour } = await import("@/stores/tour.svelte");
    const opener = el();
    start("welkom", "/", null, opener);
    stop();
    expect(tour.active).toBe(false);
    expect(sessionStorage.getItem(KEY)).toBeNull();
    expect(document.activeElement).toBe(opener);
  });

  it("goes with the session: logout stops it", async () => {
    const { start, tour } = await import("@/stores/tour.svelte");
    const { logout } = await import("@/stores/auth.svelte");
    start("welkom", "/");
    logout();
    expect(tour.active).toBe(false);
    expect(sessionStorage.getItem(KEY)).toBeNull();
  });

  it("resolves a per-page tour at start, dropping steps whose control is absent", async () => {
    const { start, tour } = await import("@/stores/tour.svelte");
    register("list.new", el());
    register("row.details", el());
    register("list.archived", el());
    expect(start("lijst", "/event", "event")).toBe(true);
    expect(tour.steps.map((s) => s.anchor)).toEqual(["list.new", "row.details", "list.archived"]);
    // The words are keyed by the declared position, whatever was dropped.
    expect(tour.steps.map((s) => s.n)).toEqual([1, 2, 5]);
    expect(tour.steps.every((s) => s.page === "/event")).toBe(true);
  });

  it("does not start a per-page tour with nothing to show", async () => {
    const { start, tour } = await import("@/stores/tour.svelte");
    expect(start("lijst", "/event")).toBe(false);
    expect(tour.active).toBe(false);
  });

  it("keeps a cross-page tour's declared list", async () => {
    const { start, tour } = await import("@/stores/tour.svelte");
    start("welkom", "/");
    expect(tour.steps).toHaveLength(5);
    expect(tour.steps[2].page).toBe("/event/new");
  });

  it("ends on next past the last step, and restart goes to the first", async () => {
    const { start, next, restart, tour } = await import("@/stores/tour.svelte");
    start("inloggen", "/");
    next();
    next();
    next();
    expect(tour.index).toBe(3);
    restart();
    expect(tour.index).toBe(0);
    next();
    next();
    next();
    next();
    expect(tour.active).toBe(false);
  });
});
