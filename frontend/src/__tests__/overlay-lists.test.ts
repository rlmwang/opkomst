import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import { useTestMessages } from "@/__tests__/i18n-harness";

import AppPopover from "@/components/AppPopover.vue";
import AutoCompleteField from "@/components/AutoCompleteField.vue";
import MultiSelectField from "@/components/MultiSelectField.vue";
import SelectField from "@/components/SelectField.vue";

// The four that took the app off PrimeVue. What is worth a test here is
// the keyboard and the dismissal: they are invisible until somebody who
// needs them cannot use the app.

useTestMessages("nl", { common: { clear: "Wissen", noResults: "Geen resultaten", remove: "Verwijderen" } });

const OPTIONS = [
  { id: "a", name: "Amsterdam" },
  { id: "b", name: "Rotterdam" },
  { id: "c", name: "Utrecht" },
];

function mountSelect(props: Record<string, unknown> = {}) {
  return mount(SelectField, {
    props: { options: OPTIONS, optionLabel: "name", optionValue: "id", ...props },
    attachTo: document.body,
  });
}

describe("SelectField", () => {
  it("opens on click and shows every option", async () => {
    const w = mountSelect();
    expect(document.querySelector(".ovl-panel")).toBeNull();
    await w.get(".ovl-field").trigger("click");
    expect(document.querySelectorAll(".ovl-option")).toHaveLength(3);
    w.unmount();
  });

  it("walks the list with the arrows and takes a row with Enter", async () => {
    const w = mountSelect();
    const field = w.get(".ovl-field");
    await field.trigger("keydown", { key: "ArrowDown" });
    expect(document.querySelector(".ovl-panel")).not.toBeNull();
    await field.trigger("keydown", { key: "ArrowDown" });
    await field.trigger("keydown", { key: "Enter" });
    expect(w.emitted("update:modelValue")!.at(-1)).toEqual(["b"]);
    expect(document.querySelector(".ovl-panel")).toBeNull();
    w.unmount();
  });

  it("jumps to the ends with Home and End", async () => {
    const w = mountSelect();
    const field = w.get(".ovl-field");
    await field.trigger("keydown", { key: "ArrowDown" });
    await field.trigger("keydown", { key: "End" });
    await field.trigger("keydown", { key: "Enter" });
    expect(w.emitted("update:modelValue")!.at(-1)).toEqual(["c"]);
    w.unmount();
  });

  it("jumps to the row the typed letters start", async () => {
    const w = mountSelect();
    const field = w.get(".ovl-field");
    await field.trigger("keydown", { key: "ArrowDown" });
    await field.trigger("keydown", { key: "u" });
    await field.trigger("keydown", { key: "Enter" });
    expect(w.emitted("update:modelValue")!.at(-1)).toEqual(["c"]);
    w.unmount();
  });

  it("narrows the list to the filter, and Enter takes the first match", async () => {
    const w = mountSelect({ filter: true });
    await w.get(".ovl-field").trigger("click");
    const box = document.querySelector(".ovl-filter") as HTMLInputElement;
    box.value = "rot";
    box.dispatchEvent(new Event("input"));
    await w.vm.$nextTick();
    expect(document.querySelectorAll(".ovl-option")).toHaveLength(1);
    await w.get(".ovl-field").trigger("keydown", { key: "Enter" });
    expect(w.emitted("update:modelValue")!.at(-1)).toEqual(["b"]);
    w.unmount();
  });

  it("says so when the filter leaves nothing", async () => {
    const w = mountSelect({ filter: true });
    await w.get(".ovl-field").trigger("click");
    const box = document.querySelector(".ovl-filter") as HTMLInputElement;
    box.value = "zzz";
    box.dispatchEvent(new Event("input"));
    await w.vm.$nextTick();
    expect(document.querySelector(".ovl-empty")!.textContent).toContain("Geen resultaten");
    w.unmount();
  });

  it("empties the model from the clear cross", async () => {
    const w = mountSelect({ modelValue: "a", showClear: true });
    (document.querySelector(".ovl-clear") as HTMLElement).click();
    await w.vm.$nextTick();
    expect(w.emitted("update:modelValue")!.at(-1)).toEqual([null]);
    w.unmount();
  });

  it("closes on a press outside it, and on Escape", async () => {
    const w = mountSelect();
    await w.get(".ovl-field").trigger("click");
    document.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true }));
    await w.vm.$nextTick();
    expect(document.querySelector(".ovl-panel")).toBeNull();

    await w.get(".ovl-field").trigger("click");
    expect(document.querySelector(".ovl-panel")).not.toBeNull();
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    await w.vm.$nextTick();
    expect(document.querySelector(".ovl-panel")).toBeNull();
    w.unmount();
  });

  it("carries the combobox wiring a screen reader reads", async () => {
    const w = mountSelect();
    const field = w.get(".ovl-field");
    expect(field.attributes("role")).toBe("combobox");
    expect(field.attributes("aria-expanded")).toBe("false");
    await field.trigger("keydown", { key: "ArrowDown" });
    expect(field.attributes("aria-expanded")).toBe("true");
    const active = field.attributes("aria-activedescendant")!;
    expect(document.getElementById(active)!.getAttribute("role")).toBe("option");
    w.unmount();
  });
});

