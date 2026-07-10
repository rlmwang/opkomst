<script setup lang="ts">
import Button from "primevue/button";
import { computed, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import AppCard from "@/components/AppCard.vue";
import DetailHeaderCard from "@/components/DetailHeaderCard.vue";
import DetailsPageShell from "@/components/DetailsPageShell.vue";
import MonthCalendar from "@/components/MonthCalendar.vue";
import RecoverLinksPill, { type RecoverableRow } from "@/components/RecoverLinksPill.vue";
import SegmentedBar, { type BarSegment } from "@/components/SegmentedBar.vue";
import TallyLegend, { type LegendItem } from "@/components/TallyLegend.vue";
import { ApiError } from "@/api/client";
import { mapLink } from "@/lib/map-link";
import { useDatepollClipboard } from "@/composables/useDatepollClipboard";
import {
  type DatepollSubmission,
  fetchDatepollSubmissions,
  useDatepoll,
  useDatepollSummary,
} from "@/composables/useDatepolls";
import { datepollQrUrl, publicDatepollUrl } from "@/lib/datepoll-urls";
import { downloadCsv } from "@/lib/csv-export";
import { filenameSlug } from "@/lib/filename-slug";
import { localeTag } from "@/lib/format";
import { useToasts } from "@/lib/toasts";

const props = defineProps<{ datepollId: string }>();

const { t, locale } = useI18n();
const toasts = useToasts();
const { copyLink, copyQr } = useDatepollClipboard();

const pollQuery = useDatepoll(computed(() => props.datepollId));
const poll = computed(() => pollQuery.data.value ?? null);
const loaded = computed(() => !pollQuery.isPending.value);

const notFound = computed(
  () => pollQuery.error.value instanceof ApiError && pollQuery.error.value.status === 404,
);
const otherError = computed(() => pollQuery.error.value && !notFound.value);

const summaryQuery = useDatepollSummary(computed(() => props.datepollId));
const summary = computed(() => summaryQuery.data.value ?? null);

// Rows for the responses pill's recovery popover.
async function recoverRows(): Promise<RecoverableRow[]> {
  const rows = await fetchDatepollSubmissions(props.datepollId);
  return rows.map((s) => ({ id: s.submission_id, name: s.display_name, recoveredAt: s.link_recovered_at ?? null }));
}

// Per-submission rows for the results grid + CSV. Eager fetch so the
// grid paints alongside the tallies.
const subs = ref<DatepollSubmission[]>([]);
onMounted(async () => {
  try {
    subs.value = await fetchDatepollSubmissions(props.datepollId);
  } catch {
    /* grid simply stays empty; tallies still render */
  }
});

function shortDate(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString(localeTag(locale.value), {
    weekday: "short",
    day: "numeric",
    month: "short",
  });
}

// A slot's column/heading label: the short date, plus the time range
// when it's a timed slot (whole-day slots show the date alone — no
// "whole day" label).
function slotHeading(s: { on_date: string; start_time?: string | null; end_time?: string | null }): string {
  const times = s.start_time && s.end_time ? ` ${s.start_time.slice(0, 5)}–${s.end_time.slice(0, 5)}` : "";
  return shortDate(s.on_date) + times;
}

// Just the time range (``19:00–21:00``), or "" for a whole-day slot —
// used to render the time on its own line in the grid header.
function slotTime(s: { start_time?: string | null; end_time?: string | null }): string {
  return s.start_time && s.end_time ? `${s.start_time.slice(0, 5)}–${s.end_time.slice(0, 5)}` : "";
}

function nameOf(s: DatepollSubmission): string {
  return s.display_name ?? t("datepolls.details.anonymous");
}

// Respondents who left a note — the comments section pairs each note with
// the (pseudo)name that wrote it.
const notedSubs = computed(() => subs.value.filter((s) => s.note?.trim()));

const AVAIL_GLYPH: Record<string, string> = { yes: "✓", maybe: "~", no: "✕" };

// Bar length is deliberately NOT normalised: each slot's bar is sized
// against the busiest slot's total responses, so a slot fewer people
// answered reads as a shorter bar and popularity stays comparable across
// rows. Within the bar, yes/maybe/no are coloured segments each carrying
// their count. "No" is grey, never red — a green/red pair is invisible to
// red-green colour-blind viewers.
const maxTotal = computed(() => Math.max(1, ...(summary.value?.slots ?? []).map((s) => s.yes + s.maybe + s.no)));
function slotSegments(s: { yes: number; maybe: number; no: number }): BarSegment[] {
  return [
    { value: s.yes, variant: "positive", title: `${s.yes} ${t("datepolls.details.yes")}` },
    { value: s.maybe, variant: "warning", title: `${s.maybe} ${t("datepolls.details.maybe")}` },
    { value: s.no, variant: "neutral", title: `${s.no} ${t("datepolls.details.no")}` },
  ];
}
const legendItems = computed<LegendItem[]>(() => [
  { variant: "positive", label: t("datepolls.details.yes") },
  { variant: "warning", label: t("datepolls.details.maybe") },
  { variant: "neutral", label: t("datepolls.details.no") },
]);

// The proposed-dates calendar opens on the month of the earliest slot (or
// the current month when the poll has no slots yet), navigable from there.
function currentMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}
const datesMonth = ref(currentMonth());
watch(
  () => poll.value?.slots,
  (slots) => {
    const first = (slots ?? []).map((s) => s.on_date).sort()[0];
    if (first) datesMonth.value = first.slice(0, 7);
  },
  { immediate: true },
);

