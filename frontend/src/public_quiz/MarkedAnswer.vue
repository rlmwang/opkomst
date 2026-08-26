<script setup lang="ts">
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
import { computed } from "vue";
import type { PublicQuizQuestion, QuizAnswerResult } from "./api";
import type { QuizStrings } from "./i18n";

const props = defineProps<{
  question: PublicQuizQuestion | undefined;
  line: QuizAnswerResult;
  strings: QuizStrings;
  reveal: boolean;
}>();

interface Row {
  key: string;
  label: string;
  /** This was a right answer. */
  right: boolean;
  /** This is what the player picked. */
  picked: boolean;
}

const given = computed(() => props.line.given_choices ?? []);
const key = computed(() => props.line.correct_choices ?? []);

const rows = computed<Row[]>(() => {
  const q = props.question;
  if (!q) return [];

  if (q.kind === "single_choice" || q.kind === "multi_choice") {
    // Every option, in the order it was asked, so the question reads
    // the way it read on the night.
    return q.options.map((opt) => ({
      key: opt,
      label: opt,
      right: props.reveal && key.value.includes(opt),
      picked: given.value.includes(opt),
    }));
  }

  // A number has no option list, so the values themselves are the rows:
  // what was right, then what was answered, and one row when they are
  // the same number.
  // No unit appended to the value: it is named on the line above,
  // where a reader can tell what it is.
  const unit = "";
  const answer = props.line.given_int;
  const correct = props.line.correct_int;
  const out: Row[] = [];
  if (props.reveal && correct !== null && correct !== answer) {
    out.push({ key: `k${correct}`, label: `${correct}${unit}`, right: true, picked: false });
  }
  if (answer !== null) {
    // Whether this answer was right is the server's verdict, not a
    // comparison with the key: a number question may allow a margin,
    // and 140000 against a key of 130000 within 20000 is right even
    // though the two numbers differ.
    out.push({ key: `a${answer}`, label: `${answer}${unit}`, right: props.line.correct, picked: true });
  }
  return out;
});

/** The scale is the question, so a rating is drawn as the scale rather
 *  than as two rows of numbers: saying 2 where the key was 4 is the
 *  whole answer, and a list would throw the distance away. */
const scale = computed(() =>
  props.question?.kind === "rating"
    ? [1, 2, 3, 4, 5].map((v) => ({
        value: v,
        // The key, and separately how the pick went: a rating can carry
        // a margin too.
        right: props.reveal && props.line.correct_int === v,
        picked: props.line.given_int === v,
        pickedRight: props.line.given_int === v && props.line.correct,
      }))
    : null,
);

/** The bounds in words, when the question had any. */
const rangeHint = computed(() => {
  const q = props.question;
  if (!q || q.kind !== "number") return null;
  return props.strings.range(q.min_value, q.max_value, q.tolerance, q.step);
});

function labelFor(row: Row): string | null {
  if (row.picked) return props.strings.yourAnswer;
  // A right option nobody ticked needs the word: an unmarked row would
  // otherwise read as "not part of the answer".
  if (row.right) return props.question?.kind === "multi_choice" ? props.strings.missed : props.strings.rightAnswer;
  return null;
}
</script>

<template>
  <!-- What counted as a valid answer. A number question without its
       range is a guess in the dark, on the result screen as much as in
       the question. -->
  <p v-if="rangeHint" class="range muted">{{ rangeHint }}</p>

  <!-- The scale, for a rating. -->
  <ol v-if="scale" class="scale" :aria-label="strings.yourAnswer">
    <li
      v-for="point in scale"
      :key="point.value"
      class="point"
      :class="{ 'is-right': point.right, 'is-picked': point.picked, 'is-picked-right': point.pickedRight }"
    >
      <span aria-hidden="true">{{ point.value }}</span>
      <span v-if="point.picked || point.right" class="visually-hidden">
        {{ point.picked ? strings.yourAnswer : strings.rightAnswer }}
      </span>
    </li>
  </ol>

  <!-- Everything else: one row per possible answer. -->
  <ul v-else class="marked">
    <li v-for="row in rows" :key="row.key" class="marked-row" :class="{ 'is-right': row.right, 'is-picked': row.picked }">
      <!-- Only the player's own row carries a mark, and which mark it
           is says how that answer went. Every other row is blank. -->
      <span class="mark" :class="row.picked ? (row.right ? 'is-good' : 'is-bad') : ''" aria-hidden="true">
        <svg v-if="row.picked && row.right" viewBox="0 0 16 16" width="14" height="14">
          <path
            d="M2.5 8.5l3.5 3.5 7.5-8"
            fill="none"
            stroke="currentColor"
            stroke-width="2.4"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
        <svg v-else-if="row.picked" viewBox="0 0 16 16" width="14" height="14">
          <path
            d="M3.5 3.5l9 9M12.5 3.5l-9 9"
            fill="none"
            stroke="currentColor"
            stroke-width="2.4"
            stroke-linecap="round"
          />
        </svg>
      </span>
      <span class="marked-label">{{ row.label }}</span>
      <span v-if="labelFor(row)" class="marked-note muted">{{ labelFor(row) }}</span>
    </li>
  </ul>
</template>

<style scoped>
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
