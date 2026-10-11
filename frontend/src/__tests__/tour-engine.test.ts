/**
 * The engine (``tours/engine.svelte``): the five outcomes of following
 * the route, with a fake path and a fake count of requests in flight.
 */
import { flushSync } from "svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { bootEngine, fake } from "@/__tests__/tour-deps.svelte";
import { register, resetAnchors, unregister } from "@/tours/anchors.svelte";
import { start, stop, tour } from "@/stores/tour.svelte";

vi.mock("@/api/client", () => ({
  get: vi.fn(),
  post: vi.fn(),
  getToken: vi.fn(() => null),
  setToken: vi.fn(),
  clearToken: vi.fn(),
  ApiError: class ApiError extends Error {},
}));

let dispose: (() => void) | null = null;
let engine: ReturnType<typeof bootEngine>["engine"];

function boot(): void {
  const booted = bootEngine();
  engine = booted.engine;
  dispose = booted.dispose;
  settle();
}

/** Let the effect run, the page paint, and the effect run again. */
function settle(): void {
  flushSync();
  fake.paint();
  flushSync();
}

function el(): HTMLElement {
  const node = document.createElement("button");
  document.body.append(node);
  return node;
}

beforeEach(() => {
  sessionStorage.clear();
  resetAnchors();
  fake.path = "/";
  fake.fetching = 0;
});
afterEach(() => {
  dispose?.();
  dispose = null;
  stop();
  document.body.innerHTML = "";
});

describe("the engine", () => {
  it("shows a step whose page matches and whose control is registered", () => {
    const tile = el();
    register("home.events", tile);
    start("welkom", "/");
    boot();
    expect(engine.shown?.el).toBe(tile);
    expect(engine.shown?.step.anchor).toBe("home.events");
  });

  it("waits while a request is in flight for a control that is not there yet", async () => {
    const { next } = await import("@/stores/tour.svelte");
    register("home.events", el());
    start("welkom", "/");
    boot();
    next();
    fake.path = "/event";
    fake.fetching = 1;
    settle();
    expect(engine.shown).toBeNull();
    expect(tour.active).toBe(true);
    expect(tour.index).toBe(1);
  });

  it("waits for the page to paint before dropping a step, then drops it", async () => {
    const { next } = await import("@/stores/tour.svelte");
    register("home.events", el());
    start("welkom", "/");
    boot();
    next();
    fake.path = "/event";
    flushSync();
    // Landed, nothing fetching, no control yet: still arriving.
    expect(tour.active).toBe(true);
    expect(tour.index).toBe(1);
    register("list.new", el());
    settle();
    expect(engine.shown?.step.anchor).toBe("list.new");
  });

  it("drops the current step when nothing is loading and its control is absent", async () => {
    const { next } = await import("@/stores/tour.svelte");
    const first = el();
    const second = el();
    register("list.new", first);
    register("row.details", second);
    start("lijst", "/event", "event");
    fake.path = "/event";
    boot();
    unregister("row.details", second);
    next();
    settle();
    // row.details is gone with nothing in flight, so it was dropped and
    // the tour ended, there being nothing after it.
    expect(tour.active).toBe(false);
  });

  it("waits after a click step while the navigation lands, and shows the next control when it does", async () => {
    const { next } = await import("@/stores/tour.svelte");
    register("home.events", el());
    start("welkom", "/");
    boot();
    // The click happened; the path is still the landing page.
    next();
    settle();
    expect(engine.shown).toBeNull();
    expect(tour.active).toBe(true);
    // The list page lands, its query is in flight.
    fake.path = "/event";
    fake.fetching = 1;
    settle();
    expect(engine.shown).toBeNull();
    expect(tour.active).toBe(true);
    // The query lands and the button registers.
    fake.fetching = 0;
    const newButton = el();
    register("list.new", newButton);
    settle();
    expect(engine.shown?.el).toBe(newButton);
  });

  it("stops when the person goes somewhere else", async () => {
    const { next } = await import("@/stores/tour.svelte");
    register("home.events", el());
    start("welkom", "/");
    boot();
    next();
    fake.path = "/datepoll";
    settle();
    expect(tour.active).toBe(false);
  });

  it("ends an until step the moment its control registers, on the next page", async () => {
    const { next } = await import("@/stores/tour.svelte");
    register("home.events", el());
    start("welkom", "/");
    boot();
    next();
    fake.path = "/event";
    register("list.new", el());
    settle();
    next();
    fake.path = "/event/new";
    const card = el();
    register("form.card", card);
    settle();
    expect(engine.shown?.el).toBe(card);
    expect(engine.shown?.step.advance.kind).toBe("until");
    // The save lands on the details page: first the navigation, then
    // the share link.
    fake.path = "/event/abc/details";
    settle();
    expect(tour.active).toBe(true);
    expect(engine.shown).toBeNull();
    const link = el();
    register("share.link", link);
    settle();
    expect(tour.index).toBe(3);
    expect(engine.shown?.el).toBe(link);
  });

  it("stops an until step when the person leaves for a page that is neither", async () => {
    const { next } = await import("@/stores/tour.svelte");
    register("home.events", el());
    start("welkom", "/");
    boot();
    next();
    fake.path = "/event";
    register("list.new", el());
    settle();
    next();
    fake.path = "/event/new";
    register("form.card", el());
    settle();
    // Cancel: back to the list, which is neither the form nor details.
    fake.path = "/event";
    settle();
    expect(tour.active).toBe(false);
  });

  it("does not end an until step on a control that was already there when the step began", async () => {
    const { next } = await import("@/stores/tour.svelte");
    register("home.events", el());
    start("welkom", "/");
    boot();
    next();
    fake.path = "/event";
    register("list.new", el());
    // The list page has a share link on every row.
    const rowLink = el();
    register("share.link", rowLink);
    settle();
    next();
    settle();
    expect(tour.index).toBe(2);
    expect(tour.active).toBe(true);
    // The list page leaves with its rows; the form page arrives.
    fake.path = "/event/new";
    unregister("share.link", rowLink);
    rowLink.remove();
    register("form.card", el());
    settle();
    expect(engine.shown?.step.anchor).toBe("form.card");
    // The details page's share link is a different element.
    fake.path = "/event/abc/details";
    register("share.link", el());
    settle();
    expect(tour.index).toBe(3);
  });

  it("does not end an until step while a page with several such controls is leaving", async () => {
    const { next } = await import("@/stores/tour.svelte");
    register("home.events", el());
    start("welkom", "/");
    boot();
    next();
    fake.path = "/event";
    register("list.new", el());
    const first = el();
    const second = el();
    register("share.link", first);
    register("share.link", second);
    settle();
    next();
    settle();
    // The first row leaves before the second: for a moment the second
    // row's link is the first in the document.
    unregister("share.link", first);
    first.remove();
    settle();
    expect(tour.index).toBe(2);
    unregister("share.link", second);
    second.remove();
    fake.path = "/event/new";
    register("form.card", el());
    settle();
    expect(engine.shown?.step.anchor).toBe("form.card");
  });
});
