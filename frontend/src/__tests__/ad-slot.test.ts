/**
 * The advertising slot's gates (``AdSlot.svelte`` / ``AdUnit.svelte``).
 *
 * Three questions decide what renders, and each has a wrong answer that
 * would be noticed by somebody else: an organisation whose members are
 * shown ads, an advertiser billed for a slot nobody can see, and a
 * deployment that loads Google's script when nobody asked it to.
 *
 * The brand is what the server injects on the page, so each test sets
 * ``window.__OPKOMST_BRAND__`` the way a shell would and mounts the
 * component fresh.
 */
import { render } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import AdSlot from "@/public_shared/AdSlot.svelte";
import type { BrandAds } from "@/lib/branding";

const BASE_BRAND = {
  slug: "opkomst",
  app_base: "/",
  app_name: "opkomst.nu",
  wordmark: "opkomst.nu",
  org_name: "opkomst.nu",
  org_url: "https://opkomst.nu",
  logo_url: "",
  favicon_url: "",
};

const UNCONFIGURED: BrandAds = {
  client_id: null,
  rail_slot: null,
  banner_slot: null,
  coffee_url: null,
  coffee_button_url: "/brand/opkomst/support-coffee.png",
  patreon_url: null,
  patreon_button_url: "/brand/opkomst/support-patreon.png",
};

function setBrand(ads: BrandAds | null) {
  window.__OPKOMST_BRAND__ = { ...BASE_BRAND, ads } as typeof window.__OPKOMST_BRAND__;
}

/** Every unit the observer was pointed at, so a test can decide when a
 *  slot comes near the viewport. happy-dom has no IntersectionObserver,
 *  and without one the component asks for its ad immediately, which is
 *  the fallback rather than the behaviour under test. */
let observed: Array<{ element: Element; fire: (visible: boolean) => void }> = [];

function installIntersectionObserver() {
  observed = [];
  class FakeObserver {
    constructor(private cb: (entries: Array<{ isIntersecting: boolean }>) => void) {}
    observe(element: Element) {
      observed.push({ element, fire: (visible) => this.cb([{ isIntersecting: visible }]) });
    }
    disconnect() {}
    unobserve() {}
  }
  (window as unknown as { IntersectionObserver: unknown }).IntersectionObserver = FakeObserver;
}

function removeIntersectionObserver() {
  delete (window as unknown as { IntersectionObserver?: unknown }).IntersectionObserver;
}

/** The ad queue the tag drains. Its length is how many ads the page has
 *  asked for. */
function adRequests(): number {
  return ((window as unknown as { adsbygoogle?: unknown[] }).adsbygoogle ?? []).length;
}

let idleQueue: Array<() => void> = [];

/** ``requestIdleCallback`` is not implemented in happy-dom either, and
 *  the script waits for it. */
function installIdleCallback() {
  idleQueue = [];
  (window as unknown as { requestIdleCallback: unknown }).requestIdleCallback = (cb: () => void) => {
    idleQueue.push(cb);
    return 1;
  };
}

function runIdleCallbacks() {
  const queue = idleQueue;
  idleQueue = [];
  queue.forEach((cb) => cb());
}

/** ``matchMedia`` is not implemented in happy-dom, and it is what picks
 *  the rails over the banner. */
function setViewport(railsFit: boolean) {
  window.matchMedia = ((query: string) => ({
    matches: railsFit,
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  })) as unknown as typeof window.matchMedia;
}

const original = window.__OPKOMST_BRAND__;

beforeEach(() => {
  setViewport(true);
  document.getElementById("adsense-tag")?.remove();
  installIntersectionObserver();
  installIdleCallback();
  (window as unknown as { adsbygoogle?: unknown[] }).adsbygoogle = [];
});
afterEach(() => {
  window.__OPKOMST_BRAND__ = original;
});

describe("whose page this is", () => {
  it("renders nothing at all on a brand an organisation owns", () => {
    setBrand(null);
    const root = render(AdSlot, { props: { locale: "nl" } }).container;
    expect(root.textContent).toBe("");
    expect(root.querySelector("ins.adsbygoogle")).toBeNull();
  });

  it("loads no ad script on an organisation's page even when one is configured", () => {
    // The server sends null for an organisation whatever the
    // environment says, so this is the belt to that braces.
    setBrand(null);
    render(AdSlot, { props: { locale: "nl" } });
    expect(document.getElementById("adsense-tag")).toBeNull();
  });

  it("renders nothing on a page that has to stand alone", () => {
    setBrand(UNCONFIGURED);
    const root = render(AdSlot, { props: { locale: "nl", hide: true } }).container;
    expect(root.textContent).toBe("");
    expect(root.querySelector("ins.adsbygoogle")).toBeNull();
  });
});

