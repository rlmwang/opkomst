<script setup lang="ts">
import Button from "primevue/button";
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import AppCard from "@/components/AppCard.vue";
import DetailsPageShell from "@/components/DetailsPageShell.vue";
import StatBar, { type StatSegment } from "@/components/StatBar.vue";
import type { ChoreOut } from "@/api/types";
import { useRoster, useRosterSchedule, useRosterVolunteers } from "@/composables/useChores";
import { useChoresClipboard } from "@/composables/useChoresClipboard";
import { choreQrUrl, publicChoreUrl } from "@/lib/chore-urls";
import { formatDate } from "@/lib/format";

const props = defineProps<{ rosterId: string }>();

const { t, locale } = useI18n();
const { copyLink, copyQr } = useChoresClipboard();

const rosterId = computed(() => props.rosterId);
const rosterQuery = useRoster(rosterId);
const roster = computed(() => rosterQuery.data.value ?? null);
const choreItems = computed<ChoreOut[]>(() => roster.value?.chores ?? []);
const loaded = computed(() => !rosterQuery.isPending.value);

const volunteersQuery = useRosterVolunteers(rosterId);
const volunteers = computed(() => volunteersQuery.data.value ?? []);
const scheduleQuery = useRosterSchedule(rosterId);
const schedule = computed(() => scheduleQuery.data.value ?? null);
const upcoming = computed(() => schedule.value?.confirmed ?? []);

// Volunteer accountability bars: length = that person's *resolved*
// shifts (done + handed-off + missed) relative to the busiest resolver,
// segmented by outcome. Upcoming shifts are deliberately excluded — for
// an open-ended roster they grow without bound. "Assigned so far" shows
// as a separate number.
type VolRow = (typeof volunteers.value)[number];
function resolved(v: VolRow): number {
  return v.completed + v.deferred + v.missed;
}
const maxResolved = computed(() => Math.max(1, ...volunteers.value.map(resolved)));
function barPct(n: number): string {
  return `${(n / maxResolved.value) * 100}%`;
}
function volSegments(v: VolRow): StatSegment[] {
  const segs: StatSegment[] = [];
  if (v.completed) segs.push({ width: barPct(v.completed), variant: "positive", title: t("chores.details.doneCount", { n: v.completed }) });
  if (v.deferred) segs.push({ width: barPct(v.deferred), variant: "warning", title: t("chores.details.deferredCount", { n: v.deferred }) });
  if (v.missed) segs.push({ width: barPct(v.missed), variant: "danger", title: t("chores.details.missedCount", { n: v.missed }) });
  return segs;
}
function barLabel(v: VolRow): string {
  return [
    t("chores.details.doneCount", { n: v.completed }),
    t("chores.details.deferredCount", { n: v.deferred }),
    t("chores.details.missedCount", { n: v.missed }),
  ].join(", ");
}

const choreName = computed<Record<string, string>>(() =>
  Object.fromEntries(choreItems.value.map((c) => [c.id, c.name])),
);

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

/** Human-readable day summary for one chore's cycle_slots, grouped by
 * week when k>1 (e.g. "Wk 1: Wed, Fri · Wk 2: Mon"). */
