/**
 * Playing a quiz (``PublicQuiz.vue``): the walk, the gate on a required
 * question, and what the result screen says.
 *
 * The cover comes first and the walk follows it, so every test here
 * starts by pressing the button the player presses
 * (``docs/design-quizzes.md`` part 3). Grading is the server's and is tested in ``tests/test_quizzes.py``;
 * what matters here is that one POST carries every answer, that the page
 * never shows a question it should be gating, and that the score comes
 * from the response rather than from anything the page worked out.
 */
import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/public_quiz/api";
import PublicQuiz from "@/public_quiz/PublicQuiz.vue";

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
      kind: "single_choice",
      prompt: "Hoofdstad?",
      required: true,
      options: ["Rotterdam", "Amsterdam"],
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
  return mount(PublicQuiz, { global: { stubs: { PublicShell: { template: "<div><slot /></div>" } } } });
}

/** The cover, then the first question. The name is asked here, so a
 *  test that wants one passes it. */
async function start(wrapper: ReturnType<typeof mountQuiz>, name?: string) {
  if (name) await wrapper.find("input[type=text]").setValue(name);
  // The cover's button submits its form; a click on it does not fire a
  // submit event in happy-dom, so the form is submitted directly.
  await wrapper.find("form").trigger("submit");
  await flushPromises();
}

beforeEach(() => {
  vi.clearAllMocks();
  window.history.replaceState(null, "", "/q/abc12345");
});

describe("playing a quiz", () => {
  it("opens on a cover, then shows one question at a time", async () => {
    const wrapper = mountQuiz();
    await flushPromises();
    // The cover: what this is, and the one thing it asks.
    expect(wrapper.text()).toContain("Pubquiz");
    expect(wrapper.text()).not.toContain("Hoofdstad?");
    await start(wrapper);
    expect(wrapper.text()).toContain("Vraag 1 van 2");
    expect(wrapper.text()).toContain("Hoofdstad?");
    expect(wrapper.text()).not.toContain("Hoeveel provincies?");
  });

  it("will not move past a required question that has no answer", async () => {
    const wrapper = mountQuiz();
    await flushPromises();
    await start(wrapper);
    await wrapper.findAll("button").find((b) => b.text() === "Volgende")!.trigger("click");
    await flushPromises();
    // Still on the first question, and told why.
    expect(wrapper.text()).toContain("Vraag 1 van 2");
    expect(wrapper.text()).toContain("Geef eerst een antwoord op deze vraag.");
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
    const wrapper = mountQuiz();
    await flushPromises();
    await start(wrapper, "Sam");

    await wrapper.findAll("input[type=radio]")[1].setValue(true);
    await wrapper.findAll("button").find((b) => b.text() === "Volgende")!.trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("Vraag 2 van 2");

    await wrapper.findAll("button").find((b) => b.text() === "Klaar")!.trigger("click");
    await flushPromises();

    const [slug, payload] = vi.mocked(api.postQuizAnswers).mock.calls[0];
    expect(slug).toBe("abc12345");
    // The name came from the cover and travels with the answers.
    expect(payload.display_name).toBe("Sam");
    // Every question, answered or not: the server decides what an empty
    // optional answer is worth.
    expect(payload.answers.map((a) => a.question_id)).toEqual(["one", "two"]);
    expect(payload.answers[0].answer_choices).toEqual(["Amsterdam"]);

    // The score is the response's, not a sum the page did itself.
    expect(wrapper.text()).toContain("2/ 5 punten");
    // Both halves of the comparison: what was given and what was right.
    expect(wrapper.text()).toContain("7");
    expect(wrapper.text()).toContain("12");
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
    const wrapper = mountQuiz();
    await flushPromises();
    expect(api.fetchQuizResult).toHaveBeenCalledWith("tok");
    expect(wrapper.text()).toContain("5/ 5 punten");
    // Nothing to answer again: a quiz submission has no edit.
    expect(wrapper.findAll("button").some((b) => b.text() === "Volgende")).toBe(false);
    expect(wrapper.findAll("button").some((b) => b.text() === "Beginnen")).toBe(false);
  });
});
