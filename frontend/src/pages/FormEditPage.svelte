<script lang="ts">
import { untrack } from "svelte";

import AppButton from "@/components/AppButton.svelte";
import AppCard from "@/components/AppCard.svelte";
import AppHeader from "@/components/AppHeader.svelte";
import AppInput from "@/components/AppInput.svelte";
import AppToggle from "@/components/AppToggle.svelte";
import CompassAxesEditor from "@/components/CompassAxesEditor.svelte";
import FormPageShell from "@/components/FormPageShell.svelte";
import ImageField from "@/components/ImageField.svelte";
import QuestionEditor, {
  type PoleOption,
  type QuestionDraft,
} from "@/components/QuestionEditor.svelte";
import RichTextField from "@/components/RichTextField.svelte";
import SelectField from "@/components/SelectField.svelte";
import StartAccountField from "@/components/StartAccountField.svelte";
import StartedPanel from "@/components/StartedPanel.svelte";
import RouterLink from "@/router/RouterLink.svelte";
import { bilingualField } from "@/composables/useBilingualField.svelte";
import { chaptersQuery, sortedChapters } from "@/composables/useChapters.svelte";
import { formDraft } from "@/composables/useFormDraft.svelte";
import { formText } from "@/composables/useFormText.svelte";
import {
  type FormCreate,
  type FormQuestionIn,
  type FormUpdate,
  formsApi,
} from "@/composables/useForms.svelte";
import { orderedList } from "@/composables/useOrderedList.svelte";
import { type StartKind, startMode } from "@/composables/useStartMode.svelte";
import { locale, t } from "@/i18n.svelte";
import { ApiError } from "@/api/client";
import { go, route } from "@/router/navigation.svelte";
import { useToasts } from "@/lib/toasts";
import { auth } from "@/stores/auth.svelte";
import type { CompassAxisIn, Pole } from "@/api/types";

/**
 * Making or changing a questionnaire, a quiz or a kompas.
 *
 * One page, three products (``docs/design-quizzes.md``,
 * ``docs/design-kompas.md``). The route says which, and everything
 * below reads the same, because a quiz is a questionnaire with an
 * answer key and a kompas is one with a direction per answer.
 */
const { formId }: { formId?: string } = $props();

const toasts = useToasts();
const api = formsApi();
const { L, isQuiz, isCompass } = formText();

/** The create body's wire name at the root's front door, per product. */
const START_KIND: Record<string, StartKind> = {
  form: "form",
  quiz: "quiz",
  compass: "compass",
};

const start = startMode(START_KIND[api.resource] ?? "form");
const chapters = chaptersQuery({ enabled: () => start.hasChapters });
const create = api.create();
const update = api.update();

const isEdit = $derived(Boolean(formId));
const query = api.single(
  () => formId ?? "",
  { enabled: () => Boolean(formId) },
);
const notFound = $derived(query.error instanceof ApiError && query.error.status === 404);

let chapterId = $state<string | null>(null);
const chapterOptions = $derived.by(() => {
  const mine = new Set((auth.user?.chapters ?? []).map((c) => c.id));
  return sortedChapters(chapters.data).filter((c) => mine.has(c.id));
});

let nameNl = $state("");
let nameEn = $state("");
let descNl = $state("");
let descEn = $state("");
const title = bilingualField(
  () => ({ nl: nameNl, en: nameEn }),
  (next) => {
    nameNl = next.nl;
    nameEn = next.en;
  },
);
const body = bilingualField(
  () => ({ nl: descNl, en: descEn }),
  (next) => {
    descNl = next.nl;
    descEn = next.en;
  },
);
let imageUrl = $state<string | null>(null);
let imageArtistInstagram = $state("");
let imageField = $state<ReturnType<typeof ImageField> | null>(null);
let formLocale = $state<"nl" | "en">(locale() === "en" ? "en" : "nl");

/* Only a quiz reveals the right answers, and an organiser running the
 * same quiz twice in one evening turns that off. */
