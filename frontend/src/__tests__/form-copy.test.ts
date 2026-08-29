/**
 * The copy the four shared organiser pages resolve, enumerated.
 *
 * `FormListPage`, `ArchivedFormsPage`, `FormEditPage` and
 * `FormDetailsPage` are registered once per product in the forms table
 * and look their strings up through `useFormText().L`, which falls back
 * to the questionnaire's word when a product has not defined its own.
 * The fallback is silent, so a missing key reads as the wrong product's
 * language rather than as a bug: eight of them shipped that way on the
 * quiz (`e9dd24b`), and the archived page is still resolving keys under
 * a `quiz.archived.*` block that never defined them.
 *
 * So the keys are enumerated here rather than spotted on the page.
 * Every key the four pages resolve is either SHARED (about none of the
 * products, and no product may override it) or PRODUCT (every product
 * must define it, in both languages). A key that is neither fails the
 * test, which is what forces the classification when somebody adds one.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";

import en from "@/locales/en.json";
import nl from "@/locales/nl.json";

/** The pages that share their copy across the products. */
const PAGES = ["FormListPage.vue", "ArchivedFormsPage.vue", "FormEditPage.vue", "FormDetailsPage.vue"];

/** Read a page's source once, for the assertions that are about the
 *  page rather than about a key. */
function pageSource(page: string): string {
  return readFileSync(resolve(process.cwd(), "src/pages", page), "utf8");
}

/** The products, mirroring ``FORM_RESOURCES`` in ``useForms``.
 *  ``forms`` is the base vocabulary, so it is the fallback rather than
 *  an override. */
const OVERRIDING = ["quizzes", "compasses"] as const;

/** Keys about none of the products: the page furniture, the CSV
 *  headers, the chapter and language fields, the two validation
 *  messages every product's questions get. A product overriding one of
 *  these is a key that is not shared, so the test says so. */
const SHARED = [
  "archived.delete",
  "archived.restore",
  "details.anonymous",
  "details.csvFail",
  "details.csvName",
  "details.csvSubmittedAt",
  "details.exportCsv",
  "details.questionsHeading",
  "edit.addQuestion",
  "edit.fillChapter",
  "edit.localeExplainer",
  "edit.localeHeading",
  "edit.namePlaceholder",
  "edit.needsAQuestion",
  "edit.questionNeedsOptions",
  "edit.questionNeedsPrompt",
  "edit.questionsHeading",
  "edit.save",
  "list.archive",
  "list.details",
  "list.searchPlaceholder",
];

/** Keys that name the product, in its own words. Every product defines
 *  every one of these; none of them may fall through. */
const PRODUCT = [
  "archived.deleteConfirmBody",
  "archived.deleteConfirmTitle",
  "archived.deleteFail",
  "archived.deleteOk",
  "archived.empty",
  "archived.intro",
  "archived.loadFailed",
  "archived.noMatches",
  "archived.restoreFail",
  "archived.restored",
  "archived.searchPlaceholder",
  "archived.title",
  "details.backToList",
  "details.loadFailed",
  "details.noResponsesYet",
  "details.noTextResponses",
  "details.notFoundBody",
  "details.notFoundTitle",
  "details.qResponses",
  "details.responses",
  "details.responsesTitle",
  "edit.backToList",
  "edit.create",
  "edit.editTitle",
  "edit.fillName",
  "edit.loadFailed",
  "edit.newTitle",
  "edit.noQuestionsYet",
  "edit.notFoundBody",
  "edit.notFoundTitle",
  "edit.questionsExplainer",
  "edit.saveFailed",
  "list.archiveConfirmBody",
  "list.archiveConfirmTitle",
  "list.archiveFail",
  "list.archived",
  "list.empty",
  "list.intro",
  "list.loadFailed",
  "list.newForm",
  "list.noMatches",
  "list.submissionCount",
  "list.title",
];

/** ``L("some.key")`` on the page, plus the eight ``useArchivedList``
 *  resolves under the ``<resource>.archived`` prefix it is handed. */
const ARCHIVED_LIST_KEYS = [
  "archived.delete",
  "archived.deleteConfirmBody",
  "archived.deleteConfirmTitle",
  "archived.deleteFail",
  "archived.deleteOk",
  "archived.loadFailed",
  "archived.restoreFail",
  "archived.restored",
];

