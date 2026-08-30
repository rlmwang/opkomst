import { render } from "@testing-library/svelte";
import { describe, expect, it, vi } from "vitest";

import AppButton from "@/components/AppButton.svelte";
import AppTextarea from "@/components/AppTextarea.svelte";
import AppToggle from "@/components/AppToggle.svelte";

// The ones of the four with behaviour to get wrong. AppInput is a
// styled input and needs no test.

/** The component's own outermost element, not the container the test
 *  renderer wraps it in. */
const classesOf = (container: HTMLElement) => [
  ...(container.firstElementChild as HTMLElement).classList,
];

describe("AppButton", () => {
  it("does not fire while disabled or loading", async () => {
    for (const props of [{ disabled: true }, { loading: true }]) {
      const onclick = vi.fn();
      const { container, unmount } = render(AppButton, {
        props: { label: "Opslaan", onclick, ...props },
      });
      const button = container.querySelector("button") as HTMLButtonElement;
      expect(button.disabled).toBe(true);
      button.click();
      expect(onclick).not.toHaveBeenCalled();
      unmount();
    }
  });

  it("shows a spinner instead of the icon while loading", () => {
    const { container } = render(AppButton, {
      props: { label: "x", icon: "send", loading: true },
    });
    expect(container.querySelector(".app-btn-spin")).not.toBeNull();
    expect(container.querySelector(".app-icon")).toBeNull();
  });

  it("is a square when it carries an icon and no label", () => {
    const bare = render(AppButton, { props: { icon: "trash" } });
    expect(classesOf(bare.container)).toContain("app-btn-icon-only");
    bare.unmount();
    const labelled = render(AppButton, { props: { icon: "trash", label: "Weg" } });
    expect(classesOf(labelled.container)).not.toContain("app-btn-icon-only");
  });

  it("carries the severity and variant the call site asked for", () => {
    const { container } = render(AppButton, {
      props: { label: "x", severity: "secondary", text: true, size: "small" },
    });
    expect(classesOf(container)).toEqual(
      expect.arrayContaining(["app-btn-secondary", "app-btn-text", "app-btn-sm"]),
    );
  });
});

/** Flip the box the way a person does: the DOM flag, then the event. */
async function flip(container: HTMLElement, on: boolean) {
  const box = container.querySelector("input") as HTMLInputElement;
  box.checked = on;
  box.dispatchEvent(new Event("change", { bubbles: true }));
  await Promise.resolve();
}

describe("AppToggle", () => {
  it("follows the box, so a bound caller sees the flip", async () => {
    const { container } = render(AppToggle, { props: { checked: false } });
    expect(classesOf(container)).not.toContain("app-toggle-checked");
    await flip(container, true);
    // The class is driven by the same value ``bind:checked`` writes
    // back, so it moving is the binding working.
    expect(classesOf(container)).toContain("app-toggle-checked");
  });

  it("shows as on when it is checked", () => {
    const { container } = render(AppToggle, { props: { checked: true } });
    expect(classesOf(container)).toContain("app-toggle-checked");
  });

  it("goes off again, so a caller can patch with either value", async () => {
    const { container } = render(AppToggle, { props: { checked: true } });
    await flip(container, false);
    expect(classesOf(container)).not.toContain("app-toggle-checked");
  });

  it("cannot be flipped while disabled", () => {
    const { container } = render(AppToggle, { props: { checked: false, disabled: true } });
    expect((container.querySelector("input") as HTMLInputElement).disabled).toBe(true);
    expect(classesOf(container)).toContain("app-toggle-disabled");
  });
});

describe("AppTextarea", () => {
  it("only takes over the height when asked to", () => {
    const plain = render(AppTextarea, { props: { value: "" } });
    expect(classesOf(plain.container)).not.toContain("app-textarea-auto");
    plain.unmount();
    const growing = render(AppTextarea, { props: { value: "", autoResize: true } });
    expect(classesOf(growing.container)).toContain("app-textarea-auto");
  });
});
