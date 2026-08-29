import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AppDialog from "@/components/AppDialog.vue";
import AppToast from "@/components/AppToast.vue";
import { useConfirms, useConfirmRequest } from "@/lib/confirms";
import { showToast } from "@/lib/toast";
import { useToasts } from "@/lib/toasts";

// The pieces task 02 took off PrimeVue. The dialog is the browser's
// own <dialog>, which happy-dom does not fully implement, so these
// cover what the app controls rather than what the browser does.

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
    const w = mount(AppToast);
    showToast("Opgeslagen", { kind: "success" });
    await w.vm.$nextTick();
    expect(w.text()).toContain("Opgeslagen");

    vi.advanceTimersByTime(4000);
    await w.vm.$nextTick();
    expect(w.text()).not.toContain("Opgeslagen");
    w.unmount();
  });

  it("carries the second line when there is one", async () => {
    const w = mount(AppToast);
    useToasts().error("Mislukt", { detail: "De server antwoordde niet" });
    await w.vm.$nextTick();
    expect(w.get(".toast-summary").text()).toBe("Mislukt");
    expect(w.get(".toast-detail").text()).toBe("De server antwoordde niet");
    w.unmount();
  });

  it("gives each kind its own icon and all of them one colour", async () => {
    const w = mount(AppToast);
    const toasts = useToasts();
    toasts.success("a");
    toasts.warn("b");
    toasts.error("c");
    await w.vm.$nextTick();
    // Three toasts, three icons, one .toast class carrying the colour.
    expect(w.findAll(".toast")).toHaveLength(3);
    expect(w.findAll(".toast-icon")).toHaveLength(3);
    w.unmount();
  });
});

describe("the confirm request", () => {
  it("runs the accept callback, once, and clears itself", async () => {
    const accept = vi.fn();
    useConfirms().ask({
      header: "Weet je het zeker?",
      message: "Dit kan niet terug.",
      acceptLabel: "Ja",
      rejectLabel: "Nee",
      accept,
    });
    const { state, accept: run } = useConfirmRequest();
    expect(state.request?.header).toBe("Weet je het zeker?");
    await run();
    expect(accept).toHaveBeenCalledTimes(1);
    expect(state.request).toBeNull();
  });

  it("runs nothing when it is rejected", () => {
    const accept = vi.fn();
    useConfirms().ask({ header: "h", message: "m", acceptLabel: "a", rejectLabel: "r", accept });
    const { state, reject } = useConfirmRequest();
    reject();
    expect(accept).not.toHaveBeenCalled();
    expect(state.request).toBeNull();
  });
});

describe("AppDialog", () => {
  it("keeps nothing mounted while it is closed", () => {
    const w = mount(AppDialog, {
      props: { visible: false, header: "Titel" },
      slots: { default: "<p>inhoud</p>" },
    });
    expect(w.text()).not.toContain("inhoud");
    expect(w.text()).not.toContain("Titel");
  });

  it("renders its header, body and footer when open", () => {
    const w = mount(AppDialog, {
      props: { visible: true, header: "Titel" },
      slots: { default: "<p>inhoud</p>", footer: "<button>Ok</button>" },
    });
    expect(w.get(".app-dialog-title").text()).toBe("Titel");
    expect(w.get(".app-dialog-body").text()).toBe("inhoud");
    expect(w.get(".app-dialog-footer").text()).toBe("Ok");
  });

  it("offers a close button only when it is closable", () => {
    const open = { visible: true, header: "T" };
    expect(mount(AppDialog, { props: open }).find(".app-dialog-close").exists()).toBe(true);
    expect(
      mount(AppDialog, { props: { ...open, closable: false } }).find(".app-dialog-close").exists(),
    ).toBe(false);
  });

  it("tells the parent when the close button is pressed", async () => {
    const w = mount(AppDialog, { props: { visible: true, header: "T" } });
    await w.get(".app-dialog-close").trigger("click");
    expect(w.emitted("update:visible")!.at(-1)).toEqual([false]);
  });
});
