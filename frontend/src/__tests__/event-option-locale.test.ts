/**
 * Switching an event's language rewords its seeded sign-up options, and
 * has to do that as a rename.
 *
 * A sign-up points at the option row it named, so an option keeps its
 * answers only as long as it keeps its id. Handing the save a fresh list
 * of label-only options is asking for every one of them to be deleted
 * and re-created, which takes the answers with them: "Flyer: 12" becomes
 * an option nobody chose. The server refuses that outright now, so
 * getting it wrong turns a language switch into a save the organiser
 * cannot complete.
 *
 * ``docs/design-question-edits.md``.
 */
import { describe, expect, it } from "vitest";

import { type EventOption, translated } from "@/pages/EventFormPage.svelte";

const SAVED: EventOption[] = [
  { id: "opt-1", label: "Mond-tot-mond" },
  { id: "opt-2", label: "Social media" },
];

const SEEDED_EN: EventOption[] = [{ label: "Word of mouth" }, { label: "Social media" }];

describe("translating an event's seeded options", () => {
  it("rewords each option without letting go of its id", () => {
    expect(translated(SAVED, SEEDED_EN)).toEqual([
      { id: "opt-1", label: "Word of mouth" },
      { id: "opt-2", label: "Social media" },
    ]);
  });

  it("leaves an unsaved option without one", () => {
    // A new event has no ids yet: nothing has been answered, so there is
    // nothing to keep hold of.
    expect(translated([{ label: "Mond-tot-mond" }], [{ label: "Word of mouth" }])).toEqual([
      { id: null, label: "Word of mouth" },
    ]);
  });

  it("gives a seeded option with no counterpart no id at all", () => {
    // The two seeded lists are the same length in practice. If they ever
    // are not, the extra one is new rather than a rename of something.
    expect(translated([{ id: "opt-1", label: "A" }], [{ label: "A" }, { label: "B" }])).toEqual([
      { id: "opt-1", label: "A" },
      { id: null, label: "B" },
    ]);
  });
});
