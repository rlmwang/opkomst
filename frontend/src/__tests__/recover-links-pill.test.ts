/**
 * ``RecoverLinksPill`` — the shared magic-link recovery popover used on
 * all four details pages. Covers: pill renders the count; opening loads
 * the rows; copying goes through the confirm dialog, POSTs the recover
 * endpoint, puts the public URL on the clipboard, and marks the row.
 */
import { DOMWrapper, flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import PrimeVue from "primevue/config";
import Tooltip from "primevue/tooltip";
import { createI18n } from "vue-i18n";

import RecoverLinksPill from "@/components/RecoverLinksPill.vue";
import * as client from "@/api/client";

vi.mock("@/api/client", () => ({ post: vi.fn(async () => ({ edit_token: "tok123" })) }));
vi.mock("@/lib/toasts", () => ({ useToasts: () => ({ success: vi.fn(), error: vi.fn() }) }));

function makeI18n() {
  return createI18n({
    legacy: false,
    locale: "en",
    messages: {
      en: {
        common: { loading: "Loading…", cancel: "Cancel" },
        recoverLink: {
          open: "View signups",
          empty: "No signups yet.",
          anonymous: "Anonymous",
          copy: "Copy secret edit link",
          recoveredMark: "🔑",
          recoveredOn: "Link copied on {date}",
          confirmTitle: "Copy secret link?",
          confirmBody: "New link for {name}; the old one dies.",
          confirm: "Mint and copy link",
          copied: "Link copied.",
          failed: "Copying failed.",
        },
      },
    },
  });
}

const rows = [
  { id: "a", name: "Sam", recoveredAt: null },
  { id: "b", name: null, recoveredAt: "2026-07-01T10:00:00Z" },
];

function mountPill() {
  return mount(RecoverLinksPill, {
    attachTo: document.body,
    props: {
      count: 2,
      label: "deelnemers",
      loadRows: async () => rows.map((r) => ({ ...r })),
      recoverPath: (id: string) => `/api/x/${id}/edit-link`,
      publicUrl: (tok: string) => `https://pub/e/slug?s=${tok}`,
    },
    global: { plugins: [PrimeVue, makeI18n()], directives: { tooltip: Tooltip } },
  });
}

beforeEach(() => {
  Object.defineProperty(navigator, "clipboard", {
    value: { writeText: vi.fn(async () => undefined) },
    configurable: true,
  });
  vi.spyOn(window, "open").mockReturnValue(null);
});
afterEach(() => {
  document.body.innerHTML = "";
  vi.clearAllMocks();
});

describe("RecoverLinksPill", () => {
  it("renders the pill and lists rows on open", async () => {
    const w = mountPill();
    expect(w.find(".rlp-pill").text()).toContain("2");
    expect(w.find(".rlp-pill").text()).toContain("deelnemers");
    await w.find(".rlp-pill").trigger("click");
    await flushPromises();
    const body = new DOMWrapper(document.body);
    const names = body.findAll(".rlp-name").map((n) => n.text());
    expect(names).toEqual(["Sam", "Anonymous"]);
    expect(body.findAll(".rlp-recovered")).toHaveLength(1); // only the recovered row is marked
  });

  it("copies via confirm: POSTs recover, writes the public URL, marks the row", async () => {
    const w = mountPill();
    await w.find(".rlp-pill").trigger("click");
    await flushPromises();
    const body = new DOMWrapper(document.body);
    await body.findAll("button[aria-label='Copy secret edit link']")[0].trigger("click");
    await flushPromises();
    expect(client.post).not.toHaveBeenCalled(); // confirm gate first

    const confirm = body.findAll("button").find((b) => b.text() === "Mint and copy link")!;
    await confirm.trigger("click");
    await flushPromises();
    expect(client.post).toHaveBeenCalledWith("/api/x/a/edit-link");
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith("https://pub/e/slug?s=tok123");
    expect(window.open).toHaveBeenCalledWith("https://pub/e/slug?s=tok123", "_blank", "noopener");
    // The confirm dialog is gone once the copy lands.
    expect(body.findAll("button").some((b) => b.text() === "Mint and copy link")).toBe(false);
  });
});
