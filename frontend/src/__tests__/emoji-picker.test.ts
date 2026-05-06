import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import EmojiPicker from "@/components/EmojiPicker.vue";

describe("EmojiPicker", () => {
  it("renders a trigger button with no panel by default", () => {
    const w = mount(EmojiPicker);
    expect(w.find(".emoji-trigger").exists()).toBe(true);
    expect(w.find(".emoji-panel").exists()).toBe(false);
  });

  it("opens the panel on click and closes on a second click", async () => {
    const w = mount(EmojiPicker);
    await w.find(".emoji-trigger").trigger("click");
    expect(w.find(".emoji-panel").exists()).toBe(true);
    await w.find(".emoji-trigger").trigger("click");
    expect(w.find(".emoji-panel").exists()).toBe(false);
  });

  it("emits 'select' with the picked emoji and closes the panel", async () => {
    const w = mount(EmojiPicker);
    await w.find(".emoji-trigger").trigger("click");
    const cells = w.findAll(".emoji-cell");
    expect(cells.length).toBeGreaterThan(20);
    await cells[0].trigger("click");
    expect(w.emitted("select")).toHaveLength(1);
    expect(w.emitted("select")![0][0]).toBeTypeOf("string");
    expect(w.find(".emoji-panel").exists()).toBe(false);
  });

  it("closes the panel when the click lands outside the component", async () => {
    const w = mount(EmojiPicker, { attachTo: document.body });
    await w.find(".emoji-trigger").trigger("click");
    expect(w.find(".emoji-panel").exists()).toBe(true);
    // Click on a node that isn't inside the picker.
    document.body.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await w.vm.$nextTick();
    expect(w.find(".emoji-panel").exists()).toBe(false);
    w.unmount();
  });

  it("closes the panel on Escape", async () => {
    const w = mount(EmojiPicker, { attachTo: document.body });
    await w.find(".emoji-trigger").trigger("click");
    expect(w.find(".emoji-panel").exists()).toBe(true);
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    await w.vm.$nextTick();
    expect(w.find(".emoji-panel").exists()).toBe(false);
    w.unmount();
  });
});
