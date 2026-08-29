import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import AppButton from "@/components/AppButton.vue";
import AppTextarea from "@/components/AppTextarea.vue";
import AppToggle from "@/components/AppToggle.vue";

// The ones of the four with behaviour to get wrong. AppInput is a
// styled input and needs no test.

describe("AppButton", () => {
  it("does not fire while disabled or loading", async () => {
    for (const props of [{ disabled: true }, { loading: true }]) {
      const w = mount(AppButton, { props: { label: "Opslaan", ...props } });
      expect(w.get("button").attributes("disabled")).toBeDefined();
      await w.get("button").trigger("click");
      expect(w.emitted("click")).toBeUndefined();
      w.unmount();
    }
  });

  it("shows a spinner instead of the icon while loading", () => {
    const w = mount(AppButton, { props: { label: "x", icon: "pi pi-send", loading: true } });
    expect(w.find(".app-btn-spin").exists()).toBe(true);
    expect(w.find("i.pi-send").exists()).toBe(false);
  });

  it("is a square when it carries an icon and no label", () => {
    expect(mount(AppButton, { props: { icon: "pi pi-trash" } }).classes()).toContain("app-btn-icon-only");
    expect(mount(AppButton, { props: { icon: "pi pi-trash", label: "Weg" } }).classes()).not.toContain(
      "app-btn-icon-only",
    );
  });

  it("carries the severity and variant the call site asked for", () => {
    const w = mount(AppButton, { props: { label: "x", severity: "secondary", text: true, size: "small" } });
    expect(w.classes()).toEqual(expect.arrayContaining(["app-btn-secondary", "app-btn-text", "app-btn-sm"]));
  });
});

describe("AppToggle", () => {
  it("reflects the model and emits the flip", async () => {
    const w = mount(AppToggle, { props: { modelValue: false } });
    expect(w.classes()).not.toContain("app-toggle-checked");
    await w.get("input").setValue(true);
    expect(w.emitted("update:modelValue")!.at(-1)).toEqual([true]);
  });

  it("shows as on when the model is true", () => {
    expect(mount(AppToggle, { props: { modelValue: true } }).classes()).toContain("app-toggle-checked");
  });

  it("emits a boolean, never undefined, so a caller can patch with it", async () => {
    const w = mount(AppToggle, { props: { modelValue: true } });
    await w.get("input").setValue(false);
    expect(w.emitted("update:modelValue")!.at(-1)![0]).toBe(false);
  });

  it("cannot be flipped while disabled", () => {
    const w = mount(AppToggle, { props: { modelValue: false, disabled: true } });
    expect(w.get("input").attributes("disabled")).toBeDefined();
    expect(w.classes()).toContain("app-toggle-disabled");
  });
});

describe("AppTextarea", () => {
  it("exposes the real field, so a caller can read the caret", () => {
    // AdminWhatsAppPage inserts emoji at the selection through $el.
    const w = mount(AppTextarea, { props: { modelValue: "hallo" } });
    expect((w.vm.$el as HTMLTextAreaElement).tagName).toBe("TEXTAREA");
    expect((w.vm.$el as HTMLTextAreaElement).selectionStart).toBeDefined();
  });

  it("only takes over the height when asked to", () => {
    expect(mount(AppTextarea, { props: { modelValue: "" } }).classes()).not.toContain("app-textarea-auto");
    expect(mount(AppTextarea, { props: { modelValue: "", autoResize: true } }).classes()).toContain(
      "app-textarea-auto",
    );
  });
});
