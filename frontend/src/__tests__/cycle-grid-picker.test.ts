/**
 * CycleGridPicker: the day-toggle grid maps each cell to a flat cycle
 * offset (week*7 + day) and emits a sorted cycle_slots array. k rows
 * render for a k-week cycle.
 */
import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import { useTestMessages } from "@/__tests__/i18n-harness";

import CycleGridPicker from "@/components/CycleGridPicker.vue";

useTestMessages("en", {
        chores: {
          edit: {
            weekLabel: "Week {n}",
            weekday: { mon: "Mon", tue: "Tue", wed: "Wed", thu: "Thu", fri: "Fri", sat: "Sat", sun: "Sun" },
          },
        },
      });

function mountPicker(modelValue: number[], periodWeeks: number) {
  return mount(CycleGridPicker, {
    props: { modelValue, periodWeeks },
  });
}

function lastEmit(wrapper: ReturnType<typeof mountPicker>): number[] {
  const events = wrapper.emitted("update:modelValue");
  return (events?.at(-1)?.[0] ?? []) as number[];
}

describe("CycleGridPicker", () => {
  it("renders one row of 7 toggles for k=1", () => {
    const w = mountPicker([], 1);
    expect(w.findAll(".day-toggle")).toHaveLength(7);
    expect(w.findAll(".week-label")).toHaveLength(0);
  });

  it("renders two unlabelled weekday rows (14 toggles) for k=2", () => {
    const w = mountPicker([], 2);
    expect(w.findAll(".day-toggle")).toHaveLength(14);
    expect(w.findAll(".cycle-week")).toHaveLength(2);
    expect(w.findAll(".week-label")).toHaveLength(0);
  });

  it("emits the flat offset when a day is toggled on (k=1, Wed = 2)", async () => {
    const w = mountPicker([], 1);
    await w.findAll(".day-toggle")[2].trigger("click");
    expect(lastEmit(w)).toEqual([2]);
  });

  it("maps week*7 + day for k=2 (week 2 Wed = 9)", async () => {
    const w = mountPicker([], 2);
    await w.findAll(".day-toggle")[9].trigger("click");
    expect(lastEmit(w)).toEqual([9]);
  });

  it("toggles an active offset back off", async () => {
    const w = mountPicker([2], 1);
    await w.findAll(".day-toggle")[2].trigger("click");
    expect(lastEmit(w)).toEqual([]);
  });

  it("keeps the emitted array sorted", async () => {
    const w = mountPicker([4], 1);
    await w.findAll(".day-toggle")[2].trigger("click");
    expect(lastEmit(w)).toEqual([2, 4]);
  });

  it("marks the active cell with aria-pressed", () => {
    const w = mountPicker([0], 1);
    expect(w.findAll(".day-toggle")[0].attributes("aria-pressed")).toBe("true");
    expect(w.findAll(".day-toggle")[1].attributes("aria-pressed")).toBe("false");
  });
});
