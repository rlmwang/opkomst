<script lang="ts">
/**
 * One marked answer on the result screen, drawn as the question it was.
 *
 * Design and the reasoning per kind: ``docs/design-quizzes.md`` §3.4.
 * The short version: a summary like "you 3, right 3" throws away what
 * was asked and what could have been answered, so each kind is redrawn
 * with the answers marked in place.
 *
 * One mark, one meaning: the tick and the cross describe *this
 * person's answer*, never the option. A tick on a row they did not
 * pick would put "right" next to a question they got wrong, which is
 * the confusion this shape exists to avoid. What was right instead
 * carries a tint and says so in words.
 *
 * When the organiser turned the reveal off, no row claims to be right;
 * the player still sees what they answered.
 */
import type { PublicQuizQuestion, QuizAnswerResult } from "./api";
import type { QuizStrings } from "./i18n";

const {
  question,
  line,
  strings,
  reveal,
}: {
  question: PublicQuizQuestion | undefined;
  line: QuizAnswerResult;
  strings: QuizStrings;
  reveal: boolean;
} = $props();

interface Row {
  key: string;
  label: string;
  /** This was a right answer. */
  right: boolean;
  /** This is what the player picked. */
  picked: boolean;
}

const given = $derived(line.given_choices ?? []);
const key = $derived(line.correct_choices ?? []);

const rows = $derived.by<Row[]>(() => {
  const q = question;
  if (!q) return [];

  if (q.kind === "single_choice" || q.kind === "multi_choice") {
    // Every option, in the order it was asked, so the question reads
    // the way it read on the night.
    // ``given`` is option ids and ``key`` is the labels the reveal
    // sends, so each is matched against its own kind of thing.
    return q.options.map((opt) => ({
      key: opt.id,
      label: opt.label,
      right: reveal && key.includes(opt.label),
      picked: given.includes(opt.id),
    }));
  }

  // A number has no option list, so the values themselves are the rows:
  // what was right, then what was answered, and one row when they are
  // the same number.
  // No unit appended to the value: it is named on the line above, where
  // a reader can tell what it is.
  const unit = "";
  const answer = line.given_int;
  const correct = line.correct_int;
  const out: Row[] = [];
  if (reveal && correct !== null && correct !== answer) {
    out.push({ key: `k${correct}`, label: `${correct}${unit}`, right: true, picked: false });
  }
  if (answer !== null) {
    // Whether this answer was right is the server's verdict, not a
    // comparison with the key: a number question may allow a margin,
    // and 140000 against a key of 130000 within 20000 is right even
    // though the two numbers differ.
    out.push({ key: `a${answer}`, label: `${answer}${unit}`, right: line.correct, picked: true });
  }
  return out;
});

/** The scale is the question, so a rating is drawn as the scale rather
 *  than as two rows of numbers: saying 2 where the key was 4 is the
 *  whole answer, and a list would throw the distance away. */
const scale = $derived(
  question?.kind === "rating"
    ? [1, 2, 3, 4, 5].map((v) => ({
        value: v,
        // The key, and separately how the pick went: a rating can carry
        // a margin too.
        right: reveal && line.correct_int === v,
        picked: line.given_int === v,
        pickedRight: line.given_int === v && line.correct,
      }))
    : null,
);

/** The bounds in words, when the question had any. */
const rangeHint = $derived.by(() => {
  if (!question || question.kind !== "number") return null;
  return strings.range(question.min_value, question.max_value, question.tolerance, question.step);
});

function labelFor(row: Row): string | null {
  if (row.picked) return strings.yourAnswer;
  // A right option nobody ticked needs the word: an unmarked row would
  // otherwise read as "not part of the answer".
  if (row.right) return question?.kind === "multi_choice" ? strings.missed : strings.rightAnswer;
  return null;
}
</script>

<!-- What counted as a valid answer. A number question without its range
     is a guess in the dark, on the result screen as much as in the
     question. -->
{#if rangeHint}<p class="range muted">{rangeHint}</p>{/if}

{#if scale}
  <!-- The scale, for a rating. -->
  <ol class="scale" aria-label={strings.yourAnswer}>
    {#each scale as point (point.value)}
      <li
        class="point"
        class:is-right={point.right}
        class:is-picked={point.picked}
        class:is-picked-right={point.pickedRight}
      >
        <span aria-hidden="true">{point.value}</span>
        {#if point.picked || point.right}
          <span class="visually-hidden">
            {point.picked ? strings.yourAnswer : strings.rightAnswer}
          </span>
        {/if}
      </li>
    {/each}
  </ol>
{:else}
  <!-- Everything else: one row per possible answer. -->
  <ul class="marked">
    {#each rows as row (row.key)}
      <li class="marked-row" class:is-right={row.right} class:is-picked={row.picked}>
        <!-- Only the player's own row carries a mark, and which mark it
             is says how that answer went. Every other row is blank. -->
        <span class="mark" class:is-good={row.picked && row.right} class:is-bad={row.picked && !row.right} aria-hidden="true">
          {#if row.picked && row.right}
            <svg viewBox="0 0 16 16" width="14" height="14">
              <path
                d="M2.5 8.5l3.5 3.5 7.5-8"
                fill="none"
                stroke="currentColor"
                stroke-width="2.4"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
          {:else if row.picked}
            <svg viewBox="0 0 16 16" width="14" height="14">
              <path
                d="M3.5 3.5l9 9M12.5 3.5l-9 9"
                fill="none"
                stroke="currentColor"
                stroke-width="2.4"
                stroke-linecap="round"
              />
            </svg>
          {/if}
        </span>
        <span class="marked-label">{row.label}</span>
        {#if labelFor(row)}<span class="marked-note muted">{labelFor(row)}</span>{/if}
      </li>
    {/each}
  </ul>
{/if}

<style>
.range {
  margin: 0.25rem 0 0;
  font-size: 0.8125rem;
}
.marked,
.scale {
  list-style: none;
  margin: 0.375rem 0 0;
  padding: 0;
}
.marked {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
}
.marked-row {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: baseline;
  gap: 0.5rem;
  padding: 0.25rem 0.5rem;
  border-radius: 6px;
  font-size: 0.9375rem;
}
/* What was right is tinted and says so in words. No icon: an icon here
 * would be a tick beside an answer this person never gave. */
.marked-row.is-right {
  background: var(--brand-green-soft);
}
.marked-row.is-picked .marked-label {
  font-weight: 600;
}
/* Fixed width so every label starts on the same line, marked or not. */
.mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.25rem;
  flex-shrink: 0;
}
.mark.is-good {
  color: var(--brand-green);
}
.mark.is-bad {
  color: var(--brand-red);
}
.marked-label {
  overflow-wrap: anywhere;
}
.marked-note {
  font-size: 0.75rem;
  white-space: nowrap;
}

/* The rating scale, drawn the way it was answered. */
.scale {
  display: flex;
  gap: 0.375rem;
}
.point {
  position: relative;
  width: 2.25rem;
  height: 2.25rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--brand-border);
  border-radius: 8px;
  font-size: 0.875rem;
  font-variant-numeric: tabular-nums;
  color: var(--brand-text-muted);
}
.point.is-right {
  border-color: var(--brand-green);
  background: var(--brand-green-soft);
  color: var(--brand-text);
}
/* Same two channels as the rows: the pick says how it went, the key
 * says what it was. */
.point.is-picked {
  border-width: 2px;
  border-color: var(--brand-red);
  font-weight: 700;
  color: var(--brand-text);
}
.point.is-picked-right {
  border-color: var(--brand-green);
}

.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
  border: 0;
}
</style>
