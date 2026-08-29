import { cleanup, render } from "@testing-library/svelte";
import { afterEach, describe, expect, it } from "vitest";

import { bindable } from "@/__tests__/bind.svelte";
import DatePicker from "@/components/DatePicker.svelte";

// The picker replaced PrimeVue's, whose behaviour four call sites rely
// on: the dd-mm-yyyy format, a six-week grid that never changes height,
// single vs multiple selection, and the time spinner's step.

// An inline calendar and a panel both outlive their test otherwise, and
// the panel is moved to the body, so the next test's query would find
// the last test's calendar.
afterEach(cleanup);

/** The picker with its value bound, so a test reads back what it wrote.
 *  The panel is moved to the body, so panel queries go through
 *  ``document``; everything the field owns is in the container. */
function picker(value: Date | Date[] | null, rest: Record<string, unknown> = {}) {
  const model = bindable("modelValue", value, rest);
  const { container, unmount } = render(DatePicker, { props: model.props });
  const input = container.querySelector("input") as HTMLInputElement;
  return {
    model,
    container,
    unmount,
    input,
    all: (selector: string) => [...document.querySelectorAll(selector)] as HTMLElement[],
    async type(text: string) {
      input.value = text;
      input.dispatchEvent(new Event("input", { bubbles: true }));
      await Promise.resolve();
    },
    async focus() {
      input.dispatchEvent(new FocusEvent("focus", { bubbles: true }));
      await Promise.resolve();
    },
    async click(el: HTMLElement) {
      el.click();
      await Promise.resolve();
    },
  };
}

describe("date input", () => {
  it("formats the value the way dd-mm-yy means in this vocabulary", () => {
    // ``yy`` is the four-digit year, not the last two.
    const p = picker(new Date(2026, 2, 5));
    expect(p.input.value).toBe("05-03-2026");
  });

  it("parses what the user types back into a date", async () => {
    const p = picker(null);
    await p.type("09-04-2026");
    const out = p.model.current as Date;
    expect([out.getFullYear(), out.getMonth(), out.getDate()]).toEqual([2026, 3, 9]);
  });

  it("leaves the value alone while a date is half-typed", async () => {
    const p = picker(new Date(2026, 2, 5));
    await p.type("09-04");
    expect(p.model.writes).toHaveLength(0);
  });

  it("clears when the field is emptied", async () => {
    const p = picker(new Date(2026, 2, 5));
    await p.type("");
    expect(p.model.current).toBeNull();
  });

  it("opens on focus and closes once a day is picked", async () => {
    const p = picker(new Date(2026, 2, 5));
    expect(document.querySelector(".dp-panel")).toBeNull();
    await p.focus();
    expect(document.querySelector(".dp-panel")).not.toBeNull();
    await p.click(p.all(".dp-day:not(.dp-day-other)")[10]);
    expect(document.querySelector(".dp-panel")).toBeNull();
    p.unmount();
  });
});

describe("the calendar grid", () => {
  it("always draws six weeks, so the panel height never shifts", () => {
    // February 2026 fits in five rows; May 2026 needs six.
    for (const month of [new Date(2026, 1, 10), new Date(2026, 4, 10)]) {
      const p = picker(month, { inline: true });
      expect(p.container.querySelectorAll("tbody tr")).toHaveLength(6);
      p.unmount();
    }
  });

  it("starts the week on Monday in the page language", () => {
    const p = picker(new Date(2026, 2, 5), { inline: true, locale: "nl" });
    const heads = [...p.container.querySelectorAll(".dp-weekday")].map((n) => n.textContent);
    expect(heads[0]).toBe("ma");
    expect(heads[6]).toBe("zo");
    expect(p.container.querySelector(".dp-title-month")?.textContent).toBe("maart");
    p.unmount();
  });

  it("shows the neighbouring months' days but does not select them", async () => {
    // 1 March 2026 is a Sunday, so the row leads with six February days.
    const p = picker(new Date(2026, 2, 5), { inline: true });
    const others = [...p.container.querySelectorAll(".dp-day-other")] as HTMLElement[];
    expect(others.length).toBeGreaterThan(0);
    await p.click(others[0]);
    expect(p.model.writes).toHaveLength(0);
    p.unmount();
  });

  it("marks today and the selected day", () => {
    const p = picker(new Date(), { inline: true });
    expect(p.container.querySelectorAll(".dp-today")).toHaveLength(1);
    expect(p.container.querySelectorAll(".dp-day-selected")).toHaveLength(1);
    p.unmount();
  });
});

describe("multiple selection", () => {
  it("adds a day, and removes one already chosen", async () => {
    const first = new Date(2026, 2, 5);
    const p = picker([first], { inline: true, selectionMode: "multiple" });
    const days = [...p.container.querySelectorAll(".dp-day:not(.dp-day-other)")] as HTMLElement[];

    await p.click(days[9]); // 10 March
    expect(p.model.current as Date[]).toHaveLength(2);

    await p.click(days[4]); // 5 March again, off
    const left = p.model.current as Date[];
    expect(left).toHaveLength(1);
    expect(left[0].getDate()).toBe(10);
    p.unmount();
  });
});

describe("time only", () => {
  it("shows hours and minutes, and no calendar", async () => {
    const p = picker(new Date(2026, 2, 5, 18, 30), { timeOnly: true });
    expect(p.input.value).toBe("18:30");
    await p.focus();
    expect(document.querySelector(".dp-dayview")).toBeNull();
    expect(document.querySelectorAll(".dp-timepicker span")[0].textContent).toBe("18");
    p.unmount();
  });

  it("steps minutes by stepMinute and wraps the hour", async () => {
    const p = picker(new Date(2026, 2, 5, 23, 45), { timeOnly: true, stepMinute: 15 });
    await p.focus();
    const buttons = p.all(".dp-timepicker .dp-navbtn");
    await p.click(buttons[2]); // minute up
    expect((p.model.current as Date).getMinutes()).toBe(0);
    await p.click(buttons[0]); // hour up, 23 -> 0
    expect((p.model.current as Date).getHours()).toBe(0);
    p.unmount();
  });
});

describe("button bar", () => {
  it("offers today and clear in the page language", async () => {
    const p = picker(null, { showButtonBar: true, locale: "nl" });
    await p.focus();
    const bar = p.all(".dp-barbtn");
    expect(bar.map((b) => b.textContent)).toEqual(["Vandaag", "Wissen"]);
    await p.click(bar[1]);
    expect(p.model.current).toBeNull();
    p.unmount();
  });
});
