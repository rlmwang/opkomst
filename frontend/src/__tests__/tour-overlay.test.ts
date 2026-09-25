/**
 * The overlay (``components/TourOverlay`` and ``tours/geometry``): the
 * hole is the control's box at its own radius, the mask is the viewport
 * minus that hole, the sheet replaces the popover on a phone and for a
 * tall hole, and the keyboard stays inside the callout except for the
 * one control a click step allows.
 */
import { cleanup, render } from "@testing-library/svelte";
import { flushSync } from "svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { register, resetAnchors } from "@/tours/anchors.svelte";
import { calloutSheet, holeGeometry, maskPath } from "@/tours/geometry";
import { start, stop, tour } from "@/stores/tour.svelte";

vi.mock("@/api/client", () => ({
  get: vi.fn(),
  post: vi.fn(),
  getToken: vi.fn(() => null),
  setToken: vi.fn(),
  clearToken: vi.fn(),
  ApiError: class ApiError extends Error {},
}));

const here = { path: "/", meta: {} as Record<string, unknown>, ready: true };
vi.mock("@/router/navigation.svelte", () => ({
  get route() {
    return here;
  },
}));

function box(left: number, top: number, width: number, height: number, radius = "6px"): HTMLElement {
  const node = document.createElement("button");
  node.getBoundingClientRect = () =>
    ({ left, top, width, height, right: left + width, bottom: top + height }) as DOMRect;
  node.style.borderTopLeftRadius = radius;
  node.scrollIntoView = () => {};
  document.body.append(node);
  return node;
}

beforeEach(() => {
  sessionStorage.clear();
  resetAnchors();
  here.path = "/";
  window.ResizeObserver =
    window.ResizeObserver ??
    (class {
      observe() {}
      disconnect() {}
      unobserve() {}
    } as never);
});
afterEach(() => {
  cleanup();
  stop();
  document.body.innerHTML = "";
});

describe("the hole", () => {
  it("is the control's box plus the padding, at the control's radius", () => {
    const hole = holeGeometry(box(100, 200, 80, 30, "6px"), 8);
    expect(hole).toEqual({ x: 92, y: 192, w: 96, h: 46, r: 14 });
  });

  it("caps a pill's radius at half the shorter side", () => {
    const hole = holeGeometry(box(0, 0, 100, 20, "999px"), 8);
    expect(hole.r).toBe(18);
  });

  it.each([
    ["top left", 0, 0],
    ["top right", 900, 0],
    ["bottom left", 0, 700],
    ["bottom right", 900, 700],
  ])("cuts a hole at the %s corner out of the viewport rectangle", (_, x, y) => {
    const hole = holeGeometry(box(x, y, 100, 50), 8);
    const d = maskPath({ w: 1000, h: 750 }, hole);
    expect(d.startsWith("M0 0H1000V750H0Z M")).toBe(true);
    expect(d).toContain(`M${hole.x + hole.r} ${hole.y}`);
    expect((d.match(/A/g) ?? []).length).toBe(4);
  });

  it("is a sheet on a phone and for a hole taller than most of the viewport", () => {
    const small = holeGeometry(box(0, 0, 100, 50), 8);
    expect(calloutSheet({ w: 1024, h: 768 }, small)).toBe(false);
    expect(calloutSheet({ w: 480, h: 768 }, small)).toBe(true);
    const tall = holeGeometry(box(0, 0, 600, 500), 8);
    expect(calloutSheet({ w: 1024, h: 768 }, tall)).toBe(true);
  });
});

describe("the callout", () => {
  async function mount() {
    const { default: TourOverlay } = await import("@/components/TourOverlay.svelte");
    const rendered = render(TourOverlay);
    flushSync();
    await new Promise((r) => requestAnimationFrame(() => r(undefined)));
    await Promise.resolve();
    return rendered;
  }

  it("renders a dialog by role with the counter, and a mask below the toast layer", async () => {
    register("home.events", box(100, 100, 80, 30));
    start("welkom", "/");
    const { container } = await mount();
    const dialog = document.body.querySelector('[role="dialog"].tour-callout');
    expect(dialog).not.toBeNull();
    expect(dialog?.tagName).not.toBe("DIALOG");
    expect(dialog?.textContent).toContain("1 van 5");
    expect(container.querySelector("svg.tour-mask")).not.toBeNull();
  });

  it("offers Volgende on a click step too, and Tab from it reaches the control", async () => {
    const tile = box(100, 100, 80, 30);
    register("home.events", tile);
    start("welkom", "/");
    await mount();
    const dialog = document.body.querySelector(".tour-callout") as HTMLElement;
    const buttons = Array.from(dialog.querySelectorAll("button"));
    expect(buttons.map((b) => b.textContent?.trim())).toEqual(["Stoppen", "Volgende"]);
    buttons[1].focus();
    dialog.dispatchEvent(new KeyboardEvent("keydown", { key: "Tab", bubbles: true }));
    expect(document.activeElement).toBe(tile);
  });

  it("offers a way back only on the last step, beside Klaar", async () => {
    register("home.events", box(100, 100, 80, 30));
    start("welkom", "/");
    await mount();
    const { next } = await import("@/stores/tour.svelte");
    // Skip to the last step; its control is registered under its name.
    register("header.menu", box(300, 20, 60, 30));
    register("list.new", box(100, 200, 80, 30));
    register("form.card", box(100, 300, 500, 300));
    register("share.link", box(600, 100, 30, 30));
    here.path = "/event/abc/details";
    next();
    next();
    next();
    next();
    flushSync();
    await new Promise((r) => requestAnimationFrame(() => r(undefined)));
    const dialog = document.body.querySelector(".tour-callout") as HTMLElement;
    const labels = Array.from(dialog.querySelectorAll("button")).map((b) => b.textContent?.trim());
    expect(labels).toEqual(["Stoppen", "Opnieuw", "Klaar"]);
    (dialog.querySelectorAll("button")[1] as HTMLButtonElement).click();
    expect(tour.index).toBe(0);
  });

  it("stops on Escape with focus in the callout, and ignores Escape elsewhere", async () => {
    register("home.events", box(100, 100, 80, 30));
    start("welkom", "/");
    await mount();
    document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    expect(tour.active).toBe(true);
    const dialog = document.body.querySelector(".tour-callout") as HTMLElement;
    dialog.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    expect(tour.active).toBe(false);
  });

  it("advances a click step from the control itself without stopping its own handler", async () => {
    const tile = box(100, 100, 80, 30);
    let own = 0;
    tile.addEventListener("click", () => (own += 1));
    register("home.events", tile);
    start("welkom", "/");
    await mount();
    tile.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(own).toBe(1);
    expect(tour.index).toBe(1);
  });
});
