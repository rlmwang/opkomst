<script lang="ts">
import AppButton from "@/components/AppButton.svelte";
import AppCard from "@/components/AppCard.svelte";
import AppDialog from "@/components/AppDialog.svelte";
import DetailHeaderCard from "@/components/DetailHeaderCard.svelte";
import DetailsPageShell from "@/components/DetailsPageShell.svelte";
import RecoverLinksPill, { type RecoverableRow } from "@/components/RecoverLinksPill.svelte";
import RosterCalendar from "@/components/RosterCalendar.svelte";
import SegmentedBar, { type BarSegment } from "@/components/SegmentedBar.svelte";
import TallyLegend, { type LegendItem } from "@/components/TallyLegend.svelte";
import WeekdayGrid from "@/components/WeekdayGrid.svelte";
import {
  accountabilityQuery,
  rosters,
  scheduleQuery,
} from "@/composables/useChores.svelte";
import { lt } from "@/composables/useLocalizedText.svelte";
import { shareClipboard } from "@/composables/useShareClipboard.svelte";
import { locale, t } from "@/i18n.svelte";
import { get, post } from "@/api/client";
import { choreQrUrl, publicChoreUrl } from "@/lib/chore-urls";
import { formatDate } from "@/lib/format";
import { queryClient } from "@/lib/query-client";
import { useToasts } from "@/lib/toasts";
import { auth } from "@/stores/auth.svelte";
import type { ChoreOut, VolunteerSummary } from "@/api/types";

/**
 * A roster, as the organiser reads it: what the chores are, who is
 * doing them and how the turns have fallen out, and the calendar of
 * what is pinned.
 */
const { rosterId }: { rosterId: string } = $props();

const toasts = useToasts();
const share = shareClipboard({
  publicUrlFor: publicChoreUrl,
  qrUrlFor: choreQrUrl,
  copyPrefix: "chore.share",
});

const query = rosters.single(() => rosterId);
const roster = $derived(query.data ?? null);
const chores = $derived<ChoreOut[]>(roster?.chores ?? []);
const volunteerCount = $derived(roster?.volunteer_count ?? 0);

// One section per chore, each listing the people enrolled in it with
// their split of turns for that chore alone.
const accountability = accountabilityQuery(() => rosterId);
const perChore = $derived(accountability.data ?? []);
const schedule = scheduleQuery(() => rosterId);

/** The rows behind the volunteers pill's recovery popover. */
async function recoverRows(): Promise<RecoverableRow[]> {
  const vols = await get<VolunteerSummary[]>(`/api/v1/chore/${rosterId}/volunteers`);
  return vols.map((v) => ({
    id: v.id,
    name: v.display_name,
    recoveredAt: v.link_recovered_at ?? null,
  }));
}

// There is somebody to fold in only while the roster is running and at
// least one enrolled person is still waiting for their first turn. The
// dialog previews what would change before anything is committed.
const hasPending = $derived(
  roster?.activated_at != null && perChore.some((c) => c.volunteers.some((v) => v.pending)),
);
let showFoldIn = $state(false);
let rebalancing = $state(false);

async function confirmFoldIn(): Promise<void> {
  rebalancing = true;
  try {
    await post(`/api/v1/chore/${rosterId}/rebalance`);
    await queryClient.invalidateQueries({ queryKey: ["chore"] });
    showFoldIn = false;
    toasts.success(t("chore.details.foldInDone"));
  } catch {
    toasts.error(t("chore.details.foldInFailed"));
  } finally {
    rebalancing = false;
  }
}

/** Where the pinned window currently ends. A newcomer's first turns
 *  land on that edge as it rolls forward. */
const horizonEdge = $derived.by(() => {
  const days = roster?.commit_horizon_days;
  if (days == null) return null;
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
});

// A person's bar: their own turns, the ones they picked up for somebody
// else, the ones they handed off, and the ones they missed. Every bar
// fills the track, so a newcomer's is not a sliver merely for having
// done less; the count sits inside each segment. Missed is grey rather
// than red, because the bar already uses green and a red-green pair
// says nothing to a colour-blind reader.
type VolRow = (typeof perChore)[number]["volunteers"][number];

function volSegments(v: VolRow): BarSegment[] {
  return [
    {
      value: v.regular_turns,
      variant: "positive",
      title: t("chore.details.regularCount", { n: v.regular_turns }),
    },
    {
      value: v.picked_up,
      variant: "accent",
      title: t("chore.details.pickedUpCount", { n: v.picked_up }),
    },
    {
      value: v.deferred,
      variant: "warning",
      title: t("chore.details.deferredCount", { n: v.deferred }),
    },
    { value: v.missed, variant: "neutral", title: t("chore.details.missedCount", { n: v.missed }) },
  ];
}

function barLabel(v: VolRow): string {
  return volSegments(v)
    .filter((s) => s.value > 0)
    .map((s) => s.title)
    .join(", ");
}

const legendItems = $derived<LegendItem[]>([
  { variant: "positive", label: t("chore.details.legend.regular") },
  { variant: "accent", label: t("chore.details.legend.pickedUp") },
  { variant: "warning", label: t("chore.details.legend.deferred") },
  { variant: "neutral", label: t("chore.details.legend.missed") },
]);