let revealAnswers = $state(true);
/* Whether somebody may reopen their own link and change what they
 * said. A quiz never offers it, so the switch is not drawn there. */
let answersEditable = $state(true);
let nameRequired = $state(false);
/* The switches sit behind one fold, the same one every other edit page
 * ends with, and it starts closed every time. */
let advancedOpen = $state(false);

/* A kompas's two axes and their four sides. Empty until the organiser
 * names them, which the save refuses by name the moment there is a
 * question to point at one (``docs/design-kompas.md`` 4.4). */
let axes = $state<CompassAxisIn[]>([]);
const questionList = orderedList<QuestionDraft>();
let submitting = $state(false);

// Armed by a 409 and spent on the next Save. An edit that destroys
// answers is refused once with a count; saying Save again is the
// organiser confirming they meant it.
let confirmDestructive = $state(false);
/** The four sides, labelled with what the organiser called them. Read
 *  live off the axes block above, so renaming an axis renames every
 *  select on the page. Before the axes are named they read "As X, kant
 *  1", which is a placeholder the save then refuses. */
const poleOptions = $derived<PoleOption[]>(
  (["x", "y"] as const).flatMap((axis) => {
    const row = axes.find((a) => a.axis === axis);
    const axisName = row?.name.trim() || t(`compass.edit.axis${axis.toUpperCase()}`);
    return (["low", "high"] as const).map((side) => {
      const own = (side === "low" ? row?.low_name : row?.high_name)?.trim();
      // Before a side is named, the select says where it lands, which
      // is what the axes block calls it too.
      const fallback = t(
        `compass.edit.side${side === "low" ? "Low" : "High"}${axis.toUpperCase()}`,
      );
      return { value: `${axis}_${side}` as Pole, label: `${axisName}: ${own || fallback}` };
    });
  }),
);

// --- The draft -------------------------------------------------------
//
// The product is in the key because this page is three pages. Without
// it ``/form/new``, ``/quiz/new`` and ``/compass/new`` all wrote to
// ``form-edit-draft:new``, so a half-typed questionnaire came back on
// the kompas page, with a number question in it that a kompas cannot
// ask, and the kind select rendered blank over a number box.
interface FormEditDraft {
  nameNl: string;
  nameEn: string;
  descNl: string;
  descEn: string;
  imageArtistInstagram: string;
  chapterId: string | null;
  formLocale: "nl" | "en";
  questions: QuestionDraft[];
  axes: CompassAxisIn[];
}

function snapshot(): FormEditDraft {
  return {
    nameNl,
    nameEn,
    descNl,
    descEn,
    imageArtistInstagram,
    chapterId,
    formLocale,
    questions: questionList.items,
    axes,
  };
}

function applyDraft(d: FormEditDraft): void {
  nameNl = d.nameNl ?? "";
  nameEn = d.nameEn ?? "";
  descNl = d.descNl ?? "";
  descEn = d.descEn ?? "";
  imageArtistInstagram = d.imageArtistInstagram ?? "";
  chapterId = d.chapterId ?? null;
  formLocale = d.formLocale ?? "nl";
  questionList.items = (d.questions ?? []).map((q) => ({
    ...q,
    // Each option keeps the id it came back with. That id is the only
    // thing tying an answer to the choice it named, so a draft that
    // dropped it would delete every answer on save
    // (``docs/design-question-edits.md``).
    options: (q.options ?? []).map((o) => ({
      id: o.id,
      label: o.label,
      pole: (o.pole as Pole | null) ?? null,
      is_correct: o.is_correct ?? false,
    })),
  }));
  axes = (d.axes ?? []).map((a) => ({ ...a }));
}

const draft = formDraft<FormEditDraft>({
  key: () => `${api.resource}-edit-draft:${formId ?? "new"}`,
  snapshot,
  track: snapshot,
});

// Restored at most once. The draft should override what the server
// sent, and never clobber an edit made after that.
let draftRestored = false;
function restoreDraftOnce(): void {
  if (draftRestored) return;
  draftRestored = true;
  const saved = draft.load();
  if (saved) applyDraft(saved);
}

