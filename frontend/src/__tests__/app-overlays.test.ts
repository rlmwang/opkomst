import { render } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import DialogHarness from "@/__tests__/DialogHarness.svelte";
import { bindable } from "@/__tests__/bind.svelte";
import AppToast from "@/components/AppToast.svelte";
import { acceptConfirm, ask, currentConfirm, rejectConfirm } from "@/lib/confirms.svelte";
import { showToast } from "@/lib/toast";
import { useToasts } from "@/lib/toasts";

// The pieces task 02 took off PrimeVue. The dialog is the browser's own
// <dialog>, which happy-dom does not fully implement, so these cover
// what the app controls rather than what the browser does.

const settle = () => new Promise((r) => setTimeout(r, 0));

describe("the toast queue", () => {
  // The queue is module-level, so it has to be drained between tests or
  // one test's toast is still on screen during the next.
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.advanceTimersByTime(10_000);
    vi.useRealTimers();
  });

  it("shows a message and takes it away again", async () => {
    const { container, unmount } = render(AppToast);
    showToast("Opgeslagen", { kind: "success" });
    await vi.advanceTimersByTimeAsync(0);
    expect(container.textContent).toContain("Opgeslagen");

    // Past its lifetime and past the fly-out that takes it off.
    await vi.advanceTimersByTimeAsync(4000 + 500);
    expect(container.textContent).not.toContain("Opgeslagen");
    unmount();
  });

  it("carries the second line when there is one", async () => {
    const { container, unmount } = render(AppToast);
    useToasts().error("Mislukt", { detail: "De server antwoordde niet" });
    await vi.advanceTimersByTimeAsync(0);
    expect(container.querySelector(".toast-summary")?.textContent).toBe("Mislukt");
    expect(container.querySelector(".toast-detail")?.textContent).toBe("De server antwoordde niet");
    unmount();
  });

  it("gives each kind its own icon and all of them one colour", async () => {
    const { container, unmount } = render(AppToast);
    const toasts = useToasts();
    toasts.success("a");
    toasts.warn("b");
    toasts.error("c");
    await vi.advanceTimersByTimeAsync(0);
    // Three toasts, three icons, one .toast class carrying the colour.
    expect(container.querySelectorAll(".toast")).toHaveLength(3);
    expect(container.querySelectorAll(".toast-icon")).toHaveLength(3);
    unmount();
  });
});

describe("the confirm request", () => {
  it("runs the accept callback, once, and clears itself", async () => {
    const accept = vi.fn();
    ask({
      header: "Weet je het zeker?",
      message: "Dit kan niet terug.",
      acceptLabel: "Ja",
      rejectLabel: "Nee",
      accept,
    });
    expect(currentConfirm()?.header).toBe("Weet je het zeker?");
    await acceptConfirm();
    expect(accept).toHaveBeenCalledTimes(1);
    expect(currentConfirm()).toBeNull();
  });

  it("runs nothing when it is rejected", () => {
    const accept = vi.fn();
    ask({ header: "h", message: "m", acceptLabel: "a", rejectLabel: "r", accept });
    rejectConfirm();
    expect(accept).not.toHaveBeenCalled();
    expect(currentConfirm()).toBeNull();
  });
});

describe("AppDialog", () => {
  it("keeps nothing mounted while it is closed", () => {
    const { container } = render(DialogHarness, { props: { visible: false, header: "Titel" } });
    expect(container.textContent).not.toContain("inhoud");
    expect(container.textContent).not.toContain("Titel");
  });

  it("renders its header, body and footer when open", () => {
    const { container } = render(DialogHarness, { props: { visible: true, header: "Titel" } });
    expect(container.querySelector(".app-dialog-title")?.textContent).toBe("Titel");
    expect(container.querySelector(".app-dialog-body")?.textContent?.trim()).toBe("inhoud");
    expect(container.querySelector(".app-dialog-footer")?.textContent?.trim()).toBe("Ok");
  });

  it("offers a close button only when it is closable", () => {
    const open = render(DialogHarness, { props: { visible: true, header: "T" } });
    expect(open.container.querySelector(".app-dialog-close")).not.toBeNull();
    open.unmount();
    const fixed = render(DialogHarness, {
      props: { visible: true, header: "T", closable: false },
    });
    expect(fixed.container.querySelector(".app-dialog-close")).toBeNull();
  });

  it("tells the parent when the close button is pressed", async () => {
    const open = bindable("visible", true, { header: "T" });
    const { container } = render(DialogHarness, { props: open.props });
    (container.querySelector(".app-dialog-close") as HTMLElement).click();
    await settle();
    expect(open.current).toBe(false);
  });
});
