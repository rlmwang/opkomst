<script lang="ts">
import AppButton from "@/components/AppButton.svelte";
import AppCard from "@/components/AppCard.svelte";
import AppSkeleton from "@/components/AppSkeleton.svelte";
import DetailHeaderCard from "@/components/DetailHeaderCard.svelte";
import DetailsPageShell from "@/components/DetailsPageShell.svelte";
import EventMetaLines from "@/components/EventMetaLines.svelte";
import MonthGrid from "@/components/MonthGrid.svelte";
import RecoverLinksPill, { type RecoverableRow } from "@/components/RecoverLinksPill.svelte";
import StatBar from "@/components/StatBar.svelte";
import {
  deleteSignup,
  events,
  occurrenceSignupsQuery,
  occurrenceStatsQuery,
  occurrencesQuery,
  sendEmailsNow,
} from "@/composables/useEvents.svelte";
import {
  type EmailChannel,
  feedbackSummaryQuery,
} from "@/composables/useFeedback.svelte";
import { guarded } from "@/composables/useGuardedMutation.svelte";
import { lt } from "@/composables/useLocalizedText.svelte";
import { shareClipboard } from "@/composables/useShareClipboard.svelte";
import { locale, t } from "@/i18n.svelte";
import { downloadFile } from "@/lib/download";
import { eventQrUrl, publicEventUrl } from "@/lib/event-urls";
import { barWidth, formatAverage, formatDate, formatTimeRange } from "@/lib/format";
import { tip } from "@/lib/tooltip";
import { useToasts } from "@/lib/toasts";
import { auth } from "@/stores/auth.svelte";
import type { SignupSummary } from "@/api/types";

/**
 * An event, as the organiser reads it: who signed up for which session,
 * what the day-after questionnaire came back with, and whether the mail
 * it owes has gone out.
 */
const { eventId }: { eventId: string } = $props();

const toasts = useToasts();
const share = shareClipboard({
  publicUrlFor: publicEventUrl,
  qrUrlFor: eventQrUrl,
  copyPrefix: "event.share",
});

const eventQuery = events.single(() => eventId);
const event = $derived(eventQuery.data ?? null);

const occQuery = occurrencesQuery(() => eventId);
const occurrenceList = $derived(occQuery.data ?? null);
const occurrences = $derived(occurrenceList?.occurrences ?? []);
const projected = $derived(occurrenceList?.projected ?? []);

/** The session the header's public page and QR point at: the soonest
 *  one that has not ended, else the last one that ran. */
const primary = $derived.by(() => {
  if (occurrences.length === 0) return null;
  const now = Date.now();
  return (
    occurrences.find((o) => new Date(o.ends_at).getTime() > now) ??
    occurrences[occurrences.length - 1]
  );
});

// --- Which day the sign-ups below belong to --------------------------
const isoDate = (dt: string) => dt.slice(0, 10);
const occByIso = $derived(new Map(occurrences.map((o) => [isoDate(o.starts_at), o])));
const projectedIsos = $derived(new Set(projected.map((p) => isoDate(p.starts_at))));

let selectedIso = $state<string | null>(null);
// Opens on the primary session, and stays wherever the organiser puts
// it afterwards.
$effect(() => {
  if (!selectedIso && primary) selectedIso = isoDate(primary.starts_at);
});

const selectedOccurrence = $derived(selectedIso ? (occByIso.get(selectedIso) ?? null) : null);
const selectedOccurrenceId = $derived(selectedOccurrence?.id ?? null);

const signupsQuery = occurrenceSignupsQuery(
  () => eventId,
  () => selectedOccurrenceId,
);
const daySignups = $derived(signupsQuery.data ?? []);
const statsQuery = occurrenceStatsQuery(
  () => eventId,
  () => selectedOccurrenceId,
);
const dayStats = $derived(statsQuery.data ?? null);

const removeSignup = deleteSignup();

/** Asked again each time the popover opens, so a stamp from a moment
 *  ago is never stale. The id is the booking's, which is what a
 *  recovery link is minted against, not the line item's. */
