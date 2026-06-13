<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import Disclosure from "@/public_shared/Disclosure.vue";
import PublicNotice from "@/public_shared/PublicNotice.vue";
import PublicShell from "@/public_shared/PublicShell.vue";
import { type Locale, chromeStrings, pickLocale } from "@/public_shared/strings";
import {
  type Availability,
  type PublicDatepoll,
  ApiError,
  fetchDatepollBySlug,
  postSubmission,
} from "./api";
import { datepollStrings, formatLongDate } from "./i18n";
import DateRow from "./DateRow.vue";
import MonthCalendar from "./MonthCalendar.vue";

type Status = "loading" | "ready" | "unavailable" | "load-failed" | "submitted";

const status = ref<Status>("loading");
const poll = ref<PublicDatepoll | null>(null);
const locale = ref<Locale>("nl");
const c = computed(() => chromeStrings(locale.value));
const d = computed(() => datepollStrings(locale.value));

const displayName = ref("");
const submitting = ref(false);
const errorMsg = ref("");

// One answers map keyed by ISO date — the single source of truth both
// the calendar and the list bind to.
const answers = reactive<Record<string, { availability: Availability | null; comment: string }>>({});
const idByIso: Record<string, string> = {};

const slug = (): string => {
  const parts = window.location.pathname.split("/").filter(Boolean);
  return parts[parts.length - 1] ?? "";
};

function hydrate(p: PublicDatepoll): void {
  poll.value = p;
  locale.value = pickLocale(p.locale);
  for (const dt of p.dates) {
    answers[dt.on_date] = { availability: null, comment: "" };
    idByIso[dt.on_date] = dt.id;
  }
  status.value = "ready";
}

onMounted(async () => {
  const inlined = window.__OPKOMST_DATEPOLL__;
  if (inlined !== undefined) {
    if (inlined === null) {
      status.value = "unavailable";
      return;
    }
    hydrate(inlined);
    return;
  }
  try {
    hydrate(await fetchDatepollBySlug(slug()));
  } catch (e) {
    status.value = e instanceof ApiError && e.status === 410 ? "unavailable" : "load-failed";
  }
});

const sortedIsos = computed(() => poll.value?.dates.map((dt) => dt.on_date).slice().sort() ?? []);

const months = computed(() => {
  const seen = new Set<string>();
  const out: { year: number; month: number }[] = [];
  for (const iso of sortedIsos.value) {
    const [y, m] = iso.split("-").map(Number);
    const key = `${y}-${m}`;
    if (!seen.has(key)) {
      seen.add(key);
      out.push({ year: y, month: m - 1 });
    }
  }
  return out;
});

const cells = computed<Record<string, Availability | null>>(() =>
  Object.fromEntries(sortedIsos.value.map((iso) => [iso, answers[iso].availability])),
);

const CYCLE: (Availability | null)[] = [null, "yes", "maybe", "no"];
function toggle(iso: string): void {
  const cur = answers[iso].availability;
  answers[iso].availability = CYCLE[(CYCLE.indexOf(cur) + 1) % CYCLE.length];
}

async function submit(): Promise<void> {
  errorMsg.value = "";
  const picked = sortedIsos.value
    .filter((iso) => answers[iso].availability !== null)
    .map((iso) => ({
      datepoll_date_id: idByIso[iso],
      availability: answers[iso].availability as Availability,
      comment: answers[iso].comment.trim() || null,
    }));
  if (picked.length === 0) {
    errorMsg.value = d.value.pickOne;
    return;
  }
  submitting.value = true;
  try {
    await postSubmission(slug(), {
      display_name: displayName.value.trim() || null,
      answers: picked,
    });
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
    <PublicNotice v-else-if="status === 'submitted'" :title="c.thanks" :message="d.thanksBody" />

    <template v-else-if="poll">
      <div class="card title-card">
        <h1>{{ poll.name }}</h1>
        <p v-if="poll.description" class="muted">{{ poll.description }}</p>
      </div>

      <Disclosure :locale="locale" />

      <!-- Pseudonym first, mirroring the events sign-up form. -->
      <div class="card">
        <input v-model="displayName" class="textfield" type="text" :placeholder="c.displayName" maxlength="100" />
      </div>

      <div class="card">
        <p class="intro muted">{{ d.intro }}</p>
        <p class="legend">
          <span class="legend-label">{{ d.legend }}</span>
          <span class="swatch yes">{{ d.yes }}</span>
          <span class="swatch maybe">{{ d.maybe }}</span>
          <span class="swatch no">{{ d.no }}</span>
        </p>
        <div class="months">
          <MonthCalendar
            v-for="m in months"
            :key="`${m.year}-${m.month}`"
            :year="m.year"
            :month="m.month"
            :cells="cells"
            :locale="locale"
            @toggle="toggle"
          />
        </div>
      </div>

      <div class="card">
        <DateRow
          v-for="iso in sortedIsos"
          :key="iso"
          :label="formatLongDate(iso, locale)"
          :state="answers[iso].availability"
          :comment="answers[iso].comment"
          :t="d"
          @update:state="(v) => (answers[iso].availability = v)"
          @update:comment="(v) => (answers[iso].comment = v)"
        />
      </div>

      <div class="card submit-card">
        <p v-if="errorMsg" class="error" role="alert">{{ errorMsg }}</p>
        <button type="button" class="btn-primary" :disabled="submitting" @click="submit">
          {{ submitting ? c.submitting : c.submit }}
        </button>
      </div>
    </template>
  </PublicShell>
</template>

<style scoped>
.muted { color: var(--brand-text-muted); }
.title-card h1 { margin: 0; overflow-wrap: anywhere; }
.title-card .muted { margin: 0.5rem 0 0; }
.intro { margin: 0 0 0.75rem; }
.textfield {
  width: 100%;
  box-sizing: border-box;
  padding: 0.625rem 0.75rem;
  border: 1px solid var(--brand-border);
  border-radius: 8px;
  background: var(--brand-bg);
  color: var(--brand-text);
  font: inherit;
}
.legend { display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; margin: 0 0 1rem; font-size: 0.8125rem; }
.legend-label { color: var(--brand-text-muted); }
.swatch { padding: 0.125rem 0.5rem; border-radius: 999px; color: #fff; }
.swatch.yes { background: #1f7a3c; }
.swatch.maybe { background: #c98a00; }
.swatch.no { background: #6b6b6b; }
/* Two months side by side; cells stay square (aspect-ratio in
 * MonthCalendar), wrapping to the next row beyond two and collapsing
 * to one column on narrow screens. */
.months {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 1rem 1.25rem;
}
.months :deep(.month) { margin-bottom: 0; }
@media (max-width: 480px) {
  .months { grid-template-columns: 1fr; }
}
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
