/**
 * Playing a quiz (``PublicQuiz.svelte``): the walk, the gate on a required
 * question, and what the result screen says.
 *
 * The cover comes first and the walk follows it, so every test here
 * starts by pressing the button the player presses
 * (``docs/design-quizzes.md`` part 3). Grading is the server's and is tested in ``tests/test_quizzes.py``;
 * what matters here is that one POST carries every answer, that the page
 * never shows a question it should be gating, and that the score comes
 * from the response rather than from anything the page worked out.
 */
import { render } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/public_quiz/api";
import PublicQuiz from "@/public_quiz/PublicQuiz.svelte";

/** Let every pending promise and the effects they schedule settle. */
async function settle() {
  for (let i = 0; i < 4; i++) await Promise.resolve();
  await new Promise((r) => setTimeout(r, 0));
}

const text = () => document.body.textContent ?? "";
const buttons = () => [...document.querySelectorAll("button")];
const byLabel = (label: string) => buttons().find((b) => b.textContent?.trim() === label);

vi.mock("@/public_quiz/api", () => ({
  ApiError: class ApiError extends Error {},
  fetchQuizBySlug: vi.fn(),
  fetchQuizResult: vi.fn(),
  postQuizAnswers: vi.fn(),
}));

const QUIZ = {
  id: "q1",
  name_nl: "Pubquiz",
  name_en: "Pubquiz",
  description_nl: null,
  description_en: null,
  image_url: null,
  image_artist_instagram: null,
  locale: "nl" as const,
  mode: "quiz" as const,
  questions: [
    {
      id: "one",
      ordinal: 1,
      kind: "multiple_choice",
      prompt: "Hoofdstad?",
      required: true,
      options: [{ id: "opt-rotterdam", label: "Rotterdam" }, { id: "opt-amsterdam", label: "Amsterdam" }],
      low_label: null,
      high_label: null,
      min_value: null,
      max_value: null,
      step: null,
      points: 2,
    },
    {
      id: "two",
      ordinal: 2,
      kind: "number",
      prompt: "Hoeveel provincies?",
      required: false,
      options: [],
      low_label: null,
      high_label: null,
      min_value: null,
      max_value: null,
      step: null,
      points: 3,
    },
  ],
};

function mountQuiz() {
  window.__OPKOMST_QUIZ__ = structuredClone(QUIZ) as never;
  return render(PublicQuiz);
}

/** The cover, then the first question. The name is asked here, so a
 *  test that wants one passes it. */
async function start(name?: string) {
  if (name) {
    const box = document.querySelector("input[type=text]") as HTMLInputElement;
    box.value = name;
    box.dispatchEvent(new Event("input", { bubbles: true }));
  }
  // The cover's button submits its form; a click on it does not fire a
  // submit event in happy-dom, so the form is submitted directly.
  document.querySelector("form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  await settle();
}

beforeEach(() => {
  vi.clearAllMocks();
  window.history.replaceState(null, "", "/q/abc12345");
});

afterEach(() => {
  document.body.innerHTML = "";
});

describe("playing a quiz", () => {
  it("opens on a cover, then shows one question at a time", async () => {
    mountQuiz();
    await settle();
    // The cover: what this is, and the one thing it asks.
    expect(text()).toContain("Pubquiz");
    expect(text()).not.toContain("Hoofdstad?");
    await start();
    expect(text()).toContain("Vraag 1 van 2");
    expect(text()).toContain("Hoofdstad?");
    expect(text()).not.toContain("Hoeveel provincies?");
  });

  it("will not move past a required question that has no answer", async () => {
    mountQuiz();
    await settle();
    await start();
    byLabel("Volgende")!.click();
    await settle();
    // Still on the first question, and told why.
    expect(text()).toContain("Vraag 1 van 2");
    expect(text()).toContain("Geef eerst een antwoord op deze vraag.");
  });

  it("sends every answer in one submit and shows what came back", async () => {
    vi.mocked(api.postQuizAnswers).mockResolvedValue({
      submission_id: "s1",
      edit_token: "tok",
      score: 2,
      max_score: 5,
      reveal_answers: true,
      answers: [
        {
          question_id: "one",
          awarded: 2,
          points: 2,
          correct: true,
          given_int: null,
          given_text: null,
          given_choices: ["Amsterdam"],
          correct_int: null,
          correct_text: null,
          correct_choices: ["Amsterdam"],
        },
        {
          question_id: "two",
          awarded: 0,
          points: 3,
          correct: false,
          given_int: 7,
          given_text: null,
          given_choices: null,
          correct_int: 12,
          correct_text: null,
          correct_choices: null,
        },
      ],
    });
    mountQuiz();
    await settle();
    await start("Sam");

    const radio = document.querySelectorAll("input[type=radio]")[1] as HTMLInputElement;
    radio.checked = true;
    radio.dispatchEvent(new Event("change", { bubbles: true }));
    await settle();
    byLabel("Volgende")!.click();
    await settle();
    expect(text()).toContain("Vraag 2 van 2");

    byLabel("Klaar")!.click();
    await settle();

    const [slug, payload] = vi.mocked(api.postQuizAnswers).mock.calls[0];
    expect(slug).toBe("abc12345");
    // The name came from the cover and travels with the answers.
    expect(payload.display_name).toBe("Sam");
    // Every question, answered or not: the server decides what an empty
    // optional answer is worth.
    expect(payload.answers.map((a) => a.question_id)).toEqual(["one", "two"]);
    // The answer names the option by id. The label is what was read on
    // screen, and the organiser can reword it afterwards without
    // detaching this (``docs/design-question-edits.md``).
    expect(payload.answers[0].answer_choices).toEqual(["opt-amsterdam"]);

    // The score is the response's, not a sum the page did itself.
    expect(text()).toContain("2/ 5 punten");
    // Both halves of the comparison: what was given and what was right.
    expect(text()).toContain("7");
    expect(text()).toContain("12");
  });

  it("shows the link back to the attempt, and does not promise an edit", async () => {
    // A quiz has no edit path at all, so the link is how you see the
    // score again and the copy says exactly that.
    window.history.replaceState(null, "", "/q/abc12345?s=tok");
    vi.mocked(api.fetchQuizResult).mockResolvedValue({
      submission_id: "s1",
      edit_token: "tok",
      score: 5,
      max_score: 5,
      reveal_answers: false,
      answers: [],
    });
    mountQuiz();
    await settle();

    expect(document.querySelector("a.link")!.getAttribute("href")).toContain("/q/abc12345?s=tok");
    expect(document.querySelector("button.copy-btn")).not.toBeNull();
    expect(text()).toContain("terug te zien");
  });

  it("reopens a finished attempt read-only from its token", async () => {
    window.history.replaceState(null, "", "/q/abc12345?s=tok");
    vi.mocked(api.fetchQuizResult).mockResolvedValue({
      submission_id: "s1",
      edit_token: "tok",
      score: 5,
      max_score: 5,
      reveal_answers: false,
      answers: [],
    });
    mountQuiz();
    await settle();
    expect(api.fetchQuizResult).toHaveBeenCalledWith("tok");
    expect(text()).toContain("5/ 5 punten");
    // Nothing to answer again: a quiz submission has no edit.
    expect(byLabel("Volgende")).toBeUndefined();
    expect(byLabel("Beginnen")).toBeUndefined();
  });
});
