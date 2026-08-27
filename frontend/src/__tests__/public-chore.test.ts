/**
 * Public chore mini-app (``PublicChore.vue``): enrol payload shape,
 * personal-mode rendering, and the shift actions. The bare-fetch api
 * module is mocked; the roster payload is set on ``window`` as the
 * backend would inline it.
 */
import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/public_chore/api";
import PublicChore from "@/public_chore/PublicChore.vue";

vi.mock("@/public_chore/api", () => ({
  ApiError: class ApiError extends Error {},
  fetchRosterBySlug: vi.fn(),
  fetchPersonalPage: vi.fn(),
  fetchTokenCalendar: vi.fn(),
  postEnrolment: vi.fn(),
  putEnrolment: vi.fn(),
  postShiftAction: vi.fn(),
  postLeave: vi.fn(),
}));

const ROSTER = {
  id: "r1",
  name_nl: "Bins roster",
  name_en: "Bins roster",
  description_nl: null,
  description_en: null,
  location: null,
  latitude: null,
  longitude: null,
  image_url: null,
  image_artist_instagram: null,
  locale: "en" as const,
  period_weeks: 1,
  starts_on: "2026-01-05",
  ends_on: null,
  reminder_enabled: true,
  chores: [
    { id: "c1", name: "Bins", description: null, cycle_slots: [2], people_per_shift: 1, emoji: null },
    { id: "c2", name: "Sweep", description: null, cycle_slots: [4], people_per_shift: 1, emoji: null },
  ],
};

function setUrl(path: string): void {
  window.history.pushState({}, "", path);
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.fetchTokenCalendar).mockResolvedValue([]);
  window.__OPKOMST_CHORE__ = structuredClone(ROSTER);
});

afterEach(() => {
  window.__OPKOMST_CHORE__ = undefined;
});

describe("PublicChore enrol mode", () => {
  it("submits the picked chores + name, no email", async () => {
    setUrl("/c/abc12345");
    vi.mocked(api.postEnrolment).mockResolvedValueOnce({ edit_token: "tok" });
    const w = mount(PublicChore);
    await flushPromises();

    // Pick the first chore + type a name.
    const checks = w.findAll('input[type="checkbox"]');
    await checks[0].setValue(true); // c1
    await w.find('input[type="text"]').setValue("Sam");
    await w.findAll("button").find((b) => b.text() === "Sign up")!.trigger("click");
    await flushPromises();

    expect(api.postEnrolment).toHaveBeenCalledWith("abc12345", {
      display_name: "Sam",
      email: null,
      email_reminders: false,
      chore_ids: ["c1"],
    });
    // The standardized confirmation card (shared across all four entity
    // types) is shown, with the edit link.
    expect(w.text()).toContain("Thank you!");
  });

  it("giving an email turns reminders on (no separate opt-in)", async () => {
    setUrl("/c/abc12345");
    vi.mocked(api.postEnrolment).mockResolvedValueOnce({ edit_token: "tok" });
    const w = mount(PublicChore);
    await flushPromises();

    await w.findAll('input[type="checkbox"]')[0].setValue(true); // c1 pick
    await w.find('input[type="text"]').setValue("Sam"); // name is required
    await w.find('input[type="email"]').setValue("sam@local.dev");
    await w.findAll("button").find((b) => b.text() === "Sign up")!.trigger("click");
    await flushPromises();

    expect(api.postEnrolment).toHaveBeenCalledWith(
      "abc12345",
      expect.objectContaining({ email: "sam@local.dev", email_reminders: true, chore_ids: ["c1"] }),
    );
  });
});

