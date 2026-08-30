<script lang="ts">
import AppButton from "@/components/AppButton.svelte";
import AppCard from "@/components/AppCard.svelte";
import DetailHeaderCard from "@/components/DetailHeaderCard.svelte";
import DetailsPageShell from "@/components/DetailsPageShell.svelte";
import MonthCalendar from "@/components/MonthCalendar.svelte";
import RecoverLinksPill, { type RecoverableRow } from "@/components/RecoverLinksPill.svelte";
import SegmentedBar, { type BarSegment } from "@/components/SegmentedBar.svelte";
import TallyLegend, { type LegendItem } from "@/components/TallyLegend.svelte";
import RouterLink from "@/router/RouterLink.svelte";
import {
  type DatepollSubmission,
  datepollSummaryQuery,
  datepolls,
  fetchDatepollSubmissions,
} from "@/composables/useDatepolls.svelte";
import { lt } from "@/composables/useLocalizedText.svelte";
import { shareClipboard } from "@/composables/useShareClipboard.svelte";
import { locale, t } from "@/i18n.svelte";
import { ApiError } from "@/api/client";
import { downloadFile } from "@/lib/download";
import { datepollQrUrl, publicDatepollUrl } from "@/lib/datepoll-urls";
import { localeTag } from "@/lib/format";
import { mapLink } from "@/lib/map-link";
import { useToasts } from "@/lib/toasts";
import { auth } from "@/stores/auth.svelte";

/**
 * What a date poll came back with.
 *
 * The dates on offer, a bar per date, the notes people left, and a grid
 * of who said what. The grid is the only place an organiser can read
 * one person's answers across every date, which is what settling on a
 * date actually needs.
 */
const { datepollId }: { datepollId: string } = $props();

const toasts = useToasts();
const share = shareClipboard({
  publicUrlFor: publicDatepollUrl,
  qrUrlFor: datepollQrUrl,
  copyPrefix: "datepoll.share",
});

const query = datepolls.single(() => datepollId);
const poll = $derived(query.data ?? null);
const notFound = $derived(query.error instanceof ApiError && query.error.status === 404);

const summaryQuery = datepollSummaryQuery(() => datepollId);
const summary = $derived(summaryQuery.data ?? null);

// The per-person rows, fetched alongside the tallies so the grid paints
// with them. A failure leaves the grid out; the bars still say what
// people picked.
let subs = $state<DatepollSubmission[]>([]);
$effect(() => {
  void (async () => {
    try {
      subs = await fetchDatepollSubmissions(datepollId);
    } catch {
      /* the grid stays empty; the tallies still render */
    }
  })();
});

/** The rows behind the responses pill's recovery popover. */
async function recoverRows(): Promise<RecoverableRow[]> {
  const rows = await fetchDatepollSubmissions(datepollId);
  return rows.map((s) => ({
    id: s.submission_id,
    name: s.display_name,
    recoveredAt: s.link_recovered_at ?? null,
  }));
}

function shortDate(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString(localeTag(locale()), {
    weekday: "short",
    day: "numeric",
    month: "short",
  });
}

/** Just the times, or nothing at all for a whole-day slot. A whole day
 *  carries no label of its own: the date is the answer. */
function slotTime(s: { start_time?: string | null; end_time?: string | null }): string {
  return s.start_time && s.end_time
    ? `${s.start_time.slice(0, 5)}–${s.end_time.slice(0, 5)}`
    : "";
}

function slotHeading(s: {
  on_date: string;
  start_time?: string | null;
  end_time?: string | null;
}): string {
  const times = slotTime(s);
  return shortDate(s.on_date) + (times ? ` ${times}` : "");
}

function nameOf(s: DatepollSubmission): string {
  return s.display_name ?? t("datepoll.details.anonymous");
}

const noted = $derived(subs.filter((s) => s.note?.trim()));

const AVAIL_GLYPH: Record<string, string> = { yes: "✓", maybe: "~", no: "✕" };

// The bars are deliberately not normalised: every bar is measured
// against the busiest date, so a date fewer people answered reads as a
// shorter bar and the rows stay comparable. Inside a bar, yes, maybe and
// no each carry their own count. No is grey and never red, because a
// green and red pair says nothing to a red-green colour-blind reader.
const maxTotal = $derived(
  Math.max(1, ...(summary?.slots ?? []).map((s) => s.yes + s.maybe + s.no)),
);

function slotSegments(s: { yes: number; maybe: number; no: number }): BarSegment[] {
  return [
    { value: s.yes, variant: "positive", title: `${s.yes} ${t("datepoll.details.yes")}` },
    { value: s.maybe, variant: "warning", title: `${s.maybe} ${t("datepoll.details.maybe")}` },
    { value: s.no, variant: "neutral", title: `${s.no} ${t("datepoll.details.no")}` },
  ];
}

