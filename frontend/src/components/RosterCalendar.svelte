<script lang="ts">
/**
 * The organiser's roster calendar: fetches the whole roster for a month
 * (live, or the post-"fold in" look-ahead) and feeds the shared
 * ``RosterCalendarView``. Owns its month so chores/panels scroll on their
 * own. With ``reassignable`` the live view lets the organiser hand any
 * upcoming pinned shift to another enrolled volunteer ("overnemen"): each
 * such day opens a popover with a per-shift volunteer picker.
 */
import { untrack } from "svelte";

import RosterCalendarView, {
  type RosterAssignment,
  type RosterDay,
} from "./RosterCalendarView.svelte";
import { post } from "@/api/client";
import { t } from "@/i18n.svelte";
import { queryClient } from "@/lib/query-client";
import { useToasts } from "@/lib/toasts";
import {
  calendarQuery,
  rebalancePreviewQuery,
  volunteersQuery,
} from "@/composables/useChores.svelte";

const {
  rosterId,
  preview,
  enabled = true,
  reassignable,
  locale,
  openLabel,
  anonLabel,
  prevLabel,
  nextLabel,
  noChangeLabel,
}: {
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
} = $props();

const toasts = useToasts();

function currentMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}
function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

let month = $state(currentMonth());

// Live or look-ahead is fixed for the component's lifetime; only the
// month it shows moves.
const query = untrack(() => preview)
  ? rebalancePreviewQuery(() => rosterId, () => month, () => enabled)
  : calendarQuery(() => rosterId, () => month, () => enabled);

// Fold every chore's days into one per-date bucket of emoji-tagged
// assignments. With ``reassignable``, an upcoming pinned shift carries
// an action so its day opens the hand-over popover.
const daysByIso = $derived.by<Record<string, RosterDay>>(() => {
  const today = todayIso();
  const map: Record<string, RosterDay> = {};
  for (const chore of $query.data ?? []) {
    for (const day of chore.days) {
      const d = (map[day.on_date] ??= { assignments: [], tentative: false, changed: false });
      if (day.tentative) d.tentative = true;
      if (day.changed) d.changed = true;
      for (const a of day.assignees) {
        const handoverable =
          !!reassignable && !preview && !!a.shift_id && day.on_date >= today && a.status !== "done";
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
const hasChanges = $derived(Object.values(daysByIso).some((d) => d.changed));

// The hand-over picker: every volunteer enrolled in the shift's chore.
const volunteers = volunteersQuery(() => rosterId);
function candidates(a: RosterAssignment) {
  return ($volunteers.data ?? []).filter(
    (v) => a.choreId && v.enrolled_chore_ids.includes(a.choreId),
  );
}

let saving = $state(false);
async function handOver(a: RosterAssignment, volunteerId: string, close: () => void): Promise<void> {
  if (!a.action || !volunteerId) return;
  saving = true;
  try {
    await post(`/api/v1/chore/${rosterId}/shifts/${a.action.shiftId}/reassign`, {
      volunteer_id: volunteerId,
    });
    await queryClient.invalidateQueries({ queryKey: ["chore", rosterId] });
    toasts.success(t("chore.details.handOverDone"));
  } catch {
    toasts.error(t("chore.details.handOverFailed"));
  } finally {
    saving = false;
    close();
  }
}

const weekdays = $derived.by(() => {
  const fmt = new Intl.DateTimeFormat(locale === "en" ? "en-GB" : "nl-NL", { weekday: "short" });
  return Array.from({ length: 7 }, (_, i) => fmt.format(new Date(2024, 0, 1 + i)));
});
</script>

<div>
  {#if preview && noChangeLabel && !hasChanges}
    <p class="muted rc-note">{noChangeLabel}</p>
  {/if}
  <RosterCalendarView
    bind:month
    {daysByIso}
    {weekdays}
    {prevLabel}
    {nextLabel}
    {locale}
    {openLabel}
    {anonLabel}
    busy={saving}
    popover={reassignable ? handoverPopover : undefined}
  />
</div>

{#snippet handoverPopover({ assignments, close }: { assignments: RosterAssignment[]; close: () => void })}
  {#each assignments.filter((x: RosterAssignment) => x.action) as a, i (i)}
    <div class="rc-handover">
      <span class="rc-who">
        {#if a.emoji}<span aria-hidden="true">{a.emoji}</span>{/if}
        {a.open ? `(${openLabel})` : a.name || anonLabel}
      </span>
      <select
        class="rc-picker"
        disabled={saving}
        aria-label={t("chore.details.handOver")}
        onchange={(e) => handOver(a, (e.currentTarget as HTMLSelectElement).value, close)}
      >
        <option value="" disabled selected>{t("chore.details.handOver")}</option>
        {#each candidates(a) as v (v.id)}
          <option value={v.id}>{v.display_name || anonLabel}</option>
        {/each}
      </select>
    </div>
  {/each}
{/snippet}

<style>
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
