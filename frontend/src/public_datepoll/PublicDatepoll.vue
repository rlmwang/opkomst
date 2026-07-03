<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref } from "vue";
import Disclosure from "@/public_shared/Disclosure.vue";
import EditLink from "@/public_shared/EditLink.vue";
import PublicEditBar from "@/public_shared/PublicEditBar.vue";
import PublicHero from "@/public_shared/PublicHero.vue";
import PublicNotice from "@/public_shared/PublicNotice.vue";
import PublicShell from "@/public_shared/PublicShell.vue";
import { showToast } from "@/public_shared/publicToast";
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

async function prefillFromSubmission(): Promise<void> {
  const sub = await fetchSubmission(editToken!);
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
  if (!displayName.value.trim()) {
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
      errorMsg.value = c.value.submitFail;
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
  <PublicShell v-model:locale="locale">
    <PublicNotice v-if="status === 'loading'" :message="c.loading" />
    <PublicNotice v-else-if="status === 'unavailable'" :message="c.unavailable" />
    <PublicNotice v-else-if="status === 'load-failed'" :message="c.loadFailed" />
    <PublicNotice v-else-if="status === 'withdrawn'" :message="d.withdrawn" />

    <!-- ``ready`` and ``submitted`` both keep the title/info card; on
         submit the body is replaced by a thanks card below it, same
         shape as the events confirmation. -->
    <template v-else-if="poll">
      <div class="card title-card">
        <PublicHero
          :image-url="poll.image_url"
          :artist="poll.image_artist_instagram"
          :credit-label="c.imageCredit"
        />
        <h1>{{ poll.name }}</h1>
        <p v-if="poll.description" class="muted">{{ poll.description }}</p>
        <a
          v-if="poll.location"
          class="location"
          :href="mapLink({ location: poll.location, latitude: poll.latitude, longitude: poll.longitude })"
          target="_blank"
          rel="noopener"
        >
          <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" /><circle cx="12" cy="10" r="3" /></svg>
          {{ poll.location }}
        </a>
      </div>

      <template v-if="status === 'submitted'">
        <div class="card stack thanks-card">
          <h2>{{ c.thanks }}</h2>
          <p class="muted">{{ d.thanksBody }}</p>
        </div>
        <EditLink v-if="editUrl" :url="editUrl" :locale="locale" />
      </template>

      <template v-else>
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

        <div class="card">
          <p class="legend">
            <span class="intro-text">{{ d.intro }}</span>
            <span class="swatch yes">{{ d.yes }}</span>
            <span class="swatch maybe">{{ d.maybe }}</span>
            <span class="swatch no">{{ d.no }}</span>
          </p>
          <MonthCalendar
            v-for="m in months"
            :key="`${m.year}-${m.month}`"
            :year="m.year"
            :month="m.month"
            :slots-by-iso="slotsByIso"
            :answers="answers"
            :locale="locale"
            @toggle="toggle"
          />
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
            :dirty="dirty"
            :saving="submitting"
            :just-saved="justSaved"
            :locale="locale"
            @save="submit"
            @revert="revert"
            @withdraw="withdraw"
          />
        </div>
      </template>
    </template>
  </PublicShell>
</template>

<style scoped>
.muted { color: var(--brand-text-muted); }
.title-card h1 { margin: 0; overflow-wrap: anywhere; }
.thanks-card h2 { margin: 0; }
.title-card .muted { margin: 0.5rem 0 0; }
.location {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  margin: 0.5rem 0 0;
  color: var(--brand-red);
  text-decoration: none;
  font-size: 0.9375rem;
}
.location:hover { text-decoration: underline; }
.location svg { flex: none; }
.intro-text { color: var(--brand-text-muted); margin-right: auto; }
/* Text boxes use the shared ``.input`` (forms.css). */
.name-card { display: flex; flex-direction: column; gap: 0.625rem; }
/* Note grows with its content via JS; no manual drag handle. */
.note { resize: none; overflow: hidden; }
.legend { display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; margin: 0 0 0.75rem; font-size: 0.8125rem; }
.swatch { padding: 0.125rem 0.5rem; border-radius: 999px; color: #fff; }
.swatch.yes { background: var(--brand-green); }
.swatch.maybe { background: var(--brand-amber); }
.swatch.no { background: #6b6b6b; }
/* Each month renders at full content width, stacked vertically — the
 * cells are wide enough to hold their time-slot pills inline. */
.card :deep(.month):last-child { margin-bottom: 0; }
.submit-card { display: flex; flex-direction: column; gap: 0.75rem; align-items: stretch; }
.error { color: var(--brand-red); margin: 0; }
/* .btn-primary (+ .full) comes from ``src/public_shared/forms.css``. */
</style>
