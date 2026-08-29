/**
 * Filling in a kompas (``PublicCompass.svelte``): the cover, the walk, and
 * what the map says afterwards.
 *
 * The arithmetic is the server's and is tested in
 * ``tests/test_compass.py``; what matters here is that the walk never
 * shows a direction before the answering is over, that one POST carries
 * every answer, that the coordinates come from the response rather than
 * from anything the page worked out, and that "change your answers"
 * reopens the walk with the answers still in it.
 */
import { render } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/public_compass/api";
import PublicCompass from "@/public_compass/PublicCompass.svelte";

/** Let every pending promise and the effects they schedule settle. */
async function settle() {
  for (let i = 0; i < 4; i++) await Promise.resolve();
  await new Promise((r) => setTimeout(r, 0));
}

const text = () => document.body.textContent ?? "";

vi.mock("@/public_compass/api", () => ({
  ApiError: class ApiError extends Error {},
  fetchCompassBySlug: vi.fn(),
  fetchCompassResult: vi.fn(),
  postCompassAnswers: vi.fn(),
  putCompassAnswers: vi.fn(),
}));

const AXES = [
  {
    axis: "x",
    name: "Economie",
    description: "Waar het geld heen gaat",
    low_name: "Links",
    high_name: "Rechts",
  },
  {
    axis: "y",
    name: "Cultuur",
    description: null,
    low_name: "Open",
    high_name: "Behoud",
  },
];

const COMPASS = {
  id: "k1",
  name_nl: "Waar sta jij?",
  name_en: "Where do you stand?",
  description_nl: null,
  description_en: null,
  image_url: null,
  image_artist_instagram: null,
  locale: "nl" as const,
  mode: "compass" as const,
  name_required: false,
  answers_editable: true,
  axes: AXES,
  questions: [
    {
      id: "one",
      ordinal: 1,
      kind: "rating",
      prompt: "De overheid moet meer huizen bouwen",
      required: true,
      options: [],
      low_label: "Oneens",
      high_label: "Eens",
      min_value: null,
      max_value: null,
      step: null,
      points: 0,
    },
    {
      id: "two",
      ordinal: 2,
      kind: "single_choice",
      prompt: "Waar moet het geld heen?",
      required: true,
      options: ["Zorg", "Defensie"],
      low_label: null,
      high_label: null,
      min_value: null,
      max_value: null,
      step: null,
      points: 0,
    },
  ],
};

const RESULT = {
  submission_id: "s1",
  edit_token: "tok",
  display_name: "Sam",
  link_recovered_at: null,
  x: -0.5,
  y: 1,
  counted_x: 2,
  counted_y: 1,
  // The result carries each axis with where the whole room sits on it,
  // which is the band the reader's own marker is drawn against.
  axes: AXES.map((axis) => ({ axis, average: 0, ci_low: -0.6, ci_high: 0.6 })),
  points: [
    { name: "Sam", x: -0.5, y: 1, you: true },
    { name: null, x: 0.5, y: -1, you: false },
  ],
  answers: [
    {
      question_id: "one",
      kind: "rating",
      pole: "x_high",
      option_poles: null,
      given_int: 2,
      given_choices: null,
      axis: "x",
      value: -0.5,
    },
    {
      question_id: "two",
      kind: "single_choice",
      pole: null,
      option_poles: ["x_low", "y_high"],
      given_int: null,
      given_choices: ["Zorg"],
      axis: "x",
      value: -1,
    },
  ],
};

function mountCompass(over: Record<string, unknown> = {}) {
  window.__OPKOMST_COMPASS__ = { ...structuredClone(COMPASS), ...over } as never;
  return render(PublicCompass);
}