function keysUsed(): Set<string> {
  const found = new Set<string>(ARCHIVED_LIST_KEYS);
  for (const page of PAGES) {
    // Vitest runs with the frontend package root as cwd.
    const src = readFileSync(resolve(process.cwd(), "src/pages", page), "utf8");
    for (const m of src.matchAll(/L\(\s*['"]([\w.]+)['"]/g)) found.add(m[1]);
  }
  return found;
}

/** Every source file under ``src``, so a key can be looked for
 *  wherever somebody wrote one. */
function sourceFiles(dir: string, found: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    if (entry === "node_modules" || entry === "__tests__") continue;
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) sourceFiles(path, found);
    else if (/\.(vue|ts)$/.test(entry)) found.push(path);
  }
  return found;
}

/** Literal keys under the three product namespaces, wherever they are
 *  written: a component resolving one of these is as capable of
 *  shipping a ``[compasses.question.pickOptionPoles]`` onto the page as
 *  a page is, and one of them did. Interpolated keys
 *  (``compass.edit.axis${axis}``) are skipped: the literal half of
 *  them is not a key. So is ``form.css``, which is a stylesheet. */
function literalKeys(): string[] {
  const keys = new Set<string>();
  for (const file of sourceFiles(resolve(process.cwd(), "src"))) {
    const src = readFileSync(file, "utf8");
    for (const m of src.matchAll(/["'`]((?:forms|quizzes|compasses)\.[\w.]+)["'`]/g)) {
      if (!/\.(css|ts|vue|json)$/.test(m[1])) keys.add(m[1]);
    }
  }
  return [...keys].sort();
}

function lookup(messages: unknown, path: string): unknown {
  let cur: unknown = messages;
  for (const part of path.split(".")) {
    if (typeof cur !== "object" || cur === null || !(part in cur)) return undefined;
    cur = (cur as Record<string, unknown>)[part];
  }
  return cur;
}

const LOCALES: Record<string, unknown> = { nl, en };

describe("shared organiser-page copy", () => {
  it("classifies every key the four pages resolve", () => {
    const classified = new Set([...SHARED, ...PRODUCT]);
    const unclassified = [...keysUsed()].filter((k) => !classified.has(k)).sort();
    // A new key on one of the four pages lands here until somebody
    // decides whether it is about the product or about neither.
    expect(unclassified).toEqual([]);
  });

  it("has no classified key that no page resolves", () => {
    const used = keysUsed();
    const stale = [...SHARED, ...PRODUCT].filter((k) => !used.has(k)).sort();
    expect(stale).toEqual([]);
  });

  it("keys the localStorage draft by product, not just by form id", () => {
    // The four pages are three pages. A draft key that names only the
    // form id put ``/form/new``, ``/quiz/new`` and
    // ``/compass/new`` on one key, so a half-typed questionnaire came
    // back on the kompas page carrying a question kind a kompas cannot
    // ask. Pinned here because the next product would reintroduce it
    // silently.
    const src = pageSource("FormEditPage.vue");
    const key = src.match(/const draftKey = computed\(\(\) => (.+)\);/);
    expect(key, "draftKey moved").not.toBeNull();
    expect(key![1]).toContain("api.resource");
  });

  for (const locale of Object.keys(LOCALES)) {
    it(`resolves every product key written anywhere in the tree (${locale})`, () => {
      const messages = LOCALES[locale];
      // A prefix a helper appends to (``form.archived`` in
      // ``useArchivedList``) resolves to the block rather than to a
      // string, and is just as present.
      const missing = literalKeys().filter((k) => lookup(messages, k) === undefined);
      // A key with no string behind it renders as ``[the.key]`` on the
      // page. There is no fallback that saves it, so the only place to
      // catch it is here.
      expect(missing).toEqual([]);
    });


    it(`defines every shared key on forms, and nowhere else (${locale})`, () => {
      const messages = LOCALES[locale];
      const missing = SHARED.filter((k) => typeof lookup(messages, `form.${k}`) !== "string");
      expect(missing).toEqual([]);
      // An override of a shared key means it is not shared: either the
      // product wants its own word (move it to PRODUCT) or the override
      // is a copy of the same string (delete it).
      const overridden = OVERRIDING.flatMap((r) =>
        SHARED.filter((k) => lookup(messages, `${r}.${k}`) !== undefined).map((k) => `${r}.${k}`),
      );
      expect(overridden).toEqual([]);
    });

    it(`defines every product key for every product (${locale})`, () => {
      const messages = LOCALES[locale];
      const missing = ["forms", ...OVERRIDING].flatMap((r) =>
        PRODUCT.filter((k) => typeof lookup(messages, `${r}.${k}`) !== "string").map((k) => `${r}.${k}`),
      );
      expect(missing).toEqual([]);
    });
  }
});
