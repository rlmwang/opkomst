<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref } from "vue";
import Disclosure from "@/public_shared/Disclosure.vue";
import EditLink from "@/public_shared/EditLink.vue";
import PublicHero from "@/public_shared/PublicHero.vue";
import PublicNotice from "@/public_shared/PublicNotice.vue";
import PublicShell from "@/public_shared/PublicShell.vue";
import { type Locale, chromeStrings, pickLocale } from "@/public_shared/strings";
import {
  type Availability,
  type PublicDatepoll,
  ApiError,
  fetchDatepollBySlug,
  fetchSubmission,
  postSubmission,
  putSubmission,
} from "./api";
import { datepollStrings, formatTimeRange } from "./i18n";
import MonthCalendar from "./MonthCalendar.vue";

type Status = "loading" | "ready" | "unavailable" | "load-failed" | "submitted";

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

// ``?s={token}`` puts the page in edit mode: pre-fill from the existing
// submission and PUT instead of POST on save.
const editToken = new URL(window.location.href).searchParams.get("s");
const savedToken = ref<string | null>(null);
const editUrl = computed(() =>
  savedToken.value ? `${window.location.origin}/d/${slug()}?s=${savedToken.value}` : "",
);

// One answers map keyed by slot id — the single source of truth the
// inline calendar binds to (``null`` = unset).
const answers = reactive<Record<string, Availability | null>>({});

const slug = (): string => {
  const parts = window.location.pathname.split("/").filter(Boolean);
  return parts[parts.length - 1] ?? "";
};

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
  const picked = Object.entries(answers)
    .filter(([, a]) => a !== null)
    .map(([slotId, a]) => ({ datepoll_slot_id: slotId, availability: a as Availability }));
  if (picked.length === 0) {
    errorMsg.value = d.value.pickOne;
    return;
  }
  submitting.value = true;
  const body = { display_name: displayName.value.trim() || null, note: note.value.trim() || null, answers: picked };
  try {
    if (editToken) {
      await putSubmission(editToken, body);
      savedToken.value = editToken;
    } else {
      const ack = await postSubmission(slug(), body);
      savedToken.value = ack.edit_token;
    }
    status.value = "submitted";
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
</script>

<template>
  <PublicShell v-model:locale="locale">
    <PublicNotice v-if="status === 'loading'" :message="c.loading" />
    <PublicNotice v-else-if="status === 'unavailable'" :message="c.unavailable" />
    <PublicNotice v-else-if="status === 'load-failed'" :message="c.loadFailed" />

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
          <input v-model="displayName" class="textfield" type="text" :placeholder="c.displayName" maxlength="100" />
          <textarea
            ref="noteEl"
            v-model="note"
            class="textfield note"
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
          <button type="button" class="btn-primary" :disabled="submitting" @click="submit">
            {{ submitting ? c.submitting : c.submit }}
          </button>
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
.intro-text { color: var(--brand-text-muted); margin-right: auto; }
/* Text boxes match the public form's (--brand-surface, 1rem) so the
 * three public pages read identically. */
.textfield {
  width: 100%;
  box-sizing: border-box;
  padding: 0.625rem 0.75rem;
  border: 1px solid var(--brand-border);
  border-radius: 8px;
  background: var(--brand-surface);
  color: var(--brand-text);
  font-family: inherit;
  font-size: 1rem;
  line-height: 1.4;
}
.textfield:focus {
  outline: 2px solid var(--brand-red);
  outline-offset: 0;
  border-color: var(--brand-red);
}
.name-card { display: flex; flex-direction: column; gap: 0.625rem; }
/* Note grows with its content via JS; no manual drag handle. */
.note { resize: none; overflow: hidden; }
.legend { display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; margin: 0 0 0.75rem; font-size: 0.8125rem; }
.swatch { padding: 0.125rem 0.5rem; border-radius: 999px; color: #fff; }
.swatch.yes { background: #1f7a3c; }
.swatch.maybe { background: #c98a00; }
.swatch.no { background: #6b6b6b; }
/* Each month renders at full content width, stacked vertically — the
 * cells are wide enough to hold their time-slot pills inline. */
.card :deep(.month):last-child { margin-bottom: 0; }
.submit-card { display: flex; flex-direction: column; gap: 0.75rem; align-items: stretch; }
.error { color: var(--brand-red); margin: 0; }
.btn-primary {
  width: 100%;
  padding: 0.75rem;
  border: none;
  border-radius: 8px;
  background: var(--brand-red);
  color: #fff;
  font-size: 1rem;
  font-weight: 600;
  cursor: pointer;
}
.btn-primary:disabled { opacity: 0.6; cursor: default; }
</style>
