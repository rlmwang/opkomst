<script setup lang="ts">
import Button from "primevue/button";
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import AppCard from "@/components/AppCard.vue";
import DetailsPageShell from "@/components/DetailsPageShell.vue";
import type { ChoreOut } from "@/api/types";
import { useRoster } from "@/composables/useChores";
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
      <AppCard>
        <div class="overview-head">
          <div>
            <h1>
              {{ roster.name }}
              <span v-if="roster.chapter_name" class="chapter-chip">{{ roster.chapter_name }}</span>
            </h1>
            <p class="muted">{{ cadence }} · {{ dateWindow() }}</p>
            <p v-if="roster.description" class="description">{{ roster.description }}</p>
          </div>
          <router-link :to="`/chores/${roster.id}/edit`">
            <Button :label="t('chores.details.edit')" icon="pi pi-pencil" size="small" severity="secondary" />
          </router-link>
        </div>
        <div class="share-row">
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

      <!-- Volunteers + Schedule land with their data in tasks 05/06. -->
      <AppCard>
        <h2>{{ t("chores.details.volunteersHeading") }}</h2>
        <p class="muted">{{ t("chores.details.volunteersEmpty") }}</p>
      </AppCard>

      <AppCard>
        <h2>{{ t("chores.details.scheduleHeading") }}</h2>
        <p class="muted">{{ t("chores.details.scheduleEmpty") }}</p>
      </AppCard>
    </template>
  </DetailsPageShell>
</template>

<style scoped>
.overview-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
}
.overview-head h1 { margin: 0 0 0.25rem; }
.description { margin: 0.5rem 0 0; }
.chapter-chip {
  display: inline-flex;
  align-items: center;
  margin-left: 0.5rem;
  padding: 0.125rem 0.5rem;
  border-radius: 999px;
  background: var(--brand-surface-subtle, rgba(0, 0, 0, 0.05));
  color: var(--brand-text-muted);
  font-size: 0.75rem;
  vertical-align: baseline;
}
.share-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  margin-top: 0.75rem;
}
.link-row {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  min-width: 0;
}
.qr-button {
  line-height: 0;
  background: none;
  border: 0;
  padding: 0;
  cursor: pointer;
  border-radius: 6px;
}
.qr {
  width: 96px;
  height: 96px;
  background: white;
  border: 1px solid var(--brand-border);
  border-radius: 6px;
  padding: 4px;
  display: block;
}
.link-row a {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
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
</style>
