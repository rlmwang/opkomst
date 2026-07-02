<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import EditLink from "@/public_shared/EditLink.vue";
import PublicHero from "@/public_shared/PublicHero.vue";
import PublicNotice from "@/public_shared/PublicNotice.vue";
import PublicShell from "@/public_shared/PublicShell.vue";
import WeekdayGrid from "@/components/WeekdayGrid.vue";
import { type Locale, GITHUB_URL, chromeStrings, pickLocale } from "@/public_shared/strings";
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
const picked = reactive<Record<string, boolean>>({});
const busy = ref(false);
const errorMsg = ref("");
const savedFlash = ref(false);

const personal = ref<PersonalPage | null>(null);
const availDraft = ref<AvailabilityRange[]>([]);

function slug(): string {
  const parts = window.location.pathname.split("/").filter(Boolean);
  return parts[parts.length - 1] ?? "";
}

const { editToken, editUrl, confirmSaved } = useEditLink("c", slug);

const chores = computed(() => roster.value?.chores ?? []);
const chosenIds = computed(() => Object.keys(picked).filter((id) => picked[id]));

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
  for (const chore of chores.value) picked[chore.id] = page.enrolled_chore_ids.includes(chore.id);
  availDraft.value = (page.availability ?? []).map((r) => ({ ...r }));
}

function addAvailRange(): void {
  availDraft.value.push({ start: "", end: "" });
}

function removeAvailRange(index: number): void {
  availDraft.value.splice(index, 1);
}

async function saveAvailability(): Promise<void> {
  if (!editToken) return;
  const ranges = availDraft.value.filter((r) => r.start && r.end);
  busy.value = true;
  errorMsg.value = "";
  try {
    hydratePersonal(await putAvailability(editToken, ranges));
  } catch {
    errorMsg.value = ch.value.actionFailed;
  } finally {
    busy.value = false;
  }
}

async function enrol(): Promise<void> {
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
  busy.value = true;
  errorMsg.value = "";
  try {
    // Reminders follow the email: on if one's on file or newly entered.
    const enteredEmail = email.value.trim() || null;
    const page = await putEnrolment(editToken, {
      display_name: displayName.value.trim() || null,
      chore_ids: chosenIds.value,
      email_reminders: enteredEmail !== null || (personal.value?.has_email ?? false),
      email: enteredEmail,
    });
    hydratePersonal(page);
    email.value = ""; // one-shot add/replace; never echo it back
    savedFlash.value = true;
    window.setTimeout(() => (savedFlash.value = false), 2000);
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
          <p v-if="personal.my_shifts.length === 0" class="muted">{{ ch.noUpcoming }}</p>
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
          <p v-if="personal.open_shifts.length === 0" class="muted">{{ ch.noOpen }}</p>
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
          <p v-if="(personal.coverable_shifts ?? []).length === 0" class="muted">{{ ch.noCoverable }}</p>
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
          <p v-if="(personal.outlook_shifts ?? []).length === 0" class="muted">{{ ch.noOutlook }}</p>
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
          <p v-if="availDraft.length === 0" class="muted">{{ ch.availabilityEmpty }}</p>
          <div v-for="(r, i) in availDraft" :key="i" class="avail-row">
            <label class="avail-field">
              <span class="muted">{{ ch.availabilityFrom }}</span>
              <input v-model="r.start" type="date" />
            </label>
            <label class="avail-field">
              <span class="muted">{{ ch.availabilityTo }}</span>
              <input v-model="r.end" type="date" />
            </label>
            <button type="button" class="btn ghost" :disabled="busy" @click="removeAvailRange(i)">
              {{ ch.availabilityRemove }}
            </button>
          </div>
          <div class="shift-actions">
            <button type="button" class="btn ghost" :disabled="busy" @click="addAvailRange">
              {{ ch.availabilityAdd }}
            </button>
            <button type="button" class="btn" :disabled="busy" @click="saveAvailability">
              {{ ch.availabilitySave }}
            </button>
          </div>
        </div>
      </template>

      <!-- Chore picker (both modes) -->
      <div class="card stack">
        <h2>{{ ch.chooseChores }}</h2>
        <p v-if="status === 'enrol'" class="muted">{{ ch.enrolIntro }}</p>
        <p v-if="chores.length === 0" class="muted">{{ ch.noChores }}</p>
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

      <!-- Name + email + reminders -->
      <div class="card stack">
        <label class="field">
          <span>{{ c.displayName }}</span>
          <input v-model="displayName" type="text" class="input" />
        </label>

        <label class="field">
          <span>{{ ch.emailLabel }}</span>
          <input v-model="email" type="email" class="input" :placeholder="personal?.has_email ? '••••••' : ''" />
        </label>
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

      <div class="submit-row">
        <button v-if="status === 'enrol'" type="button" class="btn-primary" :disabled="busy" @click="enrol">
          {{ ch.enrolButton }}
        </button>
        <template v-else>
          <button type="button" class="btn-primary" :disabled="busy" @click="saveChanges">
            {{ savedFlash ? ch.saved : ch.saveChanges }}
          </button>
          <button type="button" class="btn ghost" :disabled="busy" @click="leave">{{ ch.leave }}</button>
        </template>
      </div>
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
.field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.field > span { font-size: 0.875rem; color: var(--brand-text-muted); }
/* .input + .btn-primary come from ``src/public_shared/forms.css``. */
.toggle {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
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
.avail-row { display: flex; gap: 0.5rem; align-items: end; flex-wrap: wrap; margin-bottom: 0.5rem; }
.avail-field { display: flex; flex-direction: column; gap: 0.25rem; }
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