describe("MultiSelectField", () => {
  const mountMulti = (props: Record<string, unknown> = {}) =>
    mount(MultiSelectField, {
      props: { options: OPTIONS, optionLabel: "name", optionValue: "id", ...props },
      attachTo: document.body,
    });

  it("adds a row and takes it away again without closing", async () => {
    const w = mountMulti({ modelValue: [] });
    await w.get(".ovl-field").trigger("click");
    (document.querySelectorAll(".ovl-option")[1] as HTMLElement).click();
    await w.vm.$nextTick();
    expect(w.emitted("update:modelValue")!.at(-1)).toEqual([["b"]]);
    expect(document.querySelector(".ovl-panel")).not.toBeNull();

    await w.setProps({ modelValue: ["b"] });
    (document.querySelectorAll(".ovl-option")[1] as HTMLElement).click();
    await w.vm.$nextTick();
    expect(w.emitted("update:modelValue")!.at(-1)).toEqual([[]]);
    w.unmount();
  });

  it("shows the chosen ones as chips, each with its own cross", async () => {
    const w = mountMulti({ modelValue: ["a", "c"], display: "chip" });
    expect(w.findAll(".ms-chip")).toHaveLength(2);
    await w.findAll(".ms-chip-remove")[0].trigger("click");
    expect(w.emitted("update:modelValue")!.at(-1)).toEqual([["c"]]);
    w.unmount();
  });
});

describe("AutoCompleteField", () => {
  const mountAuto = (props: Record<string, unknown> = {}) =>
    mount(AutoCompleteField, {
      props: { suggestions: [], optionLabel: "name", delay: 0, ...props },
      attachTo: document.body,
    });

  it("asks the caller for a list once the typing stops", async () => {
    const w = mountAuto({ modelValue: "" });
    await w.get("input").setValue("ams");
    expect(w.emitted("update:modelValue")!.at(-1)).toEqual(["ams"]);
    await new Promise((r) => setTimeout(r, 5));
    expect(w.emitted("complete")!.at(-1)![0]).toMatchObject({ query: "ams" });
    w.unmount();
  });

  it("stays quiet below the minimum length", async () => {
    const w = mountAuto({ modelValue: "", minLength: 3 });
    await w.get("input").setValue("am");
    await new Promise((r) => setTimeout(r, 5));
    expect(w.emitted("complete")).toBeUndefined();
    w.unmount();
  });

  it("opens on the answer, and Enter takes the walked-to suggestion", async () => {
    const w = mountAuto({ modelValue: "" });
    await w.get("input").setValue("a");
    await w.setProps({ suggestions: OPTIONS });
    await w.vm.$nextTick();
    expect(document.querySelectorAll(".ovl-option")).toHaveLength(3);
    await w.get("input").trigger("keydown", { key: "ArrowDown" });
    await w.get("input").trigger("keydown", { key: "Enter" });
    expect(w.emitted("option-select")!.at(-1)![0]).toMatchObject({ value: OPTIONS[0] });
    expect(document.querySelector(".ovl-panel")).toBeNull();
    w.unmount();
  });

  it("leaves Enter alone when nothing is walked to, so the caller can act on it", async () => {
    const w = mountAuto({ modelValue: "" });
    await w.get("input").setValue("a");
    await w.setProps({ suggestions: OPTIONS });
    await w.get("input").trigger("keydown", { key: "Enter" });
    expect(w.emitted("option-select")).toBeUndefined();
    expect(document.querySelector(".ovl-panel")).toBeNull();
    w.unmount();
  });
});

describe("AppPopover", () => {
  it("opens against the button that toggled it and closes again", async () => {
    const button = document.createElement("button");
    document.body.appendChild(button);
    const w = mount(AppPopover, { attachTo: document.body });

    w.vm.toggle({ currentTarget: button } as unknown as Event);
    await w.vm.$nextTick();
    expect(document.querySelector(".pop")).not.toBeNull();
    expect(w.emitted("show")).toHaveLength(1);

    w.vm.toggle({ currentTarget: button } as unknown as Event);
    await w.vm.$nextTick();
    expect(document.querySelector(".pop")).toBeNull();
    expect(w.emitted("hide")).toHaveLength(1);
    w.unmount();
  });

  it("closes on a press outside it", async () => {
    const button = document.createElement("button");
    document.body.appendChild(button);
    const w = mount(AppPopover, { attachTo: document.body });
    w.vm.show({ currentTarget: button } as unknown as Event);
    await w.vm.$nextTick();
    document.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true }));
    await w.vm.$nextTick();
    expect(document.querySelector(".pop")).toBeNull();
    w.unmount();
  });
});