// Rank the top three slots by the same rule the backend uses for the
// winner (most yes, tie-break fewest no); only slots with ≥1 yes rank.
// Shown as a 1st/2nd/3rd chip in front of each slot (chronological)
// row; a reserved-width slot keeps the labels aligned.
const rankById = computed<Record<string, number>>(() => {
  const total = summary.value?.submission_count ?? 0;
  const blanks = (s: { yes: number; maybe: number; no: number }) => total - s.yes - s.maybe - s.no;
  const ranked = [...(summary.value?.slots ?? [])]
    .filter((s) => s.yes > 0)
    // Most yes, then most maybe, then most "not filled"; no is ignored.
    .sort((a, b) => b.yes - a.yes || b.maybe - a.maybe || blanks(b) - blanks(a))
    .slice(0, 3);
  const map: Record<string, number> = {};
  ranked.forEach((s, i) => {
    map[s.id] = i + 1;
  });
  return map;
});
function rankLabel(id: string): string {
  const r = rankById.value[id];
  return r ? t(`datepolls.details.rank${r}`) : "";
}

async function exportCsv() {
  if (!poll.value || !summary.value) return;
  try {
    const rows = await fetchDatepollSubmissions(props.datepollId);
    const slots = summary.value.slots;
    const header = [
      t("datepolls.details.csvName"),
      t("datepolls.details.csvSubmittedAt"),
      ...slots.map(slotHeading),
      t("datepolls.details.csvNote"),
    ];
    const body = rows.map((s) => [
      nameOf(s),
      s.created_at,
      ...slots.map((sl) => s.answers[sl.id] ?? ""),
      s.note ?? "",
    ]);
    downloadCsv(`${filenameSlug(poll.value.name)}-${poll.value.id}.csv`, [header, ...body]);
  } catch {
    toasts.error(t("datepolls.details.csvFail"));
  }
}
</script>

