<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from "vue";
import Disclosure from "@/public_shared/Disclosure.vue";
import PublicConfirmation from "@/public_shared/PublicConfirmation.vue";
import PublicEditBar from "@/public_shared/PublicEditBar.vue";
import SupportButtons from "@/public_shared/SupportButtons.vue";
import RecoveredNotice from "@/public_shared/RecoveredNotice.vue";
import PublicMetaRow from "@/public_shared/PublicMetaRow.vue";
import PublicTopCard from "@/public_shared/PublicTopCard.vue";
import PublicNotice from "@/public_shared/PublicNotice.vue";
import PublicShell from "@/public_shared/PublicShell.vue";
import { showToast } from "@/lib/toast";
import { resolveText } from "@/public_shared/bilingual";
import { type Locale, chromeStrings, pickLocale } from "@/public_shared/strings";
import { useEditForm } from "@/public_shared/useEditForm";
import { useEditLink } from "@/public_shared/useEditLink";
import {
  type Availability,
  type PublicDatepoll,
  ApiError,
  fetchDatepollBySlug,
  fetchSubmission,
  postSubmission,
  putSubmission,
  withdrawSubmission,
} from "./api";
import { mapLink } from "@/lib/map-link";
import { datepollStrings, formatTimeRange } from "./i18n";
import MonthCalendar from "./MonthCalendar.vue";

type Status = "loading" | "ready" | "unavailable" | "load-failed" | "submitted" | "withdrawn";

const status = ref<Status>("loading");
const poll = ref<PublicDatepoll | null>(null);
const locale = ref<Locale>("nl");
const pollTitle = computed(() =>
  poll.value ? resolveText(poll.value.name_nl, poll.value.name_en, locale.value) : null,
);
const pollDescription = computed(() =>
  poll.value ? resolveText(poll.value.description_nl, poll.value.description_en, locale.value) : null,
);
const c = computed(() => chromeStrings(locale.value));
const d = computed(() => datepollStrings(locale.value));

const displayName = ref("");
const note = ref("");
const submitting = ref(false);
const errorMsg = ref("");

// Auto-grow the note textarea to fit its content (no manual drag).
const noteEl = ref<HTMLTextAreaElement | null>(null);
function growNote(): void {
  const el = noteEl.value;
  if (!el) return;
  el.style.height = "auto";
  el.style.height = `${el.scrollHeight}px`;
}

// One answers map keyed by slot id — the single source of truth the
// inline calendar binds to (``null`` = unset).
const answers = reactive<Record<string, Availability | null>>({});

const slug = (): string => {
  const parts = window.location.pathname.split("/").filter(Boolean);
  return parts[parts.length - 1] ?? "";
};

// ``?s={token}`` puts the page in edit mode: pre-fill from the existing
// submission and PUT instead of POST on save. ``confirmSaved`` records the
// token AND routes the URL onto it so a refresh reopens the edit page.
const { editToken, editUrl, confirmSaved } = useEditLink("d", slug);

function hydrate(p: PublicDatepoll): void {
  poll.value = p;
  locale.value = pickLocale(p.locale);
  for (const s of p.slots) answers[s.id] = null;
}

const recoveredAt = ref<string | null>(null);

async function prefillFromSubmission(): Promise<void> {
  const sub = await fetchSubmission(editToken!);
  recoveredAt.value = sub.link_recovered_at ?? null;
  displayName.value = sub.display_name ?? "";
  note.value = sub.note ?? "";
  for (const [slotId, availability] of Object.entries(sub.answers)) {
    if (slotId in answers) answers[slotId] = availability;
  }
}

// Dirty/revert/saved state for the shared edit bar (edit mode only).
const { dirty, justSaved, captureBaseline, revert, flashSaved } = useEditForm({
  snapshot: () => ({ name: displayName.value, note: note.value, answers: { ...answers } }),
  apply: (s) => {
    displayName.value = s.name;
    note.value = s.note;
    for (const slotId of Object.keys(answers)) answers[slotId] = s.answers[slotId] ?? null;
  },
});

onMounted(async () => {
  const inlined = window.__OPKOMST_DATEPOLL__;
  if (inlined === null) {
    status.value = "unavailable";
    return;
  }
  try {
    const loaded = inlined ?? (await fetchDatepollBySlug(slug()));
    hydrate(loaded);
    if (editToken) await prefillFromSubmission();
    captureBaseline();
    status.value = "ready";
    await nextTick();
    growNote(); // fit a pre-filled note on first paint
  } catch (e) {
    status.value = e instanceof ApiError && e.status === 410 ? "unavailable" : "load-failed";
  }
});

// Slots come pre-sorted (date, then whole-day before timed, then start
// time). Group them by day for the calendar cells, and derive the
// distinct months to render.
const slotsByIso = computed<Record<string, { id: string; label: string | null }[]>>(() => {
  const out: Record<string, { id: string; label: string | null }[]> = {};
  for (const s of poll.value?.slots ?? []) {
    (out[s.on_date] ??= []).push({
      id: s.id,
      label: s.start_time && s.end_time ? formatTimeRange(s.start_time, s.end_time) : null,
    });
  }
  return out;
});

