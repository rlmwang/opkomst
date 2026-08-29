import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import DatePicker from "@/components/DatePicker.vue";

// The picker replaced PrimeVue's, whose behaviour four call sites rely
// on: the dd-mm-yyyy format, a six-week grid that never changes height,
// single vs multiple selection, and the time spinner's step.

type Props = InstanceType<typeof DatePicker>["$props"];

const mountAt = (props: Props) => mount(DatePicker, { props, attachTo: document.body });

describe("date input", () => {
  it("formats the value the way dd-mm-yy means in this vocabulary", () => {
    // ``yy`` is the four-digit year, not the last two.
    const w = mountAt({ modelValue: new Date(2026, 2, 5) });
    expect((w.get("input").element as HTMLInputElement).value).toBe("05-03-2026");
  });

  it("parses what the user types back into a date", async () => {
    const w = mountAt({ modelValue: null });
    const input = w.get("input");
    await input.setValue("09-04-2026");
    const emitted = w.emitted("update:modelValue")!.at(-1)![0] as Date;
    expect([emitted.getFullYear(), emitted.getMonth(), emitted.getDate()]).toEqual([2026, 3, 9]);
  });

  it("leaves the value alone while a date is half-typed", async () => {
    const w = mountAt({ modelValue: new Date(2026, 2, 5) });
    await w.get("input").setValue("09-04");
    expect(w.emitted("update:modelValue")).toBeUndefined();
  });

  it("clears when the field is emptied", async () => {
    const w = mountAt({ modelValue: new Date(2026, 2, 5) });
    await w.get("input").setValue("");
    expect(w.emitted("update:modelValue")!.at(-1)![0]).toBeNull();
  });

  it("opens on focus and closes once a day is picked", async () => {
    const w = mountAt({ modelValue: new Date(2026, 2, 5) });
    expect(document.querySelector(".dp-panel")).toBeNull();
    await w.get("input").trigger("focus");
    expect(document.querySelector(".dp-panel")).not.toBeNull();
    const days = document.querySelectorAll(".dp-day:not(.dp-day-other)");
    (days[10] as HTMLElement).click();
    await w.vm.$nextTick();
    expect(document.querySelector(".dp-panel")).toBeNull();
    w.unmount();
  });
});

describe("the calendar grid", () => {
  it("always draws six weeks, so the panel height never shifts", async () => {
    // February 2026 fits in five rows; May 2026 needs six.
    for (const month of [new Date(2026, 1, 10), new Date(2026, 4, 10)]) {
      const w = mountAt({ modelValue: month, inline: true });
      expect(w.findAll("tbody tr")).toHaveLength(6);
      w.unmount();
    }
  });

  it("starts the week on Monday in the page language", () => {
    const w = mountAt({ modelValue: new Date(2026, 2, 5), inline: true, locale: "nl" });
    const heads = w.findAll(".dp-weekday").map((n) => n.text());
    expect(heads[0]).toBe("ma");
    expect(heads[6]).toBe("zo");
    expect(w.get(".dp-title-month").text()).toBe("maart");
    w.unmount();
  });

  it("shows the neighbouring months' days but does not select them", async () => {
    // 1 March 2026 is a Sunday, so the row leads with six February days.
    const w = mountAt({ modelValue: new Date(2026, 2, 5), inline: true });
    const others = w.findAll(".dp-day-other");
    expect(others.length).toBeGreaterThan(0);
    await others[0].trigger("click");
    expect(w.emitted("update:modelValue")).toBeUndefined();
    w.unmount();
  });

  it("marks today and the selected day", () => {
    const w = mountAt({ modelValue: new Date(), inline: true });
    expect(w.findAll(".dp-today")).toHaveLength(1);
    expect(w.findAll(".dp-day-selected")).toHaveLength(1);
    w.unmount();
  });
});

describe("multiple selection", () => {
  it("adds a day, and removes one already chosen", async () => {
    const first = new Date(2026, 2, 5);
    const w = mountAt({ modelValue: [first], inline: true, selectionMode: "multiple" });
    const days = w.findAll(".dp-day:not(.dp-day-other)");

    await days[9].trigger("click"); // 10 March
    let out = w.emitted("update:modelValue")!.at(-1)![0] as Date[];
    expect(out).toHaveLength(2);

    await days[4].trigger("click"); // 5 March again
    out = w.emitted("update:modelValue")!.at(-1)![0] as Date[];
    expect(out).toHaveLength(0);
    w.unmount();
  });
});

describe("time only", () => {
  it("shows hours and minutes, and no calendar", async () => {
    const at = new Date(2026, 2, 5, 18, 30);
    const w = mountAt({ modelValue: at, timeOnly: true });
    expect((w.get("input").element as HTMLInputElement).value).toBe("18:30");
    await w.get("input").trigger("focus");
    expect(document.querySelector(".dp-dayview")).toBeNull();
    expect(document.querySelectorAll(".dp-timepicker span")[0].textContent).toBe("18");
    w.unmount();
  });

  it("steps minutes by stepMinute and wraps the hour", async () => {
    const w = mountAt({ modelValue: new Date(2026, 2, 5, 23, 45), timeOnly: true, stepMinute: 15 });
    await w.get("input").trigger("focus");
    const buttons = document.querySelectorAll(".dp-timepicker .dp-navbtn");
    (buttons[2] as HTMLElement).click(); // minute up
    let out = w.emitted("update:modelValue")!.at(-1)![0] as Date;
    expect(out.getMinutes()).toBe(0);
    (buttons[0] as HTMLElement).click(); // hour up, 23 -> 0
    out = w.emitted("update:modelValue")!.at(-1)![0] as Date;
    expect(out.getHours()).toBe(0);
    w.unmount();
  });
});

describe("button bar", () => {
  it("offers today and clear in the page language", async () => {
    const w = mountAt({ modelValue: null, showButtonBar: true, locale: "nl" });
    await w.get("input").trigger("focus");
    const bar = document.querySelectorAll(".dp-barbtn");
    expect([...bar].map((b) => b.textContent)).toEqual(["Vandaag", "Wissen"]);
    (bar[1] as HTMLElement).click();
    expect(w.emitted("update:modelValue")!.at(-1)![0]).toBeNull();
    w.unmount();
  });
});
