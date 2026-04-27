<script setup lang="ts">
import Button from "primevue/button";
import { computed, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import AppCard from "@/components/AppCard.vue";
import AppHeader from "@/components/AppHeader.vue";
import AppSkeleton from "@/components/AppSkeleton.vue";
import { ApiError } from "@/api/client";
import { useEventClipboard } from "@/composables/useEventClipboard";
import { useConfirms } from "@/lib/confirms";
import { eventQrUrl, publicEventUrl } from "@/lib/event-urls";
import { formatDateTime } from "@/lib/format";
import { mapLink } from "@/lib/map-link";
import { useToasts } from "@/lib/toasts";
import {
  type EventOut,
  type EventStats,
  type SignupSummary,
  useEventsStore,
} from "@/stores/events";
import { type FeedbackSummary, useFeedbackStore } from "@/stores/feedback";

const props = defineProps<{ eventId: string }>();

const { t, locale } = useI18n();
const events = useEventsStore();
const feedback = useFeedbackStore();
const confirms = useConfirms();
const toasts = useToasts();
const { copyLink, copyQr } = useEventClipboard();

const event = ref<EventOut | null>(null);
const stats = ref<EventStats | null>(null);
const signups = ref<SignupSummary[]>([]);
const summary = ref<FeedbackSummary | null>(null);
const triggering = ref(false);

onMounted(async () => {
  if (events.all.length === 0) await events.fetchAll();
  event.value = events.all.find((e: EventOut) => e.id === props.eventId) ?? null;
  const [s, sg, fs] = await Promise.all([
    events.getStats(props.eventId),
    events.getSignups(props.eventId).catch(() => [] as SignupSummary[]),
    feedback.getSummary(props.eventId).catch(() => null),
  ]);
  stats.value = s;
  signups.value = sg;
  summary.value = fs;
});

const responsesLine = computed(() => {
  if (!summary.value) return "";
  const rate = `${Math.round(summary.value.response_rate * 100)}%`;
  return t("feedback.summary.responsesOf", {
    responses: summary.value.submission_count,
    signups: summary.value.signup_count,
    rate,
  });
});

function questionPrompt(key: string): string {
  return t(`feedback.questions.${key}.prompt`);
}

// --- CSV export ----------------------------------------------------
// One row per submission. Columns: submission id + one per question
// (in the same ordinal order the questionnaire asks them). Question
// headers are the localised prompts so an organiser opening the CSV
// in their language gets readable headers without joining to the
// questions table.
function csvEscape(v: unknown): string {
  const s = String(v ?? "");
  if (/[",\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
  return s;
}

// File-system-safe slug: lowercase, ASCII-ish, dashes only — strips
// punctuation that some operating systems refuse in filenames and
// trims runs of dashes so the result reads cleanly.
function _filenameSlug(value: string): string {
  return value
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60);
}

async function downloadCsv() {
  if (!event.value || !summary.value) return;
  try {
    const submissions = await feedback.getSubmissions(props.eventId);
    const keys = summary.value.questions.map((q) => q.key);
    const header = [t("feedback.summary.submissionId"), ...keys.map(questionPrompt)];
    const rows = submissions.map((s) => [
      s.submission_id,
      ...keys.map((k) => s.answers[k] ?? ""),
    ]);
    const csv = [header, ...rows].map((r) => r.map(csvEscape).join(",")).join("\n");
    // BOM so Excel reads UTF-8 correctly (otherwise Dutch diacritics
    // mojibake on Windows).
    const blob = new Blob(["﻿", csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    // ``{YYYY-MM-DD}-{name-slug}-{entity-id}.csv`` — date first so
    // the file sorts chronologically next to other event exports;
    // entity id last as the canonical disambiguator.
    const date = event.value.starts_at.slice(0, 10);
    const slug = _filenameSlug(event.value.name);
    a.download = `${date}-${slug}-${event.value.id}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  } catch {
    toasts.error(t("feedback.summary.csvFail"));
  }
}

function bar(distribution: number[], idx: number): { width: string; count: number } {
  const max = Math.max(...distribution, 1);
  return { width: `${Math.round((distribution[idx] / max) * 100)}%`, count: distribution[idx] };
}

const canTriggerNow = computed(() => {
  if (!event.value || !summary.value) return false;
  if (!event.value.questionnaire_enabled) return false;
  return summary.value.email_health.pending > 0;
});

const triggerDisabledReason = computed(() => {
  if (!event.value) return "";
  if (!event.value.questionnaire_enabled) return t("event.sendNow.disabledOff");
  if (summary.value && summary.value.email_health.pending === 0) {
    return t("event.sendNow.disabledNothingPending");
  }
  return "";
});

async function refreshSummary() {
  summary.value = await feedback.getSummary(props.eventId).catch(() => summary.value);
}

function askTriggerNow() {
  if (!event.value) return;
  confirms.ask({
    header: t("event.sendNow.confirmTitle"),
    message: t("event.sendNow.confirmBody", {
      n: summary.value?.email_health.pending ?? 0,
    }),
    icon: "pi pi-send",
    rejectLabel: t("common.cancel"),
    acceptLabel: t("event.sendNow.confirm"),
    accept: async () => {
      triggering.value = true;
      try {
        const r = await events.sendFeedbackEmailsNow(props.eventId);
        toasts.success(t("event.sendNow.successTitle"), {
          detail: t("event.sendNow.successBody", { n: r.processed }),
        });
        await refreshSummary();
      } catch (e) {
        const msg = e instanceof ApiError ? e.message : t("event.sendNow.failed");
        toasts.error(msg);
      } finally {
        triggering.value = false;
      }
    },
  });
}

const HEALTH_KEYS = ["sent", "not_applicable", "pending", "bounced", "complaint", "failed"] as const;
</script>

<template>
  <AppHeader />
  <div class="container stack">
    <AppSkeleton v-if="!event || !stats" :rows="4" cards />

    <template v-else>
      <!-- Overview: title spans the full width on top so a long
           event name has the whole container to wrap into. The
           meta line, URL + copy, and the QR sit side-by-side on
           the next row (QR on the right, starting from the meta).
           The edit button gets its own line below, left-aligned. -->
      <div class="overview">
        <h1>{{ event.name }}</h1>
        <div class="overview-body">
          <div class="overview-text">
            <p class="muted overview-meta">
              <a
                :href="mapLink({
                  location: event.location,
                  latitude: event.latitude,
                  longitude: event.longitude,
                })"
                target="_blank"
                rel="noopener"
                class="meta-link"
              >{{ event.location }}</a>
              · {{ formatDateTime(event.starts_at, locale) }}
            </p>
            <div class="link-row">
              <a :href="publicEventUrl(event.slug)" target="_blank" rel="noopener">
                {{ publicEventUrl(event.slug) }}
              </a>
              <Button
                icon="pi pi-copy"
                size="small"
                severity="secondary"
                text
                v-tooltip.top="t('event.share.copyLink')"
                :aria-label="t('event.share.copyLink')"
                @click="copyLink(event.slug)"
              />
            </div>
            <div>
              <router-link :to="`/events/${event.id}/edit`">
                <Button :label="t('common.edit')" icon="pi pi-pencil" size="small" severity="secondary" />
              </router-link>
            </div>
          </div>
          <button
            type="button"
            class="qr-button"
            v-tooltip.top="t('event.share.copyQr')"
            :aria-label="t('event.share.copyQr')"
            @click="copyQr(event.slug)"
          >
            <img :src="eventQrUrl(event.slug)" alt="" class="qr" />
          </button>
        </div>
      </div>

      <AppCard>
        <div class="signups-header">
          <h2>{{ t("event.signupsTitle") }}</h2>
          <div class="totals">
            <div class="total-pill">
              <span class="count">{{ stats.total_signups }}</span>
              <span class="label">{{ t("event.totalSignups") }}</span>
            </div>
            <div class="total-pill">
              <span class="count">{{ stats.total_attendees }}</span>
              <span class="label">{{ t("event.totalAttendees") }}</span>
            </div>
          </div>
        </div>

        <div v-if="Object.keys(stats.by_source).length > 0" class="subgroup">
          <h3 class="subhead">{{ t("event.bySource") }}</h3>
          <div v-for="(count, src) in stats.by_source" :key="src" class="list-row">
            <span class="list-row-label">{{ src }}</span>
            <span class="row-count">{{ count }}</span>
          </div>
        </div>

        <div v-if="stats.by_help && Object.keys(stats.by_help).length > 0" class="subgroup">
          <h3 class="subhead">{{ t("event.byHelp") }}</h3>
          <div v-for="(count, opt) in stats.by_help" :key="opt" class="list-row">
            <span class="list-row-label">{{ opt }}</span>
            <span class="row-count">{{ count }}</span>
          </div>
        </div>

        <details v-if="signups.length > 0" class="subgroup signup-list">
          <summary class="subhead">{{ t("event.signupList") }}</summary>
          <div v-for="(s, i) in signups" :key="i" class="list-row signup-row">
            <span class="list-row-label">{{ s.display_name ?? t("event.signupAnonymous") }}</span>
            <span v-if="s.help_choices.length > 0" class="help-chips">
              <span
                v-for="opt in s.help_choices"
                :key="opt"
                class="help-chip"
              >{{ opt }}</span>
            </span>
            <span class="row-count">{{ s.party_size }}</span>
          </div>
        </details>
      </AppCard>

      <AppCard>
        <div class="feedback-header">
          <h2>{{ t("feedback.summary.title") }}</h2>
          <div class="feedback-actions">
            <Button
              :label="t('feedback.summary.exportCsv')"
              size="small"
              severity="secondary"
              text
              icon="pi pi-download"
              :disabled="!summary || summary.submission_count === 0"
              @click="downloadCsv"
            />
            <router-link to="/questionnaire">
              <Button :label="t('feedback.preview.open')" size="small" severity="secondary" text icon="pi pi-eye" />
            </router-link>
          </div>
        </div>
        <p v-if="!summary || summary.submission_count === 0" class="muted">
          {{ t("feedback.summary.noResponsesYet") }}
        </p>
        <template v-else>
          <p>{{ responsesLine }}</p>
          <div v-for="q in summary.questions" :key="q.question_id" class="q-block">
            <p class="q-prompt">{{ questionPrompt(q.key) }}</p>
            <template v-if="q.kind === 'rating' && q.rating_distribution">
              <p class="muted q-meta">
                {{ t("feedback.summary.responses", { n: q.response_count }) }}
                <template v-if="q.rating_average">
                  · {{ t("feedback.summary.average", { avg: q.rating_average.toFixed(1) }) }}
                </template>
              </p>
              <div class="bars">
                <div v-for="i in 5" :key="i" class="bar-row">
                  <span class="bar-label">{{ i }}</span>
                  <div class="bar-track">
                    <div class="bar-fill" :style="{ width: bar(q.rating_distribution, i - 1).width }" />
                  </div>
                  <span class="bar-count">{{ q.rating_distribution[i - 1] }}</span>
                </div>
              </div>
            </template>
            <template v-else-if="q.kind === 'text'">
              <p v-if="!q.texts || q.texts.length === 0" class="muted q-meta">
                {{ t("feedback.summary.noTextResponses") }}
              </p>
              <ul v-else class="texts">
                <li v-for="(txt, i) in q.texts" :key="i">{{ txt }}</li>
              </ul>
            </template>
          </div>
        </template>
      </AppCard>

      <!-- Email-delivery health follows the feedback card so it
           contextualises the response numbers above (a low response
           rate is easier to read with the bounce / complaint counts
           visible right next to it). -->
      <AppCard v-if="summary">
        <h2>{{ t("feedback.email.title") }}</h2>
        <p class="muted">{{ t("feedback.email.explainer") }}</p>
        <div class="email-health">
          <div
            v-for="key in HEALTH_KEYS"
            :key="key"
            class="health-pill"
            :class="`health-${key}`"
            v-tooltip.top="t(`feedback.email.tooltips.${key}`)"
          >
            <span class="count">{{ summary.email_health[key] }}</span>
            <span class="label">{{ t(`feedback.email.${key}`) }}</span>
          </div>
        </div>
      </AppCard>

      <AppCard>
        <h2>{{ t("event.sendNow.title") }}</h2>
        <p>{{ t("event.sendNow.explainer") }}</p>
        <p v-if="triggerDisabledReason" class="muted small">{{ triggerDisabledReason }}</p>
        <div>
          <Button
            :label="t('event.sendNow.button')"
            icon="pi pi-send"
            :disabled="!canTriggerNow || triggering"
            :loading="triggering"
            @click="askTriggerNow"
          />
        </div>
      </AppCard>
    </template>
  </div>
</template>

<style scoped>
/* --- Overview (title + meta + URL + QR + edit) -------------------- */
.overview {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.overview h1 {
  margin: 0;
  /* Long names wrap mid-word rather than overflow. */
  overflow-wrap: anywhere;
}
/* Body row: meta + URL+copy on the left, QR on the right. The QR
 * starts at the same vertical position as the meta line. */
.overview-body {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 1rem;
  align-items: start;
}
.overview-text {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  min-width: 0;
}
.overview-meta {
  margin: 0;
}
/* The URL takes its natural width (truncated with an ellipsis if
 * it can't fit the column) with the copy button glued to its right;
 * leftover space falls clear of the QR. */
.link-row {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  min-width: 0;
}
.link-row a {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.qr-button {
  background: none;
  border: none;
  padding: 0;
  cursor: pointer;
  flex-shrink: 0;
}
.qr-button:focus-visible {
  outline: 2px solid var(--brand-red);
  outline-offset: 2px;
  border-radius: 8px;
}
.qr {
  width: 96px;
  height: 96px;
  background: white;
  border: 1px solid var(--brand-border);
  border-radius: 6px;
  padding: 0.375rem;
  display: block;
}

/* --- Signups card -------------------------------------------------- */
/* Signups card header: title left, totals chips top-right. The
 * chips re-flow below the title on narrow viewports via flex-wrap. */
.signups-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
}
.totals {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}
.total-pill {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.125rem;
  padding: 0.5rem 1rem;
  border-radius: 8px;
  border: 1px solid var(--brand-border);
  background: var(--brand-bg);
  min-width: 5rem;
}
.total-pill .count {
  font-weight: 700;
  font-size: 1.25rem;
  line-height: 1;
  color: var(--brand-red);
}
.total-pill .label {
  font-size: 0.75rem;
  color: var(--brand-text-muted);
}
.subhead {
  /* Breathing room above the section title. The card's ``stack``
   * already provides 0.75rem between siblings; add 0.25rem on top
   * for an extra rest stop before the new sub-section. */
  margin: 0.25rem 0 0.25rem;
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--brand-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
/* Group a subhead with its rows so they sit tight together (the
 * card's stack would put a 0.75rem gap between them otherwise). */
.subgroup {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.row-count {
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  color: var(--brand-red);
  min-width: 1.5rem;
  text-align: right;
}
/* Foldable individual-signup list — same layout as the other
 * subgroups; the <summary> takes the .subhead role and renders as
 * a click target. The list-row inside still spaces out at .25rem. */
.signup-list summary {
  cursor: pointer;
  user-select: none;
  list-style: none;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.signup-list summary::-webkit-details-marker {
  display: none;
}
.signup-list summary::before {
  content: "›";
  display: inline-block;
  transition: transform 120ms ease-out;
  color: var(--brand-text-muted);
}
.signup-list[open] > summary::before {
  transform: rotate(90deg);
}
/* Each row of the signup list: name on the left, optional
 * help-chips next to the name, party_size right-aligned. */
.signup-row {
  align-items: center;
}
.help-chips {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 0.25rem;
  margin-left: 0.5rem;
}
.help-chip {
  font-size: 0.75rem;
  padding: 0.05rem 0.4rem;
  border-radius: 0.75rem;
  background: var(--brand-surface-muted, rgba(0, 0, 0, 0.05));
  color: var(--brand-text-muted);
  white-space: nowrap;
}

/* --- Feedback card ------------------------------------------------- */
.feedback-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.feedback-actions {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}
.q-block {
  border-top: 1px solid var(--brand-border);
  padding-top: 0.75rem;
  margin-top: 0.25rem;
}
.q-block:first-of-type {
  border-top: none;
  padding-top: 0;
  margin-top: 0;
}
.q-prompt { margin: 0 0 0.5rem; font-weight: 600; }
.q-meta { margin: 0 0 0.5rem; }
.bars { display: flex; flex-direction: column; gap: 0.25rem; }
.bar-row {
  display: grid;
  grid-template-columns: 1.25rem 1fr 2.5rem;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
}
.bar-label { color: var(--brand-text-muted); }
.bar-track {
  height: 0.625rem;
  background: var(--brand-border);
  border-radius: 999px;
  overflow: hidden;
}
.bar-fill { height: 100%; background: var(--brand-red); border-radius: 999px; }
.bar-count { text-align: right; color: var(--brand-text-muted); }
.texts {
  margin: 0;
  padding-left: 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}
.texts li { line-height: 1.45; }

/* --- Email-delivery card ------------------------------------------ */
/* Six chips, one per delivery state, in equal-width grid columns so
 * the row reads as a uniform breakdown rather than a ragged wrap. */
.email-health {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 0.5rem;
}
.health-pill {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
  align-items: center;
  justify-content: center;
  padding: 0.5rem 0.5rem;
  border-radius: 8px;
  border: 1px solid var(--brand-border);
  background: var(--brand-bg);
  cursor: help;
}
.health-pill .count { font-weight: 700; font-size: 1.0625rem; line-height: 1; }
.health-pill .label { font-size: 0.75rem; color: var(--brand-text-muted); }
.health-sent { background: var(--brand-surface); border-color: var(--brand-border); }
.health-sent .count { color: var(--brand-red); }
.health-pending { background: #fdf3d8; border-color: #ead9b3; }
.health-pending .count { color: #8a6915; }
.health-bounced, .health-failed, .health-complaint {
  background: #fbdadc;
  border-color: #f5b0b4;
}
.health-bounced .count, .health-failed .count, .health-complaint .count {
  color: #9f000b;
}
.health-not_applicable .count { color: var(--brand-text-muted); }

.small { font-size: 0.875rem; }

/* Mobile fallbacks: the 6-column delivery-chip grid is too tight
 * below ~520px (~85px / chip), so collapse to 3 columns. The
 * overview body keeps stacking via its existing flex; the QR
 * shrinks one notch so the grid still has room for the URL row. */
@media (max-width: 520px) {
  .email-health {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  .qr {
    width: 80px;
    height: 80px;
  }
}
</style>
