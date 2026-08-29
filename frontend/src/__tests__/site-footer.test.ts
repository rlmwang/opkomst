/**
 * ``SiteFooter`` — where the colophon appears and where it does not.
 *
 * Two wrong answers this pins down. One is an organisation's page
 * carrying a list of our essays, which is the same mistake as putting
 * an ad there. The other is quieter: the footer is mounted once in
 * ``App.svelte``, so without a route test it silently returns to every
 * page in the organiser app, which is where the noise complaint came
 * from in the first place.
 */
import { render } from "@testing-library/svelte";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useTestMessages } from "@/__tests__/i18n-harness";
import SiteFooter from "@/components/SiteFooter.svelte";

// The footer asks the router two things: where we are, and whether this
// route is one of the create pages. Both come from one module, so the
// test sets them directly rather than driving a real navigation.
const here = { path: "/", meta: {} as Record<string, unknown> };
vi.mock("@/router/navigation.svelte", () => ({
  get route() {
    return here;
  },
}));

const BRAND = {
  slug: "opkomst",
  app_base: "/",
  app_name: "opkomst.nu",
  wordmark: "opkomst.nu",
  org_name: "opkomst.nu",
  org_url: "https://opkomst.nu",
  logo_url: "",
  favicon_url: "",
};

// The pages a stranger can land on: the root and every create page.
// The create pages carry ``startable`` in the real router, which is
// what the footer reads, so the routes here carry it too.
const CREATE = ["/event/new", "/form/new", "/datepoll/new", "/chore/new", "/quiz/new", "/compass/new"];
const INDEXED = ["/", ...CREATE];

useTestMessages("nl", { footer: { label: "Meer lezen", privacy: "Privacy", source: "Broncode" } });

function renderAt(path: string) {
  here.path = path;
  here.meta = CREATE.includes(path) ? { startable: true } : {};
  return render(SiteFooter).container;
}

const hrefsIn = (root: HTMLElement) =>
  [...root.querySelectorAll("a")].map((a) => a.getAttribute("href"));

beforeEach(() => {
  window.__OPKOMST_BRAND__ = { ...BRAND } as typeof window.__OPKOMST_BRAND__;
});

describe("SiteFooter", () => {
  it.each(INDEXED)("renders on %s, the pages a stranger lands on", (path) => {
    const hrefs = hrefsIn(renderAt(path));
    expect(hrefs).toContain("/datumplanner-zonder-account");
    expect(hrefs).toContain("/aanmeldformulier-zonder-google");
    expect(hrefs).toContain("/wat-gebeurt-er-met-je-mailadres");
    expect(hrefs).toContain("/vrijwilligers-inroosteren");
    expect(hrefs).toContain("/privacy");
    expect(hrefs.some((h) => h?.includes("github.com"))).toBe(true);
  });

  it("stays off the organiser's working pages", () => {
    expect(renderAt("/event").querySelector("footer")).toBeNull();
    expect(renderAt("/chore/abc/edit").querySelector("footer")).toBeNull();
  });

  it("drops the blogs on a brand an organisation owns", () => {
    window.__OPKOMST_BRAND__ = { ...BRAND, slug: "rsp", app_base: "/rsp/" } as typeof window.__OPKOMST_BRAND__;
    const hrefs = hrefsIn(renderAt("/"));
    // The policy, the source and the way to report something belong on
    // every page; our essays are not part of their identity.
    expect(hrefs).toContain("/privacy");
    expect(hrefs).toContain("/voorwaarden");
    expect(hrefs.some((h) => h?.includes("github.com"))).toBe(true);
    expect(hrefs).not.toContain("/datumplanner-zonder-account");
  });
});
