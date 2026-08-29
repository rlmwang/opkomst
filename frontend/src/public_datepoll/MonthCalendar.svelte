<script lang="ts">
/**
 * One month of a datepoll's candidate days for public voting, built on the
 * shared ``MonthGrid`` (so it matches every other calendar). Each candidate
 * day shows one tri-state pill per slot (whole-day → a single pill; timed →
 * a pill per time range). Tapping a pill cycles its state; the parent owns
 * the cycle. Rendered one grid per month (no navigator — months stack).
 */
import MonthGrid from "@/components/MonthGrid.svelte";
import type { Availability } from "./api";
import type { Locale } from "@/public_shared/strings";

interface SlotCell {
  id: string;
  label: string | null; // null = whole-day
}

const {
  year,
  month,
  slotsByIso,
  answers,
  locale,
  columns,
  ontoggle,
}: {
  year: number;
  month: number; // 0-based
  slotsByIso: Record<string, SlotCell[]>;
  answers: Record<string, Availability | null>;
  locale: Locale;
  // Shared column template (see PublicDatepoll): one fixed grid so every
  // stacked month lines up with the next and with the weekday header.
  columns: string;
  ontoggle: (slotId: string) => void;
} = $props();

const GLYPH: Record<Availability, string> = { yes: "✓", maybe: "~", no: "✕" };
const monthStr = $derived(`${year}-${String(month + 1).padStart(2, "0")}`);
const weekdays = $derived.by(() => {
  const fmt = new Intl.DateTimeFormat(locale === "en" ? "en-GB" : "nl-NL", { weekday: "short" });
  return Array.from({ length: 7 }, (_, i) => fmt.format(new Date(2024, 0, 1 + i)));
});
function dayClass(iso: string) {
  return { occ: !!slotsByIso[iso]?.length };
}
</script>

<MonthGrid month={monthStr} {locale} {weekdays} nav={false} {dayClass} {columns}>
  {#snippet day({ iso })}
    {#if slotsByIso[iso]?.length}
      <div class="votes">
        {#each slotsByIso[iso] as s (s.id)}
          <button
            type="button"
            class="vote {answers[s.id] ?? 'unset'}"
            onclick={(e) => {
              e.stopPropagation();
              ontoggle(s.id);
            }}
          >
            {#if s.label}<span class="vote-time">{s.label}</span>{/if}
            <span class="vote-glyph"
              >{answers[s.id] ? GLYPH[answers[s.id] as Availability] : s.label ? "" : "·"}</span
            >
          </button>
        {/each}
      </div>
    {/if}
  {/snippet}
</MonthGrid>

<style>
.votes {
  display: flex;
  flex-direction: column;
  gap: 3px;
  width: 100%;
  pointer-events: auto;
}
.vote {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.1875rem;
  border: 1px solid var(--brand-border);
  border-radius: 6px;
  background: var(--brand-bg);
  color: var(--brand-text);
  cursor: pointer;
  padding: 0.25rem 0.125rem;
  font-size: 0.6875rem;
  line-height: 1.1;
}
.vote.unset {
  border-style: dashed;
}
.vote-time {
  white-space: nowrap;
}
/* Always reserve the toggle glyph's slot — a fixed-width box whether it's
 * empty (unset) or showing ✓/~/✕ — so the pill and its time label don't
 * shift sideways the moment you tap. */
.vote-glyph {
  flex: none;
  width: 1em;
  text-align: center;
}
.vote.yes {
  background: var(--brand-green);
  color: #fff;
  border-color: var(--brand-green);
}
.vote.maybe {
  background: var(--brand-amber);
  color: #fff;
  border-color: var(--brand-amber);
}
.vote.no {
  background: var(--brand-neutral);
  color: var(--brand-text);
  border-color: var(--brand-neutral);
}
</style>
