<script setup lang="ts">
import Button from "primevue/button";
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";
import { useQueryClient } from "@tanstack/vue-query";
import AppCard from "@/components/AppCard.vue";
import AppDialog from "@/components/AppDialog.vue";
import DetailsPageShell from "@/components/DetailsPageShell.vue";
import RosterCalendar from "@/components/RosterCalendar.vue";
import SegmentedBar, { type BarSegment } from "@/components/SegmentedBar.vue";
import TallyLegend, { type LegendItem } from "@/components/TallyLegend.vue";
import WeekdayGrid from "@/components/WeekdayGrid.vue";
import type { ChoreOut } from "@/api/types";
import { post } from "@/api/client";
import { useRoster, useRosterAccountability, useRosterSchedule } from "@/composables/useChores";
import { useChoresClipboard } from "@/composables/useChoresClipboard";
import { choreQrUrl, publicChoreUrl } from "@/lib/chore-urls";
import { formatDate } from "@/lib/format";
import { useToasts } from "@/lib/toasts";

const props = defineProps<{ rosterId: string }>();

const { t, locale } = useI18n();
const { copyLink, copyQr } = useChoresClipboard();
const toasts = useToasts();
const queryClient = useQueryClient();

const rosterId = computed(() => props.rosterId);
const rosterQuery = useRoster(rosterId);
const roster = computed(() => rosterQuery.data.value ?? null);
const choreItems = computed<ChoreOut[]>(() => roster.value?.chores ?? []);
const loaded = computed(() => !rosterQuery.isPending.value);

// Accountability broken down per chore — one section per chore, each
// listing the volunteers enrolled in it with their per-chore turn split.
const accountabilityQuery = useRosterAccountability(rosterId);
const accountability = computed(() => accountabilityQuery.data.value ?? []);
const volunteerCount = computed(() => roster.value?.volunteer_count ?? 0);

// "Fold in now": there's someone to fold in only while the roster is
// running and at least one enrolled volunteer is still pending. Preview the
// confirmed-shift changes first, then commit the rebalance on confirm.
const hasPending = computed(
  () => roster.value?.activated_at != null && accountability.value.some((c) => c.volunteers.some((v) => v.pending)),
);
const showFoldIn = ref(false);
const rebalancing = ref(false);

// Each chore renders its own ChoreCalendarPanel (own month + fetch), so the
// page only owns the dialog toggle; the panels do the calendar plumbing.
function openFoldIn() {
  showFoldIn.value = true;
}
async function confirmFoldIn() {
  rebalancing.value = true;
  try {
    await post(`/api/v1/chores/${props.rosterId}/rebalance`);
    await queryClient.invalidateQueries({ queryKey: ["chores"] });
    showFoldIn.value = false;
    toasts.success(t("chores.details.foldInDone"));
  } catch {
    toasts.error(t("chores.details.foldInFailed"));
  } finally {
    rebalancing.value = false;
  }
}

// A pending newcomer folds into pins as the horizon edge rolls forward
// (design §7): their first turns land at today + commit_horizon_days.
const horizonEdge = computed(() => {
  const days = roster.value?.commit_horizon_days;
  if (days == null) return null;
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
});
const scheduleQuery = useRosterSchedule(rosterId);
const schedule = computed(() => scheduleQuery.data.value ?? null);

