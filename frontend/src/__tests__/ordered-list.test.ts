/** Unit tests for the ordered-list editor composable. */

import { describe, expect, it } from "vitest";
import { useOrderedList } from "@/composables/useOrderedList";

describe("useOrderedList", () => {
  it("adds and removes by index", () => {
    const l = useOrderedList<string>(["a", "b"]);
    l.add("c");
    expect(l.items.value).toEqual(["a", "b", "c"]);
    l.removeAt(1);
    expect(l.items.value).toEqual(["a", "c"]);
  });

  it("replaces in place", () => {
    const l = useOrderedList<string>(["a", "b"]);
    l.replaceAt(1, "B");
    expect(l.items.value).toEqual(["a", "B"]);
  });

  it("moves up and down, clamped at the ends", () => {
    const l = useOrderedList<string>(["a", "b", "c"]);
    l.moveDown(0);
    expect(l.items.value).toEqual(["b", "a", "c"]);
    l.moveUp(2);
    expect(l.items.value).toEqual(["b", "c", "a"]);
    l.moveUp(0); // no-op at the top
    expect(l.items.value).toEqual(["b", "c", "a"]);
    l.moveDown(2); // no-op at the bottom
    expect(l.items.value).toEqual(["b", "c", "a"]);
  });

  it("reports movability at the boundaries", () => {
    const l = useOrderedList<string>(["a", "b", "c"]);
    expect(l.canMoveUp(0)).toBe(false);
    expect(l.canMoveDown(0)).toBe(true);
    expect(l.canMoveUp(2)).toBe(true);
    expect(l.canMoveDown(2)).toBe(false);
  });

  it("replaces the whole list via set", () => {
    const l = useOrderedList<number>([1, 2]);
    l.set([9, 8, 7]);
    expect(l.items.value).toEqual([9, 8, 7]);
  });
});