// The form arrives, its values go in, and anything half-typed goes on
// top: a draft is newer than what was saved.
let seeded: unknown = undefined;
$effect(() => {
  const existing = query.data;
  if (!existing || existing === seeded) return;
  seeded = existing;
  nameNl = existing.name_nl ?? "";
  nameEn = existing.name_en ?? "";
  descNl = existing.description_nl ?? "";
  descEn = existing.description_en ?? "";
  imageUrl = existing.image_url ?? null;
  imageArtistInstagram = existing.image_artist_instagram ?? "";
  formLocale = existing.locale;
  chapterId = existing.chapter_id;
  questionList.items = (existing.questions ?? []).map((q): QuestionDraft => ({
    id: q.id,
    kind: q.kind as QuestionDraft["kind"],
    prompt: q.prompt,
    required: q.required,
    // Each option keeps the id the server sent. That id is the only
    // thing tying an answer to the choice it named, so a draft that
    // dropped it would delete every answer on save
    // (``docs/design-question-edits.md``).
    options: (q.options ?? []).map((o) => ({
      id: o.id,
      label: o.label,
      pole: (o.pole as Pole | null) ?? null,
      is_correct: o.is_correct ?? false,
    })),
    low_label: q.low_label ?? null,
    high_label: q.high_label ?? null,
    min_value: q.min_value ?? null,
    max_value: q.max_value ?? null,
    step: q.step ?? null,
    points: q.points ?? 0,
    correct_int: q.correct_int ?? null,
    correct_text: q.correct_text ?? null,
    tolerance: q.tolerance ?? null,
    pole: (q.pole as Pole | null) ?? null,
  }));
  revealAnswers = existing.reveal_answers ?? true;
  answersEditable = existing.answers_editable ?? true;
  nameRequired = existing.name_required ?? false;
  axes = (existing.axes ?? []).map((a) => ({ ...a, axis: a.axis as "x" | "y" }));
  restoreDraftOnce();
});

// A new form: the chapter is the one the organiser came from, or the
// only one they are in. Read once, at mount.
untrack(() => {
  if (isEdit) return;
  const fromQuery = route.query.get("chapter");
  const mine = new Set((auth.user?.chapters ?? []).map((c) => c.id));
  if (fromQuery && mine.has(fromQuery)) chapterId = fromQuery;
  else if (auth.user?.chapters?.length === 1) chapterId = auth.user.chapters[0].id;
  restoreDraftOnce();
});

// --- What the server would refuse, said here first --------------------
//
// A 400 from the API is accurate and English, and "saving failed" is
// neither: an organiser who left one answer unmarked should be told
// which one.

/** An axis with no name, or a side with none. Only a kompas has any,
 *  and only once there is something to name them for: a draft with
 *  neither questions nor axes saves, which is what an organiser coming
 *  back to it expects (``docs/design-kompas.md`` 4.4). */
function firstAxisNamingProblem(): string | null {
  if (!isCompass) return null;
  if (!questionList.items.length && !axes.length) return null;
  for (const axis of ["x", "y"] as const) {
    const row = axes.find((a) => a.axis === axis);
    const name = row?.name.trim() ?? "";
    if (!name) return t("compass.edit.fillAxisName", { axis: axis.toUpperCase() });
    if (!row?.low_name.trim() || !row?.high_name.trim()) {
      return t("compass.edit.fillPoleNames", { name });
    }
  }
  return null;
}

/**
 * An axis no question ever points at.
 *
 * Any of the four sides may go unused, which is the organiser's choice
 * and sometimes the honest one; an axis nothing touches is a
 * half-written kompas.
 *
 * Checked after the per-question problems and never before them: a
 * question whose direction is still empty makes its axis look unused
 * too, and being told "nobody can move on Economie" when the real
 * answer is "question 1 has no side yet" sends the organiser to the
 * wrong end of the page. The same order the server runs them in.
 */
