<script setup lang="ts">
import Button from "primevue/button";
import { computed, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import AppCard from "@/components/AppCard.vue";
import DetailsPageShell from "@/components/DetailsPageShell.vue";
import { ApiError } from "@/api/client";
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

function nameOf(s: DatepollSubmission): string {
  return s.display_name ?? t("datepolls.details.anonymous");
}

const AVAIL_GLYPH: Record<string, string> = { yes: "✓", maybe: "~", no: "✕" };

// Bar width as a share of all respondents, so the three columns are
// comparable row-to-row (a full bar = everyone) and the winning slot
// reads at a glance.
function pct(value: number): string {
  const total = summary.value?.submission_count ?? 0;
  return total ? `${Math.round((value / total) * 100)}%` : "0%";
}

// Rank the top three slots by the same rule the backend uses for the
// winner (most yes, tie-break fewest no); only slots with ≥1 yes rank.
// Shown as a 1st/2nd/3rd chip in front of each slot (chronological)
// row; a reserved-width slot keeps the labels aligned.
const rankById = computed<Record<string, number>>(() => {
  const ranked = [...(summary.value?.slots ?? [])]
    .filter((s) => s.yes > 0)
    .sort((a, b) => b.yes - a.yes || a.no - b.no)
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
          <span v-if="poll.chapter_name" class="chip">{{ poll.chapter_name }}</span>
        </h1>
        <p v-if="poll.description" class="muted description">{{ poll.description }}</p>
        <figure v-if="poll.image_url" class="detail-image">
          <img :src="poll.image_url" :alt="poll.name" />
          <figcaption v-if="poll.image_artist_instagram" class="muted">
            {{ t("imageField.credit") }}
            <a :href="`https://instagram.com/${poll.image_artist_instagram}`" target="_blank" rel="noopener">@{{ poll.image_artist_instagram }}</a>
          </figcaption>
        </figure>
        <div class="overview-body">
          <div class="overview-text">
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
          <button
            type="button"
            class="qr-button"
            v-tooltip.top="t('datepolls.share.copyQr')"
            :aria-label="t('datepolls.share.copyQr')"
            @click="copyQr(poll.slug)"
          >
            <img :src="datepollQrUrl(poll.slug)" alt="" class="qr" />
          </button>
        </div>
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
          <!-- Per-slot tallies as a borderless 4-column table: slot,
               then a colored bar + count for yes / maybe / no. Winning
               slot highlighted. -->
          <table class="tally">
            <thead>
              <tr>
                <th class="slot-col" />
                <th>{{ t("datepolls.details.yes") }}</th>
                <th>{{ t("datepolls.details.maybe") }}</th>
                <th>{{ t("datepolls.details.no") }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="s in summary.slots" :key="s.id">
                <td class="slot-col">
                  <span class="rank" :class="rankById[s.id] ? `r${rankById[s.id]}` : ''">{{ rankLabel(s.id) }}</span>
                  {{ slotHeading(s) }}
                </td>
                <td v-for="kind in (['yes', 'maybe', 'no'] as const)" :key="kind" class="bar-cell">
                  <div class="bar-track"><div class="bar-fill" :class="kind" :style="{ width: pct(s[kind]) }" /></div>
                  <span class="bar-count">{{ s[kind] }}</span>
                </td>
              </tr>
            </tbody>
          </table>

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
                  <th v-for="s in summary.slots" :key="s.id">{{ slotHeading(s) }}</th>
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
.back-link { display: inline-block; margin-top: 0.5rem; color: var(--brand-red); }
.overview { display: flex; flex-direction: column; gap: 0.5rem; }
.overview h1 { margin: 0; overflow-wrap: anywhere; }
.description { margin: 0; }
.detail-image { margin: 0; }
.detail-image img {
  display: block;
  max-width: 200px;
  aspect-ratio: 4 / 5;
  object-fit: cover;
  border-radius: 8px;
  border: 1px solid var(--brand-border);
}
.detail-image figcaption { margin-top: 0.375rem; font-size: 0.8125rem; }
.chip {
  display: inline-flex; align-items: center; margin-left: 0.5rem;
  padding: 0.125rem 0.625rem; border-radius: 999px;
  background: var(--brand-surface-subtle, rgba(0, 0, 0, 0.05));
  color: var(--brand-text-muted); font-size: 0.875rem; font-weight: 400;
  vertical-align: middle; white-space: nowrap;
}
.overview-body { display: grid; grid-template-columns: 1fr auto; gap: 1rem; align-items: start; }
.overview-text { display: flex; flex-direction: column; gap: 0.5rem; min-width: 0; }
.link-row { display: flex; align-items: center; gap: 0.375rem; min-width: 0; }
.link-row a { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.qr-button { background: none; border: none; padding: 0; cursor: pointer; flex-shrink: 0; }
.qr-button:focus-visible { outline: 2px solid var(--brand-red); outline-offset: 2px; border-radius: 8px; }
.qr { width: 96px; height: 96px; background: white; border: 1px solid var(--brand-border); border-radius: 6px; padding: 0.375rem; display: block; }
@media (max-width: 480px) { .overview-body { grid-template-columns: 1fr; } }

.summary-header { display: flex; justify-content: space-between; align-items: center; gap: 1rem; flex-wrap: wrap; }
.header-actions { display: flex; align-items: center; gap: 0.5rem; }
.count-pill {
  display: inline-flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 0.125rem; padding: 0.5rem 1rem; border-radius: 8px; border: 1px solid var(--brand-border);
  background: var(--brand-bg); min-width: 5rem;
}
.count-pill .count { font-weight: 700; font-size: 1.25rem; line-height: 1; color: var(--brand-red); }
.count-pill .label { font-size: 0.75rem; color: var(--brand-text-muted); }

/* Per-slot tally table — borderless, minimal. One row per slot;
 * yes/maybe/no cells each hold a proportional bar + count. */
.tally { width: 100%; border-collapse: collapse; }
.tally th, .tally td { padding: 0.45rem 0.625rem; text-align: left; vertical-align: middle; }
.tally thead th {
  font-weight: 500;
  font-size: 0.8125rem;
  color: var(--brand-text-muted);
}
.tally .slot-col { white-space: nowrap; }
/* Reserved-width rank chip in front of the slot label so all labels
 * align whether or not the row is ranked. */
.rank {
  display: inline-block;
  width: 2.25rem;
  margin-right: 0.5rem;
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
.rank.r1 { background: #1f7a3c; }
.rank.r2 { background: #8a8f98; }
.rank.r3 { background: #b8763a; }
/* Bar cell: a track that fills the column width + a fixed count. */
.bar-cell { width: 30%; }
.bar-track {
  display: inline-block;
  width: calc(100% - 1.75rem);
  height: 0.625rem;
  background: var(--brand-border);
  border-radius: 999px;
  overflow: hidden;
  vertical-align: middle;
}
.bar-fill { height: 100%; border-radius: 999px; }
.bar-fill.yes { background: #1f7a3c; }
.bar-fill.maybe { background: #c98a00; }
.bar-fill.no { background: var(--brand-text-muted); }
.bar-count {
  display: inline-block;
  width: 1.5rem;
  margin-left: 0.25rem;
  text-align: right;
  font-size: 0.8125rem;
  color: var(--brand-text-muted);
  vertical-align: middle;
}
.comments { margin: 0.5rem 0 0; padding-left: 1.25rem; display: flex; flex-direction: column; gap: 0.25rem; }
.comments li { line-height: 1.4; }
.notes-section { border-top: 1px solid var(--brand-border); padding-top: 1.25rem; margin-top: 1.25rem; }
.notes-section h3 { margin: 0 0 0.25rem; font-size: 0.9375rem; }

.grid-wrap { margin-top: 1.5rem; overflow-x: auto; }
.grid { border-collapse: collapse; font-size: 0.8125rem; }
.grid th, .grid td { border: 1px solid var(--brand-border); padding: 0.25rem 0.5rem; text-align: center; white-space: nowrap; }
.grid th.who, .grid td.who { text-align: left; position: sticky; left: 0; background: var(--brand-surface); }
.grid th.note-col, .grid td.note-col { text-align: left; white-space: normal; min-width: 8rem; max-width: 16rem; }
.cell.yes { background: rgba(31, 122, 60, 0.18); }
.cell.maybe { background: rgba(201, 138, 0, 0.18); }
.cell.no { background: rgba(0, 0, 0, 0.05); color: var(--brand-text-muted); }
</style>