const dayLabels = $derived([
  t("chore.edit.weekday.mon"),
  t("chore.edit.weekday.tue"),
  t("chore.edit.weekday.wed"),
  t("chore.edit.weekday.thu"),
  t("chore.edit.weekday.fri"),
  t("chore.edit.weekday.sat"),
  t("chore.edit.weekday.sun"),
]);

const cadence = $derived(
  !roster
    ? ""
    : roster.period_weeks <= 1
      ? t("chore.recurrence.weekly")
      : t("chore.recurrence.everyKWeeks", { k: roster.period_weeks }),
);

const dateWindow = $derived.by(() => {
  if (!roster) return "";
  const start = formatDate(roster.starts_on, locale());
  if (!roster.ends_on) return t("chore.details.fromDate", { date: start });
  return `${start} – ${formatDate(roster.ends_on, locale())}`;
});
</script>

<DetailsPageShell loaded={!query.isPending} skeletonRows={4}>
  {#if roster}
    {@const slug = roster.slug}
    <DetailHeaderCard
      title={lt(roster.name_nl, roster.name_en) ?? ""}
      chapterName={roster.chapter_name}
      imageUrl={roster.image_url}
      imageArtist={roster.image_artist_instagram}
      descriptionHtml={lt(roster.description_nl, roster.description_en)}
      qrSrc={choreQrUrl(slug)}
      publicUrl={publicChoreUrl(slug)}
      editTo={`/chore/${roster.id}/edit`}
      oncopyQr={() => void share.copyQr(slug)}
      oncopyLink={() => void share.copyLink(slug)}
    >
      {#snippet meta()}
        <p class="muted overview-meta">{cadence} · {dateWindow}</p>
      {/snippet}
    </DetailHeaderCard>

    <AppCard>
      <div class="summary-header">
        <h2>{t("chore.details.choresHeading")}</h2>
      </div>
      {#if chores.length === 0}
        <p class="muted">{t("chore.details.noChores")}</p>
      {:else}
        <ul class="chore-list">
          {#each chores as c (c.id)}
            <li class="chore-item">
              <div class="chore-head">
                <span class="chore-name">
                  {#if c.emoji}<span class="chore-emoji">{c.emoji}</span>{/if}
                  {c.name}
                </span>
                {#if c.people_per_shift > 1}
                  <span class="people-chip">
                    {t("chore.details.peoplePerShift", { n: c.people_per_shift })}
                  </span>
                {/if}
              </div>
              {#if c.description}<p class="muted chore-desc">{c.description}</p>{/if}
              {#if c.cycle_slots.length === 0}
                <p class="muted chore-days">{t("chore.details.noDays")}</p>
              {:else}
                <WeekdayGrid
                  cycleSlots={c.cycle_slots}
                  periodWeeks={roster.period_weeks ?? 1}
                  weekdayLabels={dayLabels}
                />
              {/if}
            </li>
          {/each}
        </ul>
      {/if}
    </AppCard>

    <AppCard>
      <div class="summary-header">
        <h2>{t("chore.details.volunteersHeading")}</h2>
        {#if volunteerCount}
          <RecoverLinksPill
            count={volunteerCount}
            cap={auth.user?.participant_cap ?? null}
            label={t("chore.details.volunteersLabel")}
            loadRows={recoverRows}
            recoverPath={(id) => `/api/v1/chore/${rosterId}/volunteers/${id}/edit-link`}
            publicUrl={(tok) => `${publicChoreUrl(slug)}?s=${tok}`}
          />
        {/if}
      </div>
      {#if volunteerCount === 0}
        <p class="muted">{t("chore.details.volunteersEmpty")}</p>
      {:else}
        <TallyLegend items={legendItems} />
        <!-- One section per chore. A row is the person and their bar for
             that chore; the heading has already named it. -->
        {#each perChore as c (c.chore_id)}
          <section class="chore-section">
            <h3 class="chore-section-name">
              {#if c.emoji}<span class="chore-emoji">{c.emoji}</span>{/if}{c.chore_name}
            </h3>
            {#if c.volunteers.length === 0}
              <p class="muted chore-section-empty">{t("chore.details.choreNoVolunteers")}</p>
            {:else}
              <ul class="vol-tally">
                {#each c.volunteers as v (v.id)}
                  <li class="vol-row">
                    <span class="vol-name">{v.display_name || t("chore.details.anonymous")}</span>
                    <!-- Somebody with no turn of this chore yet gets the
                         date they join in place of an empty bar. -->
                    {#if v.pending && horizonEdge}
                      <span class="vol-joining">
                        {t("chore.details.joining", { date: formatDate(horizonEdge, locale()) })}
                      </span>
                    {:else}
                      <SegmentedBar segments={volSegments(v)} ariaLabel={barLabel(v)} />
                    {/if}
                  </li>
                {/each}
              </ul>
            {/if}
          </section>
        {/each}
      {/if}
    </AppCard>

    <AppCard>
      <div class="summary-header">
        <h2>{t("chore.details.scheduleHeading")}</h2>
        {#if hasPending}
          <AppButton
            label={t("chore.details.foldIn")}
            icon="user-plus"
            size="small"
            severity="secondary"
            onclick={() => (showFoldIn = true)}
          />
        {/if}
      </div>
      {#if schedule.data}
        <p class="muted stats-line">
          {t("chore.details.stats", {
            scheduled: schedule.data.stats.scheduled,
            done: schedule.data.stats.done,
            missed: schedule.data.stats.missed,
            open: schedule.data.stats.open,
          })}
        </p>
      {/if}
      {#if roster.activated_at}
        <div class="cal-legend muted">
          <span><i class="cal-swatch locked"></i>{t("chore.details.calLocked")}</span>
          <span><i class="cal-swatch tentative"></i>{t("chore.details.calTentative")}</span>
          {#each chores as c (c.id)}
            <span class="cal-chore">
              {#if c.emoji}<span class="cal-chore-emoji">{c.emoji}</span>{/if}{c.name}
            </span>
          {/each}
        </div>
        <RosterCalendar
          {rosterId}
          reassignable
          locale={locale()}
          openLabel={t("chore.details.openShift")}
          anonLabel={t("chore.details.anonymous")}
          prevLabel={t("chore.details.prevMonth")}
          nextLabel={t("chore.details.nextMonth")}
        />
      {:else}
        <p class="muted">{t("chore.details.scheduleEmpty")}</p>
      {/if}
    </AppCard>
  {/if}

  <AppDialog bind:visible={showFoldIn} header={t("chore.details.foldInTitle")} width="560px">
    <p class="muted">{t("chore.details.foldInIntro")}</p>
    <div class="cal-legend muted">
      <span><i class="cal-swatch locked"></i>{t("chore.details.calLocked")}</span>
      <span><i class="cal-swatch tentative"></i>{t("chore.details.calTentative")}</span>
      <span><i class="cal-swatch changed"></i>{t("chore.details.calChanged")}</span>
      {#each chores as c (c.id)}
        <span class="cal-chore">
          {#if c.emoji}<span class="cal-chore-emoji">{c.emoji}</span>{/if}{c.name}
        </span>
      {/each}
    </div>
    <RosterCalendar
      {rosterId}
      preview
      enabled={showFoldIn}
      locale={locale()}
      openLabel={t("chore.details.openShift")}
      anonLabel={t("chore.details.anonymous")}
      prevLabel={t("chore.details.prevMonth")}
      nextLabel={t("chore.details.nextMonth")}
      noChangeLabel={t("chore.details.foldInNoneMonth")}
    />
    {#snippet footer()}
      <AppButton
        label={t("common.cancel")}
        size="small"
        severity="secondary"
        text
        disabled={rebalancing}
        onclick={() => (showFoldIn = false)}
      />
      <AppButton
        label={t("chore.details.foldInConfirm")}
        size="small"
        loading={rebalancing}
        onclick={confirmFoldIn}
      />
    {/snippet}
  </AppDialog>
</DetailsPageShell>

<style>
/* The header card owns its own layout, and ``.overview-meta`` comes
 * from theme.css. Only the chore-specific lists live here. */
.chore-list {
  list-style: none;
  margin: 0.5rem 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
.chore-item {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}
.chore-head {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}
.chore-name {
  font-weight: 600;
}
.chore-emoji {
  margin-right: 0.25rem;
}
.chore-desc {
  font-size: 0.875rem;
}
.chore-days {
  font-size: 0.875rem;
}
.people-chip {
  padding: 0.125rem 0.5rem;
  border-radius: 999px;
  background: var(--brand-surface-100);
  color: var(--brand-text-muted);
  font-size: 0.75rem;
}
.chore-section {
  margin-top: 1.25rem;
}
.chore-section-name {
  margin: 0;
  font-size: 0.875rem;
}
.chore-section-empty {
  margin: 0.375rem 0 0;
  font-size: 0.8125rem;
}
.vol-tally {
  list-style: none;
  margin: 0.5rem 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
}
.vol-row {
  display: grid;
  grid-template-columns: minmax(3.5rem, 7rem) 1fr;
  align-items: center;
  gap: 0.75rem;
}
.vol-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.vol-joining {
  font-size: 0.8125rem;
  color: var(--brand-text-muted);
}
.stats-line {
  margin: 0 0 0.5rem;
}

/* The legend's swatches match the calendar's own cell styles. */
.cal-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem 1rem;
  font-size: 0.8125rem;
  margin: 0.25rem 0 0.75rem;
}
.cal-legend span {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
}
.cal-swatch {
  width: 0.875rem;
  height: 0.875rem;
  border-radius: 4px;
  flex: none;
  border: 1px solid color-mix(in srgb, var(--brand-text-muted) 42%, var(--brand-border));
  background: var(--brand-surface);
}
.cal-swatch.tentative {
  border-style: dashed;
}
.cal-swatch.changed {
  outline: 2px solid var(--brand-red);
  outline-offset: -1px;
}
/* The emoji key, so the calendar's markers decode. */
.cal-chore-emoji {
  font-size: 0.875rem;
}
</style>
