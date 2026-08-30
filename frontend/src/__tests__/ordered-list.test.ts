/** The ordered-list editor behind the chore and question editors. */

import { describe, expect, it } from "vitest";

import { orderedList } from "@/composables/useOrderedList.svelte";

describe("orderedList", () => {
  it("adds and removes by index", () => {
    const l = orderedList<string>(["a", "b"]);
    l.add("c");
    expect(l.items).toEqual(["a", "b", "c"]);
    l.removeAt(1);
    expect(l.items).toEqual(["a", "c"]);
  });

  it("replaces in place", () => {
    const l = orderedList<string>(["a", "b"]);
    l.replaceAt(1, "B");
    expect(l.items).toEqual(["a", "B"]);
  });

  it("moves up and down, clamped at the ends", () => {
    const l = orderedList<string>(["a", "b", "c"]);
    l.move(0, 1);
    expect(l.items).toEqual(["b", "a", "c"]);
    l.move(2, -1);
    expect(l.items).toEqual(["b", "c", "a"]);
    l.move(0, -1); // nothing above the first
    expect(l.items).toEqual(["b", "c", "a"]);
    l.move(2, 1); // nothing below the last
    expect(l.items).toEqual(["b", "c", "a"]);
  });

  it("takes a whole new list", () => {
    const l = orderedList<number>([1, 2]);
    l.items = [9, 8, 7];
    expect(l.items).toEqual([9, 8, 7]);
  });
});
