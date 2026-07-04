<script setup lang="ts">
import Button from "primevue/button";
import { computed, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import AppCard from "@/components/AppCard.vue";
import DetailsPageShell from "@/components/DetailsPageShell.vue";
import MonthCalendar from "@/components/MonthCalendar.vue";
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
      <AppCard :stack="false" class="overview">
        <h1>
          {{ poll.name }}
          <span v-if="poll.chapter_name" class="chapter-chip">{{ poll.chapter_name }}</span>
        </h1>
        <figure v-if="poll.image_url" class="detail-image">
          <img :src="poll.image_url" :alt="poll.name" />
          <figcaption v-if="poll.image_artist_instagram" class="muted">
            {{ t("imageField.credit") }}
            <a :href="`https://instagram.com/${poll.image_artist_instagram}`" target="_blank" rel="noopener">@{{ poll.image_artist_instagram }}</a>
          </figcaption>
        </figure>
        <div class="overview-body">
          <button
            type="button"
            class="qr-button"
            v-tooltip.top="t('datepolls.share.copyQr')"
            :aria-label="t('datepolls.share.copyQr')"
            @click="copyQr(poll.slug)"
          >
            <img :src="datepollQrUrl(poll.slug)" alt="" class="qr" />
          </button>
          <div class="overview-text">
            <p v-if="poll.description" class="muted description">{{ poll.description }}</p>
            <a
              v-if="poll.location"
              class="location"
              :href="mapLink({ location: poll.location, latitude: poll.latitude ?? null, longitude: poll.longitude ?? null })"
              target="_blank"
              rel="noopener"
            >
              <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" /><circle cx="12" cy="10" r="3" /></svg>
              {{ poll.location }}
            </a>
            <div class="link-row">
              <a :href="publicDatepollUrl(poll.slug)" target="_blank" rel="noopener">
                {{ publicDatepollUrl(poll.slug) }}
              </a>
              <Button
                icon="pi pi-copy"
                size="small"
                severity="secondary"
                text
                v-tooltip.top="t('datepolls.share.copyLink')"
                :aria-label="t('datepolls.share.copyLink')"
                @click="copyLink(poll.slug)"
              />
            </div>
            <div>
              <router-link :to="`/datepolls/${poll.id}/edit`">
                <Button :label="t('common.edit')" icon="pi pi-pencil" size="small" severity="secondary" />
              </router-link>
            </div>
          </div>
        </div>
      </AppCard>

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
            <div v-if="summary" class="count-pill">
              <span class="count">{{ summary.submission_count }}</span>
              <span class="label">{{ t("datepolls.details.responses") }}</span>
            </div>
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

          <!-- Submission notes (one optional note per respondent). -->
          <div v-if="summary.notes?.length" class="notes-section">
            <h3>{{ t("datepolls.details.notesTitle") }}</h3>
            <ul class="comments">
              <li v-for="(n, i) in summary.notes" :key="i">{{ n }}</li>
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
                  <th class="note-col">{{ t("datepolls.details.note") }}</th>
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
                  <td class="note-col">{{ sub.note }}</td>
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
/* Overview card (.overview*, .detail-image, .qr*), .summary-header /
 * .header-actions, and the mobile stack override are shared from
 * theme.css. Only the datepoll-specific location link stays here. */
.description { margin: 0; }
.location {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  width: fit-content;
  color: var(--brand-red);
  text-decoration: none;
  font-size: 0.9375rem;
}
.location:hover { text-decoration: underline; }
.location svg { flex: none; }

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
.comments { margin: 0.5rem 0 0; padding-left: 1.25rem; display: flex; flex-direction: column; gap: 0.25rem; }
.comments li { line-height: 1.4; }
.notes-section { margin-top: 1.25rem; }
.notes-section h3 { margin: 0 0 0.25rem; font-size: 0.9375rem; }

.grid-wrap { margin-top: 1.5rem; overflow-x: auto; }
.grid { border-collapse: collapse; font-size: 0.8125rem; }
.grid th, .grid td { border: 1px solid var(--brand-border); padding: 0.25rem 0.5rem; text-align: center; white-space: nowrap; }
.grid th.who, .grid td.who { text-align: left; position: sticky; left: 0; background: var(--brand-surface); }
.grid th.note-col, .grid td.note-col { text-align: left; white-space: normal; min-width: 8rem; max-width: 16rem; }
/* Slot columns (everything between respondent and note) share one
 * fixed width so they line up evenly. */
.grid th.slot-th, .grid tbody td:not(.who):not(.note-col) { width: 4rem; }
.grid th.slot-th .th-time { font-weight: 400; font-size: 0.75rem; color: var(--brand-text-muted); }
.cell.yes { background: var(--brand-green); color: #fff; }
.cell.maybe { background: var(--brand-amber); color: #fff; }
.cell.no { background: #6b6b6b; color: #fff; }
</style>
