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
 */
import { render } from "@testing-library/svelte";
import { describe, expect, it } from "vitest";

import MultiSelectInDialog from "@/__tests__/MultiSelectInDialog.svelte";

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