function axisCoverageProblem(): string | null {
  if (!isCompass || !questionList.items.length) return null;
  const used = new Set(
    questionList.items
      .flatMap((q) => (q.kind === "rating" ? [q.pole] : q.options.map((o) => o.pole)))
      .filter(Boolean)
      .map((pole) => (pole as string).split("_")[0]),
  );
  for (const axis of ["x", "y"] as const) {
    if (used.has(axis)) continue;
    const name = axes.find((a) => a.axis === axis)?.name.trim() ?? axis.toUpperCase();
    return t("compass.edit.axisUnused", { name });
  }
  return null;
}

/** The first thing wrong with the question list, in words. The same
 *  rules the three server-side validators run; the server is still the
 *  authority, this is so the answer arrives in Dutch and names the
 *  question. */
function firstQuestionProblem(): string | null {
  // Nothing to answer is a public page whose only button does nothing.
  if (questionList.items.length === 0) return L("edit.needsAQuestion");
  for (const [index, q] of questionList.items.entries()) {
    const n = index + 1;
    if (!q.prompt.trim()) return L("edit.questionNeedsPrompt", { n });
    const choice = q.kind === "single_choice" || q.kind === "multi_choice";
    if (choice && q.options.length < 2) return L("edit.questionNeedsOptions", { n });
    if (isCompass) {
      if (q.kind === "rating" && !q.pole) return t("compass.edit.questionNeedsPole", { n });
      // Each option carries its own side, so there is no second list to
      // fall out of step with this one.
      if (q.kind === "single_choice" && q.options.some((o) => !o.pole)) {
        return t("compass.edit.questionNeedsOptionPoles", { n });
      }
      continue;
    }
    if (!isQuiz || q.points <= 0) continue;
    if (choice && !q.options.some((o) => o.is_correct)) {
      return t("quiz.edit.questionNeedsKey", { n });
    }
    if (q.kind === "single_choice" && q.options.filter((o) => o.is_correct).length !== 1) {
      return t("quiz.edit.questionNeedsOneKey", { n });
    }
    if ((q.kind === "number" || q.kind === "rating") && q.correct_int === null) {
      return t("quiz.edit.questionNeedsKey", { n });
    }
  }
  return null;
}

function addQuestion(): void {
  questionList.add({
    id: null,
    kind: "rating",
    prompt: "",
    required: true,
    options: [],
    low_label: null,
    high_label: null,
    min_value: null,
    max_value: null,
    step: null,
    // A new quiz question is worth one point; a questionnaire's is
    // worth nothing and the server drops it either way.
    points: isQuiz ? 1 : 0,
    correct_int: null,
    correct_text: null,
    tolerance: null,
    pole: null,
  });
}

function cancel(): void {
  draft.clear();
  if (start.cancel()) return;
  void go(isEdit && formId ? `/${api.resource}/${formId}/details` : `/${api.resource}`);
}

