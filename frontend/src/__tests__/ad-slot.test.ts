/**
 * The advertising slot's gates (``AdSlot.vue`` / ``AdUnit.vue``).
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
import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import AdSlot from "@/public_shared/AdSlot.vue";
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
});
afterEach(() => {
  window.__OPKOMST_BRAND__ = original;
});

describe("whose page this is", () => {
  it("renders nothing at all on a brand an organisation owns", () => {
    setBrand(null);
    const w = mount(AdSlot, { props: { locale: "nl" } });
    expect(w.html()).toBe("<!--v-if-->");
  });

  it("loads no ad script on an organisation's page even when one is configured", () => {
    // The server sends null for an organisation whatever the
    // environment says, so this is the belt to that braces.
    setBrand(null);
    mount(AdSlot, { props: { locale: "nl" } });
    expect(document.getElementById("adsense-tag")).toBeNull();
  });

  it("renders nothing on a page that has to stand alone", () => {
    setBrand(UNCONFIGURED);
    const w = mount(AdSlot, { props: { locale: "nl", hide: true } });
    expect(w.html()).toBe("<!--v-if-->");
  });
});

describe("with no network configured", () => {
  it("says so, and loads nothing from Google", () => {
    setBrand(UNCONFIGURED);
    const w = mount(AdSlot, { props: { locale: "nl" } });
    expect(w.text()).toContain("Geen advertenties");
    expect(w.find("ins.adsbygoogle").exists()).toBe(false);
    expect(document.getElementById("adsense-tag")).toBeNull();
  });

  it("carries no advertisement label, because there is no advertisement", () => {
    setBrand(UNCONFIGURED);
    const w = mount(AdSlot, { props: { locale: "nl" } });
    expect(w.find(".ad-label").exists()).toBe(false);
  });

  it("offers the support buttons when their URLs are set", () => {
    // Counted against the phone banner, which is one slot; at desktop
    // width there are two rails and each carries the same pair.
    setViewport(false);
    setBrand({ ...UNCONFIGURED, coffee_url: "https://buymeacoffee.com/x", patreon_url: "https://patreon.com/x" });
    const w = mount(AdSlot, { props: { locale: "nl" } });
    const links = w.findAll("a.support-link");
    expect(links).toHaveLength(2);
    expect(links[0].attributes("href")).toBe("https://buymeacoffee.com/x");
    // Their own artwork, served from this app rather than their CDNs.
    expect(links[0].find("img").attributes("src")).toContain("/brand/opkomst/");
  });

  it("shows only the service that is configured", () => {
    setViewport(false);
    setBrand({ ...UNCONFIGURED, coffee_url: "https://buymeacoffee.com/x" });
    const w = mount(AdSlot, { props: { locale: "nl" } });
    expect(w.findAll("a.support-link")).toHaveLength(1);
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
    const w = mount(AdSlot, { props: { locale: "nl" } });
    const units = w.findAll("ins.adsbygoogle");
    expect(units).toHaveLength(2); // one rail either side
    expect(units[0].attributes("data-ad-client")).toBe("ca-pub-0000000000000000");
    expect(units[0].attributes("data-ad-slot")).toBe("1111111111");
    expect(w.findAll(".ad-label")).toHaveLength(2);
  });

  it("loads the tag once however many units are on the page", () => {
    setBrand(CONFIGURED);
    mount(AdSlot, { props: { locale: "nl" } });
    mount(AdSlot, { props: { locale: "nl" } });
    expect(document.querySelectorAll("script#adsense-tag")).toHaveLength(1);
  });

  it("uses the banner unit below the rail breakpoint", () => {
    setViewport(false);
    setBrand(CONFIGURED);
    const w = mount(AdSlot, { props: { locale: "nl" } });
    const units = w.findAll("ins.adsbygoogle");
    expect(units).toHaveLength(1);
    expect(units[0].attributes("data-ad-slot")).toBe("2222222222");
  });
});
