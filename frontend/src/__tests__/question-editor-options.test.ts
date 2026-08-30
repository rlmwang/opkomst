/**
 * QuestionEditor's option-identity contract.
 *
 * A choice is a row on the server and an answer points at its id, so an
 * option keeps the answers to it exactly as long as the editor keeps its
 * id. Every edit here has to rewrite fields on the row the organiser is
 * looking at, never swap it for a new one: a rename that produced a new
 * id would read to the server as "delete this option, add another", and
 * take everyone's answers with it (``docs/design-question-edits.md``).
 *
 * That is invisible in the UI, which is why it is asserted here. The
 * screen looks identical either way; the difference only shows up in the
 * counts on the results page afterwards, when it is too late.
 *
 * Driven through the rendered controls rather than by calling the patch
 * helpers, for the same reason the kind-switching tests are: a test that
 * reaches inside the component stops telling you whether the screen
 * still works.
 */
import { cleanup, fireEvent, render } from "@testing-library/svelte";
import type { ComponentProps } from "svelte";
import { afterEach, describe, expect, it } from "vitest";

import { bindable } from "@/__tests__/bind.svelte";
import { useTestMessages } from "@/__tests__/i18n-harness";
import QuestionEditor, {
  type OptionDraft,
  type QuestionDraft,
} from "@/components/QuestionEditor.svelte";

