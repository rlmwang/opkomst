<script setup lang="ts">
import DatePicker from "primevue/datepicker";
import { computed, onMounted, reactive, ref } from "vue";
import EditLink from "@/public_shared/EditLink.vue";
import PublicEditBar from "@/public_shared/PublicEditBar.vue";
import PublicHero from "@/public_shared/PublicHero.vue";
import PublicNotice from "@/public_shared/PublicNotice.vue";
import PublicShell from "@/public_shared/PublicShell.vue";
import WeekdayGrid from "@/components/WeekdayGrid.vue";
import { isValidEmail } from "@/lib/validate";
import { showToast } from "@/public_shared/publicToast";
import { type Locale, GITHUB_URL, chromeStrings, pickLocale } from "@/public_shared/strings";
import { useEditForm } from "@/public_shared/useEditForm";
import { useEditLink } from "@/public_shared/useEditLink";
import {
  type AvailabilityRange,
  type PersonalPage,
  type PublicRoster,
  type ShiftAction,
  ApiError,
  fetchPersonalPage,
  fetchRosterBySlug,
  postEnrolment,
  postLeave,
  postShiftAction,
  putAvailability,
  putEnrolment,
} from "./api";
import { choreStrings, formatLongDate } from "./i18n";

type Status = "loading" | "enrol" | "personal" | "enrolled" | "unavailable" | "load-failed" | "left";

const status = ref<Status>("loading");
const roster = ref<PublicRoster | null>(null);
const locale = ref<Locale>("nl");
const c = computed(() => chromeStrings(locale.value));
const ch = computed(() => choreStrings(locale.value));

const displayName = ref("");
const email = ref("");
// Edit mode: when a hidden email is on file, mark it for removal on save
// (leaving the field empty keeps the existing one).
const clearEmail = ref(false);
const picked = reactive<Record<string, boolean>>({});
const busy = ref(false);
const errorMsg = ref("");

// Placeholder reflects the email state: hidden-on-file, being-removed, or
// none. Avoids the password-like dots.
const emailPlaceholder = computed(() => {
  if (clearEmail.value) return ch.value.emailClearing;
  if (personal.value?.has_email) return ch.value.emailHidden;
  return ch.value.emailLabel;
});

const personal = ref<PersonalPage | null>(null);
const availDraft = ref<AvailabilityRange[]>([]);

function slug(): string {
  const parts = window.location.pathname.split("/").filter(Boolean);
  return parts[parts.length - 1] ?? "";
}

const { editToken, editUrl, confirmSaved } = useEditLink("c", slug);

const chores = computed(() => roster.value?.chores ?? []);
const chosenIds = computed(() => Object.keys(picked).filter((id) => picked[id]));

// Dirty/revert/saved state for the shared edit bar.
const { dirty, justSaved, captureBaseline, revert, flashSaved } = useEditForm({
  snapshot: () => ({
    name: displayName.value,
    chores: [...chosenIds.value].sort(),
    avail: availDraft.value.map((r) => `${r.start}|${r.end}`),
    email: email.value,
    clearEmail: clearEmail.value,
  }),
  apply: (s) => {
    displayName.value = s.name;
    for (const chore of chores.value) picked[chore.id] = s.chores.includes(chore.id);
    availDraft.value = s.avail.map((pair) => {
      const [start, end] = pair.split("|");
      return { start, end };
    });
    email.value = s.email;
    clearEmail.value = s.clearEmail;
  },
});

onMounted(async () => {
  const inlined = window.__OPKOMST_CHORE__;
  if (inlined === null) {
    status.value = "unavailable";
    return;
  }
  try {
    const loaded = inlined ?? (await fetchRosterBySlug(slug()));
    roster.value = loaded;
    locale.value = pickLocale(loaded.locale);
    for (const chore of loaded.chores) picked[chore.id] = false;

    if (editToken) {
      const page = await fetchPersonalPage(editToken);
      hydratePersonal(page);
      captureBaseline();
      status.value = "personal";
    } else {
      status.value = "enrol";
    }
  } catch (e) {
    status.value = e instanceof ApiError && e.status === 410 ? "unavailable" : "load-failed";
  }
});