// Volunteer accountability bar: the split of a person's shifts across
// their own turns, ones picked up for others, handed off, and missed.
// Normalised (each bar fills the track) so a newcomer's bar isn't tiny
// just because they've done less (design §7); the count sits in each
// segment. Regular turns vs picked-up is the provenance split; handed
// off / missed are the outcomes that cost favour.
type VolRow = (typeof accountability.value)[number]["volunteers"][number];
function volSegments(v: VolRow): BarSegment[] {
  return [
    { value: v.regular_turns, variant: "positive", title: t("chores.details.regularCount", { n: v.regular_turns }) },
    { value: v.picked_up, variant: "accent", title: t("chores.details.pickedUpCount", { n: v.picked_up }) },
    { value: v.deferred, variant: "warning", title: t("chores.details.deferredCount", { n: v.deferred }) },
    // Grey, not red: the bar already uses green (own turns), so red would
    // be a red/green pair that colour-blind users can't separate.
    { value: v.missed, variant: "neutral", title: t("chores.details.missedCount", { n: v.missed }) },
  ];
}
function barLabel(v: VolRow): string {
  return volSegments(v)
    .filter((s) => s.value > 0)
    .map((s) => s.title)
    .join(", ");
}
const legendItems = computed<LegendItem[]>(() => [
  { variant: "positive", label: t("chores.details.legend.regular") },
  { variant: "accent", label: t("chores.details.legend.pickedUp") },
  { variant: "warning", label: t("chores.details.legend.deferred") },
  { variant: "neutral", label: t("chores.details.legend.missed") },
]);

const dayLabels = computed(() => [
  t("chores.edit.weekday.mon"),
  t("chores.edit.weekday.tue"),
  t("chores.edit.weekday.wed"),
  t("chores.edit.weekday.thu"),
  t("chores.edit.weekday.fri"),
  t("chores.edit.weekday.sat"),
  t("chores.edit.weekday.sun"),
]);

const cadence = computed(() => {
  const r = roster.value;
  if (!r) return "";
  return r.period_weeks <= 1
    ? t("chores.recurrence.weekly")
    : t("chores.recurrence.everyKWeeks", { k: r.period_weeks });
});


function dateWindow(): string {
  const r = roster.value;
  if (!r) return "";
  const start = formatDate(r.starts_on, locale.value);
  if (!r.ends_on) return t("chores.details.fromDate", { date: start });
  return `${start} – ${formatDate(r.ends_on, locale.value)}`;
}
</script>

