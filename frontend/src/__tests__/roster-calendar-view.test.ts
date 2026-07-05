/**
 * ``RosterCalendarView`` popover behaviour: an actionable day opens the
 * popover on click; the default popover renders one button per action
 * (the public claim/cover shape); the ``popover`` slot replaces that
 * content (the organiser hand-over pickers) and receives the day's
 * assignments plus a working ``close``.
 */
import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import RosterCalendarView, { type RosterDay } from "@/components/RosterCalendarView.vue";

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

function mountView(slots: Record<string, string> = {}) {
  return mount(RosterCalendarView, {
    props: {
      month: "2026-01",
      daysByIso: DAYS,
      weekdays: ["ma", "di", "wo", "do", "vr", "za", "zo"],
      prevLabel: "prev",
      nextLabel: "next",
      locale: "nl",
      openLabel: "open",
      anonLabel: "anon",
    },
    slots,
  });
}

function cellFor(w: ReturnType<typeof mountView>, iso: string) {
  return w.findAll(".mg-cell").find((c) => c.text().includes(iso.slice(8).replace(/^0/, "")) && c.find(".rcv-list").exists())!;
}

describe("RosterCalendarView popover", () => {
  it("opens the default popover with one button per action and emits act", async () => {
    const w = mountView();
    await cellFor(w, ISO).trigger("click");
    const buttons = w.findAll(".rcv-pop .btn");
    expect(buttons).toHaveLength(1); // only the actionable assignment
    await buttons[0].trigger("click");
    expect(w.emitted("act")).toEqual([["s1", "cover"]]);
    expect(w.find(".rcv-pop").exists()).toBe(false); // acting closes it
  });

  it("renders the popover slot instead, with the day's assignments and a working close", async () => {
    const w = mountView({
      popover: `
        <template #popover="{ assignments, close }">
          <button class="handover" @click="close()">{{ assignments.length }}</button>
        </template>
      `,
    });
    await cellFor(w, ISO).trigger("click");
    expect(w.find(".rcv-pop .btn").exists()).toBe(false); // default replaced
    const custom = w.find(".rcv-pop .handover");
    expect(custom.text()).toBe("2"); // slot sees every assignment of the day
    await custom.trigger("click");
    expect(w.find(".rcv-pop").exists()).toBe(false); // slot's close() works
  });
});
