import { render } from "@testing-library/svelte";
import { describe, expect, it, vi } from "vitest";

import { useTestMessages } from "@/__tests__/i18n-harness";
import EmojiPicker from "@/components/EmojiPicker.svelte";

useTestMessages("en", { chore: { edit: { pickEmoji: "Pick an emoji" } } });

function picker(props: Record<string, unknown> = {}) {
  const onselect = vi.fn();
  const { container, unmount } = render(EmojiPicker, { props: { onselect, ...props } });
  const find = (selector: string) => container.querySelector(selector) as HTMLElement | null;
  return {
    onselect,
    unmount,
    find,
    all: (selector: string) => [...container.querySelectorAll(selector)] as HTMLElement[],
    async openClose() {
      find(".emoji-trigger")!.click();
      await Promise.resolve();
    },
  };
}

describe("EmojiPicker", () => {
  it("renders a trigger button with no panel by default", () => {
    const p = picker();
    expect(p.find(".emoji-trigger")).not.toBeNull();
    expect(p.find(".emoji-panel")).toBeNull();
  });

  it("opens the panel on click and closes on a second click", async () => {
    const p = picker();
    await p.openClose();
    expect(p.find(".emoji-panel")).not.toBeNull();
    await p.openClose();
    expect(p.find(".emoji-panel")).toBeNull();
  });

  it("hands back the picked emoji and closes the panel", async () => {
    const p = picker();
    await p.openClose();
    const cells = p.all(".emoji-cell");
    expect(cells.length).toBeGreaterThan(20);
    cells[0].click();
    await Promise.resolve();
    expect(p.onselect).toHaveBeenCalledTimes(1);
    expect(p.onselect.mock.calls[0][0]).toBeTypeOf("string");
    expect(p.find(".emoji-panel")).toBeNull();
  });

  it("shows the current emoji in the trigger when one is set", () => {
    const p = picker({ value: "🧹" });
    expect(p.find(".emoji-current")?.textContent).toBe("🧹");
  });

  it("closes the panel when the click lands outside the component", async () => {
    const p = picker();
    await p.openClose();
    expect(p.find(".emoji-panel")).not.toBeNull();
    document.body.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await Promise.resolve();
    expect(p.find(".emoji-panel")).toBeNull();
    p.unmount();
  });

  it("closes the panel on Escape", async () => {
    const p = picker();
    await p.openClose();
    expect(p.find(".emoji-panel")).not.toBeNull();
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    await Promise.resolve();
    expect(p.find(".emoji-panel")).toBeNull();
    p.unmount();
  });
});
