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
import { barWidth, localeTag } from "@/lib/format";
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

function nameOf(s: DatepollSubmission): string {
  return s.display_name ?? t("datepolls.details.anonymous");
}

const AVAIL_GLYPH: Record<string, string> = { yes: "✓", maybe: "~", no: "✕" };

async function exportCsv() {
  if (!poll.value || !summary.value) return;
  try {
    const rows = await fetchDatepollSubmissions(props.datepollId);
    const dates = summary.value.dates;
    const header = [
      t("datepolls.details.csvName"),
      t("datepolls.details.csvSubmittedAt"),
      ...dates.map((d) => shortDate(d.on_date)),
      t("datepolls.details.csvComments"),
    ];
    const body = rows.map((s) => {
      const comments = dates
        .filter((d) => s.comments[d.id])
        .map((d) => `${shortDate(d.on_date)}: ${s.comments[d.id]}`)
        .join(" | ");
      return [
        nameOf(s),
        s.created_at,
        ...dates.map((d) => s.answers[d.id] ?? ""),
        comments,
      ];
    });
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
          <!-- Per-date tallies, winning date highlighted. -->
          <div
            v-for="d in summary.dates"
            :key="d.id"
            class="date-block"
            :class="{ best: d.id === summary.best_date_id }"
          >
            <p class="date-head">
              {{ shortDate(d.on_date) }}
              <span v-if="d.id === summary.best_date_id" class="best-badge">{{ t("datepolls.details.best") }}</span>
            </p>
            <div class="bars">
              <template v-for="kind in (['yes', 'maybe', 'no'] as const)" :key="kind">
                <span class="bar-label" :class="kind">{{ t(`datepolls.details.${kind}`) }}</span>
                <div class="bar-track">
                  <div
                    class="bar-fill"
                    :class="kind"
                    :style="{ width: barWidth([d.yes, d.maybe, d.no], d[kind]) }"
                  />
                </div>
                <span class="bar-count">{{ d[kind] }}</span>
              </template>
            </div>
            <ul v-if="d.comments?.length" class="comments">
              <li v-for="(c, i) in d.comments" :key="i">{{ c }}</li>
            </ul>
          </div>

          <!-- Per-respondent grid. -->
          <div v-if="subs.length" class="grid-wrap">
            <table class="grid">
              <thead>
                <tr>
                  <th class="who">{{ t("datepolls.details.respondent") }}</th>
                  <th v-for="d in summary.dates" :key="d.id">{{ shortDate(d.on_date) }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="s in subs" :key="s.submission_id">
                  <td class="who">{{ nameOf(s) }}</td>
                  <td
                    v-for="d in summary.dates"
                    :key="d.id"
                    class="cell"
                    :class="s.answers[d.id] ?? 'none'"
                    :title="s.comments[d.id] || undefined"
                  >
                    {{ s.answers[d.id] ? AVAIL_GLYPH[s.answers[d.id]] : "" }}<span v-if="s.comments[d.id]" class="has-comment">*</span>
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
.back-link { display: inline-block; margin-top: 0.5rem; color: var(--brand-red); }
.overview { display: flex; flex-direction: column; gap: 0.5rem; }
.overview h1 { margin: 0; overflow-wrap: anywhere; }
.description { margin: 0; }
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

.date-block { border-top: 1px solid var(--brand-border); padding-top: 1.25rem; margin-top: 1.25rem; }
.date-block:first-of-type { border-top: none; padding-top: 0; margin-top: 0; }
.date-block.best { background: rgba(31, 122, 60, 0.06); border-radius: 8px; padding: 0.75rem; }
.date-head { margin: 0 0 0.5rem; font-weight: 600; }
.best-badge {
  margin-left: 0.5rem; padding: 0.0625rem 0.5rem; border-radius: 999px;
  background: #1f7a3c; color: white; font-size: 0.6875rem; font-weight: 600;
}
.bars {
  display: grid; grid-template-columns: minmax(3.5rem, max-content) 1fr 2rem;
  align-items: center; gap: 0.3rem 0.5rem; font-size: 0.875rem;
}
.bar-label { color: var(--brand-text-muted); }
.bar-track { height: 0.625rem; background: var(--brand-border); border-radius: 999px; overflow: hidden; }
.bar-fill { height: 100%; border-radius: 999px; }
.bar-fill.yes { background: #1f7a3c; }
.bar-fill.maybe { background: #c98a00; }
.bar-fill.no { background: var(--brand-text-muted); }
.bar-count { text-align: right; color: var(--brand-text-muted); }
.comments { margin: 0.5rem 0 0; padding-left: 1.25rem; display: flex; flex-direction: column; gap: 0.25rem; }
.comments li { line-height: 1.4; }

.grid-wrap { margin-top: 1.5rem; overflow-x: auto; }
.grid { border-collapse: collapse; font-size: 0.8125rem; }
.grid th, .grid td { border: 1px solid var(--brand-border); padding: 0.25rem 0.5rem; text-align: center; white-space: nowrap; }
.grid th.who, .grid td.who { text-align: left; position: sticky; left: 0; background: var(--brand-surface); }
.cell.yes { background: rgba(31, 122, 60, 0.18); }
.cell.maybe { background: rgba(201, 138, 0, 0.18); }
.cell.no { background: rgba(0, 0, 0, 0.05); color: var(--brand-text-muted); }
.has-comment { color: var(--brand-red); font-weight: 700; }
</style>
