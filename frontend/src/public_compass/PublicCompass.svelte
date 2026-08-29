<script lang="ts">
/**
 * Filling in a kompas: a cover, one question at a time, then the map.
 *
 * The cover carries everything about the kompas as a thing (picture,
 * title, description, disclosure) and the one question that is not part
 * of it, which is who is filling it in. That question needs a sentence
 * the other five products do not: the name is going on a chart everyone
 * else will read, and the moment to say so is above the box rather than
 * after the submit (``docs/design-kompas.md`` 5.1).
 *
 * A question page is the title and the question, nothing else. The
 * directions are not in this page: which answer moves you where arrives
 * with the result, the same seam and the same reason as the quiz's
 * answer key.
 *
 * The result is three blocks, in this order: the map, because it is
 * what the person came for; where they landed on each axis, in the
 * organiser's own words; and every question redrawn as it was asked
 * with the direction it carried, so the map has a visible reason.
 *
 * Unlike a quiz, the answers stay editable. Changing your answer after
 * seeing the map is changing your mind, not a second attempt.
 */
import CompassPlot from "@/public_shared/CompassPlot.svelte";
import EditLink from "@/public_shared/EditLink.svelte";
import { useEditLink } from "@/public_shared/useEditLink.svelte";
import Disclosure from "@/public_shared/Disclosure.svelte";
import PublicNotice from "@/public_shared/PublicNotice.svelte";
import PublicShell from "@/public_shared/PublicShell.svelte";
import PublicTopCard from "@/public_shared/PublicTopCard.svelte";
import QuestionField from "@/public_shared/QuestionField.svelte";
import RecoveredNotice from "@/public_shared/RecoveredNotice.svelte";
import SupportButtons from "@/public_shared/SupportButtons.svelte";
import { resolveText } from "@/public_shared/bilingual";
import { type Locale, chromeStrings, pickLocale } from "@/public_shared/strings";
import {
  ApiError,
  type CompassAnswerResult,
  type CompassAxis,
  type CompassResult,
  type Pole,
  type PublicCompass,
  type PublicCompassQuestion,
  type SubmitAnswer,
  fetchCompassBySlug,
  fetchCompassResult,
  postCompassAnswers,
  putCompassAnswers,
} from "./api";
import { compassStrings, decimal } from "./i18n";