function slotSummary(c: ChoreOut): string {
  const r = roster.value;
  const k = r ? r.period_weeks : 1;
  if (c.cycle_slots.length === 0) return t("chores.details.noDays");
  if (k <= 1) {
    return c.cycle_slots.map((o) => dayLabels.value[o % 7]).join(", ");
  }
  const parts: string[] = [];
  for (let w = 0; w < k; w++) {
    const days = c.cycle_slots
      .filter((o) => Math.floor(o / 7) === w)
      .map((o) => dayLabels.value[o % 7]);
    if (days.length) parts.push(`${t("chores.edit.weekLabel", { n: w + 1 })}: ${days.join(", ")}`);
  }
  return parts.join(" · ");
}

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
          <button
            type="button"
            class="qr-button"
            v-tooltip.top="t('chores.share.copyQr')"
            :aria-label="t('chores.share.copyQr')"
            @click="copyQr(roster.slug)"
          >
            <img :src="choreQrUrl(roster.slug)" alt="" class="qr" />
          </button>
        </div>
      </AppCard>

      <AppCard>
        <h2>{{ t("chores.details.choresHeading") }}</h2>
        <p v-if="choreItems.length === 0" class="muted">{{ t("chores.details.noChores") }}</p>
        <ul v-else class="chore-list">
          <li v-for="c in choreItems" :key="c.id" class="chore-item">
            <span class="chore-name">
              <span v-if="c.emoji" class="chore-emoji">{{ c.emoji }}</span>
              {{ c.name }}
            </span>
            <span class="muted chore-days">{{ slotSummary(c) }}</span>
            <span v-if="c.people_per_shift > 1" class="people-chip">
              {{ t("chores.details.peoplePerShift", { n: c.people_per_shift }) }}
            </span>
          </li>
        </ul>
      </AppCard>

      <AppCard>
        <h2>{{ t("chores.details.volunteersHeading") }}</h2>
        <p v-if="volunteers.length === 0" class="muted">{{ t("chores.details.volunteersEmpty") }}</p>
        <template v-else>
          <div class="bar-legend muted">
            <span class="key"><i class="dot done" />{{ t("chores.details.legend.done") }}</span>
            <span class="key"><i class="dot deferred" />{{ t("chores.details.legend.deferred") }}</span>
            <span class="key"><i class="dot missed" />{{ t("chores.details.legend.missed") }}</span>
            <span class="key total-key">{{ t("chores.details.legend.assigned") }}</span>
          </div>
          <ul class="vol-tally">
            <li v-for="v in volunteers" :key="v.id" class="vol-row">
              <div class="vol-id">
                <span class="vol-name">{{ v.display_name || t("chores.details.anonymous") }}</span>
                <span class="muted vol-chores">
                  {{ v.enrolled_chore_ids.map((id) => choreName[id]).filter(Boolean).join(", ") }}
                </span>
              </div>
              <StatBar
                :segments="volSegments(v)"
                :aria-label="barLabel(v)"
                style="--stat-bar-height: 0.75rem"
              />
              <span class="vol-total" :title="t('chores.details.assignedCount', { n: v.assigned })">
                {{ v.assigned }}
              </span>
            </li>
          </ul>
        </template>
      </AppCard>

      <AppCard>
        <h2>{{ t("chores.details.scheduleHeading") }}</h2>
        <p v-if="schedule" class="muted stats-line">
          {{ t("chores.details.stats", {
            scheduled: schedule.stats.scheduled,
            done: schedule.stats.done,
            missed: schedule.stats.missed,
            open: schedule.stats.open,
          }) }}
        </p>
        <p v-if="upcoming.length === 0" class="muted">
          {{ t("chores.details.scheduleEmpty") }}
        </p>
        <ul v-else class="shift-list">
          <li v-for="s in upcoming" :key="s.id" class="shift-item">
            <span class="shift-date">{{ formatDate(s.on_date, locale) }}</span>
            <span class="shift-chore">{{ s.chore_name }}</span>
            <span class="shift-assignee" :class="{ open: !s.assignee_name }">
              {{ s.assignee_name || t("chores.details.openShift") }}
            </span>
          </li>
        </ul>
      </AppCard>
    </template>
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
  gap: 0.5rem;
}
.chore-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}
.chore-name { font-weight: 600; }
.chore-emoji { margin-right: 0.25rem; }
.chore-days { font-size: 0.875rem; }
.people-chip {
  padding: 0.125rem 0.5rem;
  border-radius: 999px;
  background: var(--brand-surface-subtle, rgba(0, 0, 0, 0.05));
  color: var(--brand-text-muted);
  font-size: 0.75rem;
}
.shift-list {
  list-style: none;
  margin: 0.5rem 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.shift-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}
.vol-chores,
.shift-chore { font-size: 0.875rem; }

/* Volunteer accountability tally — a datepoll-style stacked bar per
 * person (done / handed-off / missed), plus their assigned total. */
.bar-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem 1rem;
  font-size: 0.8125rem;
  margin: 0.25rem 0 0.75rem;
}
.bar-legend .key {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
}
.bar-legend .total-key { margin-left: auto; font-variant: small-caps; }
.dot {
  width: 0.625rem;
  height: 0.625rem;
  border-radius: 2px;
  flex-shrink: 0;
}
.dot.done { background: var(--brand-green); }
.dot.deferred { background: var(--brand-amber); }
.dot.missed { background: var(--brand-red); }
.vol-tally {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
}
.vol-row {
  display: grid;
  grid-template-columns: minmax(6rem, 12rem) 1fr auto;
  align-items: center;
  gap: 0.75rem;
}
.vol-id {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.vol-name {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.vol-chores {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.vol-total {
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  min-width: 1.5rem;
  text-align: right;
}
.stats-line { margin: 0 0 0.5rem; }
.shift-date { min-width: 8rem; }
.shift-assignee { margin-left: auto; font-weight: 500; }
.shift-assignee.open { color: var(--brand-red); font-weight: 600; }
</style>
