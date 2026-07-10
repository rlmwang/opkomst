<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { formatDate, formatTimeRange } from "@/lib/format";
import { mapLink } from "@/lib/map-link";
import { isValidEmail } from "@/lib/validate";
import PublicConfirmation from "@/public_shared/PublicConfirmation.vue";
import PublicEditBar from "@/public_shared/PublicEditBar.vue";
import RecoveredNotice from "@/public_shared/RecoveredNotice.vue";
import PublicMetaRow from "@/public_shared/PublicMetaRow.vue";
import PublicNotice from "@/public_shared/PublicNotice.vue";
import PublicShell from "@/public_shared/PublicShell.vue";
import PublicTopCard from "@/public_shared/PublicTopCard.vue";
import MonthGrid from "@/components/MonthGrid.vue";
import { chromeStrings } from "@/public_shared/strings";
import { stripHtml } from "@/public_shared/stripHtml";
import { showToast } from "@/public_shared/publicToast";
import { useEditForm } from "@/public_shared/useEditForm";
import { useEditLink } from "@/public_shared/useEditLink";
import BrandedSelect from "./BrandedSelect.vue";
import {
  ApiError,
  type Booking,
  type PublicEvent,
  fetchBooking,
  fetchEventBySlug,
  postSignup,
  putBooking,
  putBookingOccurrences,
  withdrawBooking,
} from "./api";
import { type Locale, pickLocale, strings } from "./i18n";