async function recoverRows(): Promise<RecoverableRow[]> {
  const fresh = (await signupsQuery.refetch()) ?? [];
  return fresh.map((s) => ({
    id: s.registration_id,
    name: s.display_name,
    recoveredAt: s.link_recovered_at ?? null,
  }));
}

const askDeleteSignup = guarded(removeSignup.run, (s: SignupSummary) => ({
  vars: { eventId, occurrenceId: selectedOccurrenceId ?? "", signupId: s.id },
  ok: t("event.deleteSignup.ok"),
  fail: t("event.deleteSignup.fail"),
  confirm: {
    header: t("event.deleteSignup.confirmTitle"),
    message: t("event.deleteSignup.confirmBody", {
      name: s.display_name ?? t("event.signupAnonymous"),
    }),
    icon: "exclamation-triangle" as const,
    rejectLabel: t("common.cancel"),
    acceptLabel: t("event.deleteSignup.confirm"),
  },
}));

// The help options this event still asks about. Switched off, the
// question is not asked and its answers are not shown: no column, no
// chips, no breakdown. Switching it back on brings what was recorded
// back with it.
const helpColumns = $derived(event?.help_enabled ? event.help_options : []);

/** name | one column per help option | party size | delete */
const signupGridTemplate = $derived(
  helpColumns.length > 0
    ? `minmax(0, 1fr) repeat(${helpColumns.length}, auto) auto auto`
    : "minmax(0, 1fr) auto auto",
);

/** Which session of how many, for the caption over the breakdowns. */
const selectedBadge = $derived.by(() => {
  const occ = selectedOccurrence;
  if (!occ) return "";
  const total = occurrenceList?.total_sessions ?? null;
  return total === null
    ? t("event.occurrences.sessionOpen", { i: occ.index + 1 })
    : t("event.occurrences.sessionOf", { i: occ.index + 1, n: total });
});

let calendarMonth = $state<string | null>(null);
const shownMonth = {
  get value(): string {
    return (calendarMonth ?? (selectedIso ?? isoDate(new Date().toISOString()))).slice(0, 7);
  },
  set value(next: string) {
    calendarMonth = next;
  },
};