describe("PublicChore personal mode", () => {
  // Both calendars open on the current month, so the fixture shifts have to
  // sit in it — a hardcoded month drifts out of view and the day cells the
  // tests click stop existing. Days 8 and 10 exist in every month.
  function dayOfThisMonth(day: number): string {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
  }
  const MY_DAY = 8;
  const OPEN_DAY = 10;

  const PAGE = {
    display_name: "Sam",
    enrolled_chore_ids: ["c1"],
    email_reminders: false,
    has_email: false,
    my_shifts: [
      {
        id: "s1",
        chore_id: "c1",
        chore_name: "Bins",
        on_date: dayOfThisMonth(MY_DAY),
        status: "scheduled",
        inherited: false,
      },
    ],
    open_shifts: [
      {
        id: "s2",
        chore_id: "c2",
        chore_name: "Sweep",
        on_date: dayOfThisMonth(OPEN_DAY),
        status: "open",
        inherited: false,
      },
    ],
  };

  it("renders my shifts + available shifts as calendars", async () => {
    setUrl("/c/abc12345?s=tok");
    vi.mocked(api.fetchPersonalPage).mockResolvedValueOnce(structuredClone(PAGE));
    const w = mount(PublicChore);
    await flushPromises();

    expect(w.text()).toContain("My shifts");
    expect(w.text()).toContain("Bins"); // my confirmed shift, in the calendar
    expect(w.text()).toContain("Pitch in");
    expect(w.text()).toContain("Sweep"); // an open shift, in the calendar
  });

  it("done calls the endpoint (via the day popover) and refetches", async () => {
    setUrl("/c/abc12345?s=tok");
    vi.mocked(api.fetchPersonalPage).mockResolvedValueOnce(structuredClone(PAGE));
    vi.mocked(api.postShiftAction).mockResolvedValueOnce({ ...structuredClone(PAGE), my_shifts: [] });
    const w = mount(PublicChore);
    await flushPromises();

    // Click the cell of my Bins shift to open its popover, then Done.
    await w.find(`[aria-label="${MY_DAY}"]`).trigger("click");
    await w.findAll("button").find((b) => b.text() === "Done")!.trigger("click");
    await flushPromises();
    expect(api.postShiftAction).toHaveBeenCalledWith("tok", "s1", "done");
  });

  it("claim takes an open shift (via the day popover)", async () => {
    setUrl("/c/abc12345?s=tok");
    vi.mocked(api.fetchPersonalPage).mockResolvedValueOnce(structuredClone(PAGE));
    // The "Bijspringen" card is the whole-roster calendar: the open Sweep slot
    // (shift s2) shows on its day; its shift id matches an open_shift, so it's
    // claimable.
    vi.mocked(api.fetchTokenCalendar).mockResolvedValue([
      {
        chore_id: "c2",
        chore_name: "Sweep",
        emoji: null,
        days: [
          {
            on_date: dayOfThisMonth(OPEN_DAY),
            tentative: false,
            assignees: [{ name: null, open: true, status: "scheduled", shift_id: "s2" }],
          },
        ],
      },
    ]);
    vi.mocked(api.postShiftAction).mockResolvedValueOnce(structuredClone(PAGE));
    const w = mount(PublicChore);
    await flushPromises();

    // Click the open Sweep shift's cell, then Take it on.
    await w.find(`[aria-label="${OPEN_DAY}"]`).trigger("click");
    await w.findAll("button").find((b) => b.text() === "Take it on")!.trigger("click");
    await flushPromises();
    expect(api.postShiftAction).toHaveBeenCalledWith("tok", "s2", "claim");
  });

  it("withdraw confirms then calls the endpoint", async () => {
    setUrl("/c/abc12345?s=tok");
    vi.mocked(api.fetchPersonalPage).mockResolvedValueOnce(structuredClone(PAGE));
    vi.mocked(api.postLeave).mockResolvedValueOnce(undefined);
    const confirmMock = vi.fn(() => true);
    window.confirm = confirmMock;
    const w = mount(PublicChore);
    await flushPromises();

    await w.findAll("button").find((b) => b.text() === "Withdraw")!.trigger("click");
    await flushPromises();
    expect(confirmMock).toHaveBeenCalled();
    expect(api.postLeave).toHaveBeenCalledWith("tok");
  });
});