function hydratePersonal(page: PersonalPage): void {
  personal.value = page;
  displayName.value = page.display_name ?? "";
  email.value = "";
  clearEmail.value = false;
  for (const chore of chores.value) picked[chore.id] = page.enrolled_chore_ids.includes(chore.id);
  availDraft.value = (page.availability ?? []).map((r) => ({ ...r }));
}

// DatePicker binds a Date; the draft (and API) carry "YYYY-MM-DD" strings.
// Local, no UTC shift — mirrors the roster edit form.
function isoDate(d: Date | null): string {
  if (!d) return "";
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function parseDate(s: string): Date | null {
  if (!s) return null;
  const [y, m, d] = s.split("-").map(Number);
  if (!y || !m || !d) return null;
  return new Date(y, m - 1, d);
}

function toggleClearEmail(): void {
  clearEmail.value = !clearEmail.value;
  if (clearEmail.value) email.value = ""; // removing wins over a typed value
}

function addAvailRange(): void {
  availDraft.value.push({ start: "", end: "" });
}

function removeAvailRange(index: number): void {
  availDraft.value.splice(index, 1);
}

// Client-side validation shared by enrol + save; specific reasons toast.
function validateForm(): boolean {
  if (!displayName.value.trim()) {
    showToast(c.value.nameRequired);
    return false;
  }
  const em = email.value.trim();
  if (em && !isValidEmail(em)) {
    showToast(c.value.invalidEmail);
    return false;
  }
  return true;
}

async function enrol(): Promise<void> {
  if (!validateForm()) return;
  busy.value = true;
  errorMsg.value = "";
  try {
    // Giving an email means reminders are on — there's no separate opt-in.
    const enteredEmail = email.value.trim() || null;
    const ack = await postEnrolment(slug(), {
      display_name: displayName.value.trim() || null,
      email: enteredEmail,
      email_reminders: enteredEmail !== null,
      chore_ids: chosenIds.value,
    });
    // Records the token and routes the URL onto the magic link so a
    // refresh reopens the edit page (guaranteed by useEditLink).
    confirmSaved(ack.edit_token);
    status.value = "enrolled";
  } catch {
    errorMsg.value = ch.value.actionFailed;
  } finally {
    busy.value = false;
  }
}

async function saveChanges(): Promise<void> {
  if (!editToken) return;
  if (!validateForm()) return;
  busy.value = true;
  errorMsg.value = "";
  try {
    // One page, one save: persist the enrolment and the time-off ranges
    // together so there's a single confirmation button for everything.
    // Clearing wins; otherwise reminders stay on if an email is on file or
    // newly entered.
    const enteredEmail = clearEmail.value ? null : email.value.trim() || null;
    const keepReminders = clearEmail.value ? false : enteredEmail !== null || (personal.value?.has_email ?? false);
    await putEnrolment(editToken, {
      display_name: displayName.value.trim() || null,
      chore_ids: chosenIds.value,
      email_reminders: keepReminders,
      email: enteredEmail,
    });
    const ranges = availDraft.value.filter((r) => r.start && r.end);
    hydratePersonal(await putAvailability(editToken, ranges));
    email.value = ""; // one-shot add/replace; never echo it back
    captureBaseline();
    flashSaved();
  } catch {
    errorMsg.value = ch.value.actionFailed;
  } finally {
    busy.value = false;
  }
}

async function act(shiftId: string, action: ShiftAction): Promise<void> {
  if (!editToken) return;
  busy.value = true;
  errorMsg.value = "";
  try {
    personal.value = await postShiftAction(editToken, shiftId, action);
  } catch {
    errorMsg.value = ch.value.actionFailed;
  } finally {
    busy.value = false;
  }
}

async function leave(): Promise<void> {
  if (!editToken) return;
  if (!window.confirm(ch.value.leaveConfirm)) return;
  busy.value = true;
  try {
    await postLeave(editToken);
    status.value = "left";
  } catch {
    errorMsg.value = ch.value.actionFailed;
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <PublicShell v-model:locale="locale">
    <PublicNotice v-if="status === 'loading'" :message="c.loading" />
    <PublicNotice v-else-if="status === 'unavailable'" :message="c.unavailable" />
    <PublicNotice v-else-if="status === 'load-failed'" :message="c.loadFailed" />
    <PublicNotice v-else-if="status === 'left'" :message="ch.left" />

    <PublicNotice v-else-if="status === 'enrolled'" :title="ch.enrolled" :message="c.editPrompt" />
    <EditLink v-if="status === 'enrolled'" :url="editUrl" :locale="locale" />

    <template v-else-if="roster && (status === 'enrol' || status === 'personal')">
      <PublicHero
        :image-url="roster.image_url"
        :artist="roster.image_artist_instagram"
        :credit-label="c.imageCredit"
      />
      <div class="card stack">
        <h1>{{ roster.name }}</h1>
        <p v-if="roster.description" class="muted">{{ roster.description }}</p>
      </div>

      <!-- Personal mode: my turns + up-for-grabs -->
      <template v-if="status === 'personal' && personal">
        <div class="card stack">
          <h2>{{ ch.myTurns }}</h2>
          <p v-if="personal.my_shifts.length === 0" class="empty muted">{{ ch.noUpcoming }}</p>
          <ul v-else class="shift-list">
            <li v-for="s in personal.my_shifts" :key="s.id" class="shift-row">
              <span class="shift-main">
                <strong>{{ s.chore_name }}</strong>
                <span class="muted">{{ formatLongDate(s.on_date, locale) }}</span>
                <span v-if="s.inherited" class="muted origin-note">{{ ch.coveringForLeaver }}</span>
              </span>
              <span class="shift-actions">
                <button type="button" class="btn" :disabled="busy" @click="act(s.id, 'done')">
                  {{ ch.markDone }}
                </button>
                <button type="button" class="btn ghost" :disabled="busy" @click="act(s.id, 'pass')">
                  {{ ch.cantMakeIt }}
                </button>
              </span>
            </li>
          </ul>
        </div>

        <div class="card stack">
          <h2>{{ ch.upForGrabs }}</h2>
          <p v-if="personal.open_shifts.length === 0" class="empty muted">{{ ch.noOpen }}</p>
          <ul v-else class="shift-list">
            <li v-for="s in personal.open_shifts" :key="s.id" class="shift-row">
              <span class="shift-main">
                <strong>{{ s.chore_name }}</strong>
                <span class="muted">{{ formatLongDate(s.on_date, locale) }}</span>
              </span>
              <button type="button" class="btn" :disabled="busy" @click="act(s.id, 'claim')">
                {{ ch.claim }}
              </button>
            </li>
          </ul>
        </div>

        <div class="card stack">
          <h2>{{ ch.coverHeading }}</h2>
          <p v-if="(personal.coverable_shifts ?? []).length === 0" class="empty muted">{{ ch.noCoverable }}</p>
          <ul v-else class="shift-list">
            <li v-for="s in personal.coverable_shifts ?? []" :key="s.id" class="shift-row">
              <span class="shift-main">
                <strong>{{ s.chore_name }}</strong>
                <span class="muted">
                  {{ formatLongDate(s.on_date, locale) }}
                  <template v-if="s.assignee_name"> · {{ ch.coverForName.replace("{name}", s.assignee_name) }}</template>
                </span>
              </span>
              <button type="button" class="btn ghost" :disabled="busy" @click="act(s.id, 'cover')">
                {{ ch.coverButton }}
              </button>
            </li>
          </ul>
        </div>

        <div class="card stack">
          <h2>{{ ch.outlookHeading }}</h2>
          <p class="muted">{{ ch.outlookNote }}</p>
          <p v-if="(personal.outlook_shifts ?? []).length === 0" class="empty muted">{{ ch.noOutlook }}</p>
          <ul v-else class="shift-list">
            <li v-for="(s, i) in personal.outlook_shifts ?? []" :key="`${s.chore_id}-${s.on_date}-${i}`" class="shift-row">
              <span class="shift-main">
                <strong>{{ s.chore_name }}</strong>
                <span class="muted">{{ formatLongDate(s.on_date, locale) }}</span>
              </span>
            </li>
          </ul>
        </div>

        <div class="card stack">
          <h2>{{ ch.availabilityHeading }}</h2>
          <p class="muted">{{ ch.availabilityHint }}</p>
          <p v-if="availDraft.length === 0" class="empty muted">{{ ch.availabilityEmpty }}</p>
          <div v-for="(r, i) in availDraft" :key="i" class="list-row avail-row">
            <div class="avail-fields">
              <DatePicker
                :model-value="parseDate(r.start)"
                @update:model-value="(d) => (r.start = isoDate(d as Date | null))"
                date-format="dd-mm-yy"
                :placeholder="ch.availabilityFrom"
                :aria-label="ch.availabilityFrom"
                fluid
              />
              <DatePicker
                :model-value="parseDate(r.end)"
                @update:model-value="(d) => (r.end = isoDate(d as Date | null))"
                date-format="dd-mm-yy"
                :placeholder="ch.availabilityTo"
                :aria-label="ch.availabilityTo"
                fluid
              />
            </div>
            <button
              type="button"
              class="icon-btn"
              :disabled="busy"
              :aria-label="ch.availabilityRemove"
              @click="removeAvailRange(i)"
            >
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <polyline points="3 6 5 6 21 6" />
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                <line x1="10" y1="11" x2="10" y2="17" />
                <line x1="14" y1="11" x2="14" y2="17" />
              </svg>
            </button>
          </div>
          <button type="button" class="btn-secondary avail-add" :disabled="busy" @click="addAvailRange">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            {{ ch.availabilityAdd }}
          </button>
        </div>
      </template>

      <!-- Chore picker (both modes) -->
      <div class="card stack">
        <h2>{{ ch.chooseChores }}</h2>
        <p v-if="status === 'enrol'" class="muted">{{ ch.enrolIntro }}</p>
        <p v-if="chores.length === 0" class="empty muted">{{ ch.noChores }}</p>
        <label v-for="chore in chores" :key="chore.id" class="chore-check">
          <input type="checkbox" class="check" v-model="picked[chore.id]" />
          <span class="chore-label">
            <span class="chore-title">
              <span v-if="chore.emoji" class="emoji">{{ chore.emoji }}</span>
              <strong>{{ chore.name }}</strong>
            </span>
            <span v-if="chore.description" class="muted chore-desc">{{ chore.description }}</span>
            <WeekdayGrid
              v-if="chore.cycle_slots.length"
              :cycle-slots="chore.cycle_slots"
              :period-weeks="roster.period_weeks"
              :weekday-labels="ch.weekdays"
            />
          </span>
        </label>
      </div>

      <!-- Name + email -->
      <div class="card stack">
        <input
          v-model="displayName"
          type="text"
          class="input"
          :placeholder="c.displayName"
          autocomplete="name"
        />
        <div class="email-row">
          <input
            v-model="email"
            type="email"
            class="input"
            :placeholder="emailPlaceholder"
            :disabled="clearEmail"
            autocomplete="email"
          />
          <button
            v-if="personal?.has_email"
            type="button"
            class="icon-btn"
            :class="{ active: clearEmail }"
            :aria-label="clearEmail ? ch.emailKeep : ch.emailClear"
            @click="toggleClearEmail"
          >
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <polyline points="3 6 5 6 21 6" />
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
              <line x1="10" y1="11" x2="10" y2="17" />
              <line x1="14" y1="11" x2="14" y2="17" />
            </svg>
          </button>
        </div>
      </div>

      <div class="card">
        <details class="disclosure">
          <summary>{{ c.explainerTitle }}</summary>
          <p class="muted">{{ ch.emailDisclosureBody }}</p>
          <p class="muted">
            {{ c.explainerBody }}
            <a :href="GITHUB_URL" target="_blank" rel="noopener">{{ c.explainerLink }}</a>
          </p>
        </details>
      </div>

      <p v-if="errorMsg" class="error">{{ errorMsg }}</p>

      <div v-if="status === 'enrol'" class="submit-row">
        <button type="button" class="btn-primary" :disabled="busy" @click="enrol">
          {{ ch.enrolButton }}
        </button>
      </div>
      <PublicEditBar
        v-else
        :dirty="dirty"
        :saving="busy"
        :just-saved="justSaved"
        :locale="locale"
        @save="saveChanges"
        @revert="revert"
        @withdraw="leave"
      />
    </template>
  </PublicShell>
</template>

<style scoped>
.stack > * + * { margin-top: 0.75rem; }
h1 { margin: 0; }
h2 { margin: 0; font-size: 1.1rem; }
.chore-check {
  display: flex;
  align-items: flex-start;
  gap: 0.625rem;
  cursor: pointer;
  padding: 0.75rem;
  border-radius: 8px;
  transition: background 120ms ease;
}
/* A touch more breathing room between chore rows than the card's stack. */
.chore-check + .chore-check {
  margin-top: 0.25rem;
}
/* Highlight the whole clickable row (checkbox + label) on hover. */
.chore-check:hover {
  background: color-mix(in srgb, var(--brand-red) 7%, transparent);
}
.chore-label {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  flex: 1 1 0;
  min-width: 0;
}
.chore-title {
  display: inline-flex;
  align-items: baseline;
  gap: 0.375rem;
}
.emoji { line-height: 1; }
.chore-desc { font-size: 0.8125rem; }
/* .input + .btn-primary come from ``src/public_shared/forms.css``. */
.email-row { display: flex; gap: 0.5rem; align-items: center; }
.email-row > .input { flex: 1; min-width: 0; }
/* Armed (email marked for removal): the bin reads active. */
.icon-btn.active {
  color: var(--brand-red);
  background: color-mix(in srgb, var(--brand-red) 12%, transparent);
}
.disclosure summary { cursor: pointer; font-weight: 600; }
.shift-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.shift-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  flex-wrap: wrap;
}
.shift-main { display: flex; flex-direction: column; }
.shift-actions { display: flex; gap: 0.5rem; flex-wrap: wrap; }
/* Time-off rows reuse the global ``.list-row`` (hover + rounding) from
 * theme.css, matching the admin editable lists. */
.avail-row { margin-bottom: 0.25rem; }
.avail-fields { display: flex; gap: 0.5rem; flex: 1; min-width: 0; flex-wrap: wrap; }
.avail-fields > :deep(.p-datepicker) { flex: 1 1 8rem; min-width: 0; }
/* .btn-secondary (soft-pink add button) comes from theme.css. Add buttons
 * span the section full-width, matching the admin form add buttons. */
.avail-add { width: 100%; justify-content: center; }
.icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 2rem;
  padding: 0;
  flex-shrink: 0;
  background: transparent;
  border: 0;
  border-radius: 6px;
  color: var(--brand-text-muted);
  cursor: pointer;
  transition: background 120ms, color 120ms;
}
.icon-btn:hover {
  color: var(--brand-red);
  background: color-mix(in srgb, var(--brand-red) 8%, transparent);
}
/* .submit-row (right-aligned action row) comes from ``forms.css``. */
.btn {
  padding: 0.5rem 0.875rem;
  border: 1px solid var(--brand-border);
  border-radius: 6px;
  background: var(--brand-surface);
  color: var(--brand-text);
  font: inherit;
  cursor: pointer;
}
.btn:disabled { opacity: 0.5; cursor: default; }
.btn.ghost { background: none; }
.error { color: var(--brand-red); }
</style>
