<script setup lang="ts">
/**
 * The organiser's roster calendar: fetches the whole roster for a month
 * (live, or the post-"fold in" look-ahead) and feeds the shared
 * ``RosterCalendarView``. Owns its month so chores/panels scroll on their
 * own. With ``reassignable`` the live view lets the organiser hand any
 * upcoming pinned shift to another enrolled volunteer ("overnemen"): each
 * such day opens a popover with a per-shift volunteer picker.
 */
import { computed, ref } from "vue";
import { useI18n } from "@/i18n";
import { useQueryClient } from "@tanstack/vue-query";
import RosterCalendarView, { type RosterAssignment, type RosterDay } from "./RosterCalendarView.vue";
import { post } from "@/api/client";
import { useRebalancePreviewCalendar, useRosterCalendar, useRosterVolunteers } from "@/composables/useChores";
import { useToasts } from "@/lib/toasts";

const props = defineProps<{
  rosterId: string;
  preview?: boolean;
  enabled?: boolean;
  reassignable?: boolean;
  locale: string;
  openLabel: string;
  anonLabel: string;
  prevLabel: string;
  nextLabel: string;
  noChangeLabel?: string;
}>();

const { t } = useI18n();
const toasts = useToasts();
const queryClient = useQueryClient();

function currentMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}
function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}
const month = ref(currentMonth());
const rosterId = computed(() => props.rosterId);
const enabled = computed(() => props.enabled ?? true);
const query = props.preview
  ? useRebalancePreviewCalendar(rosterId, month, enabled)
  : useRosterCalendar(rosterId, month);

// Fold every chore's days into one per-date bucket of emoji-tagged assignments.
// With ``reassignable``, an upcoming pinned shift carries an action so its day
// opens the hand-over popover.
const daysByIso = computed<Record<string, RosterDay>>(() => {
  const today = todayIso();
  const map: Record<string, RosterDay> = {};
  for (const chore of query.data.value ?? []) {
    for (const day of chore.days) {
      const d = (map[day.on_date] ??= { assignments: [], tentative: false, changed: false });
      if (day.tentative) d.tentative = true;
      if (day.changed) d.changed = true;
      for (const a of day.assignees) {
        const handoverable =
          !!props.reassignable && !props.preview && !!a.shift_id && day.on_date >= today && a.status !== "done";
        d.assignments.push({
          emoji: chore.emoji,
          name: a.name,
          open: a.open,
          status: a.status,
          choreId: chore.chore_id,
          action: handoverable ? { shiftId: a.shift_id!, kind: "reassign", label: "" } : undefined,
        });
      }
    }
  }
  return map;
});
const hasChanges = computed(() => Object.values(daysByIso.value).some((d) => d.changed));

// The hand-over picker: every volunteer enrolled in the shift's chore.
const volunteersQuery = useRosterVolunteers(rosterId);
function candidates(a: RosterAssignment) {
  return (volunteersQuery.data.value ?? []).filter((v) => a.choreId && v.enrolled_chore_ids.includes(a.choreId));
}
const saving = ref(false);
async function handOver(a: RosterAssignment, volunteerId: string, close: () => void): Promise<void> {
  if (!a.action || !volunteerId) return;
  saving.value = true;
  try {
    await post(`/api/v1/chore/${props.rosterId}/shifts/${a.action.shiftId}/reassign`, {
      volunteer_id: volunteerId,
    });
    await queryClient.invalidateQueries({ queryKey: ["chore", props.rosterId] });
    toasts.success(t("chore.details.handOverDone"));
  } catch {
    toasts.error(t("chore.details.handOverFailed"));
  } finally {
    saving.value = false;
    close();
  }
}

const weekdays = computed(() => {
  const fmt = new Intl.DateTimeFormat(props.locale === "en" ? "en-GB" : "nl-NL", { weekday: "short" });
  return Array.from({ length: 7 }, (_, i) => fmt.format(new Date(2024, 0, 1 + i)));
});
</script>

<template>
  <div>
    <p v-if="preview && noChangeLabel && !hasChanges" class="muted rc-note">{{ noChangeLabel }}</p>
    <RosterCalendarView
      v-model:month="month"
      :days-by-iso="daysByIso"
      :weekdays="weekdays"
      :prev-label="prevLabel"
      :next-label="nextLabel"
      :locale="locale"
      :open-label="openLabel"
      :anon-label="anonLabel"
      :busy="saving"
    >
      <template v-if="reassignable" #popover="{ assignments, close }">
        <div v-for="(a, i) in assignments.filter((x) => x.action)" :key="i" class="rc-handover">
          <span class="rc-who">
            <span v-if="a.emoji" aria-hidden="true">{{ a.emoji }}</span>
            {{ a.open ? `(${openLabel})` : a.name || anonLabel }}
          </span>
          <select
            class="rc-picker"
            :disabled="saving"
            :aria-label="t('chore.details.handOver')"
            @change="handOver(a, ($event.target as HTMLSelectElement).value, close)"
          >
            <option value="" disabled selected>{{ t("chore.details.handOver") }}</option>
            <option v-for="v in candidates(a)" :key="v.id" :value="v.id">{{ v.display_name || anonLabel }}</option>
          </select>
        </div>
      </template>
    </RosterCalendarView>
  </div>
</template>

<style scoped>
.rc-note {
  margin: 0 0 0.5rem;
  font-size: 0.8125rem;
}
.rc-handover {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.rc-who {
  font-size: 0.8125rem;
  font-weight: 600;
}
.rc-picker {
  padding: 0.4rem 0.5rem;
  border: 1px solid var(--brand-border);
  border-radius: 6px;
  background: var(--brand-surface);
  color: var(--brand-text);
  font: inherit;
  font-size: 0.8125rem;
  cursor: pointer;
}
.rc-picker:disabled {
  cursor: default;
  opacity: 0.6;
}
</style>
