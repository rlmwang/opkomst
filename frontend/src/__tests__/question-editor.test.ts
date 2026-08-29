/**
 * QuestionEditor's kind-switching contract: changing the kind clears
 * the fields that do not belong to the new one, so the payload shipped
 * to the backend carries nothing left over from the previous kind.
 *
 * Driven through the kind select rather than by calling the patch
 * helper: the select is how an organiser changes a kind, and a test
 * that reaches inside the component stops telling you whether the
 * screen still works.
 */
import { cleanup, render } from "@testing-library/svelte";
import type { ComponentProps } from "svelte";
import { afterEach, describe, expect, it } from "vitest";

import { bindable } from "@/__tests__/bind.svelte";
import { useTestMessages } from "@/__tests__/i18n-harness";
import QuestionEditor, { type QuestionDraft } from "@/components/QuestionEditor.svelte";

useTestMessages("en", {
  form: {
    question: {
      promptPlaceholder: "Question",
      kind: {
        rating: "Rating",
        number: "Number",
        text: "Long text",
        short_text: "Short text",
        single_choice: "Single choice",
        multi_choice: "Multiple choice",
      },
      required: "Required",
      lowLabel: "Low",
      highLabel: "High",
      minValue: "Min",
      maxValue: "Max",
      step: "Step",
      options: "Options",
      newOption: "Option",
      delete: "Remove",
      moveUp: "Up",
      moveDown: "Down",
    },
  },
  common: { remove: "Remove", clear: "Clear", noResults: "No results" },
});

// The select's panel is moved to the body, so a leftover one would
// answer the next test's query.
afterEach(cleanup);

const settle = () => new Promise((r) => setTimeout(r, 0));

/** The draft, and the editor driven the way an organiser drives it. */
function editor(draft: QuestionDraft) {
  const model = bindable<QuestionDraft, ComponentProps<typeof QuestionEditor>>("value", draft, {
    canMoveUp: true,
    canMoveDown: true,
    ondelete: () => {},
    onmoveUp: () => {},
    onmoveDown: () => {},
  });
  const { container } = render(QuestionEditor, { props: model.props });
  return {
    get: () => model.current,
    /** Open the kind select and pick the row with this label. */
    async setKind(label: string) {
      (container.querySelector(".kind-select") as HTMLElement).click();
      await settle();
      const row = [...document.querySelectorAll(".ovl-option")].find(
        (o) => o.textContent?.trim() === label,
      ) as HTMLElement;
      row.click();
      await settle();
    },
  };
}
const KIND_LABEL = {
  rating: "Rating",
  number: "Number",
  text: "Long text",
  short_text: "Short text",
  single_choice: "Single choice",
  multi_choice: "Multiple choice",
};

describe("QuestionEditor kind switching", () => {
  it("clears low/high labels when switching away from rating", async () => {
    const initial: QuestionDraft = {
      id: "q1",
      kind: "rating",
      prompt: "How was it?",
      required: true,
      options: [],
      low_label: "Poor",
      high_label: "Great",
      min_value: null,
      max_value: null,
      step: null,
      points: 0,
      correct_int: null,
      correct_text: null,
      correct_choices: null,
      tolerance: null,
    pole: null,
    option_poles: null,
    };
    const q = editor(initial);
    await q.setKind(KIND_LABEL.text);
    expect(q.get().low_label).toBeNull();
    expect(q.get().high_label).toBeNull();
    expect(q.get().kind).toBe("text");
  });

  it("clears options when switching away from a choice kind", async () => {
    const initial: QuestionDraft = {
      id: "q1",
      kind: "single_choice",
      prompt: "Pick one",
      required: true,
      options: ["A", "B", "C"],
      low_label: null,
      high_label: null,
      min_value: null,
      max_value: null,
      step: null,
      points: 0,
      correct_int: null,
      correct_text: null,
      correct_choices: null,
      tolerance: null,
    pole: null,
    option_poles: null,
    };
    const q = editor(initial);
    await q.setKind(KIND_LABEL.rating);
    expect(q.get().options).toEqual([]);
    expect(q.get().kind).toBe("rating");
  });

  it("preserves options when switching between the two choice kinds", async () => {
    const initial: QuestionDraft = {
      id: "q1",
      kind: "single_choice",
      prompt: "Pick one",
      required: false,
      options: ["A", "B"],
      low_label: null,
      high_label: null,
      min_value: null,
      max_value: null,
      step: null,
      points: 0,
      correct_int: null,
      correct_text: null,
      correct_choices: null,
      tolerance: null,
    pole: null,
    option_poles: null,
    };
    const q = editor(initial);
    await q.setKind(KIND_LABEL.multi_choice);
    expect(q.get().options).toEqual(["A", "B"]);
    expect(q.get().kind).toBe("multi_choice");
  });

  it("clears the number bounds when switching away from number", async () => {
    const initial: QuestionDraft = {
      id: "q1",
      kind: "number",
      prompt: "How old are you?",
      required: true,
      options: [],
      low_label: null,
      high_label: null,
      min_value: 0,
      max_value: 120,
      step: 5,
      points: 0,
      correct_int: null,
      correct_text: null,
      correct_choices: null,
      tolerance: null,
    pole: null,
    option_poles: null,
    };
    const q = editor(initial);
    await q.setKind(KIND_LABEL.short_text);
    expect(q.get().min_value).toBeNull();
    expect(q.get().max_value).toBeNull();
    expect(q.get().step).toBeNull();
  });

  it("drops a key that no longer fits when the kind changes", async () => {
    const initial: QuestionDraft = {
      id: "q1",
      kind: "single_choice",
      prompt: "Welke?",
      required: true,
      options: ["A", "B"],
      low_label: null,
      high_label: null,
      min_value: null,
      max_value: null,
      step: null,
      points: 2,
      correct_int: null,
      correct_text: null,
      correct_choices: ["A"],
      tolerance: null,
    pole: null,
    option_poles: null,
    };
    const q = editor(initial);
    await q.setKind(KIND_LABEL.number);
    expect(q.get().correct_choices).toBeNull();
    // What it is worth survives: the points are about the question,
    // not about the shape of its answer.
    expect(q.get().points).toBe(2);
  });
});
