<script module lang="ts">
/**
 * Normalise a typed time to 24-hour ``HH:MM``.
 *
 * Never AM/PM: the native time input cannot be moved off the operating
 * system's locale, so the field is ours. Minutes default to ``00`` when
 * they are left out, so ``19`` is 19:00, ``1930`` and ``19:30`` are
 * both 19:30, and ``9`` is 09:00. Empty stays empty, and anything out
 * of range clamps.
 */
export function normalizeTime(raw: string): string {
  const digits = raw.replace(/\D/g, "");
  if (!digits) return "";
  const h = digits.length <= 2 ? digits : digits.slice(0, digits.length - 2);
  const m = digits.length <= 2 ? "0" : digits.slice(-2);
  const hh = Math.min(23, Math.max(0, parseInt(h, 10)));
  const mm = Math.min(59, Math.max(0, parseInt(m, 10)));
  return `${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")}`;
}
</script>

<script lang="ts">
import { t } from "@/i18n.svelte";

/**
 * Two time boxes and an add button.
 *
 * The date poll editor has this row twice, once for the times that
 * apply to every day and once on each day's own card. The row owns what
 * is half-typed in it, which is why neither list has to keep a buffer
 * per day; the page is handed a finished pair and says whether it took
 * it.
 */
const { onadd }: { onadd: (slot: { start: string; end: string }) => boolean } = $props();

let start = $state("");
let end = $state("");

function add(): void {
  if (onadd({ start: normalizeTime(start), end: normalizeTime(end) })) {
    start = "";
    end = "";
  }
}
</script>

<div class="add-slot">
  <input
    bind:value={start}
    type="text"
    inputmode="numeric"
    placeholder="00:00"
    maxlength="5"
    class="time-input"
    aria-label={t("datepoll.edit.slotStart")}
    onblur={() => (start = normalizeTime(start))}
    onkeyup={(e) => e.key === "Enter" && (start = normalizeTime(start))}
  />
  <span class="dash">–</span>
  <input
    bind:value={end}
    type="text"
    inputmode="numeric"
    placeholder="00:00"
    maxlength="5"
    class="time-input"
    aria-label={t("datepoll.edit.slotEnd")}
    onblur={() => (end = normalizeTime(end))}
    onkeyup={(e) => e.key === "Enter" && (end = normalizeTime(end))}
  />
  <button type="button" class="add-slot-btn" onclick={add}>
    {t("datepoll.edit.addSlot")}
  </button>
</div>

<style>
.add-slot {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  flex-wrap: wrap;
}
.time-input {
  font: inherit;
  font-size: 0.875rem;
  width: 4rem;
  text-align: center;
  padding: 0.25rem 0.375rem;
  border: 1px solid var(--brand-border);
  border-radius: 6px;
  background: var(--brand-bg);
  color: var(--brand-text);
}
.dash {
  color: var(--brand-text-muted);
}
.add-slot-btn {
  border: 1px solid var(--brand-border);
  background: var(--brand-surface);
  color: var(--brand-text);
  border-radius: 6px;
  padding: 0.25rem 0.625rem;
  font: inherit;
  font-size: 0.8125rem;
  cursor: pointer;
}
.add-slot-btn:hover {
  border-color: var(--brand-red);
  color: var(--brand-red);
}
</style>
