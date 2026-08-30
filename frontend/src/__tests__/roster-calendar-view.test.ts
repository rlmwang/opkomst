/**
 * ``RosterCalendarView`` popover behaviour: an actionable day opens the
 * popover on click; the default popover renders one button per action
 * (the public claim/cover shape); the ``popover`` snippet replaces that
 * content (the organiser hand-over pickers) and receives the day's
 * assignments plus a working ``close``.
 */
import { render } from "@testing-library/svelte";
import { describe, expect, it, vi } from "vitest";

import RosterCalendarHarness from "@/__tests__/RosterCalendarHarness.svelte";
import RosterCalendarView, { type RosterDay } from "@/components/RosterCalendarView.svelte";

const ISO = "2026-01-07";
const DAYS: Record<string, RosterDay> = {
  [ISO]: {
    tentative: false,
    changed: false,
    assignments: [
      {
        emoji: "🧹",
        name: "Sam",
        open: false,
        status: "scheduled",
        choreId: "c1",
        action: { shiftId: "s1", kind: "cover", label: "Cover" },
      },
      { emoji: "🗑️", name: "Kim", open: false, status: "scheduled", choreId: "c2" },
    ],
  },
};

function view() {
  const onact = vi.fn();
  const { container } = render(RosterCalendarView, {
    props: {
      month: "2026-01",
      daysByIso: DAYS,
      weekdays: ["ma", "di", "wo", "do", "vr", "za", "zo"],
      prevLabel: "prev",
      nextLabel: "next",
      locale: "nl",
      openLabel: "open",
      anonLabel: "anon",
      onact,
    },
  });
  return { container, onact };
}

/** The cell for a day that has assignments on it. */
async function openDay(container: HTMLElement) {
  const cell = [...container.querySelectorAll(".mg-cell")].find(
    (c) =>
      (c.textContent ?? "").includes(ISO.slice(8).replace(/^0/, "")) && c.querySelector(".rcv-list"),
  ) as HTMLElement;
  cell.click();
  await Promise.resolve();
}

describe("RosterCalendarView popover", () => {
  it("opens the default popover with one button per action and reports the act", async () => {
    const { container, onact } = view();
    await openDay(container);
    const buttons = [...container.querySelectorAll(".rcv-pop .btn")] as HTMLElement[];
    expect(buttons).toHaveLength(1); // only the actionable assignment
    buttons[0].click();
    await Promise.resolve();
    expect(onact.mock.calls).toEqual([["s1", "cover"]]);
    expect(container.querySelector(".rcv-pop")).toBeNull(); // acting closes it
  });

  it("renders the popover snippet instead, with the day's assignments and a working close", async () => {
    const { container } = render(RosterCalendarHarness, { props: { daysByIso: DAYS } });
    await openDay(container);
    expect(container.querySelector(".rcv-pop .btn")).toBeNull(); // default replaced
    const custom = container.querySelector(".rcv-pop .handover") as HTMLElement;
    expect(custom.textContent).toBe("2"); // the snippet sees every assignment
    custom.click();
    await Promise.resolve();
    expect(container.querySelector(".rcv-pop")).toBeNull(); // its close() works
  });
});