const weekdayLabels = $derived(
  (["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const).map((d) =>
    t(`chore.edit.weekday.${d}`),
  ),
);

function dayClass(iso: string): Record<string, boolean> {
  return {
    "has-occurrence": occByIso.has(iso),
    selected: iso === selectedIso,
    projected: projectedIsos.has(iso),
  };
}

function onDayClick(iso: string): void {
  if (occByIso.has(iso)) selectedIso = iso;
}

// --- The questionnaire, and the mail ---------------------------------
const summaryQuery = feedbackSummaryQuery(() => eventId);
const summary = $derived(summaryQuery.data ?? null);
const sendNow = sendEmailsNow();
let triggering = $state<EmailChannel | null>(null);

const CHANNELS: EmailChannel[] = ["reminder", "feedback"];
const HEALTH_KEYS = ["sent", "not_applicable", "pending", "failed"] as const;

function channelEnabled(channel: EmailChannel): boolean {
  if (!event) return false;
  return channel === "reminder" ? event.reminder_enabled : event.feedback_enabled;
}

/** Only the channels this event actually uses get a card. A channel
 *  switched off sends nothing and can send nothing, so its counts are
 *  four zeroes and its button is dead. */
const activeChannels = $derived(CHANNELS.filter(channelEnabled));

function channelHealth(channel: EmailChannel) {
  return summary?.email_health[channel];
}

function canTrigger(channel: EmailChannel): boolean {
  if (!event || !summary || !channelEnabled(channel)) return false;
  return (channelHealth(channel)?.pending ?? 0) > 0;
}

function triggerDisabledReason(channel: EmailChannel): string {
  if (!event) return "";
  if (!channelEnabled(channel)) return t("event.sendNow.disabledOff");
  if ((channelHealth(channel)?.pending ?? 0) === 0) {
    return t("event.sendNow.disabledNothingPending");
  }
  return "";
}

const triggerNow = guarded(sendNow.run, (channel: EmailChannel) => ({
  vars: { eventId, channel },
  ok: (r: { processed: number }) => ({
    summary: t("event.sendNow.successTitle"),
    detail: t("event.sendNow.successBody", { n: r.processed }),
  }),
  fail: (err: unknown) => (err instanceof Error ? err.message : t("event.sendNow.failed")),
  confirm: {
    header: t(`event.sendNow.${channel}.confirmTitle`),
    message: t("event.sendNow.confirmBody", { n: channelHealth(channel)?.pending ?? 0 }),
    icon: "send" as const,
    rejectLabel: t("common.cancel"),
    acceptLabel: t("event.sendNow.confirm"),
  },
}));

function askTriggerNow(channel: EmailChannel): void {
  if (!event) return;
  triggering = channel;
  void triggerNow(channel).finally(() => {
    triggering = null;
  });
}

const responsesLine = $derived.by(() => {
  if (!summary) return "";
  return t("feedback.summary.responsesOf", {
    responses: summary.submission_count,
    signups: summary.signup_count,
    rate: `${Math.round(summary.response_rate * 100)}%`,
  });
});

function questionPrompt(key: string): string {
  return t(`feedback.questions.${key}.prompt`);
}

/**
 * One row per submission, one column per question, in the order the
 * questionnaire asks them. The headers are the prompts in the
 * organiser's own language, so the file reads without joining it back
 * to anything.
 *
 * Named date first, so an organiser's exports sort chronologically, and
 * the id last, because that is what tells two same-named events apart.
 */
async function exportCsv(): Promise<void> {
  if (!event) return;
  try {
    await downloadFile(`/api/v1/event/${eventId}/feedback-submissions.csv`, `${event.id}.csv`);
  } catch {
    toasts.error(t("feedback.summary.csvFail"));
  }
}
</script>

<!-- Only the event itself blocks the page. The stats and the summary
     each show their own skeleton inside their own card, so nothing
     waits on the slowest fetch. -->
<DetailsPageShell loaded={!!event} skeletonRows={4}>
  {#if event}
    <DetailHeaderCard
      title={lt(event.name_nl, event.name_en) ?? ""}
      chapterName={event.chapter_name}
      imageUrl={event.image_url}
      imageArtist={event.image_artist_instagram}
      imageHref={event.image_url}
      descriptionHtml={lt(event.topic_nl, event.topic_en)}
      qrSrc={eventQrUrl(primary?.slug ?? "")}
      publicUrl={primary ? publicEventUrl(primary.slug) : ""}
      editTo={`/event/${event.id}/edit`}
      oncopyQr={() => primary && void share.copyQr(primary.slug)}
      oncopyLink={() => primary && void share.copyLink(primary.slug)}
    >
      {#snippet meta()}
        <EventMetaLines {event} />
      {/snippet}
    </DetailHeaderCard>

    <AppCard>
      <div class="summary-header">
        <h2>{t("event.signupsHeading")}</h2>
        <div class="header-actions">
          <!-- The pill counts the session on screen. The ceiling is on
               the event as a whole, so it is said separately rather than
               folded into a number it does not bound. -->
          {#if auth.user?.participant_cap != null}
            <span class="muted">
              {t("event.capUsage", {
                n: event.attendee_count,
                cap: auth.user.participant_cap,
              })}
            </span>
          {/if}
          {#if selectedOccurrence}
            {@const occ = selectedOccurrence}
            <RecoverLinksPill
              count={occ.attendee_count}
              label={t("event.totalAttendees")}
              loadRows={recoverRows}
              recoverPath={(id) => `/api/v1/event/${eventId}/registrations/${id}/edit-link`}
              publicUrl={(tok) => `${publicEventUrl(occ.slug)}?s=${tok}`}
            />
          {/if}
        </div>
      </div>

      {#if !occurrenceList}
        <AppSkeleton rows={3} />
      {:else}
        {#if occurrences.length === 0 && projected.length === 0}
          <p class="muted">{t("event.occurrences.none")}</p>
        {/if}

        <!-- A recurring event gets a calendar of its sessions. Clicking
             a highlighted day switches which day's sign-ups and
             breakdowns show below, in the same shape a one-off uses. -->
        {#if event.cycle_slots.length > 0 && occurrences.length > 0}
          <MonthGrid
            bind:month={shownMonth.value}
            locale={locale()}
            weekdays={weekdayLabels}
            {dayClass}
            clickable={(iso) => occByIso.has(iso)}
            prevLabel={t("event.occurrences.prevMonth")}
            nextLabel={t("event.occurrences.nextMonth")}
            ondayClick={onDayClick}
          />
        {/if}

        {#if selectedOccurrence}
          {#if event.cycle_slots.length > 0}
            <p class="day-caption">
              <span class="day-date">{formatDate(selectedOccurrence.starts_at, locale())}</span>
              <span class="muted">
                · {formatTimeRange(
                  selectedOccurrence.starts_at,
                  selectedOccurrence.ends_at,
                  locale(),
                )}
              </span>
              <span class="day-badge">{selectedBadge}</span>
            </p>
          {/if}

          {#if dayStats}
            {#if event.help_enabled && Object.keys(dayStats.by_help).length > 0}
              <div class="subgroup">
                <h3 class="subhead">{t("event.byHelp")}</h3>
                {#each Object.entries(dayStats.by_help) as [opt, count] (opt)}
                  <div class="list-row">
                    <span class="list-row-label">{opt}</span>
                    <span class="row-count">{count}</span>
                  </div>
                {/each}
              </div>
            {/if}
            {#if event.source_enabled && Object.keys(dayStats.by_source).length > 0}
              <div class="subgroup">
                <h3 class="subhead">{t("event.bySource")}</h3>
                {#each Object.entries(dayStats.by_source) as [src, count] (src)}
                  <div class="list-row">
                    <span class="list-row-label">{src}</span>
                    <span class="row-count">{count}</span>
                  </div>
                {/each}
              </div>
            {/if}
          {/if}

          {#if daySignups.length > 0}
            <details class="subgroup signup-list">
              <summary class="subhead">{t("event.signupList")}</summary>
              <div class="signup-grid" style:grid-template-columns={signupGridTemplate}>
                {#each daySignups as s (s.id)}
                  <div class="signup-row">
                    <span class="signup-name">{s.display_name ?? t("event.signupAnonymous")}</span>
                    {#each helpColumns as opt (opt.id)}
                      <span class="help-cell">
                        <!-- A sign-up records the words it was offered,
                             not the row, so the two are matched on the
                             label. -->
                        {#if s.help_choices.includes(opt.label)}
                          <span class="help-chip">{opt.label}</span>
                        {/if}
                      </span>
                    {/each}
                    <span class="row-count signup-count">{s.party_size}</span>
                    <span use:tip={t("event.deleteSignup.title")}>
                      <AppButton
                        icon="trash"
                        size="small"
                        severity="secondary"
                        text
                        class="signup-delete"
                        ariaLabel={t("event.deleteSignup.title")}
                        onclick={() => askDeleteSignup(s)}
                      />
                    </span>
                  </div>
                {/each}
              </div>
            </details>
          {:else}
            <p class="muted">{t("event.occurrences.noSignups")}</p>
          {/if}
        {/if}

        <!-- Dates past the horizon. They have no page yet, so nobody can
             sign up for one and there is nothing here to act on. -->
        {#if projected.length > 0}
          <div class="subgroup projected">
            <h3 class="subhead">{t("event.occurrences.projectedHeading")}</h3>
            {#each projected as p (p.index)}
              <div class="list-row">
                <span class="list-row-label">
                  {formatDate(p.starts_at, locale())}
                  <span class="muted">
                    · {formatTimeRange(p.starts_at, p.ends_at, locale())}
                  </span>
                </span>
                <span class="muted projected-badge">
                  {occurrenceList.total_sessions === null
                    ? t("event.occurrences.sessionOpen", { i: p.index + 1 })
                    : t("event.occurrences.sessionOf", {
                        i: p.index + 1,
                        n: occurrenceList.total_sessions,
                      })}
                </span>
              </div>
            {/each}
          </div>
        {/if}
      {/if}
    </AppCard>

    <!-- The questionnaire's results. With the channel off this event
         asks nothing and its pending sends are deleted, so there is
         nothing to read; switching it back on brings any answers already
         given back with it. -->
    {#if event.feedback_enabled}
      <AppCard>
        <div class="summary-header">
          <h2>{t("feedback.summary.title")}</h2>
          <div class="header-actions">
            <AppButton
              label={t("feedback.summary.exportCsv")}
              size="small"
              severity="secondary"
              text
              icon="download"
              disabled={!summary || summary.submission_count === 0}
              onclick={exportCsv}
            />
            {#if primary}
              <a href={`/e/${primary.slug}/feedback?t=preview`} target="_blank" rel="noopener">
                <AppButton
                  label={t("feedback.preview.open")}
                  size="small"
                  severity="secondary"
                  text
                  icon="eye"
                />
              </a>
            {/if}
          </div>
        </div>
        {#if !summary || summary.submission_count === 0}
          <p class="muted">{t("feedback.summary.noResponsesYet")}</p>
        {:else}
          <p>{responsesLine}</p>
          {#each summary.questions as q (q.key)}
            <div class="q-block">
              <p class="q-prompt">{questionPrompt(q.key)}</p>
              {#if q.kind === "rating" && q.rating_distribution}
                {@const dist = q.rating_distribution}
                <p class="muted q-meta">
                  {t("feedback.summary.responses", { n: q.response_count })}
                  {#if q.rating_average}
                    · {t("feedback.summary.average", {
                      avg: formatAverage(q.rating_average, locale()),
                    })}
                  {/if}
                </p>
                <div class="bars">
                  {#each [1, 2, 3, 4, 5] as i (i)}
                    <div class="bar-row">
                      <span class="bar-label">{i}</span>
                      <StatBar segments={[{ width: barWidth(dist, dist[i - 1]) }]} />
                      <span class="bar-count">{dist[i - 1]}</span>
                    </div>
                  {/each}
                </div>
              {:else if q.kind === "text"}
                {#if !q.texts || q.texts.length === 0}
                  <p class="muted q-meta">{t("feedback.summary.noTextResponses")}</p>
                {:else}
                  <ul class="texts">
                    {#each q.texts as txt, i (i)}
                      <li>{txt}</li>
                    {/each}
                  </ul>
                {/if}
              {/if}
            </div>
          {/each}
        {/if}
      </AppCard>
    {/if}

    <!-- One card per channel, in the order they fire: the reminder
         before the event, the questionnaire after. The pills say what
         has gone out; the button sends what is still owed. -->
    {#if summary}
      {#each activeChannels as channel (channel)}
        <AppCard>
          <h2>{t(`event.sendNow.${channel}.title`)}</h2>
          <p class="muted">{t(`event.sendNow.${channel}.explainer`)}</p>
          <div class="email-health">
            {#each HEALTH_KEYS as key (key)}
              <div
                class="health-pill health-{key}"
                use:tip={t(`feedback.email.tooltips.${channel}.${key}`)}
              >
                <span class="count">{channelHealth(channel)?.[key] ?? 0}</span>
                <span class="label">{t(`feedback.email.${key}`)}</span>
              </div>
            {/each}
          </div>
          {#if triggerDisabledReason(channel)}
            <p class="muted small">{triggerDisabledReason(channel)}</p>
          {/if}
          <div class="send-now-row">
            <AppButton
              label={t(`event.sendNow.${channel}.button`)}
              icon="send"
              disabled={!canTrigger(channel) || triggering !== null}
              loading={triggering === channel}
              onclick={() => askTriggerNow(channel)}
            />
          </div>
        </AppCard>
      {/each}
    {/if}
  {/if}
</DetailsPageShell>

<style>
/* The header is the shared ``DetailHeaderCard``; the card headers use
 * the shared ``.summary-header`` and ``.header-actions`` from
 * theme.css. */
.subhead {
  /* The same family, weight and colour as the card's h2, a step
   * smaller. One heading style per card, rather than an h2 beside a
   * muted small-caps label. */
  margin: 0.5rem 0 0.25rem;
  font-size: 1rem;
  font-weight: 600;
}
/* Keeps a subhead tight against its rows; the card's own stack would
 * put 0.75rem between them. */
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
/* The day switcher: the session days stand out, the selected one is
 * filled, the ones past the horizon are muted. The cells belong to
 * MonthGrid, so the rules reach into it. */
:global(.mg-cell.has-occurrence) {
  background: var(--brand-bg);
  border-color: var(--brand-border);
  font-weight: 600;
}
:global(.mg-cell.projected) {
  color: var(--brand-text-muted);
  border-style: dashed;
}
:global(.mg-cell.selected) {
  background: var(--brand-red);
  border-color: var(--brand-red);
}
:global(.mg-cell.selected .mg-num) {
  color: #fff;
}

/* Which day everything below belongs to. Recurring events only. */
.day-caption {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
  margin: 0.75rem 0 0;
}
.day-date {
  font-weight: 600;
}
.day-badge {
  margin-left: auto;
  font-size: 0.75rem;
  padding: 0.1rem 0.5rem;
  border-radius: 0.75rem;
  background: var(--brand-bg);
  color: var(--brand-text-muted);
  white-space: nowrap;
}

/* The day's attendees, folded away: name, a column per help option,
 * the party size, and the delete. */
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
.signup-row:hover {
  background: var(--brand-bg);
}
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
  background: var(--brand-surface-100);
  color: var(--brand-text-muted);
  white-space: nowrap;
}
.signup-count {
  text-align: right;
}
.projected {
  margin-top: 0.5rem;
}
.projected-badge {
  font-size: 0.75rem;
  white-space: nowrap;
}

/* --- The questionnaire --------------------------------------------- */
/* Each question sits between two rules with the same air on either
 * side, so the results read as separate sections rather than one long
 * run. */
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
.q-prompt {
  margin: 0 0 0.5rem;
  font-weight: 600;
}
.q-meta {
  margin: 0 0 0.5rem;
}
.bars {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.bar-row {
  display: grid;
  grid-template-columns: 1.25rem 1fr 2.5rem;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
}
.bar-label {
  color: var(--brand-text-muted);
}
.bar-count {
  text-align: right;
  color: var(--brand-text-muted);
}
.texts {
  margin: 0;
  padding-left: 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}
.texts li {
  line-height: 1.45;
  white-space: pre-line;
}

/* --- The mail ------------------------------------------------------ */
/* One chip per delivery state, in equal columns, so the row reads as a
 * breakdown rather than a ragged wrap. */
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
  padding: 0.5rem;
  border-radius: 8px;
  border: 1px solid var(--brand-border);
  background: var(--brand-bg);
  cursor: help;
}
.health-pill .count {
  font-weight: 700;
  font-size: 1.125rem;
  line-height: 1;
}
.health-pill .label {
  font-size: 0.75rem;
  color: var(--brand-text-muted);
}
.health-sent {
  background: var(--brand-surface);
  border-color: var(--brand-border);
}
.health-sent .count {
  color: var(--brand-red);
}
.health-pending {
  background: var(--brand-amber-wash);
  border-color: var(--brand-notice-border);
}
.health-pending .count {
  color: var(--brand-amber-text);
}
.health-failed {
  background: var(--brand-red-soft);
  border-color: var(--brand-red-soft-border);
}
.health-failed .count {
  color: var(--brand-red);
}
.health-not_applicable .count {
  color: var(--brand-text-muted);
}

.small {
  font-size: 0.875rem;
}

/* Below the project's phone breakpoint the six chips are too tight, so
 * they go to three across. */
@media (max-width: 480px) {
  .email-health {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
</style>
