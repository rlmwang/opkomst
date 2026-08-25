<script setup lang="ts">
import Button from "primevue/button";
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useLocalizedText } from "@/composables/useLocalizedText";
import AppCard from "@/components/AppCard.vue";
import DetailHeaderCard from "@/components/DetailHeaderCard.vue";
import AppSkeleton from "@/components/AppSkeleton.vue";
import DetailsPageShell from "@/components/DetailsPageShell.vue";
import MonthGrid from "@/components/MonthGrid.vue";
import RecoverLinksPill, { type RecoverableRow } from "@/components/RecoverLinksPill.vue";
import StatBar from "@/components/StatBar.vue";
import type { SignupSummary } from "@/api/types";
import {
  eventList,
  useDeleteSignup,
  useEventList,
  useEventOccurrences,
  useOccurrenceSignups,
  useOccurrenceStats,
  useSendEmailsNow,
} from "@/composables/useEvents";
import { useEventClipboard } from "@/composables/useEventClipboard";
import { useGuardedMutation } from "@/composables/useGuardedMutation";
import { eventQrUrl, publicEventUrl } from "@/lib/event-urls";
import { downloadCsv } from "@/lib/csv-export";
import { filenameSlug } from "@/lib/filename-slug";
import { barWidth, formatDate, formatDateTime, formatTimeRange } from "@/lib/format";
import { mapLink } from "@/lib/map-link";
import { recurrenceHint } from "@/lib/recurrence";
import { useToasts } from "@/lib/toasts";
import { useAuthStore } from "@/stores/auth";
import {
  type EmailChannel,
  fetchFeedbackSubmissions,
  useFeedbackSummary,
} from "@/composables/useFeedback";

const props = defineProps<{ eventId: string }>();

const { t, locale } = useI18n();
const lt = useLocalizedText();
const toasts = useToasts();
const { copyLink, copyQr } = useEventClipboard();

// A personal account's event holds a bounded number of people; an
// organisation's has no ceiling, so there is no number to show.
const auth = useAuthStore();
const eventsQuery = useEventList();
const events = eventList(eventsQuery);
const event = computed(() => events.value.find((e) => e.id === props.eventId) ?? null);

const occurrencesQuery = useEventOccurrences(computed(() => props.eventId));
const occurrenceList = computed(() => occurrencesQuery.data.value ?? null);
const occurrences = computed(() => occurrenceList.value?.occurrences ?? []);
const projected = computed(() => occurrenceList.value?.projected ?? []);

// The occurrence whose public page + QR the header surfaces: the soonest
// session that hasn't ended, else the most recent one. Null while the
// occurrence list is still loading or a rolling series has none yet.
const primaryOccurrence = computed(() => {
  const list = occurrences.value;
  if (list.length === 0) return null;
  const now = Date.now();
  return list.find((o) => new Date(o.ends_at).getTime() > now) ?? list[list.length - 1];
});

const recurrenceSummary = computed(() =>
  event.value ? recurrenceHint(t, event.value) : "",
);

// --- "Aanmeldingen" calendar day switcher ---------------------------
// Occurrences keyed by their date; the calendar highlights those days,
// clicking one selects which day's sign-ups + stats show below.
const isoDate = (dt: string) => dt.slice(0, 10);
const occByIso = computed(() => {
  const m = new Map<string, (typeof occurrences.value)[number]>();
  for (const o of occurrences.value) m.set(isoDate(o.starts_at), o);
  return m;
});
const projectedIsos = computed(() => new Set(projected.value.map((p) => isoDate(p.starts_at))));

const selectedIso = ref<string | null>(null);
// Default to the primary occurrence once loaded; keep the user's pick after.
watch(primaryOccurrence, (occ) => {
  if (!selectedIso.value && occ) selectedIso.value = isoDate(occ.starts_at);
}, { immediate: true });

const selectedOccurrence = computed(() =>
  selectedIso.value ? (occByIso.value.get(selectedIso.value) ?? null) : null,
);
const selectedOccurrenceId = computed(() => selectedOccurrence.value?.id ?? null);