<template>
  <DetailsPageShell :loaded="loaded" :skeleton-rows="4">
    <AppCard v-if="notFound" :stack="false">
      <h2>{{ t("datepolls.details.notFoundTitle") }}</h2>
      <p class="muted">{{ t("datepolls.details.notFoundBody") }}</p>
      <router-link to="/datepolls" class="back-link">{{ t("datepolls.details.backToList") }}</router-link>
    </AppCard>

    <AppCard v-else-if="otherError" :stack="false">
      <p>{{ t("datepolls.details.loadFailed") }}</p>
    </AppCard>

    <template v-else-if="poll">
      <DetailHeaderCard
        :title="poll.name"
        :chapter-name="poll.chapter_name"
        :image-url="poll.image_url"
        :image-artist="poll.image_artist_instagram"
        :description-html="poll.description"
        :qr-src="datepollQrUrl(poll.slug)"
        :public-url="publicDatepollUrl(poll.slug)"
        :edit-to="`/datepolls/${poll.id}/edit`"
        @copy-qr="copyQr(poll.slug)"
        @copy-link="copyLink(poll.slug)"
      >
        <template v-if="poll.location" #meta>
          <p class="muted overview-meta">
            <a
              :href="mapLink({ location: poll.location, latitude: poll.latitude ?? null, longitude: poll.longitude ?? null })"
              target="_blank"
              rel="noopener"
              class="meta-link"
            >{{ poll.location }}</a>
          </p>
        </template>
      </DetailHeaderCard>

      <!-- Proposed dates overview — the poll's candidate slots, shown
           independently of any responses (mirrors the chore details
           "Taken" card listing the defined chores). -->
      <AppCard v-if="poll.slots?.length">
        <div class="summary-header">
          <h2>{{ t("datepolls.details.datesHeading") }}</h2>
        </div>
        <MonthCalendar
          v-model:month="datesMonth"
          :slots="poll.slots ?? []"
          :locale="locale"
          :prev-label="t('datepolls.details.prevMonth')"
          :next-label="t('datepolls.details.nextMonth')"
        />
      </AppCard>

      <AppCard>
        <div class="summary-header">
          <h2>{{ t("datepolls.details.resultsTitle") }}</h2>
          <div class="header-actions">
            <Button
              :label="t('datepolls.details.exportCsv')"
              size="small"
              severity="secondary"
              text
              icon="pi pi-download"
              :disabled="!summary || summary.submission_count === 0"
              @click="exportCsv"
            />
            <RecoverLinksPill
              v-if="summary && poll"
              :count="summary.submission_count"
              :label="t('datepolls.details.responses')"
              :load-rows="recoverRows"
              :recover-path="(id: string) => `/api/v1/datepolls/${props.datepollId}/submissions/${id}/edit-link`"
              :public-url="(tok: string) => `${publicDatepollUrl(poll!.slug)}?s=${tok}`"
            />
          </div>
        </div>

        <p v-if="!summary || summary.submission_count === 0" class="muted">
          {{ t("datepolls.details.noResponsesYet") }}
        </p>

        <template v-else>
          <!-- Per-slot tallies: one bar per slot, split into yes / maybe /
               no segments each carrying its count (bar length scaled to the
               busiest slot, not normalised). Ranked rows lead with a
               1st/2nd/3rd chip. -->
          <TallyLegend :items="legendItems" />
          <ul class="slot-tally">
            <li v-for="s in summary.slots" :key="s.id" class="slot-row">
              <div class="slot-label">
                <span class="rank" :class="rankById[s.id] ? `r${rankById[s.id]}` : ''">{{ rankLabel(s.id) }}</span>
                <span class="slot-when">{{ slotHeading(s) }}</span>
              </div>
              <SegmentedBar :segments="slotSegments(s)" :max="maxTotal" />
            </li>
          </ul>

          <!-- Submission notes (one optional note per respondent), each led
               by the (pseudo)name that wrote it. -->
          <div v-if="notedSubs.length" class="notes-section">
            <h3>{{ t("datepolls.details.notesTitle") }}</h3>
            <ul class="comments">
              <li v-for="sub in notedSubs" :key="sub.submission_id">
                <span class="comment-name">{{ nameOf(sub) }}</span>
                {{ sub.note }}
              </li>
            </ul>
          </div>

          <!-- Per-respondent grid. -->
          <div v-if="subs.length" class="grid-wrap">
            <table class="grid">
              <thead>
                <tr>
                  <th class="who">{{ t("datepolls.details.respondent") }}</th>
                  <th v-for="s in summary.slots" :key="s.id" class="slot-th">
                    <div>{{ shortDate(s.on_date) }}</div>
                    <div v-if="slotTime(s)" class="th-time">{{ slotTime(s) }}</div>
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="sub in subs" :key="sub.submission_id">
                  <td class="who">{{ nameOf(sub) }}</td>
                  <td
                    v-for="s in summary.slots"
                    :key="s.id"
                    class="cell"
                    :class="sub.answers[s.id] ?? 'none'"
                  >
                    {{ sub.answers[s.id] ? AVAIL_GLYPH[sub.answers[s.id]] : "" }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
      </AppCard>
    </template>
  </DetailsPageShell>
</template>

<style scoped>
/* The overview header is the shared ``DetailHeaderCard``; its chrome and
 * the .summary-header / .header-actions + mobile stack override are all
 * shared from theme.css. */

/* Per-slot tally — one row per slot: the date (time below) on the left,
 * a yes/maybe/no SegmentedBar on the right. Mirrors the chore tally. */
.slot-tally {
  list-style: none;
  margin: 0.75rem 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
}
.slot-row {
  display: grid;
  grid-template-columns: minmax(7rem, 14rem) 1fr;
  align-items: center;
  gap: 0.75rem;
}
.slot-label { display: flex; align-items: baseline; min-width: 0; }
/* Date with the time range behind it, on one line, at the normal body
 * size (it used to be shrunk to 0.8125rem). */
.slot-when { min-width: 0; }
/* Reserved-width rank chip in front of the slot label so all labels
 * align whether or not the row is ranked. */
.rank {
  display: inline-block;
  width: 2.25rem;
  margin-right: 0.5rem;
  flex: none;
  text-align: center;
  font-size: 0.6875rem;
  font-weight: 600;
  line-height: 1.2;
}
.rank.r1, .rank.r2, .rank.r3 {
  border-radius: 999px;
  padding: 0.0625rem 0;
  color: #fff;
}
.rank.r1 { background: var(--brand-green); }
.rank.r2 { background: #8a8f98; }
.rank.r3 { background: #b8763a; }
.comments { margin: 0.5rem 0 0; padding-left: 1.25rem; display: flex; flex-direction: column; gap: 0.375rem; }
.comments li { line-height: 1.4; }
.comment-name { font-weight: 600; margin-right: 0.375rem; }
.notes-section { margin-top: 1.25rem; }
.notes-section h3 { margin: 0 0 0.25rem; font-size: 0.9375rem; }

.grid-wrap { margin-top: 1.5rem; overflow-x: auto; }
/* The table's own border draws the outer frame; without it the collapsed
 * right/bottom edge can be clipped by the scroll container. */
.grid { border-collapse: collapse; border: 1px solid var(--brand-border); font-size: 0.8125rem; }
.grid th, .grid td { border: 1px solid var(--brand-border); padding: 0.25rem 0.5rem; text-align: center; white-space: nowrap; }
.grid th.who, .grid td.who { text-align: left; position: sticky; left: 0; background: var(--brand-surface); }
/* Slot columns (everything after the respondent) share one fixed width so
 * they line up evenly. */
.grid th.slot-th, .grid tbody td:not(.who) { width: 4rem; }
.grid th.slot-th .th-time { font-weight: 400; font-size: 0.75rem; color: var(--brand-text-muted); }
.cell.yes { background: var(--brand-green); color: #fff; }
.cell.maybe { background: var(--brand-amber); color: #fff; }
.cell.no { background: var(--brand-neutral); color: var(--brand-text); }
</style>
