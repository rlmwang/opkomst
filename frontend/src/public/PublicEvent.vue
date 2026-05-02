<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { formatDate, formatTimeRange } from "@/lib/format";
import { mapLink } from "@/lib/map-link";
import { isValidEmail } from "@/lib/validate";
import BrandMark from "./BrandMark.vue";
import BrandedSelect from "./BrandedSelect.vue";
import { ApiError, type PublicEvent, fetchEventBySlug, postSignup } from "./api";
import { type Locale, pickLocale, strings } from "./i18n";

const slug = window.location.pathname.replace(/^\/e\/+/, "").split(/[/?#]/)[0];

// Server-side-injected event payload. Synchronous, no round-trip
// on first paint — ``backend/routers/spa.py`` writes
// ``window.__OPKOMST_EVENT__`` into the served HTML before the
// JS bundle even parses:
//   * ``PublicEvent`` object → event exists, render the form.
//   * ``null`` → backend looked the slug up and didn't find it
//     (or the slug shape is invalid). Render not-found.
//   * ``undefined`` → dev mode (Vite serving public-event.html
//     without the backend's SPA handler in front). Fall back to
//     a fetch so dev still works; 404 from that fetch means the
//     same as the inlined-null case.
//
// Three independent state flags rather than one tri-state value
// because the logic split out cleanly: ``loadFailed`` for
// transport errors (5xx, network), ``notFound`` for "this slug
// is unknown", everything else gates on ``event`` being truthy.
// Earlier shape conflated "event is null" with "still loading"
// and the skeleton shimmer never went away on a 404.
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

// Locale: ``?lang=`` URL override beats the event's own locale.
const locale = ref<Locale>(pickLocale(event.value?.locale));
watch(event, (e) => {
  if (e) locale.value = pickLocale(e.locale);
});
const t = computed(() => strings(locale.value));

function setLocale(next: Locale) {
  locale.value = next;
  document.documentElement.lang = next;
}

// --- form state — survives a refresh on flaky mobile connections ---
const draftKey = `signup-draft:${slug}`;
type Draft = {
  displayName: string;
  partySize: number;
  sourceChoice: string | null;
  helpChoices: string[];
  email: string;
};
function emptyDraft(): Draft {
  return {
    displayName: "",
    partySize: 1,
    sourceChoice: null,
    helpChoices: [],
    email: "",
  };
}
const initialDraft: Draft = (() => {
  try {
    const raw = sessionStorage.getItem(draftKey);
    if (raw) return { ...emptyDraft(), ...JSON.parse(raw) };
  } catch { /* ignore */ }
  return emptyDraft();
})();
const displayName = ref(initialDraft.displayName);
const partySize = ref(initialDraft.partySize);
const sourceChoice = ref<string | null>(initialDraft.sourceChoice);
const helpChoices = ref<string[]>(initialDraft.helpChoices);
const email = ref(initialDraft.email);

watch(
  [displayName, partySize, sourceChoice, helpChoices, email],
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
const errorMsg = ref<string | null>(null);

const emailFieldShown = computed(
  () => Boolean(event.value && (event.value.feedback_enabled || event.value.reminder_enabled)),
);
const emailPlaceholder = computed(() => {
  const e = event.value;
  if (!e) return "";
  const r = e.reminder_enabled, q = e.feedback_enabled;
  if (r && q) return t.value.emailFor.reminderAndFeedback;
  if (r) return t.value.emailFor.reminderOnly;
  return t.value.emailFor.feedbackOnly;
});

interface EmailUseBullet {
  text: string;
  previewUrl: string;
}

// Bullets in the privacy explainer that name each email the
// visitor can expect, with a link to a server-rendered preview of
// the exact HTML that'll arrive — privacy-by-transparency.
const emailUseBullets = computed<EmailUseBullet[]>(() => {
  const e = event.value;
  if (!e) return [];
  const bullets: EmailUseBullet[] = [];
  if (e.reminder_enabled) {
    bullets.push({
      text: t.value.emailUses.reminder,
      previewUrl: `/api/v1/events/by-slug/${slug}/email-preview/reminder`,
    });
  }
  if (e.feedback_enabled) {
    bullets.push({
      text: t.value.emailUses.feedback,
      previewUrl: `/api/v1/events/by-slug/${slug}/email-preview/feedback`,
    });
  }
  return bullets;
});

// --- add-to-calendar dropdown (native ``<details>`` for the popup) ---
const calLinks = computed(() => {
  const e = event.value;
  if (!e) return null;
  const enc = encodeURIComponent;
  const utc = (iso: string) =>
    new Date(iso).toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");
  const publicUrl = `${window.location.origin}/e/${e.slug}`;
  const desc = [e.topic ?? "", publicUrl].filter(Boolean).join("\n\n");
  const ics = `/api/v1/events/by-slug/${e.slug}/event.ics`;
  const google =
    `https://calendar.google.com/calendar/render?action=TEMPLATE` +
    `&text=${enc(e.name)}` +
    `&dates=${utc(e.starts_at)}/${utc(e.ends_at)}` +
    `&details=${enc(desc)}` +
    `&location=${enc(e.location)}`;
  return { google, ics };
});

// Headcount field is a positive integer 1–50. We block invalid
// characters at the ``beforeinput`` event so the visitor never
// SEES junk in the field — typing a letter or period just does
// nothing instead of being rejected after the fact. Backspace,
// delete, arrow keys etc. are all ``deleteContent*`` /
// ``historyUndo`` etc. types and pass through. Pasted strings
// are validated the same way.
function onPartyBeforeInput(ev: InputEvent) {
  // Insertion events carry the proposed text in ``data``;
  // everything else (deletion, history) has data null/empty.
  if (ev.data == null) return;
  if (!/^\d+$/.test(ev.data)) {
    ev.preventDefault();
  }
}
function onPartyInput(ev: Event) {
  // Anything that DID get into the field is digits only (the
  // beforeinput guard ensures it). Parse + clamp to 1–50.
  const raw = (ev.target as HTMLInputElement).value;
  if (raw === "") return; // mid-edit blank — wait for blur
  const n = parseInt(raw, 10);
  if (Number.isFinite(n)) {
    partySize.value = Math.min(50, Math.max(1, n));
  }
}
function normalisePartySize(ev: FocusEvent) {
  let n = partySize.value;
  if (typeof n !== "number" || !Number.isFinite(n) || n < 1) {
    n = 1;
  } else {
    n = Math.min(50, Math.max(1, Math.floor(n)));
  }
  partySize.value = n;
  // Force the input element to reflect the model in case the
  // visitor cleared the field (model held the last valid value
  // but the visible input was empty).
  (ev.target as HTMLInputElement).value = String(n);
}

// Prevent the implicit "Enter from any input → submit the form"
// browser default. With no edit-after-submit affordance, an
// accidental Enter while typing would lock in a half-finished
// signup. The submit button itself still works: native focus +
// Enter activates a focused button, and a click event isn't
// affected. Textareas are unaffected too — they'd want Enter for
// newlines anyway, and we don't have any.
function onFormKeydown(ev: KeyboardEvent) {
  if (ev.key !== "Enter") return;
  const target = ev.target as HTMLElement | null;
  // Allow Enter-on-button (the deliberate confirm path).
  if (target && target.tagName === "BUTTON") return;
  // Allow Enter inside a textarea (newline) if we ever add one.
  if (target && target.tagName === "TEXTAREA") return;
  ev.preventDefault();
}

async function submit() {
  errorMsg.value = null;
  if (!event.value) return;
  const trimmedName = displayName.value.trim();
  const trimmedEmail = email.value.trim();
  if (trimmedEmail && !isValidEmail(trimmedEmail)) {
    errorMsg.value = t.value.invalidEmail;
    return;
  }
  submitting.value = true;
  try {
    await postSignup(slug, {
      display_name: trimmedName || null,
      party_size: partySize.value,
      source_choice: sourceChoice.value,
      help_choices: helpChoices.value,
      email: trimmedEmail || null,
    });
    submitted.value = true;
    clearDraft();
  } catch {
    errorMsg.value = t.value.submitFail;
  } finally {
    submitting.value = false;
  }
}

onMounted(() => {
  document.documentElement.lang = locale.value;
  document.title = event.value?.name ? `${event.value.name} — opkomst.nu` : "opkomst.nu";
});
watch(event, (e) => {
  if (e?.name) document.title = `${e.name} — opkomst.nu`;
});
</script>

<template>
  <div class="container stack">
    <header class="public-header">
      <BrandMark />
      <div class="lang-switcher" role="group" aria-label="Language">
        <button
          type="button"
          class="flag"
          :class="{ active: locale === 'nl' }"
          aria-label="Nederlands"
          title="Nederlands"
          @click="setLocale('nl')"
        >🇳🇱</button>
        <button
          type="button"
          class="flag"
          :class="{ active: locale === 'en' }"
          aria-label="English"
          title="English"
          @click="setLocale('en')"
        >🇬🇧</button>
      </div>
    </header>

    <div v-if="loadFailed" class="card">
      <p>{{ t.loadFailed }}</p>
    </div>

    <div v-else-if="notFound" class="card">
      <p>{{ t.notFound }}</p>
    </div>

    <div v-else-if="event?.archived" class="card">
      <h1>{{ event.name }}</h1>
      <p class="muted archived-note">{{ t.archived }}</p>
    </div>

    <template v-else>
      <div class="card event-header">
        <div class="event-title">
          <h1 v-if="event">{{ event.name }}</h1>
          <h1 v-else class="skeleton-line skeleton-title" aria-hidden="true"></h1>
          <p v-if="event?.topic" class="event-topic">{{ event.topic }}</p>
        </div>

        <dl class="event-meta">
          <div class="meta-row">
            <span class="icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
            </span>
            <span v-if="event">{{ formatDate(event.starts_at, locale) }}</span>
            <span v-else class="skeleton-line skeleton-meta" aria-hidden="true"></span>
          </div>
          <div class="meta-row">
            <span class="icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
            </span>
            <span v-if="event">{{ formatTimeRange(event.starts_at, event.ends_at, locale) }}</span>
            <span v-else class="skeleton-line skeleton-meta" aria-hidden="true"></span>
          </div>
          <div class="meta-row">
            <span class="icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
            </span>
            <a
              v-if="event"
              :href="mapLink({ location: event.location, latitude: event.latitude, longitude: event.longitude })"
              target="_blank"
              rel="noopener"
              class="meta-link"
            >
              {{ event.location }}
              <svg class="external" viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
            </a>
            <span v-else class="skeleton-line skeleton-meta" aria-hidden="true"></span>
          </div>
        </dl>

        <div v-if="event && calLinks" class="event-actions">
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
      </div>

      <div v-if="event && !submitted" class="card privacy-card">
        <details>
          <summary>{{ t.explainerTitle }}</summary>
          <template v-if="emailFieldShown">
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
          </template>
          <p v-else class="privacy-body">
            {{ t.explainerIntro }} {{ t.explainerNoEmail }} {{ t.explainerSource }}
            <a href="https://github.com/rlmwang/opkomst" target="_blank" rel="noopener">{{ t.explainerLink }}</a>.
          </p>
        </details>
      </div>

      <div v-if="submitted" class="card stack">
        <h2>{{ t.thanks }}</h2>
        <p class="muted">
          {{ event?.feedback_enabled ? t.thanksBody : t.thanksBodyNoEmail }}
        </p>
      </div>

      <form
        v-else
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
            <button
              type="button"
              class="num-step"
              aria-label="−"
              :disabled="partySize <= 1"
              @click="partySize = Math.max(1, (partySize || 1) - 1)"
            >−</button>
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
            <button
              type="button"
              class="num-step"
              aria-label="+"
              :disabled="partySize >= 50"
              @click="partySize = Math.min(50, (partySize || 0) + 1)"
            >+</button>
          </div>
        </section>

        <section v-if="event && event.help_options.length > 0" class="form-section help-section">
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
            :options="event?.source_options ?? []"
            :placeholder="event ? t.sourcePlaceholder : ''"
            :disabled="!event"
            :aria-label="t.sourcePlaceholder"
          />
          <input
            v-if="!event || emailFieldShown"
            v-model="email"
            type="email"
            class="input"
            :placeholder="event ? emailPlaceholder : ''"
            :disabled="!event"
            autocomplete="email"
          />
        </section>

        <p v-if="errorMsg" class="error" role="alert">{{ errorMsg }}</p>

        <div class="submit-row">
          <button
            type="submit"
            class="btn-primary"
            :disabled="!event || submitting"
            :aria-busy="submitting"
          >
            <!-- Submit label and spinner share the cell so the
                 button never resizes between idle and submitting
                 states; only one is visible at a time. The label
                 stays in the DOM (just hidden) to preserve width. -->
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
    </template>
  </div>
</template>

<style scoped>
/* Header — same shape as components/PublicHeader.vue. */
.public-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 1rem 0;
  flex-wrap: wrap;
}

.lang-switcher {
  display: flex;
  gap: 0.25rem;
  background: var(--brand-surface);
  border: 1px solid var(--brand-border);
  border-radius: 999px;
  padding: 0.25rem;
}
.flag {
  background: none;
  border: 2px solid transparent;
  cursor: pointer;
  padding: 0.25rem 0.5rem;
  border-radius: 999px;
  font-size: 1.1rem;
  line-height: 1;
  opacity: 0.4;
  filter: grayscale(0.6);
  transition: opacity 120ms, filter 120ms, border-color 120ms, background 120ms;
}
.flag:hover { opacity: 0.85; filter: grayscale(0.2); }
.flag.active {
  opacity: 1;
  filter: none;
  background: var(--brand-bg);
  border-color: var(--brand-red);
  box-shadow: 0 0 0 1px var(--brand-red);
}

/* Form layout — copied verbatim from the original
 * PublicEventPage.vue. */
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

/* Submit aligned right; same as the original. */
.submit-row {
  display: flex;
  justify-content: flex-end;
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
/* Checkboxes styled to match PrimeVue's Checkbox (which the
 * old PublicEventPage used): 20×20 square with brand-border, fills
 * brand-red and shows a white checkmark when checked. ``appearance:
 * none`` strips the OS default so the look stays consistent across
 * browsers. */
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
.help-row input[type="checkbox"]:hover {
  border-color: var(--brand-red);
}
.help-row input[type="checkbox"]:focus-visible {
  outline: none;
  border-color: var(--brand-red);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--brand-red) 18%, transparent);
}
.help-row input[type="checkbox"]:checked {
  background: var(--brand-red);
  border-color: var(--brand-red);
}
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

/* Event header card with absolute-positioned cal button. */
.event-header {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
.event-title h1 {
  margin: 0;
  font-size: 1.5rem;
  line-height: 1.25;
}
.event-topic {
  margin: 0.75rem 0 0;
  padding: 0.25rem 0;
  color: var(--brand-text-muted);
  font-style: italic;
  font-size: 1.0625rem;
  line-height: 1.5;
}

.event-meta {
  display: grid;
  gap: 0.5rem;
  margin: 0;
  padding: 0;
}
.meta-row {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  font-size: 0.95rem;
  line-height: 1.3;
}
.meta-row > .icon {
  color: var(--brand-red);
  width: 1rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.meta-link {
  color: inherit;
  text-decoration: none;
}
.meta-link:hover { text-decoration: underline; text-decoration-color: var(--brand-red); }
.meta-link .external {
  color: var(--brand-text-muted);
  margin-left: 0.3rem;
  vertical-align: -1px;
}

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

/* "Add to calendar" — visually matches the previous PrimeVue
 * Button(severity="secondary" size="small"): cream surface, brand
 * border, light shadow. ``<details>``/``<summary>`` is the popup
 * mechanism — accessible, no JS state machine. */
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

/* Native form inputs styled to look at home alongside the rest of
 * the brand. ``font-size: 16px`` is the magic number that stops
 * iOS Safari zooming on focus. */
.input {
  font: inherit;
  font-size: 16px;
  padding: 0.625rem 0.75rem;
  background: var(--brand-bg);
  color: var(--brand-text);
  border: 1px solid var(--brand-border);
  border-radius: 6px;
  width: 100%;
}
.input:focus {
  outline: none;
  border-color: var(--brand-red);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--brand-red) 18%, transparent);
}
.input:disabled { background: var(--brand-bg); color: var(--brand-text-muted); }
/* The "how did you hear" dropdown is rendered by ``BrandedSelect``
 * — a fully-themed listbox component instead of a native
 * ``<select>``, because native dropdown panels are OS-styled and
 * couldn't be made to match the cream/red brand of the rest of
 * the form. ``BrandedSelect`` owns its own scoped styles. */

/* Number field with explicit ``−``/``+`` step buttons — same
 * affordance as the previous PrimeVue InputNumber(show-buttons).
 * The buttons hug the input on both sides, sharing borders so
 * the whole control reads as a single field. Native spinner
 * arrows are hidden so we don't get a duplicate set on the
 * right edge of the input. */
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
/* Disabled stepper: dimmed but keep the default cursor — the
 * stop-cursor felt aggressive over what's a soft min/max bound,
 * not a forbidden action. */
.num-step:disabled { opacity: 0.45; cursor: default; }
.num-input {
  border-radius: 0;
  text-align: center;
  /* The wrapping ``.number-field`` controls width; the input
   * itself stays flex-1 so it fills the gap between the buttons. */
  flex: 1 1 auto;
  width: auto;
  min-width: 0;
}
/* Hide browser-native spinner buttons — we render our own. */
.num-input::-webkit-outer-spin-button,
.num-input::-webkit-inner-spin-button {
  -webkit-appearance: none;
  margin: 0;
}
.num-input { -moz-appearance: textfield; }

.btn-primary {
  font: inherit;
  cursor: pointer;
  padding: 0.625rem 1.5rem;
  /* Reserve a fixed minimum so the button doesn't visibly
   * shrink when its label is hidden during ``submitting`` —
   * the spinner replaces the label in the same footprint. */
  min-width: 8rem;
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--brand-red);
  border-radius: 6px;
  background: var(--brand-red);
  color: #fff;
  font-weight: 600;
  transition: background 120ms, opacity 120ms, transform 60ms ease;
}
.btn-primary:hover:not(:disabled) { background: #7f0009; }
/* Tactile click feedback so the visitor sees something happen the
 * instant they press, before the network round-trip starts. */
.btn-primary:active:not(:disabled) { transform: translateY(1px); }
/* Disabled while submitting: keep the brand-red look (the spinner
 * itself is the affordance) but lock interaction. ``cursor:
 * default`` rather than ``not-allowed`` because the action isn't
 * forbidden, it's in flight. */
.btn-primary:disabled { opacity: 0.85; cursor: default; }
/* When ``submitting`` the label is hidden but kept in DOM so the
 * button's width stays put. ``visibility: hidden`` (not display:
 * none) preserves layout. */
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
.archived-note { margin-top: 0.5rem; }

/* Skeleton shimmer while the by-slug fetch is in flight. The form
 * below is interactive immediately; these only stand in for header
 * text that genuinely depends on server data. */
.skeleton-line {
  display: inline-block;
  background: linear-gradient(
    90deg,
    var(--brand-bg) 0%,
    color-mix(in srgb, var(--brand-text) 8%, transparent) 50%,
    var(--brand-bg) 100%
  );
  background-size: 200% 100%;
  border-radius: 4px;
  animation: opkomst-skeleton 1.4s ease-in-out infinite;
}
.skeleton-title { width: 60%; height: 1.5rem; vertical-align: middle; }
.skeleton-meta  { width: 12rem; max-width: 70%; height: 0.95rem; }
@keyframes opkomst-skeleton {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
@media (prefers-reduced-motion: reduce) {
  .skeleton-line { animation: none; }
}
</style>