// The selected day's sign-ups + aggregated stats — the same content the
// card has always shown, now scoped to one occurrence.
const daySignupsQuery = useOccurrenceSignups(computed(() => props.eventId), selectedOccurrenceId);
const daySignups = computed(() => daySignupsQuery.data.value ?? []);
const dayStatsQuery = useOccurrenceStats(computed(() => props.eventId), selectedOccurrenceId);
const dayStats = computed(() => dayStatsQuery.data.value ?? null);

const deleteSignupMutation = useDeleteSignup();

// Recover rows are refetched on popover open so a just-recovered stamp is
// never stale. ``id`` is the booking (registration) id — the recover
// target — not the line-item id.
async function recoverRows(): Promise<RecoverableRow[]> {
  const fresh = (await daySignupsQuery.refetch()).data ?? [];
  return fresh.map((s) => ({
    id: s.registration_id,
    name: s.display_name,
    recoveredAt: s.link_recovered_at ?? null,
  }));
}

const askDeleteSignup = useGuardedMutation(deleteSignupMutation, (s: SignupSummary) => ({
  vars: { eventId: props.eventId, occurrenceId: selectedOccurrenceId.value ?? "", signupId: s.id },
  ok: t("event.deleteSignup.ok"),
  fail: t("event.deleteSignup.fail"),
  confirm: {
    header: t("event.deleteSignup.confirmTitle"),
    message: t("event.deleteSignup.confirmBody", { name: s.display_name ?? t("event.signupAnonymous") }),
    icon: "pi pi-exclamation-triangle",
    rejectLabel: t("common.cancel"),
    acceptLabel: t("event.deleteSignup.confirm"),
  },
}));

// Tabular layout: name | one column per help_option | party_size | delete.
const signupGridTemplate = computed(() => {
  const n = event.value?.help_options.length ?? 0;
  return n > 0 ? `minmax(0, 1fr) repeat(${n}, auto) auto auto` : "minmax(0, 1fr) auto auto";
});

// Which session the selected day is, for the caption above the breakdowns.
const selectedBadge = computed(() => {
  const occ = selectedOccurrence.value;
  const total = occurrenceList.value?.total_sessions ?? null;
  if (!occ) return "";
  return total === null
    ? t("event.occurrences.sessionOpen", { i: occ.index + 1 })
    : t("event.occurrences.sessionOf", { i: occ.index + 1, n: total });
});

const calendarMonth = ref<string | null>(null);
const shownMonth = computed({
  get: () => calendarMonth.value ?? (selectedIso.value ?? isoDate(new Date().toISOString())).slice(0, 7),
  set: (v: string) => { calendarMonth.value = v; },
});

