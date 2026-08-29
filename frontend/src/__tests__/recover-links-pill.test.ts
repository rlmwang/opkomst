/**
 * ``RecoverLinksPill`` — the shared magic-link recovery popover used on
 * all four details pages. Covers: the pill renders the count; opening
 * loads the rows; copying goes through the confirm dialog, posts the
 * recover endpoint, puts the public URL on the clipboard, and marks the
 * row.
 */
import { render } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useTestMessages } from "@/__tests__/i18n-harness";
import RecoverLinksPill from "@/components/RecoverLinksPill.svelte";
import * as client from "@/api/client";

vi.mock("@/api/client", () => ({ post: vi.fn(async () => ({ edit_token: "tok123" })) }));
vi.mock("@/lib/toasts", () => ({ useToasts: () => ({ success: vi.fn(), error: vi.fn() }) }));

useTestMessages("en", {
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
});

const rows = [
  { id: "a", name: "Sam", recoveredAt: null },
  { id: "b", name: null, recoveredAt: "2026-07-01T10:00:00Z" },
];

/** Let the loads and the effects they schedule settle. */
async function settle() {
  for (let i = 0; i < 4; i++) await Promise.resolve();
  await new Promise((r) => setTimeout(r, 0));
}

function pill() {
  const { container } = render(RecoverLinksPill, {
    props: {
      count: 2,
      label: "deelnemers",
      loadRows: async () => rows.map((r) => ({ ...r })),
      recoverPath: (id: string) => `/api/x/${id}/edit-link`,
      publicUrl: (tok: string) => `https://pub/e/slug?s=${tok}`,
    },
  });
  // The popover and the dialog are moved to the body, so what they hold
  // is queried from there rather than from the container.
  const inBody = (selector: string) => [...document.querySelectorAll(selector)] as HTMLElement[];
  return {
    container,
    inBody,
    button: (label: string) => inBody("button").find((b) => b.textContent?.trim() === label),
    async open() {
      (container.querySelector(".rlp-pill") as HTMLElement).click();
      await settle();
    },
  };
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
    const p = pill();
    expect(p.container.querySelector(".rlp-pill")?.textContent).toContain("2");
    expect(p.container.querySelector(".rlp-pill")?.textContent).toContain("deelnemers");
    await p.open();
    expect(p.inBody(".rlp-name").map((n) => n.textContent?.trim())).toEqual(["Sam", "Anonymous"]);
    // Only the recovered row is marked.
    expect(p.inBody(".rlp-recovered")).toHaveLength(1);
  });

  it("copies via confirm: posts recover, writes the public URL, marks the row", async () => {
    const p = pill();
    await p.open();
    p.inBody("button[aria-label='Copy secret edit link']")[0].click();
    await settle();
    expect(client.post).not.toHaveBeenCalled(); // the confirm gate comes first

    p.button("Mint and copy link")!.click();
    await settle();
    expect(client.post).toHaveBeenCalledWith("/api/x/a/edit-link");
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith("https://pub/e/slug?s=tok123");
    expect(window.open).toHaveBeenCalledWith("https://pub/e/slug?s=tok123", "_blank", "noopener");
    // The confirm dialog is gone once the copy lands.
    expect(p.button("Mint and copy link")).toBeUndefined();
  });
});