/** The cover, then the first question. */
async function start(name?: string) {
  if (name) {
    const box = document.querySelector("input[type=text]") as HTMLInputElement;
    box.value = name;
    box.dispatchEvent(new Event("input", { bubbles: true }));
  }
  document.querySelector("form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  await settle();
}

function buttonWith(label: string) {
  return [...document.querySelectorAll("button")].find((b) => b.textContent?.trim() === label);
}

/** A rating is five buttons, not five radios (``QuestionField``). */
async function rate(value: number) {
  (document.querySelectorAll(".rating-row button")[value - 1] as HTMLElement).click();
  await settle();
}

async function pick(index: number) {
  const radio = document.querySelectorAll("input[type=radio]")[index] as HTMLInputElement;
  radio.checked = true;
  radio.dispatchEvent(new Event("change", { bubbles: true }));
  await settle();
}

beforeEach(() => {
  vi.clearAllMocks();
  window.history.replaceState(null, "", "/k/abc123");
});

afterEach(() => {
  document.body.innerHTML = "";
});

describe("PublicCompass", () => {
  it("says on the cover that the name goes on a shared map", async () => {
    mountCompass();
    await settle();
    // The privacy contract of this feature, above the box rather than
    // after the submit (``docs/design-kompas.md`` 5.1).
    expect(text()).toContain("Je naam komt op de kaart");
    // And what the kompas places people on, which is not a secret.
    expect(text()).toContain("Economie");
  });

  it("never shows which answer points where before the result", async () => {
    mountCompass();
    await settle();
    await start();
    // The rating's own side, and the two option sides, are all absent
    // from the walk: the payload does not carry them at all.
    expect(text()).not.toContain("Rechts");
    await rate(4);
    buttonWith("Volgende")?.click();
    await settle();
    expect(text()).not.toContain("Links");
  });

  it("walks one question at a time and gates a required one", async () => {
    mountCompass();
    await settle();
    await start();

    expect(text()).toContain("Vraag 1 van 2");
    expect(text()).toContain("De overheid moet meer huizen bouwen");
    expect(text()).not.toContain("Waar moet het geld heen?");

    // Nothing answered: Next refuses rather than the submit doing it
    // ten questions later.
    buttonWith("Volgende")?.click();
    await settle();
    expect(text()).toContain("Geef eerst een antwoord");
    expect(text()).toContain("Vraag 1 van 2");
  });

  it("sends every answer in one call and takes the position from the response", async () => {
    vi.mocked(api.postCompassAnswers).mockResolvedValue(structuredClone(RESULT) as never);
    mountCompass();
    await settle();
    await start("Sam");

    // A 2 on the first statement, the first option on the second.
    await rate(2);
    buttonWith("Volgende")?.click();
    await settle();
    await pick(0);
    buttonWith("Klaar")?.click();
    await settle();
    await settle();

    expect(api.postCompassAnswers).toHaveBeenCalledTimes(1);
    const [, payload] = vi.mocked(api.postCompassAnswers).mock.calls[0];
    expect(payload.display_name).toBe("Sam");
    expect(payload.answers).toEqual([
      { question_id: "one", answer_int: 2 },
      { question_id: "two", answer_choices: ["Zorg"] },
    ]);

    // The map, and a sentence per axis built from the organiser's own
    // words. Nothing here was computed by the page.
    expect(text()).toContain("Je staat aan de kant van Links");
    expect(text()).toContain("Je staat aan de kant van Behoud");
    // And the direction each answer carried, hidden until now.
    expect(text()).toContain("Een 5 was Rechts, jij zei 2");
  });

  it("says which reason a zero on an axis has", async () => {
    const nothingSaid = { ...structuredClone(RESULT), y: 0, counted_y: 0 };
    vi.mocked(api.postCompassAnswers).mockResolvedValue(nothingSaid as never);
    mountCompass();
    await settle();
    await start();
    await rate(2);
    buttonWith("Volgende")?.click();
    await settle();
    await pick(0);
    buttonWith("Klaar")?.click();
    await settle();
    await settle();

    // A dot on the centre line has two possible reasons and the screen
    // says which one this is.
    expect(text()).toContain("Over deze as heb je niks ingevuld");
    expect(text()).not.toContain("Je staat in het midden");
  });

  it("draws the room's band behind your own marker", async () => {
    vi.mocked(api.postCompassAnswers).mockResolvedValue(structuredClone(RESULT) as never);
    mountCompass();
    await settle();
    await start();
    await rate(2);
    buttonWith("Volgende")?.click();
    await settle();
    await pick(0);
    buttonWith("Klaar")?.click();
    await settle();
    await settle();

    expect(document.querySelectorAll(".axis-room")).toHaveLength(2);
    expect(text()).toContain("waar de groep staat");
  });

  it("draws no band when the room is a point rather than a range", async () => {
    // Nobody else has filled it in, or only one person has: there is a
    // mean and no interval, so there is nothing to draw and nothing to
    // explain.
    const noRoom = structuredClone(RESULT);
    noRoom.axes = noRoom.axes.map((row) => ({ ...row, ci_low: 0, ci_high: 0 }));
    vi.mocked(api.postCompassAnswers).mockResolvedValue(noRoom as never);
    mountCompass();
    await settle();
    await start();
    await rate(2);
    buttonWith("Volgende")?.click();
    await settle();
    await pick(0);
    buttonWith("Klaar")?.click();
    await settle();
    await settle();

    expect(document.querySelector(".axis-room")).toBeNull();
    expect(text()).not.toContain("waar de groep staat");
  });

  it("shows the secret link back to this fill-in, with a way to copy it", async () => {
    // The token lives only in that URL and nobody can re-send it, so the
    // result page says so out loud rather than leaving it in the
    // address bar (the same card every other mini-app shows).
    vi.mocked(api.fetchCompassResult).mockResolvedValue(structuredClone(RESULT) as never);
    window.history.replaceState(null, "", "/k/abc123?s=tok");
    mountCompass();
    await settle();

    const link = document.querySelector("a.link")!;
    expect(link.getAttribute("href")).toContain("/k/abc123?s=tok");
    expect(document.querySelector("button.copy-btn")).not.toBeNull();
  });

  it("offers no way back into the answers when the organiser closed them", async () => {
    vi.mocked(api.fetchCompassResult).mockResolvedValue(structuredClone(RESULT) as never);
    window.history.replaceState(null, "", "/k/abc123?s=tok");
    mountCompass({ answers_editable: false });
    await settle();

    expect(buttonWith("Verander je antwoorden")).toBeUndefined();
    // The link still opens the result: seeing what you said is the
    // other half of what it is for.
    expect(document.querySelector("a.link")).not.toBeNull();
    expect(text()).toContain("terug te zien");
  });

  it("reopens a finished fill-in and lets the answers change", async () => {
    vi.mocked(api.fetchCompassResult).mockResolvedValue(structuredClone(RESULT) as never);
    vi.mocked(api.putCompassAnswers).mockResolvedValue(structuredClone(RESULT) as never);
    window.history.replaceState(null, "", "/k/abc123?s=tok");

    mountCompass();
    await settle();
    expect(text()).toContain("Waar je staat");

    // Unlike a quiz, changing your mind is allowed, and the walk comes
    // back with the answers still in it.
    buttonWith("Verander je antwoorden")?.click();
    await settle();
    await settle();
    expect(text()).toContain("Vraag 1 van 2");
    // The 2 that was given is still the one marked.
    expect([...document.querySelectorAll(".rating-row button")][1].classList).toContain("active");

    buttonWith("Volgende")?.click();
    await settle();
    buttonWith("Klaar")?.click();
    await settle();
    await settle();
    // A second save is a correction of the same submission, not a new
    // one.
    expect(api.putCompassAnswers).toHaveBeenCalledTimes(1);
    expect(api.postCompassAnswers).not.toHaveBeenCalled();
  });
});