const weekdayLabels = computed(() =>
  (["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const).map((d) => t(`chores.edit.weekday.${d}`)),
);

function dayClass(iso: string): Record<string, boolean> {
  return {
    "has-occurrence": occByIso.value.has(iso),
    selected: iso === selectedIso.value,
    projected: projectedIsos.value.has(iso),
  };
}
const dayClickable = (iso: string) => occByIso.value.has(iso);
function onDayClick(iso: string) {
  if (occByIso.value.has(iso)) selectedIso.value = iso;
}

const sendEmailsMutation = useSendEmailsNow();

const summaryQuery = useFeedbackSummary(computed(() => props.eventId));
const summary = computed(() => summaryQuery.data.value ?? null);
const triggering = ref<EmailChannel | null>(null);

// Setup-time wiring: useGuardedMutation calls inject() under the
// hood and must run during setup, not in a click handler. The
// per-channel data the spec needs (pending count, channel-specific
// confirm copy) is closed over from the click-time arg.
const triggerNow = useGuardedMutation(sendEmailsMutation, (channel: EmailChannel) => {
  const pending = channelHealth(channel)?.pending ?? 0;
  return {
    vars: { eventId: props.eventId, channel },
    ok: (r) => ({
      summary: t("event.sendNow.successTitle"),
      detail: t("event.sendNow.successBody", { n: r.processed }),
    }),
    fail: (err) =>
      err instanceof Error ? err.message : t("event.sendNow.failed"),
    confirm: {
      header: t(`event.sendNow.${channel}.confirmTitle`),
      message: t("event.sendNow.confirmBody", { n: pending }),
      icon: "pi pi-send",
      rejectLabel: t("common.cancel"),
      acceptLabel: t("event.sendNow.confirm"),
    },
  };
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
async function exportCsv() {
  if (!event.value || !summary.value) return;
  try {
    const submissions = await fetchFeedbackSubmissions(props.eventId);
    const keys = summary.value.questions.map((q) => q.key);
    const header = [t("feedback.summary.submissionId"), ...keys.map(questionPrompt)];
    const rows = submissions.map((s) => [
      s.submission_id,
      ...keys.map((k) => s.answers[k] ?? ""),
    ]);
    // ``{YYYY-MM-DD}-{name-slug}-{entity-id}.csv`` — date first so
    // the file sorts chronologically next to other event exports;
    // entity id last as the canonical disambiguator.
    const date = event.value.starts_on;
    const slug = filenameSlug(lt(event.value.name_nl, event.value.name_en) ?? "");
    downloadCsv(`${date}-${slug}-${event.value.id}.csv`, [header, ...rows]);
  } catch {
    toasts.error(t("feedback.summary.csvFail"));
  }
}

const CHANNELS: EmailChannel[] = ["reminder", "feedback"];
const HEALTH_KEYS = ["sent", "not_applicable", "pending", "failed"] as const;

function channelEnabled(channel: EmailChannel): boolean {
  if (!event.value) return false;
  return channel === "reminder"
    ? event.value.reminder_enabled
    : event.value.feedback_enabled;
}

function channelHealth(channel: EmailChannel) {
  return summary.value?.email_health[channel];
}

function canTrigger(channel: EmailChannel): boolean {
  if (!event.value || !summary.value) return false;
  if (!channelEnabled(channel)) return false;
  return (channelHealth(channel)?.pending ?? 0) > 0;
}

function triggerDisabledReason(channel: EmailChannel): string {
  if (!event.value) return "";
  if (!channelEnabled(channel)) return t("event.sendNow.disabledOff");
  if ((channelHealth(channel)?.pending ?? 0) === 0) {
    return t("event.sendNow.disabledNothingPending");
  }
  return "";
}

function askTriggerNow(channel: EmailChannel) {
  if (!event.value) return;
  triggering.value = channel;
  triggerNow(channel).finally(() => {
    triggering.value = null;
  });
}
</script>

<template>
  <!-- Only block render on ``event`` itself: it usually lives in
       the events-list cache when arriving from the dashboard, so
       the overview paints immediately. ``stats`` / ``summary``
       each show a localised skeleton inside their own card —
       the page no longer waits on the slowest fetch. -->
  <DetailsPageShell :loaded="!!event" :skeleton-rows="4">
    <template v-if="event">
<DetailHeaderCard
        :title="lt(event.name_nl, event.name_en) ?? ''"
        :chapter-name="event.chapter_name"
        :image-url="event.image_url"
        :image-artist="event.image_artist_instagram"
        :image-href="event.image_url"
        :description-html="lt(event.topic_nl, event.topic_en)"
        :qr-src="eventQrUrl(primaryOccurrence?.slug ?? '')"
        :public-url="primaryOccurrence ? publicEventUrl(primaryOccurrence.slug) : ''"
        :edit-to="`/events/${event.id}/edit`"
        @copy-qr="primaryOccurrence && copyQr(primaryOccurrence.slug)"
        @copy-link="primaryOccurrence && copyLink(primaryOccurrence.slug)"
      >
        <template #meta>
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
            · {{ recurrenceSummary }}
            <template v-if="event.next_starts_at">
              · {{ t("event.nextSession") }} {{ formatDateTime(event.next_starts_at, locale) }}
            </template>
          </p>
        </template>
      </DetailHeaderCard>

      <AppCard>
        <div class="summary-header">
          <h2>{{ t("event.signupsHeading") }}</h2>
          <div class="header-actions">
            <!-- The pill counts the selected session; the ceiling is on
                 the event as a whole, so it is stated separately rather
                 than folded into a number it doesn't bound. -->
            <span v-if="auth.user?.participant_cap != null && event" class="muted">
              {{ t("event.capUsage", { n: event.attendee_count, cap: auth.user.participant_cap }) }}
            </span>
            <RecoverLinksPill
              v-if="selectedOccurrence"
              :count="selectedOccurrence.attendee_count"
              :label="t('event.totalAttendees')"
              :load-rows="recoverRows"
              :recover-path="(id: string) => `/api/v1/events/${props.eventId}/registrations/${id}/edit-link`"
              :public-url="(tok: string) => `${publicEventUrl(selectedOccurrence!.slug)}?s=${tok}`"
            />
          </div>
        </div>

        <AppSkeleton v-if="!occurrenceList" :rows="3" />
        <template v-else>
          <p v-if="occurrences.length === 0 && projected.length === 0" class="muted">
            {{ t("event.occurrences.none") }}
          </p>

          <!-- A recurring event: a calendar of its sessions across the
               top. Clicking a highlighted day switches which day's sign-ups
               + stats show below, in the same format as a one-off. -->
          <MonthGrid
            v-if="event.cycle_slots.length > 0 && occurrences.length > 0"
            v-model:month="shownMonth"
            :locale="locale"
            :weekdays="weekdayLabels"
            :day-class="dayClass"
            :clickable="dayClickable"
            :prev-label="t('event.occurrences.prevMonth')"
            :next-label="t('event.occurrences.nextMonth')"
            @day-click="onDayClick"
          />

          <template v-if="selectedOccurrence">
            <p v-if="event.cycle_slots.length > 0" class="day-caption">
              <span class="day-date">{{ formatDate(selectedOccurrence.starts_at, locale) }}</span>
              <span class="muted">· {{ formatTimeRange(selectedOccurrence.starts_at, selectedOccurrence.ends_at, locale) }}</span>
              <span class="day-badge">{{ selectedBadge }}</span>
            </p>

            <template v-if="dayStats">
              <div v-if="Object.keys(dayStats.by_help).length > 0" class="subgroup">
                <h3 class="subhead">{{ t("event.byHelp") }}</h3>
                <div v-for="(count, opt) in dayStats.by_help" :key="opt" class="list-row">
                  <span class="list-row-label">{{ opt }}</span>
                  <span class="row-count">{{ count }}</span>
                </div>
              </div>
              <div v-if="Object.keys(dayStats.by_source).length > 0" class="subgroup">
                <h3 class="subhead">{{ t("event.bySource") }}</h3>
                <div v-for="(count, src) in dayStats.by_source" :key="src" class="list-row">
                  <span class="list-row-label">{{ src }}</span>
                  <span class="row-count">{{ count }}</span>
                </div>
              </div>
            </template>

            <details v-if="daySignups.length > 0" class="subgroup signup-list">
              <summary class="subhead">{{ t("event.signupList") }}</summary>
              <div class="signup-grid" :style="{ gridTemplateColumns: signupGridTemplate }">
                <div v-for="s in daySignups" :key="s.id" class="signup-row">
                  <span class="signup-name">{{ s.display_name ?? t("event.signupAnonymous") }}</span>
                  <span v-for="opt in event.help_options" :key="opt" class="help-cell">
                    <span v-if="s.help_choices.includes(opt)" class="help-chip">{{ opt }}</span>
                  </span>
                  <span class="row-count signup-count">{{ s.party_size }}</span>
                  <Button
                    icon="pi pi-trash"
                    size="small"
                    severity="secondary"
                    text
                    class="signup-delete"
                    v-tooltip.top="t('event.deleteSignup.title')"
                    :aria-label="t('event.deleteSignup.title')"
                    @click="askDeleteSignup(s)"
                  />
                </div>
              </div>
            </details>
            <p v-else class="muted">{{ t("event.occurrences.noSignups") }}</p>
          </template>

          <!-- Beyond-horizon dates: shown for context, no page yet,
               so not sign-up-able and read-only here. -->
          <div v-if="projected.length > 0" class="subgroup projected">
            <h3 class="subhead">{{ t("event.occurrences.projectedHeading") }}</h3>
            <div v-for="p in projected" :key="p.index" class="list-row">
              <span class="list-row-label">
                {{ formatDate(p.starts_at, locale) }}
                <span class="muted">· {{ formatTimeRange(p.starts_at, p.ends_at, locale) }}</span>
              </span>
              <span class="muted projected-badge">
                {{ occurrenceList.total_sessions === null
                  ? t("event.occurrences.sessionOpen", { i: p.index + 1 })
                  : t("event.occurrences.sessionOf", { i: p.index + 1, n: occurrenceList.total_sessions }) }}
              </span>
            </div>
          </div>
        </template>
      </AppCard>

      <AppCard>
        <div class="summary-header">
          <h2>{{ t("feedback.summary.title") }}</h2>
          <div class="header-actions">
            <Button
              :label="t('feedback.summary.exportCsv')"
              size="small"
              severity="secondary"
              text
              icon="pi pi-download"
              :disabled="!summary || summary.submission_count === 0"
              @click="exportCsv"
            />
            <a
              v-if="event"
              :href="`/e/${event.slug}/feedback?t=preview`"
              target="_blank"
              rel="noopener"
            >
              <Button :label="t('feedback.preview.open')" size="small" severity="secondary" text icon="pi pi-eye" />
            </a>
          </div>
        </div>
        <p v-if="!summary || summary.submission_count === 0" class="muted">
          {{ t("feedback.summary.noResponsesYet") }}
        </p>
        <template v-else>
          <p>{{ responsesLine }}</p>
          <div v-for="q in summary.questions" :key="q.key" class="q-block">
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
                  <StatBar :segments="[{ width: barWidth(q.rating_distribution, q.rating_distribution[i - 1]) }]" />
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

      <!-- One card per channel, each combining delivery health
           with a "send now" button. Order is chronological: the
           reminder fires before the event, feedback fires after.
           Pills explain delivery state at a glance; the button
           below lets the organiser fire that channel manually
           for any signups still ``pending``. -->
      <template v-if="summary">
        <AppCard v-for="channel in CHANNELS" :key="channel">
          <h2>{{ t(`event.sendNow.${channel}.title`) }}</h2>
          <p class="muted">{{ t(`event.sendNow.${channel}.explainer`) }}</p>
          <div class="email-health">
            <div
              v-for="key in HEALTH_KEYS"
              :key="key"
              class="health-pill"
              :class="`health-${key}`"
              v-tooltip.top="t(`feedback.email.tooltips.${channel}.${key}`)"
            >
              <span class="count">{{ channelHealth(channel)?.[key] ?? 0 }}</span>
              <span class="label">{{ t(`feedback.email.${key}`) }}</span>
            </div>
          </div>
          <p v-if="triggerDisabledReason(channel)" class="muted small">
            {{ triggerDisabledReason(channel) }}
          </p>
          <div class="send-now-row">
            <Button
              :label="t(`event.sendNow.${channel}.button`)"
              icon="pi pi-send"
              :disabled="!canTrigger(channel) || triggering !== null"
              :loading="triggering === channel"
              @click="askTriggerNow(channel)"
            />
          </div>
        </AppCard>
      </template>
    </template>
  </DetailsPageShell>
</template>

<style scoped>
/* The overview header (title + image + meta + description + URL + QR +
 * edit) is the shared ``DetailHeaderCard``. Signups + feedback card
 * headers use the shared .summary-header /
 * .header-actions + .count-pill from theme.css. */
.subhead {
  /* Calm h3 — same family/weight/colour as the card's h2, just a
   * step smaller. Keeps the card to one heading style instead of
   * mixing an h2 with an uppercase muted small-caps label. */
  margin: 0.5rem 0 0.25rem;
  font-size: 1rem;
  font-weight: 600;
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
/* Calendar day-switcher: highlight the event's session days, fill the
 * selected one, mute beyond-horizon projected dates. Cells live inside
 * MonthGrid, so reach them with :deep. */
:deep(.mg-cell.has-occurrence) {
  background: var(--brand-bg);
  border-color: var(--brand-border);
  font-weight: 600;
}
:deep(.mg-cell.projected) {
  color: var(--brand-text-muted);
  border-style: dashed;
}
:deep(.mg-cell.selected) {
  background: var(--brand-red);
  border-color: var(--brand-red);
}
:deep(.mg-cell.selected .mg-num) { color: #fff; }

/* Which day the breakdowns + list below belong to (recurring only). */
.day-caption {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
  margin: 0.75rem 0 0;
}
.day-date { font-weight: 600; }
.day-badge {
  margin-left: auto;
  font-size: 0.75rem;
  padding: 0.1rem 0.5rem;
  border-radius: 0.75rem;
  background: var(--brand-bg);
  color: var(--brand-text-muted);
  white-space: nowrap;
}

/* Signup list — a single foldable of the day's attendees, identical to
 * the original event card (name | one column per help_option | count |
 * delete). */
.signup-list summary {
  cursor: pointer;
  user-select: none;
  list-style: none;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.signup-list summary::-webkit-details-marker { display: none; }
.signup-list summary::before {
  content: "›";
  display: inline-block;
  transition: transform 120ms ease-out;
  color: var(--brand-text-muted);
}
.signup-list[open] > summary::before { transform: rotate(90deg); }
.signup-grid {
  display: grid;
  column-gap: 0.5rem;
}
.signup-row {
  display: grid;
  grid-template-columns: subgrid;
  grid-column: 1 / -1;
  align-items: center;
  gap: 0.5rem;
  padding: 0.375rem 0.5rem;
  border-radius: 6px;
  transition: background 120ms ease;
}
.signup-row:hover { background: var(--brand-bg); }
.signup-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.help-cell {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  min-width: 0;
}
.help-chip {
  font-size: 0.75rem;
  padding: 0.05rem 0.4rem;
  border-radius: 0.75rem;
  background: var(--brand-surface-muted, rgba(0, 0, 0, 0.05));
  color: var(--brand-text-muted);
  white-space: nowrap;
}
.signup-count { text-align: right; }
.projected { margin-top: 0.5rem; }
.projected-badge {
  font-size: 0.75rem;
  white-space: nowrap;
}

/* --- Feedback card ------------------------------------------------- */
/* Each q-block sits between two horizontal separators with
 * symmetric breathing room on both sides — 1.5rem of space above
 * and below the rule so the questionnaire reads as discrete
 * sections instead of one dense run-on. */
.q-block {
  border-top: 1px solid var(--brand-border);
  padding-top: 1.5rem;
  margin-top: 1.5rem;
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
.bar-count { text-align: right; color: var(--brand-text-muted); }
.texts {
  margin: 0;
  padding-left: 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}
.texts li { line-height: 1.45; white-space: pre-line; }

/* --- Email-delivery card ------------------------------------------ */
/* Six chips, one per delivery state, in equal-width grid columns so
 * the row reads as a uniform breakdown rather than a ragged wrap. */
.email-health {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 0.5rem;
  margin: 0.75rem 0;
}
.send-now-row {
  margin-top: 0.5rem;
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
.health-pending { background: var(--brand-amber-wash); border-color: var(--brand-notice-border); }
.health-pending .count { color: var(--brand-amber-text); }
.health-failed {
  background: var(--brand-red-soft);
  border-color: var(--brand-red-soft-border);
}
.health-failed .count {
  color: var(--brand-red);
}
.health-not_applicable .count { color: var(--brand-text-muted); }

.small { font-size: 0.875rem; }

/* Mobile fallbacks. ``480px`` is the project-wide phone
 * breakpoint (matches AppHeader, PublicEventPage). The 6-column
 * delivery-chip grid is too tight below ~480px (~62 px / chip
 * compresses the count + label), so collapse to 3 columns. The
 * overview body's ``1fr auto`` grid leaves only ~270 px for the
 * URL+copy row alongside a 96 px QR — stack the QR underneath
 * the text instead, so the URL gets full width. */
@media (max-width: 480px) {
  .email-health {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
</style>
