import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import { useTestMessages } from "@/__tests__/i18n-harness";
import EmojiPicker from "@/components/EmojiPicker.vue";

useTestMessages("en", { chores: { edit: { pickEmoji: "Pick an emoji" } } });

function mountPicker(options: Parameters<typeof mount>[1] = {}) {
  return mount(EmojiPicker, options);
}

describe("EmojiPicker", () => {
  it("renders a trigger button with no panel by default", () => {
    const w = mountPicker();
    expect(w.find(".emoji-trigger").exists()).toBe(true);
    expect(w.find(".emoji-panel").exists()).toBe(false);
  });

  it("opens the panel on click and closes on a second click", async () => {
    const w = mountPicker();
    await w.find(".emoji-trigger").trigger("click");
    expect(w.find(".emoji-panel").exists()).toBe(true);
    await w.find(".emoji-trigger").trigger("click");
    expect(w.find(".emoji-panel").exists()).toBe(false);
  });

  it("emits 'select' with the picked emoji and closes the panel", async () => {
    const w = mountPicker();
    await w.find(".emoji-trigger").trigger("click");
    const cells = w.findAll(".emoji-cell");
    expect(cells.length).toBeGreaterThan(20);
    await cells[0].trigger("click");
    expect(w.emitted("select")).toHaveLength(1);
    expect(w.emitted("select")![0][0]).toBeTypeOf("string");
    expect(w.find(".emoji-panel").exists()).toBe(false);
  });

  it("shows the current emoji in the trigger when modelValue is set", () => {
    const w = mountPicker({ props: { modelValue: "🧹" } });
    expect(w.find(".emoji-current").text()).toBe("🧹");
  });

  it("closes the panel when the click lands outside the component", async () => {
    const w = mountPicker({ attachTo: document.body });
    await w.find(".emoji-trigger").trigger("click");
    expect(w.find(".emoji-panel").exists()).toBe(true);
    // Click on a node that isn't inside the picker.
    document.body.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await w.vm.$nextTick();
    expect(w.find(".emoji-panel").exists()).toBe(false);
    w.unmount();
  });

  it("closes the panel on Escape", async () => {
    const w = mountPicker({ attachTo: document.body });
    await w.find(".emoji-trigger").trigger("click");
    expect(w.find(".emoji-panel").exists()).toBe(true);
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    await w.vm.$nextTick();
    expect(w.find(".emoji-panel").exists()).toBe(false);
    w.unmount();
  });
});