useTestMessages("en", {
  form: {
    question: {
      promptPlaceholder: "Question",
      kind: {
        rating: "Rating",
        number: "Number",
        text: "Long text",
        short_text: "Short text",
        multiple_choice: "Single choice",
        multiple_answer: "Multiple choice",
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
  quiz: { question: { pickCorrect: "Pick the right answer", markCorrect: "Mark correct" } },
  compass: { question: { pickOptionPoles: "Pick a side", pickPole: "Side" } },
  common: { remove: "Remove", clear: "Clear", noResults: "No results" },
});

afterEach(cleanup);

const settle = () => new Promise((r) => setTimeout(r, 0));

function option(id: string | null, label: string, extra: Partial<OptionDraft> = {}): OptionDraft {
  return { id, label, pole: null, is_correct: false, ...extra };
}

function draft(options: OptionDraft[], over: Partial<QuestionDraft> = {}): QuestionDraft {
  return {
    id: "q1",
    kind: "multiple_choice",
    prompt: "Which one?",
    required: true,
    options,
    low_label: null,
    high_label: null,
    min_value: null,
    max_value: null,
    step: null,
    points: 0,
    correct_int: null,
    correct_text: null,
    tolerance: null,
    pole: null,
    ...over,
  };
}

function editor(
  initial: QuestionDraft,
  props: Partial<ComponentProps<typeof QuestionEditor>> = {},
) {
  const model = bindable<QuestionDraft, ComponentProps<typeof QuestionEditor>>("value", initial, {
    canMoveUp: true,
    canMoveDown: true,
    ondelete: () => {},
    onmoveUp: () => {},
    onmoveDown: () => {},
    ...props,
  });
  const { container } = render(QuestionEditor, { props: model.props });
  return {
    get: () => model.current,
    /** Type a label into the add box and press its button. */
    async addOption(label: string) {
      const box = container.querySelector(".add-row input") as HTMLInputElement;
      await fireEvent.input(box, { target: { value: label } });
      (container.querySelector(".add-row button") as HTMLElement).click();
      await settle();
    },
    /** The trash button on the row showing this label. Selected as the
     *  row's own child: a quiz row also holds a tick button, inside the
     *  label, and picking the first button in the row hits that one. */
    async removeOption(label: string) {
      const row = [...container.querySelectorAll(".list-row")].find((r) =>
        r.querySelector(".list-row-label")?.textContent?.includes(label),
      ) as HTMLElement;
      (row.querySelector(":scope > button") as HTMLElement).click();
      await settle();
    },
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
    /** The tick beside a quiz option. */
    async markCorrect(label: string) {
      const row = [...container.querySelectorAll(".list-row")].find((r) =>
        r.textContent?.includes(label),
      ) as HTMLElement;
      (row.querySelector(".correct-mark") as HTMLElement).click();
      await settle();
    },
  };
}

const ids = (q: QuestionDraft) => q.options.map((o) => o.id);
const labels = (q: QuestionDraft) => q.options.map((o) => o.label);

describe("an option keeps its id", () => {
  it("through adding another one", async () => {
    const q = editor(draft([option("opt-a", "A"), option("opt-b", "B")]));
    await q.addOption("C");
    expect(labels(q.get())).toEqual(["A", "B", "C"]);
    // The two that existed still point at their rows; only the new one
    // has no id, which is what tells the server to mint it.
    expect(ids(q.get())).toEqual(["opt-a", "opt-b", null]);
  });

  it("through removing a different one", async () => {
    const q = editor(draft([option("opt-a", "A"), option("opt-b", "B"), option("opt-c", "C")]));
    await q.removeOption("B");
    expect(labels(q.get())).toEqual(["A", "C"]);
    expect(ids(q.get())).toEqual(["opt-a", "opt-c"]);
  });

  it("through being marked as the right answer", async () => {
    const q = editor(draft([option("opt-a", "A"), option("opt-b", "B")], { points: 5 }), {
      scored: true,
    });
    await q.markCorrect("B");
    expect(ids(q.get())).toEqual(["opt-a", "opt-b"]);
    expect(q.get().options.map((o) => o.is_correct)).toEqual([false, true]);
  });

  it("through a kind change between the two choice kinds", async () => {
    // Both kinds ask the same question of the same choices, so the rows
    // survive and so do the answers to them. Only a change to a kind
    // that has no options at all clears them, and the server treats
    // that as a different question entirely.
    const q = editor(
      draft([option("opt-a", "A", { is_correct: true }), option("opt-b", "B")], { points: 5 }),
      { scored: true },
    );
    await q.setKind("Multiple choice");
    expect(q.get().kind).toBe("multiple_answer");
    expect(ids(q.get())).toEqual(["opt-a", "opt-b"]);
    // The key does not survive: it belonged to the shape the question
    // had before, so it is picked again rather than carried over.
    expect(q.get().options.some((o) => o.is_correct)).toBe(false);
  });
});

describe("the answer key lives on the option", () => {
  it("single choice moves the tick rather than adding one", async () => {
    const q = editor(
      draft([option("opt-a", "A", { is_correct: true }), option("opt-b", "B")], { points: 5 }),
      { scored: true },
    );
    await q.markCorrect("B");
    // Exactly one right answer, and it moved: a single-choice question
    // with two keys is one the server refuses.
    expect(q.get().options.map((o) => o.is_correct)).toEqual([false, true]);
  });

  it("multi choice toggles each one on its own", async () => {
    const q = editor(
      draft([option("opt-a", "A"), option("opt-b", "B"), option("opt-c", "C")], {
        kind: "multiple_answer",
        points: 6,
      }),
      { scored: true },
    );
    await q.markCorrect("A");
    await q.markCorrect("C");
    expect(q.get().options.map((o) => o.is_correct)).toEqual([true, false, true]);

    await q.markCorrect("A");
    expect(q.get().options.map((o) => o.is_correct)).toEqual([false, false, true]);
  });

  it("a removed option takes its own key with it", async () => {
    // The key used to be a separate list of labels, so removing an
    // option left a key naming something that no longer existed and the
    // save was refused for a reason nobody could see.
    const q = editor(
      draft([option("opt-a", "A", { is_correct: true }), option("opt-b", "B"), option("opt-c", "C")], {
        points: 5,
      }),
      { scored: true },
    );
    await q.removeOption("A");
    expect(labels(q.get())).toEqual(["B", "C"]);
    expect(q.get().options.some((o) => o.is_correct)).toBe(false);
  });
});

describe("a kompas direction lives on the option", () => {
  it("a removed option takes its own side with it", async () => {
    // Directions used to be a list matched to the options by position,
    // so removing one shifted every later option onto somebody else's
    // side, silently changing what those answers meant.
    const q = editor(
      draft([
        option("opt-a", "A", { pole: "x_low" }),
        option("opt-b", "B", { pole: "x_high" }),
        option("opt-c", "C", { pole: "y_low" }),
      ]),
      { pointed: true, poleOptions: [] },
    );
    await q.removeOption("A");
    expect(q.get().options.map((o) => [o.label, o.pole])).toEqual([
      ["B", "x_high"],
      ["C", "y_low"],
    ]);
  });

  it("a new option starts without one", async () => {
    const q = editor(draft([option("opt-a", "A", { pole: "x_low" })]), {
      pointed: true,
      poleOptions: [],
    });
    await q.addOption("B");
    // Refused by name on save until the organiser picks a side, which is
    // better than defaulting it to one and quietly placing people.
    expect(q.get().options.map((o) => o.pole)).toEqual(["x_low", null]);
  });
});

describe("adding an option", () => {
  it("refuses a duplicate label", async () => {
    const q = editor(draft([option("opt-a", "A")]));
    await q.addOption("A");
    expect(labels(q.get())).toEqual(["A"]);
  });

  it("ignores an empty one", async () => {
    const q = editor(draft([option("opt-a", "A")]));
    await q.addOption("   ");
    expect(labels(q.get())).toEqual(["A"]);
  });
});