async function submit(): Promise<void> {
  // In the server's own order: an unnamed axis first, because nothing
  // renders without the words; then each question, which names itself;
  // then the axis nothing points at, which is only a real problem once
  // every question is complete.
  const problem = firstAxisNamingProblem() ?? firstQuestionProblem() ?? axisCoverageProblem();
  if (problem) {
    toasts.warn(problem);
    return;
  }
  // The title is required in the form's own language.
  const primaryName = (formLocale === "en" ? nameEn : nameNl).trim();
  if (!primaryName) {
    toasts.warn(L("edit.fillName"));
    return;
  }
  if (start.hasChapters && !chapterId) {
    toasts.warn(L("edit.fillChapter"));
    return;
  }
  if (start.active && !start.validate()) return;

  submitting = true;
  try {
    const payload: FormCreate | FormUpdate = {
      chapter_id: start.chapterFor(chapterId),
      name_nl: nameNl.trim() || null,
      name_en: nameEn.trim() || null,
      description_nl: descNl.trim() || null,
      description_en: descEn.trim() || null,
      image_artist_instagram: imageArtistInstagram.trim() || null,
      locale: formLocale,
      reveal_answers: revealAnswers,
      answers_editable: answersEditable,
      name_required: nameRequired,
      questions: questionList.items.map(
        (q): FormQuestionIn => ({
          id: q.id,
          kind: q.kind,
          prompt: q.prompt,
          required: q.required,
          options: q.options.map((o) => ({
            id: o.id,
            label: o.label,
            pole: o.pole,
            is_correct: o.is_correct,
          })),
          low_label: q.low_label,
          high_label: q.high_label,
          min_value: q.min_value,
          max_value: q.max_value,
          step: q.step,
          points: q.points,
          correct_int: q.correct_int,
          correct_text: q.correct_text,
          tolerance: q.tolerance,
          pole: q.pole,
        }),
      ),
      axes: isCompass ? axes : [],
      // Set on the second attempt: the first is refused with a 409 and
      // a count, which is shown as the error above the form
      // (``docs/design-question-edits.md``).
      confirm_destructive: confirmDestructive,
    };

    if (start.active) {
      // No session: the public link in the answer is the whole result,
      // and there is no details page to land on. A refusal has already
      // been explained, and the draft stays so it can be tried again.
      if (await start.submit(payload)) draft.clear();
      return;
    }

    const result =
      isEdit && formId ? await update.run({ id: formId, payload }) : await create.run(payload);
    // An image held while the row did not exist yet goes up now.
    await imageField?.flushPendingUpload(result.id);
    draft.clear();
    void go(`/${api.resource}/${result.id}/details`);
  } catch (err) {
    // 409 is the one refusal the organiser can answer: the save would
    // delete answers people gave, and the server says how many. Showing
    // its words and arming the flag turns the next Save into the
    // confirmation (``docs/design-question-edits.md``).
    if (err instanceof ApiError && err.status === 409) {
      confirmDestructive = true;
      toasts.error(err.message);
    } else {
      toasts.error(L("edit.saveFailed"));
    }
  } finally {
    submitting = false;
  }
}
</script>

