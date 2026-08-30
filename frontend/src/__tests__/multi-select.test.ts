/**
 * The chapter picker on the admin's edit dialog, and the two ways it
 * broke.
 *
 * **Picks are ids, not rows.** Held as rows and compared to the
 * options by object identity, every pick stopped matching the moment
 * the chapter list was fetched again: a window focus or a rename
 * elsewhere replaced those objects, the chips vanished, and the field
 * collapsed to the height of its own padding.
 *
 * **The panel belongs to the dialog.** ``AppDialog`` is the browser's
 * ``<dialog>`` opened with ``showModal``, which paints in the top
 * layer. A panel sent to the body renders underneath it, whatever its
 * z-index says, which is how the options came up below the popup.
 *
 * **And it is placed against the viewport.** Moving it into the dialog
 * broke the other half: the offsets were the document's, and inside a
 * modal they resolve against the dialog the browser positions, so the
 * panel landed below it and stretched its scroll area instead of
 * showing.
 */
import { cleanup, render } from "@testing-library/svelte";
import { afterEach, describe, expect, it } from "vitest";

import MultiSelectInDialog from "@/__tests__/MultiSelectInDialog.svelte";
import { placePanel } from "@/composables/overlay-panel";

// Each test renders its own dialog; without this the next one finds
// the last one's field still in the document.
afterEach(cleanup);

const CHAPTERS = [
  { id: "c1", name: "Amsterdam" },
  { id: "c2", name: "Rotterdam" },
];

/** The same chapters as the server would send them a second time: the
 *  same ids, new objects. */
const refetched = () => CHAPTERS.map((c) => ({ ...c }));

describe("the chapter picker in a dialog", () => {
  it("keeps its chips when the option rows are replaced by a refetch", async () => {
    const view = render(MultiSelectInDialog, { props: { value: ["c1"], options: CHAPTERS } });
    expect([...document.querySelectorAll(".ms-chip")].map((c) => c.textContent?.trim())).toEqual([
      "Amsterdam",
    ]);

    await view.rerender({ value: ["c1"], options: refetched() });
    expect([...document.querySelectorAll(".ms-chip")].map((c) => c.textContent?.trim())).toEqual([
      "Amsterdam",
    ]);
  });

  it("opens its panel inside the dialog, not under it", async () => {
    render(MultiSelectInDialog, { props: { value: [], options: CHAPTERS } });
    const field = document.querySelector(".ms-field") as HTMLElement;
    field.click();
    await Promise.resolve();

    const panel = document.querySelector(".ovl-panel");
    expect(panel).toBeTruthy();
    expect(panel?.closest("dialog")).toBeTruthy();
  });
});

describe("where the panel is placed", () => {
  it("is fixed to the viewport, so a positioned parent cannot move it", () => {
    // The anchor is what the field's box would be; the panel is what
    // hangs under it. The numbers are the viewport's, and the panel
    // carries no scroll offsets, because a modal is positioned by the
    // browser and an offset meant for the document lands a screen
    // below it.
    const anchor = document.createElement("div");
    anchor.getBoundingClientRect = () =>
      ({ left: 40, top: 100, bottom: 130, width: 200, height: 30 }) as DOMRect;
    const panel = document.createElement("div");
    Object.defineProperty(panel, "offsetHeight", { value: 150 });
    Object.defineProperty(panel, "offsetWidth", { value: 200 });
    window.scrollTo(0, 500);

    const { style, flipped } = placePanel(anchor, panel);

    expect(flipped).toBe(false);
    expect(style.position).toBe("fixed");
    expect(style.top).toBe("130px");
    expect(style.insetInlineStart).toBe("40px");
  });
});

describe("a caption wrapped around the field", () => {
  it("cancels the click, so the label cannot forward it to a chip's cross", () => {
    // A <label> forwards a click to the first labelable element in its
    // subtree, as the click's default action. The combobox is a div
    // and not one; a chip's remove button is. So clicking the field to
    // open it dropped a chapter, and with one picked that emptied the
    // field on the first click. The field cancels the default, which
    // is what stops the browser dispatching that second click.
    render(MultiSelectInDialog, { props: { value: ["c1", "c2"], options: CHAPTERS } });
    const field = document.querySelector(".ms-field") as HTMLElement;

    const click = new MouseEvent("click", { bubbles: true, cancelable: true });
    field.dispatchEvent(click);

    expect(click.defaultPrevented).toBe(true);
  });
});
