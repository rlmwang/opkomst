/**
 * ``FormSection`` and ``AdvancedFold``: the block every edit page is
 * made of, and the fold every edit page ends with.
 */
import { render } from "@testing-library/svelte";
import { afterEach, describe, expect, it } from "vitest";

import { bindable } from "@/__tests__/bind.svelte";
import AdvancedFold from "@/components/AdvancedFold.svelte";
import FormSection from "@/components/FormSection.svelte";
import SectionHarness from "@/__tests__/SectionHarness.svelte";
import { resetAnchors, resolve } from "@/tours/anchors.svelte";

afterEach(() => resetAnchors());

describe("FormSection", () => {
  it("renders a plain heading when nothing is bound", () => {
    const { container } = render(FormSection, { props: { heading: "Wanneer" } });
    expect(container.querySelector("h2.section-heading")?.textContent).toBe("Wanneer");
    expect(container.querySelector("label.toggle-row")).toBeNull();
    expect(container.querySelector("input[type=checkbox]")).toBeNull();
  });

  it("renders no heading at all for a section of bare fields", () => {
    const { container } = render(FormSection, { props: {} });
    expect(container.querySelector("h2")).toBeNull();
    expect(container.querySelector("section.form-section")).not.toBeNull();
  });

  it("renders the explainer only when given", () => {
    const with_ = render(FormSection, { props: { heading: "x", explainer: "Uitleg" } });
    expect(with_.container.querySelector(".section-explainer")?.textContent).toBe("Uitleg");
    with_.unmount();
    const without = render(FormSection, { props: { heading: "x" } });
    expect(without.container.querySelector(".section-explainer")).toBeNull();
  });

  it("turns the heading into a toggle row when enabled is bound, wired to the switch", async () => {
    const enabled = bindable("enabled", false, { heading: "Herinnering" });
    const { container } = render(SectionHarness, { props: enabled.props });
    const label = container.querySelector("label.toggle-row") as HTMLLabelElement;
    const box = container.querySelector("input[type=checkbox]") as HTMLInputElement;
    expect(label).not.toBeNull();
    expect(label.htmlFor).toBe(box.id);
    expect(label.querySelector("h2.section-heading")?.textContent).toBe("Herinnering");
    box.checked = true;
    box.dispatchEvent(new Event("change", { bubbles: true }));
    await Promise.resolve();
    expect(enabled.last).toBe(true);
  });

  it("registers its anchor", () => {
    const { container } = render(FormSection, { props: { heading: "x", anchor: "form.section.own" } });
    expect(resolve("form.section.own")).toBe(container.querySelector("section"));
  });
});

describe("AdvancedFold", () => {
  it("is closed on arrival and carries the fold anchor on its summary", () => {
    const { container } = render(SectionHarness, { props: { fold: true } });
    const details = container.querySelector("details.advanced") as HTMLDetailsElement;
    expect(details.open).toBe(false);
    expect(resolve("form.fold")).toBe(details.querySelector("summary"));
  });

  it("reports its open state back through the binding", async () => {
    const open = bindable("open", false, { fold: true });
    const { container } = render(SectionHarness, { props: open.props });
    const details = container.querySelector("details.advanced") as HTMLDetailsElement;
    details.open = true;
    details.dispatchEvent(new Event("toggle"));
    await Promise.resolve();
    expect(open.last).toBe(true);
  });

  it("renders the fold standalone too", () => {
    const { container } = render(AdvancedFold, { props: { children: (() => {}) as never } });
    expect(container.querySelector("details.advanced")).not.toBeNull();
  });
});