<template>
  <DetailsPageShell :loaded="loaded" :skeleton-rows="4">
    <template v-if="roster">
      <AppCard :stack="false" class="overview">
        <h1>
          {{ roster.name }}
          <span v-if="roster.chapter_name" class="chapter-chip">{{ roster.chapter_name }}</span>
        </h1>
        <figure v-if="roster.image_url" class="detail-image">
          <img :src="roster.image_url" :alt="roster.name" />
          <figcaption v-if="roster.image_artist_instagram" class="muted">
            {{ t("imageField.credit") }}
            <a :href="`https://instagram.com/${roster.image_artist_instagram}`" target="_blank" rel="noopener">@{{ roster.image_artist_instagram }}</a>
          </figcaption>
        </figure>
        <div class="overview-body">
          <button
            type="button"
            class="qr-button"
            v-tooltip.top="t('chores.share.copyQr')"
            :aria-label="t('chores.share.copyQr')"
            @click="copyQr(roster.slug)"
          >
            <img :src="choreQrUrl(roster.slug)" alt="" class="qr" />
          </button>
          <div class="overview-text">
            <p class="muted overview-meta">{{ cadence }} · {{ dateWindow() }}</p>
            <p v-if="roster.description" class="description">{{ roster.description }}</p>
            <div class="link-row">
              <a :href="publicChoreUrl(roster.slug)" target="_blank" rel="noopener">{{ publicChoreUrl(roster.slug) }}</a>
              <Button
                icon="pi pi-copy"
                size="small"
                severity="secondary"
                text
                v-tooltip.top="t('chores.share.copyLink')"
                :aria-label="t('chores.share.copyLink')"
                @click="copyLink(roster.slug)"
              />
            </div>
            <div>
              <router-link :to="`/chores/${roster.id}/edit`">
                <Button :label="t('chores.details.edit')" icon="pi pi-pencil" size="small" severity="secondary" />
              </router-link>
            </div>
          </div>
        </div>
      </AppCard>

      <AppCard>
        <div class="summary-header">
          <h2>{{ t("chores.details.choresHeading") }}</h2>
        </div>
        <p v-if="choreItems.length === 0" class="muted">{{ t("chores.details.noChores") }}</p>
        <ul v-else class="chore-list">
          <li v-for="c in choreItems" :key="c.id" class="chore-item">
            <div class="chore-head">
              <span class="chore-name">
                <span v-if="c.emoji" class="chore-emoji">{{ c.emoji }}</span>
                {{ c.name }}
              </span>
              <span v-if="c.people_per_shift > 1" class="people-chip">
                {{ t("chores.details.peoplePerShift", { n: c.people_per_shift }) }}
              </span>
            </div>
            <p v-if="c.description" class="muted chore-desc">{{ c.description }}</p>
            <p v-if="c.cycle_slots.length === 0" class="muted chore-days">{{ t("chores.details.noDays") }}</p>
            <WeekdayGrid
              v-else
              :cycle-slots="c.cycle_slots"
              :period-weeks="roster?.period_weeks ?? 1"
              :weekday-labels="dayLabels"
            />
          </li>
        </ul>
      </AppCard>

      <AppCard>
        <div class="summary-header">
          <h2>{{ t("chores.details.volunteersHeading") }}</h2>
          <div v-if="volunteerCount" class="count-pill">
            <span class="count">{{ volunteerCount }}</span>
            <span class="label">{{ t("chores.details.volunteersLabel") }}</span>
          </div>
        </div>
        <p v-if="volunteerCount === 0" class="muted">{{ t("chores.details.volunteersEmpty") }}</p>
        <template v-else>
          <TallyLegend :items="legendItems" />
          <!-- One section per chore; each row is just the volunteer + their
               per-chore bar (the section heading names the chore). -->
          <section v-for="c in accountability" :key="c.chore_id" class="chore-section">
            <h3 class="chore-section-name">
              <span v-if="c.emoji" class="chore-emoji">{{ c.emoji }}</span>{{ c.chore_name }}
            </h3>
            <p v-if="c.volunteers.length === 0" class="muted chore-section-empty">
              {{ t("chores.details.choreNoVolunteers") }}
            </p>
            <ul v-else class="vol-tally">
              <li v-for="v in c.volunteers" :key="v.id" class="vol-row">
                <span class="vol-name">{{ v.display_name || t("chores.details.anonymous") }}</span>
                <!-- A newcomer with no turns of this chore yet: show the
                     "joining" note in place of the (empty) bar. -->
                <span v-if="v.pending && horizonEdge" class="vol-joining">
                  {{ t("chores.details.joining", { date: formatDate(horizonEdge, locale) }) }}
                </span>
                <SegmentedBar v-else :segments="volSegments(v)" :aria-label="barLabel(v)" />
              </li>
            </ul>
          </section>
        </template>
      </AppCard>

      <AppCard>
        <div class="summary-header">
          <h2>{{ t("chores.details.scheduleHeading") }}</h2>
          <Button
            v-if="hasPending"
            :label="t('chores.details.foldIn')"
            icon="pi pi-user-plus"
            size="small"
            severity="secondary"
            @click="openFoldIn"
          />
        </div>
        <p v-if="schedule" class="muted stats-line">
          {{ t("chores.details.stats", {
            scheduled: schedule.stats.scheduled,
            done: schedule.stats.done,
            missed: schedule.stats.missed,
            open: schedule.stats.open,
          }) }}
        </p>
        <template v-if="roster?.activated_at">
          <div class="cal-legend muted">
            <span><i class="cal-swatch locked" />{{ t("chores.details.calLocked") }}</span>
            <span><i class="cal-swatch tentative" />{{ t("chores.details.calTentative") }}</span>
            <span><i class="cal-swatch open" />{{ t("chores.details.calOpen") }}</span>
            <span v-for="c in choreItems" :key="c.id" class="cal-chore">
              <span v-if="c.emoji" class="cal-chore-emoji">{{ c.emoji }}</span>{{ c.name }}
            </span>
          </div>
          <RosterCalendar
            :roster-id="props.rosterId"
            :locale="locale"
            :open-label="t('chores.details.openShift')"
            :anon-label="t('chores.details.anonymous')"
            :prev-label="t('chores.details.prevMonth')"
            :next-label="t('chores.details.nextMonth')"
          />
        </template>
        <p v-else class="muted">{{ t("chores.details.scheduleEmpty") }}</p>
      </AppCard>
    </template>

    <AppDialog v-model:visible="showFoldIn" :header="t('chores.details.foldInTitle')" width="560px">
      <p class="muted">{{ t("chores.details.foldInIntro") }}</p>
      <div class="cal-legend muted">
        <span><i class="cal-swatch locked" />{{ t("chores.details.calLocked") }}</span>
        <span><i class="cal-swatch tentative" />{{ t("chores.details.calTentative") }}</span>
        <span><i class="cal-swatch open" />{{ t("chores.details.calOpen") }}</span>
        <span><i class="cal-swatch changed" />{{ t("chores.details.calChanged") }}</span>
        <span v-for="c in choreItems" :key="c.id" class="cal-chore">
          <span v-if="c.emoji" class="cal-chore-emoji">{{ c.emoji }}</span>{{ c.name }}
        </span>
      </div>
      <RosterCalendar
        :roster-id="props.rosterId"
        preview
        :enabled="showFoldIn"
        :locale="locale"
        :open-label="t('chores.details.openShift')"
        :anon-label="t('chores.details.anonymous')"
        :prev-label="t('chores.details.prevMonth')"
        :next-label="t('chores.details.nextMonth')"
        :no-change-label="t('chores.details.foldInNoneMonth')"
      />
      <template #footer>
        <Button
          :label="t('common.cancel')"
          size="small"
          severity="secondary"
          text
          :disabled="rebalancing"
          @click="showFoldIn = false"
        />
        <Button
          :label="t('chores.details.foldInConfirm')"
          size="small"
          :loading="rebalancing"
          @click="confirmFoldIn"
        />
      </template>
    </AppDialog>
  </DetailsPageShell>