// One fixed column template shared by the weekday header and every stacked
// month, so day cells line up down the page. Each column gets a real minimum
// width, so when all seven weekdays are in play the grid overflows into a
// horizontal scroll (the card grows to match) instead of squashing the cells.
// Timed polls carry wider pills ("19:30–21:30 ✓") than whole-day dots, so
// they get a roomier floor.
const calendarColumns = computed(() => {
  const timed = (poll.value?.slots ?? []).some((s) => s.start_time && s.end_time);
  return `repeat(7, minmax(${timed ? "5.25rem" : "3rem"}, 1fr))`;
});

// Right-edge affordance: the stacked calendars live in their own horizontal
// scroller (``.cal-scroll``), so we read *that element's* own scroll metrics
// — reliable on every browser, unlike page-level ``scrollX`` which reads
// inconsistently across mobile engines. Show the arrow whenever there's more
// calendar to the right of the current position; hide it once at the end.
const canScrollRight = ref(false);
const calScroll = ref<HTMLElement | null>(null);
function updateScrollHint(): void {
  const el = calScroll.value;
  canScrollRight.value = !!el && el.scrollWidth - el.clientWidth - el.scrollLeft > 1;
}
function nudgeRight(): void {
  const el = calScroll.value;
  el?.scrollBy({ left: el.clientWidth * 0.6, behavior: "smooth" });
}
// Recompute when the scroller mounts and whenever its size/content changes
// (poll load, viewport resize, rotation). The template's ``@scroll`` handles
// scrolling itself.
let scrollObserver: ResizeObserver | null = null;
watch(calScroll, (el) => {
  scrollObserver?.disconnect();
  if (el) {
    scrollObserver = new ResizeObserver(() => updateScrollHint());
    scrollObserver.observe(el);
    updateScrollHint();
  }
});
onUnmounted(() => scrollObserver?.disconnect());

const months = computed(() => {
  const seen = new Set<string>();
  const out: { year: number; month: number }[] = [];
  for (const s of poll.value?.slots ?? []) {
    const [y, m] = s.on_date.split("-").map(Number);
    const key = `${y}-${m}`;
    if (!seen.has(key)) {
      seen.add(key);
      out.push({ year: y, month: m - 1 });
    }
  }
  return out;
});

const CYCLE: (Availability | null)[] = [null, "yes", "maybe", "no"];
function toggle(slotId: string): void {
  answers[slotId] = CYCLE[(CYCLE.indexOf(answers[slotId]) + 1) % CYCLE.length];
}

async function submit(): Promise<void> {
  errorMsg.value = "";
  if (poll.value?.name_required && !displayName.value.trim()) {
    showToast(c.value.nameRequired);
    return;
  }
  const picked = Object.entries(answers)
    .filter(([, a]) => a !== null)
    .map(([slotId, a]) => ({ datepoll_slot_id: slotId, availability: a as Availability }));
  if (picked.length === 0) {
    showToast(d.value.pickOne);
    return;
  }
  submitting.value = true;
  const body = { display_name: displayName.value.trim() || null, note: note.value.trim() || null, answers: picked };
  try {
    if (editToken) {
      await putSubmission(editToken, body);
      // Edit-mode save stays on the page: re-baseline + flash "Saved".
      captureBaseline();
      flashSaved();
    } else {
      const ack = await postSubmission(slug(), body);
      confirmSaved(ack.edit_token);
      status.value = "submitted";
    }
  } catch (e) {
    if (e instanceof ApiError && e.status === 410) {
      status.value = "unavailable";
    } else {
      // 409 is the poll having no places left, which the visitor can
      // understand; everything else is a failure to submit.
      errorMsg.value = e instanceof ApiError && e.status === 409 ? c.value.full : c.value.submitFail;
    }
  } finally {
    submitting.value = false;
  }
}

