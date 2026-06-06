/**
 * QuestionEditor's kind-switching contract: changing kind clears
 * the fields that don't belong to the new kind, so the payload
 * shipped to the backend doesn't carry stale data from a previous
 * kind. The patch helper is the load-bearing piece — verifying it
 * directly keeps the test focused on the behaviour, not the Select
 * widget's interaction model.
 */
import { mount } from "@vue/test-utils";
import PrimeVue from "primevue/config";
import { describe, expect, it } from "vitest";
import { createI18n } from "vue-i18n";

import QuestionEditor, { type QuestionDraft } from "@/components/QuestionEditor.vue";

function makeI18n() {
  return createI18n({
    legacy: false,
    locale: "en",
    messages: {
      en: {
        forms: {
          question: {
            promptPlaceholder: "Question",
            kind: {
              rating: "Rating",
              text: "Long text",
              short_text: "Short text",
              single_choice: "Single choice",
              multi_choice: "Multiple choice",
            },
            required: "Required",
            lowLabel: "Low",
            highLabel: "High",
            options: "Options",
            newOption: "Option",
            delete: "Remove",
            moveUp: "Up",
            moveDown: "Down",
          },
        },
        common: { remove: "Remove" },
      },
    },
  });
}

function mountEditor(draft: QuestionDraft) {
  let current = draft;
  const wrapper = mount(QuestionEditor, {
    props: {
      modelValue: current,
      canMoveUp: true,
      canMoveDown: true,
      "onUpdate:modelValue": (v: QuestionDraft) => {
        current = v;
        wrapper.setProps({ modelValue: v });
      },
    },
    global: { plugins: [makeI18n(), PrimeVue] },
  });
  return { wrapper, get: () => current };
}

describe("QuestionEditor kind switching", () => {
  it("clears low/high labels when switching away from rating", () => {
    const initial: QuestionDraft = {
      id: "q1",
      kind: "rating",
      prompt: "How was it?",
      required: true,
      options: [],
      low_label: "Poor",
      high_label: "Great",
    };
    const { wrapper, get } = mountEditor(initial);
    const exposed = wrapper.vm as unknown as {
      $: { setupState: { patch: (k: keyof QuestionDraft, v: unknown) => void } };
    };
    exposed.$.setupState.patch("kind", "text");
    expect(get().low_label).toBeNull();
    expect(get().high_label).toBeNull();
    expect(get().kind).toBe("text");
  });

  it("clears options when switching away from a choice kind", () => {
    const initial: QuestionDraft = {
      id: "q1",
      kind: "single_choice",
      prompt: "Pick one",
      required: true,
      options: ["A", "B", "C"],
      low_label: null,
      high_label: null,
    };
    const { wrapper, get } = mountEditor(initial);
    const exposed = wrapper.vm as unknown as {
      $: { setupState: { patch: (k: keyof QuestionDraft, v: unknown) => void } };
    };
    exposed.$.setupState.patch("kind", "rating");
    expect(get().options).toEqual([]);
    expect(get().kind).toBe("rating");
  });

  it("preserves options when switching between the two choice kinds", () => {
    const initial: QuestionDraft = {
      id: "q1",
      kind: "single_choice",
      prompt: "Pick one",
      required: false,
      options: ["A", "B"],
      low_label: null,
      high_label: null,
    };
    const { wrapper, get } = mountEditor(initial);
    const exposed = wrapper.vm as unknown as {
      $: { setupState: { patch: (k: keyof QuestionDraft, v: unknown) => void } };
    };
    exposed.$.setupState.patch("kind", "multi_choice");
    expect(get().options).toEqual(["A", "B"]);
    expect(get().kind).toBe("multi_choice");
  });
});