const slug = window.location.pathname.replace(/^\/e\/+/, "").split(/[/?#]/)[0];
// ``?s={token}`` puts the page in booking-edit mode: fetch the whole
// booking by token, edit name + party size, and manage per-occurrence
// withdrawals. ``confirmSaved`` records the token AND routes the URL onto
// it so a refresh reopens the edit page.
const { editToken, editUrl, confirmSaved } = useEditLink("e", () => slug);
const editing = editToken !== null;

// Server-side-injected event payload (per-occurrence). Synchronous, no
// round-trip on first paint. ``null`` = unknown slug (render not-found);
// ``undefined`` = dev mode without the SPA handler → fall back to fetch.
const initial = window.__OPKOMST_EVENT__;
const event = ref<PublicEvent | null>(initial ?? null);
const notFound = ref(initial === null);
const loadFailed = ref(false);

if (initial === undefined) {
  fetchEventBySlug(slug)
    .then((e) => {
      event.value = e;
    })
    .catch((err) => {
      if (err instanceof ApiError && err.status === 404) {
        notFound.value = true;
      } else {
        loadFailed.value = true;
      }
    });
}

const locale = ref<Locale>(pickLocale(event.value?.locale));
watch(event, (e) => {
  if (e) locale.value = pickLocale(e.locale);
  // Dev-mode async load: pre-check the landing occurrence when the form
  // had no stored draft (production injects the event synchronously, so
  // the initial draft already carries current.id).
  if (e && !editing && !hadStoredDraft && selectedIds.value.length === 0 && !allUpcoming.value) {
    selectedIds.value = [e.current.id];
  }
});
const t = computed(() => strings(locale.value));
const c = computed(() => chromeStrings(locale.value));

// A one-off event skips the calendar picker and behaves like a plain
// single sign-up.
const isOneOff = computed(() => !event.value?.is_recurring);

// --- form state (create mode) — survives a refresh on flaky mobile ---
const draftKey = `signup-draft:${slug}`;
type Draft = {
  displayName: string;
  partySize: number;
  sourceChoice: string | null;
  helpChoices: string[];
  email: string;
  occurrenceIds: string[];
  allUpcoming: boolean;
};
function emptyDraft(): Draft {
  return {
    displayName: "",
    partySize: 1,
    sourceChoice: null,
    helpChoices: [],
    email: "",
    occurrenceIds: event.value ? [event.value.current.id] : [],
    allUpcoming: false,
  };
}
let hadStoredDraft = false;
const initialDraft: Draft = (() => {
  try {
    const raw = sessionStorage.getItem(draftKey);
    if (raw) {
      hadStoredDraft = true;
      return { ...emptyDraft(), ...JSON.parse(raw) };
    }
  } catch { /* ignore */ }
  return emptyDraft();
})();
const displayName = ref(initialDraft.displayName);
const partySize = ref(initialDraft.partySize);
const sourceChoice = ref<string | null>(initialDraft.sourceChoice);
const helpChoices = ref<string[]>(initialDraft.helpChoices);
const email = ref(initialDraft.email);
// Checked occurrence ids + the "all upcoming" shortcut.
const selectedIds = ref<string[]>(initialDraft.occurrenceIds);
const allUpcoming = ref(initialDraft.allUpcoming);

watch(
  [displayName, partySize, sourceChoice, helpChoices, email, selectedIds, allUpcoming],
  () => {
    try {
      sessionStorage.setItem(
        draftKey,
        JSON.stringify({
          displayName: displayName.value,
          partySize: partySize.value,
          sourceChoice: sourceChoice.value,
          helpChoices: helpChoices.value,
          email: email.value,
          occurrenceIds: selectedIds.value,
          allUpcoming: allUpcoming.value,
        } satisfies Draft),
      );
    } catch { /* ignore quota / private-mode */ }
  },
  { deep: true },
);
function clearDraft() {
  try { sessionStorage.removeItem(draftKey); } catch { /* ignore */ }
}

const submitting = ref(false);
const submitted = ref(false);
const withdrawn = ref(false);
const errorMsg = ref<string | null>(null);

// --- booking edit mode ---------------------------------------------
const booking = ref<Booking | null>(null);
const recoveredAt = ref<string | null>(null);

// Dirty/revert/saved state for the shared edit bar (edit mode only).
const { dirty, justSaved, captureBaseline, revert, flashSaved } = useEditForm({
  // Dirty tracks name, party size, AND the future session selection, so the
  // edit bar's Save/Revert cover calendar changes too.
  snapshot: () => ({
    name: displayName.value,
    party: partySize.value,
    sessions: [...selectedIds.value].sort().join(","),
  }),
  apply: (s) => {
    displayName.value = s.name;
    partySize.value = s.party;
    selectedIds.value = s.sessions ? s.sessions.split(",") : [];
  },
});

// The booking's future sessions (pre-selection) vs its past sessions (frozen
// history, shown locked on the calendar).
function bookedFutureIds(b: Booking): string[] {
  return b.occurrences.filter((o) => !o.is_past).map((o) => o.occurrence_id);
}
const pastBookedIsos = computed(
  () => new Set((booking.value?.occurrences ?? []).filter((o) => o.is_past).map((o) => o.starts_at.slice(0, 10))),
);

if (editing) {
  fetchBooking(editToken!)
    .then((b) => {
      booking.value = b;
      recoveredAt.value = b.link_recovered_at ?? null;
      displayName.value = b.display_name ?? "";
      partySize.value = b.party_size;
      locale.value = pickLocale(b.locale);
      selectedIds.value = bookedFutureIds(b);
      allUpcoming.value = false;
      captureBaseline();
    })
    .catch((err) => {
      if (err instanceof ApiError && (err.status === 404 || err.status === 410)) {
        notFound.value = true;
      } else {
        loadFailed.value = true;
      }
    });
}

// The landing occurrence and its date/time.
const current = computed(() => event.value?.current ?? null);

// Session badge for one occurrence ("sessie i van N", or "sessie i" for
// an open-ended series).
function sessionBadge(index: number): string {
  const count = event.value?.total_sessions ?? null;
  return count === null ? t.value.sessionOpen(index + 1) : t.value.sessionOf(index + 1, count);
}

function toggleOccurrence(id: string, on: boolean) {
  if (on) {
    if (!selectedIds.value.includes(id)) selectedIds.value = [...selectedIds.value, id];
  } else {
    selectedIds.value = selectedIds.value.filter((x) => x !== id);
  }
}

// --- calendar date picker (recurring events) -----------------------
const isoDate = (dt: string) => dt.slice(0, 10);
const upcomingByIso = computed(() => {
  const m = new Map<string, PublicEvent["upcoming"][number]>();
  for (const o of event.value?.upcoming ?? []) m.set(isoDate(o.starts_at), o);
  return m;
});
const projectedIsos = computed(() => new Set((event.value?.projected ?? []).map((p) => isoDate(p.starts_at))));
// ``selectedIds`` is the single source of truth in both modes; the calendar
// just reflects it. The "select all" toggle is opt-in vs opt-out: flipping
// it seeds the selection (all / just the landing date), then the visitor
// adds or deselects individual days on top of that.
const upcomingIds = computed(() => (event.value?.upcoming ?? []).map((o) => o.id));
const selectedIsos = computed(() => {
  const s = new Set<string>();
  for (const o of event.value?.upcoming ?? []) {
    if (selectedIds.value.includes(o.id)) s.add(isoDate(o.starts_at));
  }
  return s;
});
watch(allUpcoming, (on) => {
  if (on) {
    selectedIds.value = [...upcomingIds.value];
  } else {
    // Off: sign-up falls back to the landing date; manage deselects every
    // future session (past ones are frozen and unaffected).
    selectedIds.value = editing ? [] : current.value ? [current.value.id] : [];
  }
});

// Monday-first short weekday labels, locale-aware — no extra i18n keys.
const weekdayLabels = computed(() => {
  const fmt = new Intl.DateTimeFormat(locale.value === "en" ? "en-GB" : "nl-NL", { weekday: "short" });
  return [...Array(7)].map((_, i) => fmt.format(new Date(2024, 0, 1 + i))); // 2024-01-01 is a Monday
});

const pickerMonth = ref<string | null>(null);
const shownMonth = computed({
  get: () => pickerMonth.value ?? isoDate(current.value?.starts_at ?? new Date().toISOString()).slice(0, 7),
  set: (v: string) => { pickerMonth.value = v; },
});

function dayClass(iso: string): Record<string, boolean> {
  return {
    "has-occurrence": upcomingByIso.value.has(iso),
    selected: selectedIsos.value.has(iso),
    projected: projectedIsos.value.has(iso),
    // Past sessions this booking attended: shown locked (manage mode only).
    attended: pastBookedIsos.value.has(iso),
  };
}
// Every available date is toggleable in both modes (opt-in adds, opt-out
// deselects) — never locked.
const dayClickable = (iso: string) => upcomingByIso.value.has(iso);
function onDayClick(iso: string) {
  const occ = upcomingByIso.value.get(iso);
  if (occ) toggleOccurrence(occ.id, !selectedIds.value.includes(occ.id));
}

// The reminder shown behind the select-all toggle depends on the mode.
const reminder = computed(() => (allUpcoming.value ? t.value.reminderOptOut : t.value.reminderOptIn));

// --- email transparency --------------------------------------------
interface EmailUseBullet {
  text: string;
  previewUrl: string;
}
const emailUseBullets = computed<EmailUseBullet[]>(() => {
  if (!event.value) return [];
  return [
    { text: t.value.emailUses.reminder, previewUrl: `/api/v1/events/by-slug/${slug}/email-preview/reminder` },
    { text: t.value.emailUses.feedback, previewUrl: `/api/v1/events/by-slug/${slug}/email-preview/feedback` },
  ];
});

// --- add-to-calendar dropdown (native ``<details>`` for the popup) ---
const calLinks = computed(() => {
  const e = event.value;
  if (!e) return null;
  const enc = encodeURIComponent;
  const utc = (iso: string) =>
    new Date(iso).toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");
  const publicUrl = `${window.location.origin}/e/${e.current.slug}`;
  const desc = [stripHtml(e.topic), publicUrl].filter(Boolean).join("\n\n");
  const ics = `/api/v1/events/by-slug/${e.current.slug}/event.ics`;
  const google =
    `https://calendar.google.com/calendar/render?action=TEMPLATE` +
    `&text=${enc(e.name)}` +
    `&dates=${utc(e.current.starts_at)}/${utc(e.current.ends_at)}` +
    `&details=${enc(desc)}` +
    `&location=${enc(e.location)}`;
  return { google, ics };
});

// --- party-size input guards (create mode) -------------------------
function onPartyBeforeInput(ev: InputEvent) {
  if (ev.data == null) return;
  if (!/^\d+$/.test(ev.data)) ev.preventDefault();
}
function onPartyInput(ev: Event) {
  const raw = (ev.target as HTMLInputElement).value;
  if (raw === "") return;
  const n = parseInt(raw, 10);
  if (Number.isFinite(n)) partySize.value = Math.min(50, Math.max(1, n));
}
function normalisePartySize(ev: FocusEvent) {
  let n = partySize.value;
  if (typeof n !== "number" || !Number.isFinite(n) || n < 1) n = 1;
  else n = Math.min(50, Math.max(1, Math.floor(n)));
  partySize.value = n;
  (ev.target as HTMLInputElement).value = String(n);
}

function onFormKeydown(ev: KeyboardEvent) {
  if (ev.key !== "Enter") return;
  const target = ev.target as HTMLElement | null;
  if (target && target.tagName === "BUTTON") return;
  if (target && target.tagName === "TEXTAREA") return;
  ev.preventDefault();
}

async function submit() {
  errorMsg.value = null;
  if (!event.value) return;
  const trimmedName = displayName.value.trim();
  if (!trimmedName) {
    showToast(c.value.nameRequired);
    return;
  }
  const trimmedEmail = email.value.trim();
  if (trimmedEmail && !isValidEmail(trimmedEmail)) {
    showToast(c.value.invalidEmail);
    return;
  }
  // One-off: the single current occurrence is implied.
  const ids = isOneOff.value ? [event.value.current.id] : selectedIds.value;
  // Opt-out with nothing deselected → let the server resolve "every future
  // occurrence" (robust to a stale page). Any deselection, or opt-in, sends
  // the explicit picks.
  const fullOptOut =
    allUpcoming.value && upcomingIds.value.length > 0 && upcomingIds.value.every((id) => ids.includes(id));
  if (!isOneOff.value && !fullOptOut && ids.length === 0) {
    showToast(t.value.pickSession);
    return;
  }
  submitting.value = true;
  try {
    const ack = await postSignup(event.value.current.slug, {
      display_name: trimmedName || null,
      party_size: partySize.value,
      source_choice: sourceChoice.value,
      help_choices: helpChoices.value,
      email: trimmedEmail || null,
      occurrence_ids: fullOptOut ? [] : ids,
      all_upcoming: fullOptOut,
    });
    confirmSaved(ack.edit_token);
    submitted.value = true;
    clearDraft();
  } catch {
    errorMsg.value = t.value.submitFail;
  } finally {
    submitting.value = false;
  }
}

async function saveBooking() {
  errorMsg.value = null;
  const trimmedName = displayName.value.trim();
  if (!trimmedName) {
    showToast(c.value.nameRequired);
    return;
  }
  submitting.value = true;
  try {
    let b = await putBooking(editToken!, {
      display_name: trimmedName || null,
      party_size: partySize.value,
    });
    // Recurring event: also persist the future session selection from the
    // calendar (one-off has no editable session set).
    if (!isOneOff.value) {
      const fullOptOut =
        allUpcoming.value && upcomingIds.value.length > 0 && upcomingIds.value.every((id) => selectedIds.value.includes(id));
      b = await putBookingOccurrences(editToken!, {
        occurrence_ids: fullOptOut ? [] : selectedIds.value,
        all_upcoming: fullOptOut,
      });
      selectedIds.value = bookedFutureIds(b);
      allUpcoming.value = false;
    }
    booking.value = b;
    captureBaseline();
    flashSaved();
  } catch {
    errorMsg.value = t.value.submitFail;
  } finally {
    submitting.value = false;
  }
}

async function withdrawAll() {
  if (!editing) return;
  if (!window.confirm(t.value.withdrawConfirm)) return;
  submitting.value = true;
  try {
    await withdrawBooking(editToken!);
    withdrawn.value = true;
  } catch {
    errorMsg.value = t.value.submitFail;
  } finally {
    submitting.value = false;
  }
}

onMounted(() => {
  document.title = event.value?.name ? `${event.value.name} · opkomst.nu` : "opkomst.nu";
});
watch(event, (e) => {
  if (e?.name) document.title = `${e.name} · opkomst.nu`;
});
</script>

<template>
  <PublicShell v-model:locale="locale">
    <PublicNotice v-if="loadFailed" :message="c.loadFailed" />

    <PublicNotice v-else-if="notFound" :message="c.unavailable" />

    <PublicNotice v-else-if="withdrawn" :message="t.withdrawn" />

    <PublicNotice v-else-if="event?.archived" :title="event.name" :message="c.unavailable" />

    <template v-else>
      <PublicTopCard
        v-if="!submitted"
        :title="event?.name ?? null"
        :image-url="event?.image_url ?? null"
        :artist="event?.image_artist_instagram ?? null"
        :credit-label="t.imageCredit"
        :description-html="event?.topic ?? null"
      >
        <template v-if="event && current" #meta>
          <PublicMetaRow>
            <template #icon>
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
            </template>
            {{ formatDate(current.starts_at, locale) }}
            <span v-if="!isOneOff" class="session-tag">{{ sessionBadge(current.index) }}</span>
          </PublicMetaRow>
          <PublicMetaRow>
            <template #icon>
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
            </template>
            {{ formatTimeRange(current.starts_at, current.ends_at, locale) }}
          </PublicMetaRow>
          <PublicMetaRow
            :href="mapLink({ location: event.location, latitude: event.latitude, longitude: event.longitude })"
          >
            <template #icon>
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
            </template>
            {{ event.location }}
          </PublicMetaRow>
        </template>

        <template v-if="event && calLinks" #actions>
          <div class="event-actions">
            <details class="cal">
              <summary class="cal-button">
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/><line x1="12" y1="14" x2="12" y2="20"/><line x1="9" y1="17" x2="15" y2="17"/></svg>
                {{ t.addToCalendar }}
              </summary>
              <ul class="cal-menu" role="menu">
                <li role="none"><a :href="calLinks.google" target="_blank" rel="noopener" role="menuitem">Google</a></li>
                <li role="none"><a :href="calLinks.ics" role="menuitem">{{ t.calIcs }}</a></li>
              </ul>
            </details>
          </div>
        </template>
      </PublicTopCard>

      <!-- Privacy + open-source disclosure (create mode). -->
      <div v-if="event && !editing && !submitted" class="card privacy-card">
        <details>
          <summary>{{ t.explainerTitle }}</summary>
          <p class="privacy-body">
            {{ t.explainerIntro }} {{ t.explainerEmailIntro }}
          </p>
          <ul class="privacy-bullets">
            <li v-for="b in emailUseBullets" :key="b.previewUrl">
              <a :href="b.previewUrl" target="_blank" rel="noopener" class="meta-link">
                {{ b.text }}
                <svg class="external" viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
              </a>
            </li>
          </ul>
          <p class="privacy-body">
            {{ t.explainerEmailOutro }} {{ t.explainerSource }}
            <a href="https://github.com/rlmwang/opkomst" target="_blank" rel="noopener">{{ t.explainerLink }}</a>.
          </p>
        </details>
      </div>

      <!-- Thanks screen (create-mode submit): a single confirmation card,
           nothing else, so saving the secret link stands alone. -->
      <PublicConfirmation v-if="submitted" :url="editUrl" :locale="locale" />

      <!-- ================= CREATE MODE ================= -->
      <form
        v-if="event && !editing && !submitted"
        class="card stack signup-form"
        novalidate
        @submit.prevent="submit"
        @keydown="onFormKeydown"
      >
        <h2>{{ t.essentialsTitle }}</h2>

        <section class="form-section">
          <input
            v-model="displayName"
            type="text"
            class="input"
            :placeholder="t.displayName"
            autocomplete="name"
          />
          <div class="number-field">
            <button type="button" class="num-step" aria-label="−" :disabled="partySize <= 1" @click="partySize = Math.max(1, (partySize || 1) - 1)">−</button>
            <input
              :value="partySize"
              type="number"
              class="input num-input"
              min="1"
              max="50"
              step="1"
              inputmode="numeric"
              :placeholder="t.partySize"
              @beforeinput="onPartyBeforeInput($event as InputEvent)"
              @input="onPartyInput($event)"
              @blur="normalisePartySize($event as FocusEvent)"
            />
            <button type="button" class="num-step" aria-label="+" :disabled="partySize >= 50" @click="partySize = Math.min(50, (partySize || 0) + 1)">+</button>
          </div>
        </section>

        <!-- Multi-occurrence calendar picker (hidden for a one-off). Pick
             the sessions you want, or flip the toggle to take every
             upcoming one at once. -->
        <section v-if="!isOneOff" class="form-section session-section">
          <span class="session-heading">{{ t.sessionsTitle }}</span>
          <p class="muted picker-explainer">{{ t.pickerExplainer }}</p>
          <label class="all-upcoming-row">
            <input v-model="allUpcoming" type="checkbox" role="switch" class="switch" />
            <span class="all-upcoming-label">{{ t.allUpcoming }}</span>
          </label>
          <p class="muted picker-reminder">{{ reminder }}</p>
          <MonthGrid
            v-model:month="shownMonth"
            :locale="locale"
            :weekdays="weekdayLabels"
            :day-class="dayClass"
            :clickable="dayClickable"
            :prev-label="t.prevMonth"
            :next-label="t.nextMonth"
            @day-click="onDayClick"
          />
        </section>

        <section v-if="event.help_options.length > 0" class="form-section help-section">
          <div class="help-choices" role="group" :aria-label="t.helpHeading">
            <span class="help-label">{{ t.helpHeading }}</span>
            <label v-for="opt in event.help_options" :key="opt" class="help-row">
              <input v-model="helpChoices" type="checkbox" :value="opt" />
              <span>{{ opt }}</span>
            </label>
          </div>
        </section>

        <hr class="section-divider" />

        <h2>{{ t.feedbackTitle }}</h2>

        <section class="form-section">
          <BrandedSelect
            v-model="sourceChoice"
            :options="event.source_options"
            :placeholder="t.sourcePlaceholder"
            :aria-label="t.sourcePlaceholder"
          />
          <input
            v-model="email"
            type="email"
            class="input"
            :placeholder="t.emailPlaceholder"
            autocomplete="email"
          />
        </section>

        <p v-if="errorMsg" class="error" role="alert">{{ errorMsg }}</p>

        <div class="submit-row">
          <button type="submit" class="btn-primary" :disabled="submitting" :aria-busy="submitting">
            <span class="btn-label" :class="{ hidden: submitting }">{{ t.submit }}</span>
            <span v-if="submitting" class="btn-spinner" aria-hidden="true">
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
                <circle cx="12" cy="12" r="9" stroke-opacity="0.25"/>
                <path d="M21 12a9 9 0 0 0-9-9"/>
              </svg>
            </span>
          </button>
        </div>
      </form>

      <!-- ================= EDIT MODE (booking) ================= -->
      <template v-if="editing && !submitted">
        <RecoveredNotice :recovered-at="recoveredAt" :locale="locale" />

        <form
          v-if="booking"
          class="card stack signup-form"
          novalidate
          @submit.prevent="saveBooking"
          @keydown="onFormKeydown"
        >
          <h2>{{ t.essentialsTitle }}</h2>
          <section class="form-section">
            <input v-model="displayName" type="text" class="input" :placeholder="t.displayName" autocomplete="name" />
            <div class="number-field">
              <button type="button" class="num-step" aria-label="−" :disabled="partySize <= 1" @click="partySize = Math.max(1, (partySize || 1) - 1)">−</button>
              <input
                :value="partySize"
                type="number"
                class="input num-input"
                min="1"
                max="50"
                step="1"
                inputmode="numeric"
                :placeholder="t.partySize"
                @beforeinput="onPartyBeforeInput($event as InputEvent)"
                @input="onPartyInput($event)"
                @blur="normalisePartySize($event as FocusEvent)"
              />
              <button type="button" class="num-step" aria-label="+" :disabled="partySize >= 50" @click="partySize = Math.min(50, (partySize || 0) + 1)">+</button>
            </div>
          </section>

          <!-- Manage sessions: the same calendar + toggle as sign-up,
               pre-filled with the booking. Past sessions show locked
               (attended); future ones are added/deselected freely. -->
          <section v-if="event && !isOneOff" class="form-section session-section">
            <span class="session-heading">{{ t.bookingSessions }}</span>
            <p class="muted picker-explainer">{{ t.pickerExplainer }}</p>
            <label class="all-upcoming-row">
              <input v-model="allUpcoming" type="checkbox" role="switch" class="switch" />
              <span class="all-upcoming-label">{{ t.allUpcoming }}</span>
            </label>
            <p class="muted picker-reminder">{{ reminder }}</p>
            <MonthGrid
              v-model:month="shownMonth"
              :locale="locale"
              :weekdays="weekdayLabels"
              :day-class="dayClass"
              :clickable="dayClickable"
              :prev-label="t.prevMonth"
              :next-label="t.nextMonth"
              @day-click="onDayClick"
            />
          </section>

          <p v-if="errorMsg" class="error" role="alert">{{ errorMsg }}</p>
        </form>

        <PublicEditBar
          v-if="booking"
          :dirty="dirty"
          :saving="submitting"
          :just-saved="justSaved"
          :locale="locale"
          @save="saveBooking"
          @revert="revert"
          @withdraw="withdrawAll"
        />
      </template>
    </template>
  </PublicShell>
</template>

<style scoped>
.form-section {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.form-section + .form-section {
  margin-top: 2rem;
}
.help-section {
  margin-top: 1.25rem !important;
}
.section-divider {
  border: 0;
  border-top: 1px solid var(--brand-border);
  margin: 1.5rem 0;
}
.signup-form > .section-divider + h2 {
  margin-top: 0;
}
.signup-form > h2 {
  margin-bottom: 1.5rem;
}

/* Session badge next to a date. */
.session-tag {
  font-size: 0.75rem;
  padding: 0.05rem 0.4rem;
  margin-left: 0.375rem;
  border-radius: 0.75rem;
  background: var(--brand-bg);
  color: var(--brand-text-muted);
  white-space: nowrap;
}

/* --- Occurrence picker --- */
.session-heading {
  font-size: 0.95rem;
  font-weight: 600;
}
/* Explainer under the header (above the toggle). */
.picker-explainer {
  font-size: 0.85rem;
  margin: 0 0 0.5rem;
}
/* Select-all toggle: a real switch (not a checkbox), label unbolded. */
.all-upcoming-row {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  cursor: pointer;
  font-size: 0.95rem;
  margin-bottom: 0.25rem;
}
.all-upcoming-label { font-weight: 400; }
/* Reminder tucked directly under the toggle it belongs to. */
.picker-reminder {
  font-size: 0.8rem;
  margin: 0 0 0.5rem;
  padding-left: calc(40px + 0.625rem); /* line up under the switch label */
}
.switch {
  appearance: none;
  -webkit-appearance: none;
  flex-shrink: 0;
  width: 40px;
  height: 22px;
  border-radius: 999px;
  background: var(--brand-border);
  position: relative;
  cursor: pointer;
  transition: background 120ms ease;
}
.switch::after {
  content: "";
  position: absolute;
  top: 2px;
  left: 2px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #fff;
  transition: transform 120ms ease;
}
.switch:checked { background: var(--brand-red); }
.switch:checked::after { transform: translateX(18px); }
.switch:focus-visible { outline: 2px solid var(--brand-red); outline-offset: 2px; }
/* Calendar date picker: highlight sign-up-able days, fill the selected
 * ones, mute beyond-horizon projected dates. Cells live inside MonthGrid,
 * so reach them with :deep. */
:deep(.mg-cell.has-occurrence) {
  background: var(--brand-bg);
  font-weight: 600;
}
:deep(.mg-cell.projected) {
  color: var(--brand-text-muted);
  border-style: dashed;
}
:deep(.mg-cell.selected) {
  background: var(--brand-red);
  border-color: var(--brand-red);
}
:deep(.mg-cell.selected .mg-num) { color: #fff; }
/* Past sessions this booking attended (manage mode): locked history —
 * filled but muted, with a subtle strike so they read as done, not
 * selectable. */
:deep(.mg-cell.attended) {
  background: var(--brand-bg);
  border-style: dashed;
  color: var(--brand-text-muted);
  cursor: default;
}
:deep(.mg-cell.attended .mg-num) {
  text-decoration: line-through;
  opacity: 0.7;
}
.session-row {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  cursor: pointer;
  font-size: 0.95rem;
}
.session-row.locked { cursor: default; }
.session-row.projected {
  cursor: default;
  opacity: 0.55;
}
.session-check {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
  border: 1px dashed var(--brand-border);
  border-radius: 4px;
}
.session-main { display: inline-flex; align-items: center; flex-wrap: wrap; gap: 0.25rem; }
.not-open {
  font-size: 0.75rem;
  color: var(--brand-text-muted);
  font-style: italic;
  margin-left: 0.25rem;
}
.session-row input[type="checkbox"],
.help-row input[type="checkbox"] {
  appearance: none;
  -webkit-appearance: none;
  width: 20px;
  height: 20px;
  flex-shrink: 0;
  margin: 0;
  padding: 0;
  background: var(--brand-bg);
  border: 1px solid var(--brand-border);
  border-radius: 4px;
  cursor: pointer;
  position: relative;
  transition: background 120ms, border-color 120ms;
}
.session-row input[type="checkbox"]:hover:not(:disabled),
.help-row input[type="checkbox"]:hover {
  border-color: var(--brand-red);
}
.session-row input[type="checkbox"]:focus-visible,
.help-row input[type="checkbox"]:focus-visible {
  outline: none;
  border-color: var(--brand-red);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--brand-red) 18%, transparent);
}
.session-row input[type="checkbox"]:checked,
.help-row input[type="checkbox"]:checked {
  background: var(--brand-red);
  border-color: var(--brand-red);
}
.session-row input[type="checkbox"]:disabled {
  opacity: 0.6;
}
.session-row input[type="checkbox"]:checked::after,
.help-row input[type="checkbox"]:checked::after {
  content: "";
  position: absolute;
  left: 5px;
  top: 1px;
  width: 6px;
  height: 11px;
  border: solid #fff;
  border-width: 0 2px 2px 0;
  transform: rotate(45deg);
}

/* Privacy explainer card */
.privacy-card summary {
  cursor: pointer;
  user-select: none;
  font-weight: 600;
  padding: 0.125rem 0;
}
.privacy-card .privacy-body {
  margin: 0.5rem 0 0;
  font-size: 0.9375rem;
  color: var(--brand-text-muted);
  line-height: 1.5;
}
.privacy-card .privacy-bullets {
  margin: 0.25rem 0 0;
  padding-left: 1.25rem;
  font-size: 0.9375rem;
  color: var(--brand-text-muted);
  line-height: 1.5;
}

.submit-row {
  margin-top: 2rem;
}

/* Help-with row: label + checkboxes share one line, wrap together. */
.help-choices {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 1.25rem;
}
.help-label { font-size: 0.95rem; }
.help-row {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  cursor: pointer;
  font-size: 0.95rem;
}

/* The "add to calendar" popup, pinned to the corner of PublicTopCard. */
.event-actions {
  position: absolute;
  right: 0.75rem;
  bottom: 0.75rem;
  z-index: 1;
}
@media (max-width: 600px) {
  .event-actions {
    position: static;
    display: flex;
    justify-content: flex-end;
  }
}
.cal {
  position: relative;
  display: inline-block;
}
.cal-button {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.375rem 0.75rem;
  font-size: 0.875rem;
  font-weight: 500;
  background: var(--brand-surface);
  color: var(--brand-text);
  border: 1px solid var(--brand-border);
  border-radius: 6px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.08);
  cursor: pointer;
  list-style: none;
  user-select: none;
}
.cal-button::-webkit-details-marker { display: none; }
.cal-button:hover { border-color: var(--brand-red); }
.cal[open] .cal-button {
  border-color: var(--brand-red);
}
.cal-menu {
  position: absolute;
  right: 0;
  top: calc(100% + 4px);
  list-style: none;
  margin: 0;
  padding: 0.25rem 0;
  background: var(--brand-surface);
  border: 1px solid var(--brand-border);
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  min-width: 12rem;
  z-index: 5;
}
.cal-menu li a {
  display: block;
  padding: 0.5rem 1rem;
  color: var(--brand-text);
  text-decoration: none;
  font-size: 0.9375rem;
}
.cal-menu li a:hover { background: var(--brand-bg); }

/* Number field with explicit ``−``/``+`` step buttons. */
.number-field {
  display: flex;
  align-items: stretch;
  width: 100%;
}
.num-step {
  font: inherit;
  font-size: 1.125rem;
  font-weight: 600;
  line-height: 1;
  width: 2.75rem;
  flex-shrink: 0;
  background: var(--brand-bg);
  color: var(--brand-text);
  border: 1px solid var(--brand-border);
  cursor: pointer;
  transition: background 120ms, border-color 120ms;
}
.num-step:first-child {
  border-radius: 6px 0 0 6px;
  border-right: 0;
}
.num-step:last-child {
  border-radius: 0 6px 6px 0;
  border-left: 0;
}
.num-step:hover:not(:disabled) {
  background: color-mix(in srgb, var(--brand-red) 10%, var(--brand-bg));
  border-color: var(--brand-red);
  position: relative;
  z-index: 1;
}
.num-step:disabled { opacity: 0.45; cursor: default; }
.num-input {
  border-radius: 0;
  text-align: center;
  flex: 1 1 auto;
  width: auto;
  min-width: 0;
}
.num-input::-webkit-outer-spin-button,
.num-input::-webkit-inner-spin-button {
  -webkit-appearance: none;
  margin: 0;
}
.num-input { -moz-appearance: textfield; }

.btn-label.hidden { visibility: hidden; }
.btn-spinner {
  position: absolute;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  inset: 0;
  pointer-events: none;
  animation: btn-spin 0.8s linear infinite;
  color: #fff;
}
@keyframes btn-spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) {
  .btn-spinner { animation: none; }
}

.error {
  color: var(--brand-red);
  margin: 0.5rem 0 0;
  font-size: 0.95rem;
}
</style>
