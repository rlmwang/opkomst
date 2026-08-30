import { cleanup, render } from "@testing-library/svelte";
import { afterEach, describe, expect, it, vi } from "vitest";

import PopoverHarness from "@/__tests__/PopoverHarness.svelte";
import { bindable } from "@/__tests__/bind.svelte";
import { useTestMessages } from "@/__tests__/i18n-harness";
import AutoCompleteField from "@/components/AutoCompleteField.svelte";
import MultiSelectField from "@/components/MultiSelectField.svelte";
import SelectField from "@/components/SelectField.svelte";

// The four that took the app off PrimeVue. What is worth a test here is
// the keyboard and the dismissal: they are invisible until somebody who
// needs them cannot use the app.

useTestMessages("nl", {
  common: { clear: "Wissen", noResults: "Geen resultaten", remove: "Verwijderen" },
});

const OPTIONS = [
  { id: "a", name: "Amsterdam" },
  { id: "b", name: "Rotterdam" },
  { id: "c", name: "Utrecht" },
];

// Every panel is moved to the body, so one left behind by a previous
// test would answer the next test's query.
afterEach(cleanup);

const settle = () => new Promise((r) => setTimeout(r, 0));
/** The panel is moved to the body, so it is queried from there. */
const panel = () => document.querySelector(".ovl-panel");
const options = () => [...document.querySelectorAll(".ovl-option")] as HTMLElement[];

function select(value: unknown = undefined, rest: Record<string, unknown> = {}) {
  const model = bindable("value", value, {
    options: OPTIONS,
    optionLabel: "name",
    optionValue: "id",
    ...rest,
  });
  const { container, unmount } = render(SelectField, { props: model.props });
  const field = container.querySelector(".ovl-field") as HTMLElement;
  return {
    model,
    field,
    unmount,
    async click() {
      field.click();
      await settle();
    },
    async key(key: string) {
      field.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));
      await settle();
    },
  };
}

describe("SelectField", () => {
  it("opens on click and shows every option", async () => {
    const s = select();
    expect(panel()).toBeNull();
    await s.click();
    expect(options()).toHaveLength(3);
    s.unmount();
  });

  it("walks the list with the arrows and takes a row with Enter", async () => {
    const s = select();
    await s.key("ArrowDown");
    expect(panel()).not.toBeNull();
    await s.key("ArrowDown");
    await s.key("Enter");
    expect(s.model.current).toBe("b");
    expect(panel()).toBeNull();
    s.unmount();
  });

  it("jumps to the ends with Home and End", async () => {
    const s = select();
    await s.key("ArrowDown");
    await s.key("End");
    await s.key("Enter");
    expect(s.model.current).toBe("c");
    s.unmount();
  });

  it("jumps to the row the typed letters start", async () => {
    const s = select();
    await s.key("ArrowDown");
    await s.key("u");
    await s.key("Enter");
    expect(s.model.current).toBe("c");
    s.unmount();
  });

  it("narrows the list to the filter, and Enter takes the first match", async () => {
    const s = select(undefined, { filter: true });
    await s.click();
    const box = document.querySelector(".ovl-filter") as HTMLInputElement;
    box.value = "rot";
    box.dispatchEvent(new Event("input", { bubbles: true }));
    await settle();
    expect(options()).toHaveLength(1);
    await s.key("Enter");
    expect(s.model.current).toBe("b");
    s.unmount();
  });

  it("says so when the filter leaves nothing", async () => {
    const s = select(undefined, { filter: true });
    await s.click();
    const box = document.querySelector(".ovl-filter") as HTMLInputElement;
    box.value = "zzz";
    box.dispatchEvent(new Event("input", { bubbles: true }));
    await settle();
    expect(document.querySelector(".ovl-empty")?.textContent).toContain("Geen resultaten");
    s.unmount();
  });

  it("empties the value from the clear cross", async () => {
    const s = select("a", { showClear: true });
    (s.field.querySelector(".ovl-clear") as HTMLElement).click();
    await settle();
    expect(s.model.current).toBeNull();
    s.unmount();
  });

  it("closes on a press outside it, and on Escape", async () => {
    const s = select();
    await s.click();
    document.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true }));
    await settle();
    expect(panel()).toBeNull();

    await s.click();
    expect(panel()).not.toBeNull();
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    await settle();
    expect(panel()).toBeNull();
    s.unmount();
  });

  it("carries the combobox wiring a screen reader reads", async () => {
    const s = select();
    expect(s.field.getAttribute("role")).toBe("combobox");
    expect(s.field.getAttribute("aria-expanded")).toBe("false");
    await s.key("ArrowDown");
    expect(s.field.getAttribute("aria-expanded")).toBe("true");
    const active = s.field.getAttribute("aria-activedescendant")!;
    expect(document.getElementById(active)?.getAttribute("role")).toBe("option");
    s.unmount();
  });
});