const legendItems = $derived<LegendItem[]>([
  { variant: "positive", label: t("datepoll.details.yes") },
  { variant: "warning", label: t("datepoll.details.maybe") },
  { variant: "neutral", label: t("datepoll.details.no") },
]);

// The calendar opens on the month of the earliest date on offer, or on
// this month while the poll has none yet.
function currentMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}
let datesMonth = $state(currentMonth());
let seededMonthFor: unknown = undefined;
$effect(() => {
  const slots = poll?.slots;
  if (!slots || slots === seededMonthFor) return;
  seededMonthFor = slots;
  const first = slots.map((s) => s.on_date).sort()[0];
  if (first) datesMonth = first.slice(0, 7);
});

// The top three dates, by the rule the backend uses to pick a winner:
// most yes, then most maybe, then most left blank. A date nobody said
// yes to does not rank. The chip sits in a reserved width so every row's
// label starts in the same place, ranked or not.
const rankById = $derived.by(() => {
  const total = summary?.submission_count ?? 0;
  const blanks = (s: { yes: number; maybe: number; no: number }) => total - s.yes - s.maybe - s.no;
  const ranked = [...(summary?.slots ?? [])]
    .filter((s) => s.yes > 0)
    .sort((a, b) => b.yes - a.yes || b.maybe - a.maybe || blanks(b) - blanks(a))
    .slice(0, 3);
  const map: Record<string, number> = {};
  ranked.forEach((s, i) => {
    map[s.id] = i + 1;
  });
  return map;
});

function rankLabel(id: string): string {
  const r = rankById[id];
  return r ? t(`datepoll.details.rank${r}`) : "";
}

async function exportCsv(): Promise<void> {
  if (!poll) return;
  try {
    await downloadFile(`/api/v1/datepoll/${datepollId}/submissions.csv`, `${poll.id}.csv`);
  } catch {
    toasts.error(t("datepoll.details.csvFail"));
  }
}
</script>