</template>

<style scoped>
/* Overview chrome (.overview, .overview-body, .overview-text,
 * .overview-meta, .detail-image, .link-row, .qr*) is shared from
 * theme.css. Only chore-specific list/stat styles stay here. */
.description { margin: 0; }
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
.chore-name { font-weight: 600; }
.chore-emoji { margin-right: 0.25rem; }
.chore-desc { font-size: 0.875rem; }
.chore-days { font-size: 0.875rem; }
.people-chip {
  padding: 0.125rem 0.5rem;
  border-radius: 999px;
  background: var(--brand-surface-subtle, rgba(0, 0, 0, 0.05));
  color: var(--brand-text-muted);
  font-size: 0.75rem;
}
/* Accountability tally, broken down per chore. Each chore is a section
 * (heading = chore name); rows are just the volunteer + their per-chore
 * four-colour bar (own turns / picked up / handed off / missed) with the
 * count in each segment. Legend + bar are the shared components. */
.chore-section {
  margin-top: 1.25rem;
}
.chore-section-name {
  margin: 0;
  font-size: 0.9375rem;
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
.stats-line { margin: 0 0 0.5rem; }

/* Calendar legend: swatches matching RosterCalendar's cell styles. */
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
  border: 1px solid var(--brand-border);
  background: var(--brand-surface);
}
.cal-swatch.tentative {
  border-style: dashed;
}
.cal-swatch.open {
  border-color: var(--brand-red);
  background: color-mix(in srgb, var(--brand-red) 12%, white);
}
.cal-swatch.changed {
  outline: 2px solid var(--brand-red);
  outline-offset: -1px;
}
/* Chore-emoji key, appended to the legend so the calendar's emojis decode. */
.cal-chore-emoji {
  font-size: 0.9375rem;
}
</style>