<!-- The two error states render with the bare header rather than the
     form shell: there is no form to save, and a Save button under one
     would be a lie. -->
{#if notFound}
  <AppHeader />
  <div class="container-wide stack">
    <AppCard>
      <h2>{L("edit.notFoundTitle")}</h2>
      <p class="muted">{L("edit.notFoundBody")}</p>
      <RouterLink to={`/${api.resource}`} class="back-link">{L("edit.backToList")}</RouterLink>
    </AppCard>
  </div>
{:else if query.error}
  <AppHeader />
  <div class="container-wide stack">
    <AppCard>
      <p>{L("edit.loadFailed")}</p>
    </AppCard>
  </div>
{:else if start.started}
  <StartedPanel started={start.started} email={start.email} />
{:else}
  <FormPageShell
    title={isEdit ? L("edit.editTitle") : L("edit.newTitle")}
    submitLabel={isEdit ? L("edit.save") : L("edit.create")}
    {submitting}
    onsubmit={submit}
    oncancel={cancel}
  >
    <section class="form-section">
      {#if start.active}<StartAccountField bind:value={start.email} />{/if}
      <AppInput
        bind:value={title.value}
        placeholder={title.fallback || L("edit.namePlaceholder")}
        fluid
      />
      <RichTextField
        bind:value={body.value}
        placeholder={t("form.edit.descriptionPlaceholder")}
        fallbackHtml={body.fallback || null}
      />
      {#if start.hasChapters}
        <SelectField
          bind:value={chapterId}
          options={chapterOptions}
          optionLabel="name"
          optionValue="id"
          placeholder={t("form.edit.chapterPlaceholder")}
          disabled={chapterOptions.length === 1 && chapterId !== null}
          fluid
        />
      {/if}
    </section>

    <!-- Uploading writes to the row it belongs to, which takes a
         session the visitor does not have yet. -->
    {#if !start.active}
      <ImageField
        bind:this={imageField}
        resource="forms"
        entityId={formId ?? null}
        bind:imageUrl
        bind:artist={imageArtistInstagram}
      />
    {/if}

    <!-- Above the questions, because every question points at one of
         these: the words chosen here are the words every direction
         select below then offers. -->
    {#if isCompass}
      <section class="form-section">
        <h2 class="section-heading">{t("compass.edit.axesHeading")}</h2>
        <!-- No explainer: the placeholders carry what to type and the
             example to type it like, and the arrows say where each side
             lands. A paragraph would repeat the boxes under it. -->
        <CompassAxesEditor bind:value={axes} />
      </section>
    {/if}

    <section class="form-section">
      <h2 class="section-heading">{L("edit.questionsHeading")}</h2>
      <p class="muted section-explainer">{L("edit.questionsExplainer")}</p>

      {#if questionList.items.length === 0}
        <div class="empty muted">{L("edit.noQuestionsYet")}</div>
      {/if}

      <div class="questions-stack">
        {#each questionList.items as q, idx (q.id ?? `new-${idx}`)}
          <QuestionEditor
            bind:value={questionList.items[idx]}
            scored={isQuiz}
            pointed={isCompass}
            {poleOptions}
            canMoveUp={idx > 0}
            canMoveDown={idx < questionList.items.length - 1}
            ondelete={() => questionList.removeAt(idx)}
            onmoveUp={() => questionList.move(idx, -1)}
            onmoveDown={() => questionList.move(idx, 1)}
          />
        {/each}
      </div>

      <AppButton
        type="button"
        label={L("edit.addQuestion")}
        icon="plus"
        severity="secondary"
        onclick={addQuestion}
      />
    </section>

    <!-- Every switch, folded away: the thing itself above it, the page
         language below. One fold on all six products. -->
    <details
      class="advanced"
      open={advancedOpen}
      ontoggle={(e) => (advancedOpen = (e.target as HTMLDetailsElement).open)}
    >
      <summary>{advancedOpen ? t("common.advancedHide") : t("common.advancedShow")}</summary>

      <!-- Off by default: a name real or not is what the contract
           offers, so an empty box is an answer. On when the answers are
           only useful attached to somebody. -->
      <section class="form-section">
        <label class="toggle-row" for="nameRequiredToggle">
          <AppToggle bind:checked={nameRequired} inputId="nameRequiredToggle" />
          <h2 class="section-heading">{t("common.nameRequired")}</h2>
        </label>
        <p class="muted section-explainer">{t("common.nameRequiredExplainer")}</p>
      </section>

      <!-- What happens after the questions are answered. A quiz has no
           edit at all, so it gets the reveal switch instead. -->
      {#if !isQuiz}
        <section class="form-section">
          <label class="toggle-row" for="editableToggle">
            <AppToggle bind:checked={answersEditable} inputId="editableToggle" />
            <h2 class="section-heading">{t("form.edit.editableHeading")}</h2>
          </label>
          <p class="muted section-explainer">{t("form.edit.editableExplainer")}</p>
        </section>
      {:else}
        <section class="form-section">
          <label class="toggle-row" for="revealToggle">
            <AppToggle bind:checked={revealAnswers} inputId="revealToggle" />
            <h2 class="section-heading">{t("quiz.edit.revealHeading")}</h2>
          </label>
          <p class="muted section-explainer">{t("quiz.edit.revealExplainer")}</p>
        </section>
      {/if}
    </details>

    <section class="form-section">
      <h2 class="section-heading">{L("edit.localeHeading")}</h2>
      <p class="muted section-explainer">{L("edit.localeExplainer")}</p>
      <SelectField
        bind:value={formLocale}
        options={[
          { value: "nl", label: t("form.edit.localeNl") },
          { value: "en", label: t("form.edit.localeEn") },
        ]}
        optionLabel="label"
        optionValue="value"
        fluid
      />
    </section>
  </FormPageShell>
{/if}

<style>
/* The shared form chrome lives in ``src/assets/forms.css``. */
.questions-stack {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
</style>