describe("MultiSelectField", () => {
  function multi(value: string[], rest: Record<string, unknown> = {}) {
    const model = bindable("value", value, {
      options: OPTIONS,
      optionLabel: "name",
      optionValue: "id",
      ...rest,
    });
    const { container, unmount } = render(MultiSelectField, { props: model.props });
    return { model, container, unmount };
  }

  it("adds a row and takes it away again without closing", async () => {
    const m = multi([]);
    (m.container.querySelector(".ovl-field") as HTMLElement).click();
    await settle();
    options()[1].click();
    await settle();
    expect(m.model.current).toEqual(["b"]);
    expect(panel()).not.toBeNull();

    options()[1].click();
    await settle();
    expect(m.model.current).toEqual([]);
    m.unmount();
  });

  it("shows the chosen ones as chips, each with its own cross", async () => {
    const m = multi(["a", "c"], { display: "chip" });
    expect(m.container.querySelectorAll(".ms-chip")).toHaveLength(2);
    (m.container.querySelectorAll(".ms-chip-remove")[0] as HTMLElement).click();
    await settle();
    expect(m.model.current).toEqual(["c"]);
    m.unmount();
  });
});

describe("AutoCompleteField", () => {
  function auto(value: unknown, rest: Record<string, unknown> = {}) {
    const oncomplete = vi.fn();
    const onoptionSelect = vi.fn();
    const model = bindable("value", value, {
      suggestions: [],
      optionLabel: "name",
      delay: 0,
      oncomplete,
      onoptionSelect,
      ...rest,
    });
    const { container, unmount, rerender } = render(AutoCompleteField, { props: model.props });
    const input = container.querySelector("input") as HTMLInputElement;
    return {
      model,
      oncomplete,
      onoptionSelect,
      unmount,
      rerender,
      input,
      async type(text: string) {
        input.value = text;
        input.dispatchEvent(new Event("input", { bubbles: true }));
        await settle();
      },
      async key(key: string) {
        input.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));
        await settle();
      },
    };
  }

  it("asks the caller for a list once the typing stops", async () => {
    const a = auto("");
    await a.type("ams");
    expect(a.model.current).toBe("ams");
    await new Promise((r) => setTimeout(r, 5));
    expect(a.oncomplete.mock.calls.at(-1)?.[0]).toMatchObject({ query: "ams" });
    a.unmount();
  });

  it("stays quiet below the minimum length", async () => {
    const a = auto("", { minLength: 3 });
    await a.type("am");
    await new Promise((r) => setTimeout(r, 5));
    expect(a.oncomplete).not.toHaveBeenCalled();
    a.unmount();
  });

  it("opens on the answer, and Enter takes the walked-to suggestion", async () => {
    const a = auto("");
    await a.type("a");
    await a.rerender({ suggestions: OPTIONS });
    await settle();
    expect(options()).toHaveLength(3);
    await a.key("ArrowDown");
    await a.key("Enter");
    expect(a.onoptionSelect.mock.calls.at(-1)?.[0]).toMatchObject({ value: OPTIONS[0] });
    expect(panel()).toBeNull();
    a.unmount();
  });

  it("leaves Enter alone when nothing is walked to, so the caller can act on it", async () => {
    const a = auto("");
    await a.type("a");
    await a.rerender({ suggestions: OPTIONS });
    await a.key("Enter");
    expect(a.onoptionSelect).not.toHaveBeenCalled();
    expect(panel()).toBeNull();
    a.unmount();
  });
});

describe("AppPopover", () => {
  function popover() {
    const onshow = vi.fn();
    const onhide = vi.fn();
    const { container, unmount } = render(PopoverHarness, { props: { onshow, onhide } });
    const trigger = container.querySelector(".pop-trigger") as HTMLElement;
    return {
      onshow,
      onhide,
      unmount,
      async click() {
        trigger.click();
        await settle();
      },
    };
  }

  it("opens against the button that toggled it and closes again", async () => {
    const p = popover();
    await p.click();
    expect(document.querySelector(".pop")).not.toBeNull();
    expect(p.onshow).toHaveBeenCalledTimes(1);

    await p.click();
    expect(document.querySelector(".pop")).toBeNull();
    expect(p.onhide).toHaveBeenCalledTimes(1);
    p.unmount();
  });

  it("closes on a press outside it", async () => {
    const p = popover();
    await p.click();
    expect(document.querySelector(".pop")).not.toBeNull();
    document.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true }));
    await settle();
    expect(document.querySelector(".pop")).toBeNull();
    p.unmount();
  });
});