<DetailsPageShell loaded={!query.isPending} skeletonRows={4}>
  {#if notFound}
    <AppCard stack={false}>
      <h2>{t("datepoll.details.notFoundTitle")}</h2>
      <p class="muted">{t("datepoll.details.notFoundBody")}</p>
      <RouterLink to="/datepoll" class="back-link">{t("datepoll.details.backToList")}</RouterLink>
    </AppCard>
  {:else if query.error}
    <AppCard stack={false}>
      <p>{t("datepoll.details.loadFailed")}</p>
    </AppCard>
  {:else if poll}
    {@const slug = poll.slug}
    <DetailHeaderCard
      title={lt(poll.name_nl, poll.name_en) ?? ""}
      chapterName={poll.chapter_name}
      imageUrl={poll.image_url}
      imageArtist={poll.image_artist_instagram}
      descriptionHtml={lt(poll.description_nl, poll.description_en)}
      qrSrc={datepollQrUrl(slug)}
      publicUrl={publicDatepollUrl(slug)}
      editTo={`/datepoll/${poll.id}/edit`}
      oncopyQr={() => void share.copyQr(slug)}
      oncopyLink={() => void share.copyLink(slug)}
    >
      {#snippet meta()}
        {#if poll.location}
          <p class="muted overview-meta">
            <a
              href={mapLink({
                location: poll.location,
                latitude: poll.latitude ?? null,
                longitude: poll.longitude ?? null,
              })}
              target="_blank"
              rel="noopener"
              class="meta-link">{poll.location}</a
            >
          </p>
        {/if}
      {/snippet}
    </DetailHeaderCard>

    <!-- The dates on offer, shown whether or not anybody has answered
         yet. The same card the roster page gives its chores. -->
    {#if poll.slots?.length}
      <AppCard>
        <div class="summary-header">
          <h2>{t("datepoll.details.datesHeading")}</h2>
        </div>
        <MonthCalendar
          bind:month={datesMonth}
          slots={poll.slots ?? []}
          locale={locale()}
          prevLabel={t("datepoll.details.prevMonth")}
          nextLabel={t("datepoll.details.nextMonth")}
        />
      </AppCard>
    {/if}

    <AppCard>
      <div class="summary-header">
        <h2>{t("datepoll.details.resultsTitle")}</h2>
        <div class="header-actions">
          <AppButton
            label={t("datepoll.details.exportCsv")}
            size="small"
            severity="secondary"
            text
            icon="download"
            disabled={!summary || summary.submission_count === 0}
            onclick={exportCsv}
          />
          {#if summary}
            <RecoverLinksPill
              count={summary.submission_count}
              cap={auth.user?.participant_cap ?? null}
              label={t("datepoll.details.responses")}
              loadRows={recoverRows}
              recoverPath={(id) => `/api/v1/datepoll/${datepollId}/submissions/${id}/edit-link`}
              publicUrl={(tok) => `${publicDatepollUrl(slug)}?s=${tok}`}
            />
          {/if}
        </div>
      </div>

      {#if !summary || summary.submission_count === 0}
        <p class="muted">{t("datepoll.details.noResponsesYet")}</p>
      {:else}
        <!-- One bar per date, split into yes, maybe and no. A ranked row
             leads with its chip. -->
        <TallyLegend items={legendItems} />
        <ul class="slot-tally">
          {#each summary.slots as s (s.id)}
            <li class="slot-row">
              <div class="slot-label">
                <span class="rank {rankById[s.id] ? `r${rankById[s.id]}` : ''}">
                  {rankLabel(s.id)}
                </span>
                <span class="slot-when">{slotHeading(s)}</span>
              </div>
              <SegmentedBar segments={slotSegments(s)} max={maxTotal} />
            </li>
          {/each}
        </ul>

        <!-- One note per respondent, each led by the name that wrote
             it. -->
        {#if noted.length}
          <div class="notes-section">
            <h3>{t("datepoll.details.notesTitle")}</h3>
            <ul class="comments">
              {#each noted as sub (sub.submission_id)}
                <li>
                  <span class="comment-name">{nameOf(sub)}</span>
                  {sub.note}
                </li>
              {/each}
            </ul>
          </div>
        {/if}

        {#if subs.length}
          <div class="grid-wrap">
            <table class="grid">
              <thead>
                <tr>
                  <th class="who">{t("datepoll.details.respondent")}</th>
                  {#each summary.slots as s (s.id)}
                    <th class="slot-th">
                      <div>{shortDate(s.on_date)}</div>
                      {#if slotTime(s)}<div class="th-time">{slotTime(s)}</div>{/if}
                    </th>
                  {/each}
                </tr>
              </thead>
              <tbody>
                {#each subs as sub (sub.submission_id)}
                  <tr>
                    <td class="who">{nameOf(sub)}</td>
                    {#each summary.slots as s (s.id)}
                      <td class="cell {sub.answers[s.id] ?? 'none'}">
                        {sub.answers[s.id] ? AVAIL_GLYPH[sub.answers[s.id]] : ""}
                      </td>
                    {/each}
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {/if}
      {/if}
    </AppCard>
  {/if}
</DetailsPageShell>

<style>
/* The header is the shared ``DetailHeaderCard``; its chrome, the
 * summary header and the mobile stack all come from theme.css. */

/* One row per date: the date on the left, its bar on the right. The
 * roster page's tally is the same shape. */
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
.slot-label {
  display: flex;
  align-items: baseline;
  min-width: 0;
}
.slot-when {
  min-width: 0;
}
/* The chip keeps its width whether or not the row ranks, so every label
 * starts in the same place. */
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
.rank.r1,
.rank.r2,
.rank.r3 {
  border-radius: 999px;
  padding: 0.0625rem 0;
  color: #fff;
}
.rank.r1 {
  background: var(--brand-green);
}
.rank.r2 {
  background: var(--brand-rank-silver);
}
.rank.r3 {
  background: var(--brand-rank-bronze);
}
.comments {
  margin: 0.5rem 0 0;
  padding-left: 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}
.comments li {
  line-height: 1.4;
}
.comment-name {
  font-weight: 600;
  margin-right: 0.375rem;
}
.notes-section {
  margin-top: 1.25rem;
}
.notes-section h3 {
  margin: 0 0 0.25rem;
  font-size: 0.875rem;
}

.grid-wrap {
  margin-top: 1.5rem;
  overflow-x: auto;
}
/* The table draws its own outer frame: without it the collapsed right
 * and bottom edges get clipped by the scroll container. */
.grid {
  border-collapse: collapse;
  border: 1px solid var(--brand-border);
  font-size: 0.8125rem;
}
.grid th,
.grid td {
  border: 1px solid var(--brand-border);
  padding: 0.25rem 0.5rem;
  text-align: center;
  white-space: nowrap;
}
.grid th.who,
.grid td.who {
  text-align: left;
  position: sticky;
  left: 0;
  background: var(--brand-surface);
}
/* Every date column is the same width, so they line up. */
.grid th.slot-th,
.grid tbody td:not(.who) {
  width: 4rem;
}
.grid th.slot-th .th-time {
  font-weight: 400;
  font-size: 0.75rem;
  color: var(--brand-text-muted);
}
.cell.yes {
  background: var(--brand-green);
  color: #fff;
}
.cell.maybe {
  background: var(--brand-amber);
  color: #fff;
}
.cell.no {
  background: var(--brand-neutral);
  color: var(--brand-text);
}
</style>
