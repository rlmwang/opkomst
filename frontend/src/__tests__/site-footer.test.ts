/**
 * ``SiteFooter`` — where the colophon appears and where it does not.
 *
 * Two wrong answers this pins down. One is an organisation's page
 * carrying a list of our essays, which is the same mistake as putting
 * an ad there. The other is quieter: the footer is mounted once in
 * ``App.vue``, so without a route test it silently returns to every
 * page in the organiser app, which is where the noise complaint came
 * from in the first place.
 */
import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it } from "vitest";
import { createI18n } from "vue-i18n";
import { createMemoryHistory, createRouter } from "vue-router";

import SiteFooter from "@/components/SiteFooter.vue";

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

const blank = { template: "<div />" };

function makeI18n() {
  return createI18n({
    legacy: false,
    locale: "nl",
    messages: { nl: { footer: { label: "Meer lezen", privacy: "Privacy", source: "Broncode" } } },
  });
}

async function mountAt(path: string) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      ...["/", "/event", "/chore/abc/edit"].map((p) => ({ path: p, component: blank })),
      ...CREATE.map((p) => ({ path: p, component: blank, meta: { startable: true } })),
    ],
  });
  router.push(path);
  await router.isReady();
  return mount(SiteFooter, { global: { plugins: [makeI18n(), router] } });
}

beforeEach(() => {
  window.__OPKOMST_BRAND__ = { ...BRAND } as typeof window.__OPKOMST_BRAND__;
});

describe("SiteFooter", () => {
  it.each(INDEXED)("renders on %s, the pages a stranger lands on", async (path) => {
    const wrapper = await mountAt(path);
    const hrefs = wrapper.findAll("a").map((a) => a.attributes("href"));
    expect(hrefs).toContain("/datumplanner-zonder-account");
    expect(hrefs).toContain("/aanmeldformulier-zonder-google");
    expect(hrefs).toContain("/wat-gebeurt-er-met-je-mailadres");
    expect(hrefs).toContain("/vrijwilligers-inroosteren");
    expect(hrefs).toContain("/privacy");
    expect(hrefs.some((h) => h?.includes("github.com"))).toBe(true);
  });

  it("stays off the organiser's working pages", async () => {
    expect((await mountAt("/event")).find("footer").exists()).toBe(false);
    expect((await mountAt("/chore/abc/edit")).find("footer").exists()).toBe(false);
  });

  it("stays off a brand an organisation owns", async () => {
    window.__OPKOMST_BRAND__ = { ...BRAND, slug: "rsp", app_base: "/rsp/" } as typeof window.__OPKOMST_BRAND__;
    expect((await mountAt("/")).find("footer").exists()).toBe(false);
  });
});
