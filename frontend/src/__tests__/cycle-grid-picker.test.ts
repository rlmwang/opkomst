/**
 * CycleGridPicker: the day-toggle grid maps each cell to a flat cycle
 * offset (week*7 + day) and writes back a sorted array. k rows render
 * for a k-week cycle.
 */
import { render } from "@testing-library/svelte";
import type { ComponentProps } from "svelte";
import { describe, expect, it } from "vitest";

import { bindable } from "@/__tests__/bind.svelte";
import { useTestMessages } from "@/__tests__/i18n-harness";
import CycleGridPicker from "@/components/CycleGridPicker.svelte";

useTestMessages("en", {
  chore: {
    edit: {
      weekLabel: "Week {n}",
      weekday: { mon: "Mon", tue: "Tue", wed: "Wed", thu: "Thu", fri: "Fri", sat: "Sat", sun: "Sun" },
    },
  },
});

function picker(value: number[], periodWeeks: number) {
  const slots = bindable<number[], ComponentProps<typeof CycleGridPicker>>("value", value, {
    periodWeeks,
  });
  const { container } = render(CycleGridPicker, { props: slots.props });
  const all = (selector: string) => [...container.querySelectorAll(selector)];
  return {
    slots,
    all,
    days: () => all(".day-toggle") as HTMLElement[],
    async click(index: number) {
      (all(".day-toggle")[index] as HTMLElement).click();
      await Promise.resolve();
    },
  };
}

describe("CycleGridPicker", () => {
  it("renders one row of 7 toggles for k=1", () => {
    const p = picker([], 1);
    expect(p.days()).toHaveLength(7);
    expect(p.all(".week-label")).toHaveLength(0);
  });

  it("renders two unlabelled weekday rows (14 toggles) for k=2", () => {
    const p = picker([], 2);
    expect(p.days()).toHaveLength(14);
    expect(p.all(".cycle-week")).toHaveLength(2);
    expect(p.all(".week-label")).toHaveLength(0);
  });

  it("writes the flat offset when a day is toggled on (k=1, Wed = 2)", async () => {
    const p = picker([], 1);
    await p.click(2);
    expect(p.slots.current).toEqual([2]);
  });

  it("maps week*7 + day for k=2 (week 2 Wed = 9)", async () => {
    const p = picker([], 2);
    await p.click(9);
    expect(p.slots.current).toEqual([9]);
  });

  it("toggles an active offset back off", async () => {
    const p = picker([2], 1);
    await p.click(2);
    expect(p.slots.current).toEqual([]);
  });

  it("keeps the array sorted", async () => {
    const p = picker([4], 1);
    await p.click(2);
    expect(p.slots.current).toEqual([2, 4]);
  });

  it("marks the active cell with aria-pressed", () => {
    const p = picker([0], 1);
    expect(p.days()[0].getAttribute("aria-pressed")).toBe("true");
    expect(p.days()[1].getAttribute("aria-pressed")).toBe("false");
  });
});