describe("with no network configured", () => {
  it("says so, and loads nothing from Google", () => {
    setBrand(UNCONFIGURED);
    const root = render(AdSlot, { props: { locale: "nl" } }).container;
    expect(root.textContent).toContain("Geen advertenties");
    expect(root.querySelector("ins.adsbygoogle")).toBeNull();
    expect(document.getElementById("adsense-tag")).toBeNull();
  });

  it("carries no advertisement label, because there is no advertisement", () => {
    setBrand(UNCONFIGURED);
    const root = render(AdSlot, { props: { locale: "nl" } }).container;
    expect(root.querySelector(".ad-label")).toBeNull();
  });

  it("offers the support buttons when their URLs are set", () => {
    // Counted against the phone banner, which is one slot; at desktop
    // width there are two rails and each carries the same pair.
    setViewport(false);
    setBrand({ ...UNCONFIGURED, coffee_url: "https://buymeacoffee.com/x", patreon_url: "https://patreon.com/x" });
    const root = render(AdSlot, { props: { locale: "nl" } }).container;
    const links = [...root.querySelectorAll("a.support-link")];
    expect(links).toHaveLength(2);
    expect(links[0].getAttribute("href")).toBe("https://buymeacoffee.com/x");
    // Their own artwork, served from this app rather than their CDNs.
    expect(links[0].querySelector("img")?.getAttribute("src")).toContain("/brand/opkomst/");
  });

  it("shows only the service that is configured", () => {
    setViewport(false);
    setBrand({ ...UNCONFIGURED, coffee_url: "https://buymeacoffee.com/x" });
    const root = render(AdSlot, { props: { locale: "nl" } }).container;
    expect(root.querySelectorAll("a.support-link")).toHaveLength(1);
  });
});

describe("with a network configured", () => {
  const CONFIGURED: BrandAds = {
    ...UNCONFIGURED,
    client_id: "ca-pub-0000000000000000",
    rail_slot: "1111111111",
    banner_slot: "2222222222",
  };

  it("renders the unit and labels it", () => {
    setBrand(CONFIGURED);
    const root = render(AdSlot, { props: { locale: "nl" } }).container;
    const units = [...root.querySelectorAll("ins.adsbygoogle")];
    expect(units).toHaveLength(2); // one rail either side
    expect(units[0].getAttribute("data-ad-client")).toBe("ca-pub-0000000000000000");
    expect(units[0].getAttribute("data-ad-slot")).toBe("1111111111");
    expect(root.querySelectorAll(".ad-label")).toHaveLength(2);
  });

  it("loads the tag once however many units are on the page", () => {
    setBrand(CONFIGURED);
    render(AdSlot, { props: { locale: "nl" } });
    render(AdSlot, { props: { locale: "nl" } });
    runIdleCallbacks();
    expect(document.querySelectorAll("script#adsense-tag")).toHaveLength(1);
  });

  it("waits for the browser to be idle before fetching Google's script", () => {
    // ``async`` already keeps it from blocking parsing. This is about
    // the seconds after that, while the app is hydrating and an async
    // script is still competing for bandwidth and the main thread.
    setBrand(CONFIGURED);
    render(AdSlot, { props: { locale: "nl" } });
    expect(document.getElementById("adsense-tag")).toBeNull();

    runIdleCallbacks();
    const tag = document.getElementById("adsense-tag") as HTMLScriptElement | null;
    expect(tag).not.toBeNull();
    expect(tag?.async).toBe(true);
    expect(tag?.crossOrigin).toBe("anonymous");
    expect(tag?.src).toContain("client=ca-pub-0000000000000000");
  });

  it("loads the script even on a page that never goes idle", async () => {
    // Without ``requestIdleCallback`` at all there is a plain timer, so
    // an ad slot never stays empty for ever.
    setBrand(CONFIGURED);
    delete (window as unknown as { requestIdleCallback?: unknown }).requestIdleCallback;
    render(AdSlot, { props: { locale: "nl" } });
    await new Promise((resolve) => setTimeout(resolve, 300));
    expect(document.getElementById("adsense-tag")).not.toBeNull();
  });

  it("asks for no ad until the slot comes near the viewport", () => {
    setViewport(false); // the phone banner, at the foot of the page
    setBrand(CONFIGURED);
    render(AdSlot, { props: { locale: "nl" } });

    expect(observed).toHaveLength(1);
    expect(adRequests()).toBe(0);

    observed[0].fire(true);
    expect(adRequests()).toBe(1);
  });

  it("asks for each ad exactly once", () => {
    // A second push against the same ``<ins>`` is a request that can
    // never render, which is the thing that gets lazy loading flagged.
    setViewport(false);
    setBrand(CONFIGURED);
    render(AdSlot, { props: { locale: "nl" } });

    observed[0].fire(true);
    observed[0].fire(true);
    expect(adRequests()).toBe(1);
  });

  it("never asks while the slot stays away from the viewport", () => {
    setViewport(false);
    setBrand(CONFIGURED);
    render(AdSlot, { props: { locale: "nl" } });

    observed[0].fire(false);
    expect(adRequests()).toBe(0);
  });

  it("asks straight away where there is no observer to wait for", () => {
    setViewport(false);
    setBrand(CONFIGURED);
    removeIntersectionObserver();
    render(AdSlot, { props: { locale: "nl" } });
    expect(adRequests()).toBe(1);
  });

  it("uses the banner unit below the rail breakpoint", () => {
    setViewport(false);
    setBrand(CONFIGURED);
    const root = render(AdSlot, { props: { locale: "nl" } }).container;
    const units = [...root.querySelectorAll("ins.adsbygoogle")];
    expect(units).toHaveLength(1);
    expect(units[0].getAttribute("data-ad-slot")).toBe("2222222222");
  });
});