const slug = window.location.pathname.replace(/^\/k\//, "").split("/")[0];
/** ``?s={token}`` reopens a finished fill-in: the map, and the answers
 *  behind the "change your answers" button. */
const resultToken = new URLSearchParams(window.location.search).get("s");
// The secret link back to this fill-in. ``confirmSaved`` records the
// token and routes the URL onto it in one step
// (``public_shared/useEditLink``).
// Held whole, not spread: ``editUrl`` is a getter.
const link = useEditLink("k", () => slug);

let kompas = $state<PublicCompass | null>(null);
let result = $state<CompassResult | null>(null);
/** ``ready`` is the cover; ``walking`` is the questions. */
let status = $state<"loading" | "ready" | "walking" | "unavailable" | "load-failed" | "done">("loading");
let submitting = $state(false);
let stepError = $state<string | null>(null);
/** Set once a token is in hand: the next save is a PUT rather than a
 *  POST, whether it came from the URL or from the first submit. */
let token = $state<string | null>(resultToken);

let locale = $state<Locale>("nl");
const c = $derived(chromeStrings(locale));
const k = $derived(compassStrings(locale));

const title = $derived(kompas ? resolveText(kompas.name_nl, kompas.name_en, locale) : null);
const description = $derived(
  kompas ? resolveText(kompas.description_nl, kompas.description_en, locale) : null,
);

let displayName = $state("");

type Answer = { answer_int?: number | null; answer_text?: string; answer_choices?: string[] };
let answers = $state<Record<string, Answer>>({});
let step = $state(0);

const questions = $derived<PublicCompassQuestion[]>(kompas?.questions ?? []);
const current = $derived<PublicCompassQuestion | null>(questions[step] ?? null);
const isLast = $derived(step >= questions.length - 1);
const byId = $derived(Object.fromEntries(questions.map((item) => [item.id, item])));

/** The axes, in the order the plot draws them. Taken from the result
 *  when there is one, because that is the copy the map was built from,
 *  and from the cover payload before that. */
const axes = $derived<CompassAxis[]>(
  result?.axes.map((row) => row.axis) ?? kompas?.axes ?? [],
);

/** Where the whole room sits on one axis, by axis name. The band the
 *  reader's own marker is drawn against: "you are here" says more next
 *  to where everyone else is. */
const room = $derived(new Map((result?.axes ?? []).map((row) => [row.axis.axis, row])));

/** The room's band as a left/width pair, or null when there is nothing
 *  to draw: nobody has filled it in, or one person has, and one person
 *  is a point rather than an interval. */
function roomBand(axis: CompassAxis): { left: string; width: string } | null {
  const row = room.get(axis.axis);
  if (!row || row.ci_low == null || row.ci_high == null || row.ci_high === row.ci_low) return null;
  return {
    left: `${((row.ci_low + 1) / 2) * 100}%`,
    width: `${((row.ci_high - row.ci_low) / 2) * 100}%`,
  };
}

/** The room's mean as a position along the same bar. */
function roomMeanLeft(axis: CompassAxis): string | null {
  const row = room.get(axis.axis);
  return row?.average == null ? null : `${((row.average + 1) / 2) * 100}%`;
}

/** Whether there is a band to explain at all. */
const anyRoomBand = $derived(axes.some((axis) => roomBand(axis) !== null));

function blankAnswers(loaded: PublicCompass): void {
  for (const item of loaded.questions) {
    if (item.kind === "rating" || item.kind === "number") answers[item.id] = { answer_int: null };
    else if (item.kind === "text" || item.kind === "short_text") answers[item.id] = { answer_text: "" };
    else answers[item.id] = { answer_choices: [] };
  }
}

/** Refill the walk from a result. The per-answer rows carry what was
 *  given, so reopening a link and pressing "change your answers" starts
 *  from the answers rather than from an empty form. */
function fillFrom(found: CompassResult): void {
  for (const line of found.answers) {
    if (line.given_int != null) answers[line.question_id] = { answer_int: line.given_int };
    else if (line.given_choices) answers[line.question_id] = { answer_choices: [...line.given_choices] };
  }
  displayName = found.display_name ?? "";
}

async function load() {
  const inlined = window.__OPKOMST_COMPASS__;
  if (inlined === null) {
    status = "unavailable";
    return;
  }
  try {
    const loaded = inlined ?? (await fetchCompassBySlug(slug));
    kompas = loaded;
    locale = pickLocale(loaded.locale);
    blankAnswers(loaded);
    if (resultToken) {
      const found = await fetchCompassResult(resultToken);
      result = found;
      // Reopened from the link: the page shows that link back, so the
      // token has to be recorded here too and not only on a save.
      link.confirmSaved(found.edit_token);
      fillFrom(found);
      status = "done";
      return;
    }
    status = "ready";
  } catch (e) {
    status = e instanceof ApiError && e.status === 410 ? "unavailable" : "load-failed";
  }
}
void load();

function isAnswered(item: PublicCompassQuestion): boolean {
  const a = answers[item.id] ?? {};
  if (item.kind === "rating") return a.answer_int != null;
  return (a.answer_choices ?? []).length > 0;
}

function back() {
  stepError = null;
  if (step > 0) step -= 1;
}

async function next() {
  const item = current;
  if (!item) return;
  // A required question gates the step rather than the submit: being
  // told at the end which of ten was missed is worse than being told
  // here. A skippable one contributes nothing and costs nothing, which
  // is what "no opinion" means on a kompas.
  if (item.required && !isAnswered(item)) {
    stepError = k.answerFirst;
    return;
  }
  stepError = null;
  if (!isLast) {
    step += 1;
    return;
  }
  await finish();
}

function payload(): SubmitAnswer[] {
  return questions.map((item) => {
    const a = answers[item.id] ?? {};
    if (item.kind === "rating") return { question_id: item.id, answer_int: a.answer_int ?? null };
    return { question_id: item.id, answer_choices: a.answer_choices ?? [] };
  });
}

async function finish() {
  if (!kompas || submitting) return;
  submitting = true;
  try {
    const body = { display_name: displayName.trim() || null, answers: payload() };
    const found = token
      ? await putCompassAnswers(token, body)
      : await postCompassAnswers(slug, body);
    result = found;
    token = found.edit_token;
    // The token in the URL, so a refresh reopens the map instead of
    // starting the kompas again.
    link.confirmSaved(found.edit_token);
    status = "done";
    step = 0;
  } catch {
    stepError = c.submitFail;
  } finally {
    submitting = false;
  }
}

// --- reading the result ----------------------------------------------

/** Where the reader landed on one axis, and how many answers said so. */
function place(axis: CompassAxis): { value: number; counted: number } {
  const found = result;
  if (!found) return { value: 0, counted: 0 };
  return axis.axis === "x"
    ? { value: found.x, counted: found.counted_x }
    : { value: found.y, counted: found.counted_y };
}

/** The sentence for one axis. A dot on the centre line has two
 *  possible reasons, and this is where the screen says which. */
function axisSentence(axis: CompassAxis): string {
  const { value, counted } = place(axis);
  if (counted === 0) return k.youSaidNothing;
  if (value === 0) return k.youAreCentre;
  return k.youAreAt(value < 0 ? axis.low_name : axis.high_name);
}

/** The marker's position along a [-1, 1] bar, as a percentage. */
function markerLeft(axis: CompassAxis): string {
  return `${((place(axis).value + 1) / 2) * 100}%`;
}

/** One side of one axis, in the organiser's own words. */
function poleName(pole: Pole | null): string {
  if (!pole) return "";
  const [name, side] = pole.split("_");
  const axis = axes.find((a) => a.axis === name);
  if (!axis) return "";
  return side === "low" ? axis.low_name : axis.high_name;
}

/** The direction each option of a choice question carried, by the
 *  option's own place in the list: the two arrive parallel. */
function optionPole(line: CompassAnswerResult, index: number): string {
  return poleName(line.option_poles?.[index] ?? null);
}

function isPicked(line: CompassAnswerResult, option: string): boolean {
  return (line.given_choices ?? []).includes(option);
}

/** What one rating answer did to the map, in words: the side a 5 meant,
 *  what was said, and where that landed. */
function ratingSentence(line: CompassAnswerResult): string {
  const meant = poleName(line.pole);
  const given = line.given_int ?? 0;
  if (!line.value) return k.ratingLineCentre(meant, given);
  const toward = line.value < 0 ? poleName(sideOf(line, "low")) : poleName(sideOf(line, "high"));
  return k.ratingLine(meant, given, decimal(line.value, locale), toward);
}

/** The named side of this answer's own axis, whichever way it went. */
function sideOf(line: CompassAnswerResult, side: "low" | "high"): Pole | null {
  return line.axis ? (`${line.axis}_${side}` as Pole) : null;
}

function startWalk() {
  step = 0;
  stepError = null;
  status = "walking";
}
</script>

<PublicShell bind:locale hideAds={status === "done"}>
  {#if status === "loading"}
    <PublicNotice message={c.loading} />
  {:else if status === "unavailable"}
    <PublicNotice message={c.unavailable} />
  {:else if status === "load-failed"}
    <PublicNotice message={c.loadFailed} />
  {:else if kompas}
    {#if status === "ready"}
      <!-- The cover. -->
      <PublicTopCard
        {title}
        imageUrl={kompas.image_url}
        artist={kompas.image_artist_instagram}
        creditLabel={c.imageCredit}
        descriptionHtml={description}
      />
      <!-- What the kompas places people on, said before anybody
           answers. The directions per answer are not here. -->
      {#if axes.length}
        <ul class="card axis-intro">
          {#each axes as axis (axis.axis)}
            <li>
              <strong class="axis-intro-name">{axis.name}</strong>
              {#if axis.description}<span class="muted">{axis.description}</span>{/if}
              <span class="muted axis-ends">{axis.low_name} &middot; {axis.high_name}</span>
            </li>
          {/each}
        </ul>
      {/if}
      <Disclosure {locale} />
      <form class="card stack" novalidate onsubmit={(e) => { e.preventDefault(); startWalk(); }}>
        <label class="name-label">
          <!-- The privacy contract of this feature, above the box and
               not under it. -->
          <span class="muted">{k.nameOnMap}</span>
          <input
            bind:value={displayName}
            type="text"
            class="input"
            placeholder={c.displayName}
            autocomplete="name"
            maxlength="100"
          />
        </label>
        <div class="step-row">
          <button type="submit" class="btn-primary">{k.start}</button>
        </div>
      </form>
    {:else if status === "walking"}
      <!-- A question page carries the title and the question. -->
      <p class="running-title">{title}</p>
      <div class="card stack">
        <p class="progress muted">{k.progress(step + 1, questions.length)}</p>

        {#if current}
          {#key current.id}
            <QuestionField
              question={current}
              answer={answers[current.id]}
              requiredLabel={k.required}
              markRequired={false}
              rangeHint={null}
              onupdate={(value) => (answers[current!.id] = value)}
            />
          {/key}
        {/if}

        {#if stepError}<p class="error" role="alert">{stepError}</p>{/if}

        <div class="step-row">
          {#if step > 0}
            <button type="button" class="btn-secondary" onclick={back}>{k.back}</button>
          {/if}
          <button type="button" class="btn-primary" disabled={submitting} onclick={next}>
            {isLast ? k.finish : k.next}
          </button>
        </div>
      </div>
    {:else if status === "done" && result}
      <!-- The result: the map, the axes, the answers. -->
      <p class="running-title">{title}</p>

      <div class="card stack">
        <h2 class="result-heading">{k.resultTitle}</h2>
        <CompassPlot
          {axes}
          points={result.points}
          anonymousLabel={k.anonymous}
          ariaLabel={k.resultTitle}
        />
        <p class="muted filled-in">{k.filledIn(result.points.length)}</p>
      </div>

      <div class="card stack">
        {#each axes as axis (axis.axis)}
          <div class="axis-block">
            <p class="axis-name">
              {axis.name}
              {#if axis.description}<span class="muted axis-desc">{axis.description}</span>{/if}
            </p>
            <p class="axis-sentence">{axisSentence(axis)}</p>
            <div class="axis-track">
              <span class="axis-bar">
                <!-- Where the room sits, with 95% confidence, behind the
                     reader's own marker. -->
                {#if roomBand(axis)}
                  <span
                    class="axis-room"
                    style="left: {roomBand(axis)!.left}; width: {roomBand(axis)!.width};"
                  ></span>
                {/if}
                {#if roomMeanLeft(axis)}
                  <span class="axis-room-mean" style="left: {roomMeanLeft(axis)}"></span>
                {/if}
                <span class="axis-marker" style="left: {markerLeft(axis)}"></span>
              </span>
            </div>
            <div class="axis-ends-row muted">
              <span>{axis.low_name}</span>
              <span class="axis-end-right">{axis.high_name}</span>
            </div>
          </div>
        {/each}
        {#if anyRoomBand}<p class="axis-room-note muted">{k.roomBand}</p>{/if}
      </div>

      <!-- Every question redrawn as it was asked, with the direction it
           carried: the map gets a visible reason, question by
           question. -->
      <div class="card stack">
        <h2 class="result-heading">{k.answersHeading}</h2>
        <ol class="answer-list">
          {#each result.answers as line, i (line.question_id)}
            <li class="answer-row">
              <span class="row-number" aria-hidden="true">{i + 1}</span>
              <span class="answer-text">
                <span class="answer-prompt">{byId[line.question_id]?.prompt}</span>

                {#if line.kind === "rating"}
                  <!-- A rating is the scale it was: seeing where the
                       pick sat on it is the whole answer. -->
                  <span class="scale-row" aria-hidden="true">
                    {#each [1, 2, 3, 4, 5] as n (n)}
                      <span class="scale-dot" class:is-picked={line.given_int === n}>{n}</span>
                    {/each}
                  </span>
                  <span class="answer-note muted">
                    {line.given_int == null ? k.noAnswer : ratingSentence(line)}
                  </span>
                {:else}
                  <!-- A choice is its option list in the organiser's
                       order, the pick marked in place and each option's
                       direction named beside it. -->
                  <span class="option-list">
                    {#each byId[line.question_id]?.options ?? [] as option, index (option)}
                      <span class="option-row" class:is-picked={isPicked(line, option)}>
                        <span class="option-mark" aria-hidden="true"></span>
                        <span class="option-name">{option}</span>
                        <span class="option-pole muted">{optionPole(line, index)}</span>
                      </span>
                    {/each}
                  </span>
                  {#if !(line.given_choices ?? []).length}
                    <span class="answer-note muted">{k.noAnswer}</span>
                  {/if}
                {/if}
              </span>
            </li>
          {/each}
        </ol>

        <RecoveredNotice recoveredAt={result.link_recovered_at} {locale} />
      </div>

      <!-- The link back to this fill-in, said out loud rather than left
           in the address bar: it is the only way back, and nobody can
           re-send it. Changing the answers is offered in the same
           place, when the organiser allows it. -->
      <div class="card link-card">
        <EditLink url={link.editUrl} {locale} canEdit={kompas?.answers_editable ?? false} />
        {#if kompas?.answers_editable}
          <div class="step-row">
            <button type="button" class="btn-secondary" onclick={startWalk}>{k.changeAnswers}</button>
          </div>
        {/if}
      </div>

      <SupportButtons />
    {/if}
  {/if}
</PublicShell>

<style>
/* Matches ``PublicConfirmation``: EditLink renders as a fragment, so
 * the card owns the column and its gap. */
.link-card {
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
}
.progress {
  margin: 0;
  font-size: 0.875rem;
}
.step-row {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
}
.error {
  color: var(--brand-red);
  margin: 0;
}
.result-heading {
  margin: 0;
  font-size: 1.125rem;
}
.filled-in {
  margin: 0;
  font-size: 0.875rem;
}

/* The cover's two-line summary of what this places people on. */
.axis-intro {
  list-style: none;
  margin: 0;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.axis-ends {
  display: block;
  font-size: 0.875rem;
}
/* A template's leading space collapses, so the gap is drawn. */
.axis-intro-name {
  margin-right: 0.3125rem;
}

/* --- where you landed, per axis ----------------------------------- */
.axis-block + .axis-block {
  margin-top: 1.25rem;
}
.axis-name {
  margin: 0;
  font-weight: 600;
}
.axis-desc {
  font-weight: 400;
  margin-left: 0.375rem;
}
.axis-sentence {
  margin: 0.25rem 0 0.5rem;
}
.axis-track {
  display: flex;
  align-items: center;
}
.axis-bar {
  position: relative;
  flex: 1 1 auto;
  height: 0.5rem;
  border-radius: 999px;
  background: var(--brand-border);
}
.axis-marker {
  position: absolute;
  top: -0.1875rem;
  width: 0.3125rem;
  height: 0.875rem;
  margin-left: -0.15625rem;
  border-radius: 2px;
  background: var(--brand-red);
}
/* The room, behind the reader: a band rather than a marker, because it
 * is a range the mean sits somewhere in, and drawn in the muted text
 * colour so the red marker stays the thing being read. */
.axis-room {
  position: absolute;
  top: 0;
  bottom: 0;
  border-radius: 999px;
  background: var(--brand-text-muted);
  opacity: 0.35;
}
.axis-room-mean {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 2px;
  margin-left: -1px;
  background: var(--brand-text-muted);
}
.axis-room-note {
  margin: 1.25rem 0 0;
  font-size: 0.875rem;
}
.axis-ends-row {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  margin-top: 0.375rem;
  font-size: 0.875rem;
}
.axis-end-right {
  text-align: right;
}

/* --- your answers -------------------------------------------------
 * The row grammar (.answer-list, .answer-row, .row-number,
 * .answer-prompt) is the quiz result screen's, in
 * ``public_shared/forms.css``. What is different is the direction
 * beside each option, and the absence of any mark that claims an
 * answer was right: a kompas has no right answers. */
.answer-note {
  display: block;
  font-size: 0.875rem;
  margin-top: 0.25rem;
}
.scale-row {
  display: flex;
  gap: 0.375rem;
  margin-top: 0.375rem;
}
.scale-dot {
  width: 1.75rem;
  height: 1.75rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--brand-border);
  border-radius: 999px;
  font-size: 0.875rem;
}
.scale-dot.is-picked {
  background: var(--brand-red);
  border-color: var(--brand-red);
  color: #fff;
  font-weight: 600;
}
.option-list {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  margin-top: 0.375rem;
}
.option-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.option-mark {
  flex: 0 0 auto;
  width: 0.75rem;
  height: 0.75rem;
  border-radius: 999px;
  border: 1px solid var(--brand-border);
}
.option-row.is-picked .option-mark {
  background: var(--brand-red);
  border-color: var(--brand-red);
}
.option-row.is-picked .option-name {
  font-weight: 600;
}
.option-name {
  flex: 1 1 auto;
  min-width: 0;
}
.option-pole {
  flex: 0 0 auto;
  font-size: 0.875rem;
}
</style>