async function withdraw(): Promise<void> {
  if (!editToken) return;
  if (!window.confirm(d.value.withdrawConfirm)) return;
  submitting.value = true;
  try {
    await withdrawSubmission(editToken);
    status.value = "withdrawn";
  } catch {
    errorMsg.value = c.value.submitFail;
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <PublicShell v-model:locale="locale" :hide-ads="status === 'submitted' || status === 'withdrawn'">
    <PublicNotice v-if="status === 'loading'" :message="c.loading" />
    <PublicNotice v-else-if="status === 'unavailable'" :message="c.unavailable" />
    <PublicNotice v-else-if="status === 'load-failed'" :message="c.loadFailed" />
    <PublicNotice v-else-if="status === 'withdrawn'" :message="d.withdrawn" />

    <!-- On submit the whole page collapses to a single confirmation card
         (the top card is dropped) so nothing competes with saving the
         secret link. -->
    <template v-else-if="poll">
      <PublicConfirmation v-if="status === 'submitted'" :url="editUrl" :locale="locale" />

      <template v-else>
        <PublicTopCard
          :title="pollTitle"
          :image-url="poll.image_url"
          :artist="poll.image_artist_instagram"
          :credit-label="c.imageCredit"
          :description-html="pollDescription"
        >
          <template v-if="poll.location" #meta>
            <PublicMetaRow
              :href="mapLink({ location: poll.location, latitude: poll.latitude, longitude: poll.longitude })"
            >
              <template #icon>
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" /><circle cx="12" cy="10" r="3" /></svg>
              </template>
              {{ poll.location }}
            </PublicMetaRow>
          </template>
        </PublicTopCard>

        <RecoveredNotice v-if="editToken" :recovered-at="recoveredAt" :locale="locale" />
        <Disclosure :locale="locale" />

        <!-- Pseudonym + the optional note up top, mirroring the events
             sign-up form. The note auto-grows to its content. -->
        <div class="card name-card">
          <input v-model="displayName" class="input" type="text" :placeholder="c.displayName" maxlength="100" />
          <textarea
            ref="noteEl"
            v-model="note"
            class="input note"
            :placeholder="d.notePlaceholder"
            maxlength="280"
            rows="2"
            @input="growNote"
          />
        </div>

        <div class="card poll-calendar">
          <p class="legend">
            <span class="intro-text">{{ d.intro }}</span>
            <span class="swatch yes">{{ d.yes }}</span>
            <span class="swatch maybe">{{ d.maybe }}</span>
            <span class="swatch no">{{ d.no }}</span>
          </p>
          <div ref="calScroll" class="cal-scroll" @scroll="updateScrollHint">
            <MonthCalendar
              v-for="m in months"
              :key="`${m.year}-${m.month}`"
              :year="m.year"
              :month="m.month"
              :slots-by-iso="slotsByIso"
              :answers="answers"
              :locale="locale"
              :columns="calendarColumns"
              @toggle="toggle"
            />
          </div>
          <button
            v-show="canScrollRight"
            type="button"
            class="scroll-hint"
            :aria-label="d.scrollHint"
            :title="d.scrollHint"
            @click="nudgeRight"
          >
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 6l6 6-6 6" /></svg>
          </button>
        </div>

        <div class="card submit-card">
          <p v-if="errorMsg" class="error" role="alert">{{ errorMsg }}</p>
          <button
            v-if="!editToken"
            type="button"
            class="btn-primary full"
            :disabled="submitting"
            @click="submit"
          >
            {{ submitting ? c.submitting : c.submit }}
          </button>
          <PublicEditBar
            v-else
            :can-edit="poll?.answers_editable ?? true"
            :dirty="dirty"
            :saving="submitting"
            :just-saved="justSaved"
            :locale="locale"
            @save="submit"
            @revert="revert"
            @withdraw="withdraw"
          />
          <!-- This page's primary action is full width rather than a
               right-aligned row, so the ask sits under it on the left
               instead of beside it. -->
          <SupportButtons class="support-row" />
        </div>
      </template>
    </template>
  </PublicShell>
</template>

<style scoped>
.support-row {
  margin-top: 1rem;
}
.intro-text { color: var(--brand-text-muted); margin-right: auto; }
/* Text boxes use the shared ``.input`` (forms.css). */
.name-card { display: flex; flex-direction: column; gap: 0.625rem; }
/* Note grows with its content via JS; no manual drag handle. */
.note { resize: none; overflow: hidden; }
.legend { display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; margin: 0 0 0.75rem; font-size: 0.8125rem; }
.swatch { padding: 0.125rem 0.5rem; border-radius: 999px; color: #fff; }
.swatch.yes { background: var(--brand-green); }
.swatch.maybe { background: var(--brand-amber); }
.swatch.no { background: var(--brand-neutral); color: var(--brand-text); }
/* The card stays flush with its siblings; the calendars scroll inside their
 * own container when a full week is wider than the card, so the page never
 * scrolls sideways and the surface always frames the days. ``position:
 * relative`` anchors the scroll-cue arrow. */
.poll-calendar { position: relative; }
.cal-scroll { overflow-x: auto; }
/* Breathing room between stacked months. */
.cal-scroll :deep(.mg) + :deep(.mg) { margin-top: 1rem; }
/* Right-edge scroll cue, pinned to the calendar — shown only while there's
 * more calendar to the right (see canScrollRight). Tapping nudges onward. */
.scroll-hint {
  position: absolute;
  top: 50%;
  right: 0.5rem;
  transform: translateY(-50%);
  z-index: 20;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2.25rem;
  height: 2.25rem;
  padding: 0;
  border: none;
  border-radius: 999px;
  background: var(--brand-red);
  color: #fff;
  cursor: pointer;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.25);
  animation: scroll-hint-nudge 1.3s ease-in-out infinite;
}
@keyframes scroll-hint-nudge {
  0%, 100% { transform: translateY(-50%) translateX(0); }
  50% { transform: translateY(-50%) translateX(3px); }
}
@media (prefers-reduced-motion: reduce) {
  .scroll-hint { animation: none; }
}
.submit-card { display: flex; flex-direction: column; gap: 0.75rem; align-items: stretch; }
.error { color: var(--brand-red); margin: 0; }
/* .btn-primary (+ .full) comes from ``src/public_shared/forms.css``. */
</style>
