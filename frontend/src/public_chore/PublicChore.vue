<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import Disclosure from "@/public_shared/Disclosure.vue";
import EditLink from "@/public_shared/EditLink.vue";
import PublicHero from "@/public_shared/PublicHero.vue";
import PublicNotice from "@/public_shared/PublicNotice.vue";
import PublicShell from "@/public_shared/PublicShell.vue";
import { type Locale, chromeStrings, pickLocale } from "@/public_shared/strings";
import {
  type PersonalPage,
  type PublicRoster,
  type ShiftAction,
  ApiError,
  fetchPersonalPage,
  fetchRosterBySlug,
  postEnrolment,
  postLeave,
  postShiftAction,
  putEnrolment,
} from "./api";
import { choreStrings, formatCycle, formatLongDate } from "./i18n";

type Status = "loading" | "enrol" | "personal" | "enrolled" | "unavailable" | "load-failed" | "left";

const status = ref<Status>("loading");
const roster = ref<PublicRoster | null>(null);
const locale = ref<Locale>("nl");
const c = computed(() => chromeStrings(locale.value));
const ch = computed(() => choreStrings(locale.value));

const displayName = ref("");
const email = ref("");
const emailReminders = ref(false);
const picked = reactive<Record<string, boolean>>({});
const busy = ref(false);
const errorMsg = ref("");
const savedFlash = ref(false);

const personal = ref<PersonalPage | null>(null);
const savedToken = ref<string | null>(null);

const editToken = new URL(window.location.href).searchParams.get("s");

function slug(): string {
  const parts = window.location.pathname.split("/").filter(Boolean);
  return parts[parts.length - 1] ?? "";
}

const editUrl = computed(() =>
  savedToken.value ? `${window.location.origin}/c/${slug()}?s=${savedToken.value}` : "",
);

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
  emailReminders.value = page.email_reminders;
  for (const chore of chores.value) picked[chore.id] = page.enrolled_chore_ids.includes(chore.id);
}

async function enrol(): Promise<void> {
  busy.value = true;
  errorMsg.value = "";
  try {
    const ack = await postEnrolment(slug(), {
      display_name: displayName.value.trim() || null,
      email: email.value.trim() || null,
      email_reminders: emailReminders.value,
      chore_ids: chosenIds.value,
    });
    savedToken.value = ack.edit_token;
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
    const page = await putEnrolment(editToken, {
      display_name: displayName.value.trim() || null,
      chore_ids: chosenIds.value,
      email_reminders: emailReminders.value,
      email: email.value.trim() || null,
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
              </span>
              <span class="shift-actions">
                <button type="button" class="btn" :disabled="busy" @click="act(s.id, 'done')">
                  {{ ch.markDone }}
                </button>
                <button type="button" class="btn ghost" :disabled="busy" @click="act(s.id, 'handoff')">
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
      </template>

      <!-- Chore picker (both modes) -->
      <div class="card stack">
        <h2>{{ ch.chooseChores }}</h2>
        <p v-if="status === 'enrol'" class="muted">{{ ch.enrolIntro }}</p>
        <p v-if="chores.length === 0" class="muted">{{ ch.noChores }}</p>
        <label v-for="chore in chores" :key="chore.id" class="chore-check">
          <input type="checkbox" v-model="picked[chore.id]" />
          <span class="chore-label">
            <span v-if="chore.emoji" class="emoji">{{ chore.emoji }}</span>
            <strong>{{ chore.name }}</strong>
            <span class="muted days">{{ formatCycle(chore.cycle_slots, roster.period_weeks, ch) }}</span>
          </span>
        </label>
      </div>

      <!-- Name + email + reminders -->
      <div class="card stack">
        <label class="field">
          <span>{{ c.displayName }}</span>
          <input v-model="displayName" type="text" class="text-input" />
        </label>

        <details class="disclosure">
          <summary>{{ ch.emailDisclosureTitle }}</summary>
          <p class="muted">{{ ch.emailDisclosureBody }}</p>
        </details>
        <label class="field">
          <span>{{ ch.emailLabel }}</span>
          <input v-model="email" type="email" class="text-input" :placeholder="personal?.has_email ? '••••••' : ''" />
        </label>
        <label class="toggle">
          <input type="checkbox" v-model="emailReminders" />
          <span>{{ ch.emailReminders }}</span>
        </label>
      </div>

      <Disclosure :locale="locale" />

      <p v-if="errorMsg" class="error">{{ errorMsg }}</p>

      <div class="actions">
        <button v-if="status === 'enrol'" type="button" class="btn primary" :disabled="busy" @click="enrol">
          {{ ch.enrolButton }}
        </button>
        <template v-else>
          <button type="button" class="btn primary" :disabled="busy" @click="saveChanges">
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
  gap: 0.5rem;
  cursor: pointer;
}
.chore-label {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.375rem;
}
.emoji { line-height: 1; }
.days { font-size: 0.8125rem; }
.field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.field > span { font-size: 0.875rem; color: var(--brand-text-muted); }
.text-input {
  padding: 0.5rem 0.625rem;
  border: 1px solid var(--brand-border);
  border-radius: 6px;
  background: var(--brand-bg);
  color: var(--brand-text);
  font: inherit;
}
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
.actions { display: flex; gap: 0.75rem; flex-wrap: wrap; }
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
.btn.primary {
  background: var(--brand-red);
  border-color: var(--brand-red);
  color: #fff;
  font-weight: 600;
}
.btn.ghost { background: none; }
.error { color: var(--brand-red); }
</style>
