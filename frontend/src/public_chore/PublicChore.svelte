<script lang="ts">
/**
 * The public chore roster: enrol, then your own page.
 *
 * Two modes on one component. Without a token it is the enrolment form;
 * with one it is the volunteer's own page: their turns, the whole roster
 * to jump into, their away ranges, and the same chore picker.
 */
import SupportButtons from "@/public_shared/SupportButtons.svelte";
import PublicConfirmation from "@/public_shared/PublicConfirmation.svelte";
import PublicEditBar from "@/public_shared/PublicEditBar.svelte";
import PublicTopCard from "@/public_shared/PublicTopCard.svelte";
import RecoveredNotice from "@/public_shared/RecoveredNotice.svelte";
import PublicNotice from "@/public_shared/PublicNotice.svelte";
import PublicShell from "@/public_shared/PublicShell.svelte";
import DatePicker from "@/components/DatePicker.svelte";
import WeekdayGrid from "@/components/WeekdayGrid.svelte";
import RosterCalendarView, {
  type RosterAssignment,
  type RosterDay,
} from "@/components/RosterCalendarView.svelte";
import PersonalCalendar, { type CalAction, type CalEntry } from "./PersonalCalendar.svelte";
import { isValidEmail } from "@/lib/validate";
import { showToast } from "@/lib/toast";
import { resolveText } from "@/public_shared/bilingual";
import { type Locale, GITHUB_URL, chromeStrings, pickLocale } from "@/public_shared/strings";
import { useEditForm } from "@/public_shared/useEditForm.svelte";
import { useEditLink } from "@/public_shared/useEditLink.svelte";
import {
  type AvailabilityRange,
  type ChoreCalendar,
  type PersonalPage,
  type PublicRoster,
  type ShiftAction,
  ApiError,
  fetchPersonalPage,
  fetchRosterBySlug,
  fetchTokenCalendar,
  postEnrolment,
  postLeave,
  postShiftAction,
  putAvailability,
  putEnrolment,
} from "./api";
import { choreStrings } from "./i18n";

type Status = "loading" | "enrol" | "personal" | "enrolled" | "unavailable" | "load-failed" | "left";

let status = $state<Status>("loading");
let roster = $state<PublicRoster | null>(null);
let locale = $state<Locale>("nl");
const rosterTitle = $derived(roster ? resolveText(roster.name_nl, roster.name_en, locale) : null);
const rosterDescription = $derived(
  roster ? resolveText(roster.description_nl, roster.description_en, locale) : null,
);
const c = $derived(chromeStrings(locale));
const ch = $derived(choreStrings(locale));

let displayName = $state("");
let email = $state("");
// Edit mode: when a hidden email is on file, mark it for removal on save
// (leaving the field empty keeps the existing one).
let clearEmail = $state(false);
let picked = $state<Record<string, boolean>>({});
let busy = $state(false);
let errorMsg = $state("");

// Placeholder reflects the email state: hidden-on-file, being-removed, or
// none. Avoids the password-like dots.
// What the address is actually for on this roster. One that sends no
// reminders uses it once for the personal link and stores nothing, so
// the disclosure says that instead of promising a reminder.
const emailDisclosure = $derived(
  roster?.reminder_enabled === false ? ch.emailDisclosureBodyLinkOnly : ch.emailDisclosureBody,
);
const emailPlaceholder = $derived.by(() => {
  if (clearEmail) return ch.emailClearing;
  if (personal?.has_email) return ch.emailHidden;
  return ch.emailLabel;
});

let personal = $state<PersonalPage | null>(null);
let availDraft = $state<AvailabilityRange[]>([]);

function slug(): string {
  const parts = window.location.pathname.split("/").filter(Boolean);
  return parts[parts.length - 1] ?? "";
}

// Held whole, not spread: ``editUrl`` is a getter.
const link = useEditLink("c", slug);
const editToken = link.editToken;

const chores = $derived(roster?.chores ?? []);
const chosenIds = $derived(Object.keys(picked).filter((id) => picked[id]));

// --- Personal-page calendars (my schedule / up-for-grabs / covering) ---
// Each section is a month-navigable calendar over the personal payload
// (client-side; the payload is upcoming-only, so past months are empty).
function currentMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}
let myMonth = $state(currentMonth());
let helpMonth = $state(currentMonth());

function group(rows: { on_date: string; entry: CalEntry }[]): Record<string, CalEntry[]> {
  const map: Record<string, CalEntry[]> = {};
  for (const { on_date, entry } of rows) (map[on_date] ??= []).push(entry);
  return map;
}

// "Mijn taken": confirmed shifts (done/pass) + expected outlook (tentative,
// view-only).
const myEntries = $derived.by<Record<string, CalEntry[]>>(() => {
  const actions: CalAction[] = [
    { key: "done", label: ch.markDone },
    { key: "pass", label: ch.cantMakeIt, ghost: true },
  ];
  return group([
    ...(personal?.my_shifts ?? []).map((s) => ({
      on_date: s.on_date,
      entry: {
        id: s.id,
        choreName: s.chore_name,
        tentative: false,
        done: s.status === "done",
        missed: s.status === "missed",
        // Only an upcoming shift is actionable; finished ones just show.
        note: s.inherited ? ch.coveringForLeaver : undefined,
        actions: s.status === "scheduled" ? actions : undefined,
      } satisfies CalEntry,
    })),
    ...(personal?.outlook_shifts ?? []).map((s) => ({
      on_date: s.on_date,
      entry: { id: null, choreName: s.chore_name, tentative: true } satisfies CalEntry,
    })),
  ]);
});

// "Bijspringen": the whole roster (all chores/assignees, emoji + name) so a
// volunteer sees where they can jump in — including the tentative projection
// past the horizon. Fetched per month (organiser-shaped calendar).
let rosterCalendar = $state<ChoreCalendar[]>([]);
async function loadRosterCalendar(): Promise<void> {
  if (!editToken) return;
  try {
    rosterCalendar = await fetchTokenCalendar(editToken, helpMonth);
  } catch {
    rosterCalendar = [];
  }
}
// The "Bijspringen" calendar is fetched per month, so paging it reloads.
// Guarded on the month rather than run on every read: an effect fires on
// mount too, and the first load is the one ``onMounted`` already does.
let loadedMonth: string | null = null;
$effect(() => {
  if (status !== "personal" || helpMonth === loadedMonth) return;
  loadedMonth = helpMonth;
  void loadRosterCalendar();
});

const rosterDays = $derived.by<Record<string, RosterDay>>(() => {
  // A pinned assignee whose shift I may claim (open) or cover (someone
  // else's) carries an action; matched by shift id against my personal page.
  const openIds = new Set((personal?.open_shifts ?? []).map((s) => s.id));
  const coverIds = new Set((personal?.coverable_shifts ?? []).map((s) => s.id));
  const map: Record<string, RosterDay> = {};
  for (const chore of rosterCalendar ?? []) {
    for (const day of chore.days) {
      const d = (map[day.on_date] ??= { assignments: [], tentative: false, changed: false });
      if (day.tentative) d.tentative = true;
      for (const a of day.assignees) {
        let action: RosterAssignment["action"];
        if (a.shift_id && openIds.has(a.shift_id)) {
          action = { shiftId: a.shift_id, kind: "claim", label: `${chore.emoji ?? ""} ${ch.claim}`.trim() };
        } else if (a.shift_id && coverIds.has(a.shift_id)) {
          const who = a.name ? ` · ${a.name}` : "";
          action = {
            shiftId: a.shift_id,
            kind: "cover",
            label: `${chore.emoji ?? ""} ${ch.coverButton}${who}`.trim(),
          };
        }
        d.assignments.push({ emoji: chore.emoji, name: a.name, open: a.open, status: a.status, action });
      }
    }
  }
  return map;
});

// Dirty/revert/saved state for the shared edit bar.
const edit = useEditForm({
  snapshot: () => ({
    name: displayName,
    chores: [...chosenIds].sort(),
    avail: availDraft.map((r) => `${r.start}|${r.end}`),
    email: email,
    clearEmail: clearEmail,
  }),
  apply: (s) => {
    displayName = s.name;
    for (const chore of chores) picked[chore.id] = s.chores.includes(chore.id);
    availDraft = s.avail.map((pair) => {
      const [start, end] = pair.split("|");
      return { start, end };
    });
    email = s.email;
    clearEmail = s.clearEmail;
  },
});

async function load() {
  const inlined = window.__OPKOMST_CHORE__;
  if (inlined === null) {
    status = "unavailable";
    return;
  }
  try {
    const loaded = inlined ?? (await fetchRosterBySlug(slug()));
    roster = loaded;
    locale = pickLocale(loaded.locale);
    for (const chore of loaded.chores) picked[chore.id] = false;

    if (editToken) {
      const page = await fetchPersonalPage(editToken);
      hydratePersonal(page);
      edit.captureBaseline();
      status = "personal";
      void loadRosterCalendar();
    } else {
      status = "enrol";
    }
  } catch (e) {
    status = e instanceof ApiError && e.status === 410 ? "unavailable" : "load-failed";
  }
}
void load();

function hydratePersonal(page: PersonalPage): void {
  personal = page;
  displayName = page.display_name ?? "";
  email = "";
  clearEmail = false;
  for (const chore of chores) picked[chore.id] = page.enrolled_chore_ids.includes(chore.id);
  availDraft = (page.availability ?? []).map((r) => ({ ...r }));
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
  clearEmail = !clearEmail;
  if (clearEmail) email = ""; // removing wins over a typed value
}

function addAvailRange(): void {
  availDraft = [...availDraft, { start: "", end: "" }];
}

function removeAvailRange(index: number): void {
  availDraft = availDraft.filter((_, i) => i !== index);
}

/** One end of one away range, written back into the list. */
function setAvail(index: number, key: "start" | "end", value: string): void {
  availDraft = availDraft.map((r, i) => (i === index ? { ...r, [key]: value } : r));
}

// Client-side validation shared by enrol + save; specific reasons toast.
function validateForm(): boolean {
  if (roster?.name_required && !displayName.trim()) {
    showToast(c.nameRequired);
    return false;
  }
  const em = email.trim();
  if (em && !isValidEmail(em)) {
    showToast(c.invalidEmail);
    return false;
  }
  return true;
}

async function enrol(): Promise<void> {
  if (!validateForm()) return;
  busy = true;
  errorMsg = "";
  try {
    // Giving an email means reminders are on — there's no separate opt-in.
    const enteredEmail = email.trim() || null;
    const ack = await postEnrolment(slug(), {
      display_name: displayName.trim() || null,
      email: enteredEmail,
      email_reminders: enteredEmail !== null,
      chore_ids: chosenIds,
    });
    // Records the token and routes the URL onto the magic link so a
    // refresh reopens the edit page (guaranteed by useEditLink).
    link.confirmSaved(ack.edit_token);
    status = "enrolled";
  } catch (e) {
    // 409 is the roster having no places left, which the visitor can
    // understand; everything else is a failure to act.
    errorMsg = e instanceof ApiError && e.status === 409 ? c.full : ch.actionFailed;
  } finally {
    busy = false;
  }
}

async function saveChanges(): Promise<void> {
  if (!editToken) return;
  if (!validateForm()) return;
  busy = true;
  errorMsg = "";
  try {
    // One page, one save: persist the enrolment and the time-off ranges
    // together so there's a single confirmation button for everything.
    // Clearing wins; otherwise reminders stay on if an email is on file or
    // newly entered.
    const enteredEmail = clearEmail ? null : email.trim() || null;
    const keepReminders = clearEmail ? false : enteredEmail !== null || (personal?.has_email ?? false);
    await putEnrolment(editToken, {
      display_name: displayName.trim() || null,
      chore_ids: chosenIds,
      email_reminders: keepReminders,
      email: enteredEmail,
    });
    const ranges = availDraft.filter((r) => r.start && r.end);
    hydratePersonal(await putAvailability(editToken, ranges));
    void loadRosterCalendar(); // away ranges may have handed off pinned shifts
    email = ""; // one-shot add/replace; never echo it back
    edit.captureBaseline();
    edit.flashSaved();
  } catch {
    errorMsg = ch.actionFailed;
  } finally {
    busy = false;
  }
}

async function act(shiftId: string, action: ShiftAction): Promise<void> {
  if (!editToken) return;
  busy = true;
  errorMsg = "";
  try {
    personal = await postShiftAction(editToken, shiftId, action);
    void loadRosterCalendar(); // the claimed/covered slot changes hands
  } catch {
    errorMsg = ch.actionFailed;
  } finally {
    busy = false;
  }
}

async function leave(): Promise<void> {
  if (!editToken) return;
  if (!window.confirm(ch.leaveConfirm)) return;
  busy = true;
  try {
    await postLeave(editToken);
    status = "left";
  } catch {
    errorMsg = ch.actionFailed;
  } finally {
    busy = false;
  }
}
</script>

<PublicShell bind:locale>
  {#if status === "loading"}
    <PublicNotice message={c.loading} />
  {:else if status === "unavailable"}
    <PublicNotice message={c.unavailable} />
  {:else if status === "load-failed"}
    <PublicNotice message={c.loadFailed} />
  {:else if status === "left"}
    <PublicNotice message={ch.left} />
  {:else if status === "enrolled"}
    <PublicConfirmation url={link.editUrl} {locale} />
  {:else if roster && (status === "enrol" || status === "personal")}
    <PublicTopCard
      title={rosterTitle}
      imageUrl={roster.image_url}
      artist={roster.image_artist_instagram}
      creditLabel={c.imageCredit}
      descriptionHtml={rosterDescription}
    />

    <!-- Personal mode: my turns and up-for-grabs -->
    {#if status === "personal" && personal}
      <RecoveredNotice recoveredAt={personal.link_recovered_at} {locale} />
      <div class="card stack">
        <h2>{ch.myTurns}</h2>
        <div class="cal-legend muted">
          <span><i class="cal-swatch locked"></i>{ch.calLocked}</span>
          <span><i class="cal-swatch tentative"></i>{ch.calTentative}</span>
        </div>
        {#if Object.keys(myEntries).length === 0}
          <p class="empty muted">{ch.noUpcoming}</p>
        {:else}
          <PersonalCalendar
            bind:month={myMonth}
            entriesByDate={myEntries}
            weekdays={ch.weekdays}
            prevLabel={ch.prevMonth}
            nextLabel={ch.nextMonth}
            {locale}
            {busy}
            onact={act}
          />
        {/if}
      </div>

      <div class="card stack">
        <h2>{ch.helpOutHeading}</h2>
        <div class="cal-legend muted">
          <span><i class="cal-swatch locked"></i>{ch.calLocked}</span>
          <span><i class="cal-swatch tentative"></i>{ch.calTentative}</span>
          {#each chores as chore (chore.id)}
            <span class="cal-chore">
              {#if chore.emoji}<span class="cal-chore-emoji">{chore.emoji}</span>{/if}{chore.name}
            </span>
          {/each}
        </div>
        <RosterCalendarView
          bind:month={helpMonth}
          daysByIso={rosterDays}
          weekdays={ch.weekdays}
          prevLabel={ch.prevMonth}
          nextLabel={ch.nextMonth}
          {locale}
          openLabel={ch.calOpen}
          anonLabel={ch.someone}
          {busy}
          onact={(id, kind) => act(id, kind as ShiftAction)}
        />
      </div>

      <div class="card stack">
        <h2>{ch.availabilityHeading}</h2>
        <p class="muted">{ch.availabilityHint}</p>
        {#if availDraft.length === 0}
          <p class="empty muted">{ch.availabilityEmpty}</p>
        {/if}
        {#each availDraft as r, i (i)}
          <div class="list-row avail-row">
            <div class="avail-fields">
              <DatePicker
                {locale}
                modelValue={parseDate(r.start)}
                onchange={(d) => setAvail(i, "start", isoDate(d as Date | null))}
                dateFormat="dd-mm-yy"
                placeholder={ch.availabilityFrom}
                ariaLabel={ch.availabilityFrom}
                fluid
              />
              <DatePicker
                {locale}
                modelValue={parseDate(r.end)}
                onchange={(d) => setAvail(i, "end", isoDate(d as Date | null))}
                dateFormat="dd-mm-yy"
                placeholder={ch.availabilityTo}
                ariaLabel={ch.availabilityTo}
                fluid
              />
            </div>
            <button
              type="button"
              class="icon-btn"
              disabled={busy}
              aria-label={ch.availabilityRemove}
              onclick={() => removeAvailRange(i)}
            >
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <polyline points="3 6 5 6 21 6" />
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                <line x1="10" y1="11" x2="10" y2="17" />
                <line x1="14" y1="11" x2="14" y2="17" />
              </svg>
            </button>
          </div>
        {/each}
        <button type="button" class="btn-secondary avail-add" disabled={busy} onclick={addAvailRange}>
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          {ch.availabilityAdd}
        </button>
      </div>
    {/if}

    <!-- Chore picker (both modes) -->
    <div class="card stack">
      <h2>{ch.chooseChores}</h2>
      {#if status === "enrol"}<p class="muted">{ch.enrolIntro}</p>{/if}
      {#if chores.length === 0}<p class="empty muted">{ch.noChores}</p>{/if}
      {#each chores as chore (chore.id)}
        <label class="chore-check">
          <input type="checkbox" class="check" bind:checked={picked[chore.id]} />
          <span class="chore-label">
            <span class="chore-title">
              {#if chore.emoji}<span class="emoji">{chore.emoji}</span>{/if}
              <strong>{chore.name}</strong>
            </span>
            {#if chore.description}<span class="muted chore-desc">{chore.description}</span>{/if}
            {#if chore.cycle_slots.length}
              <WeekdayGrid
                cycleSlots={chore.cycle_slots}
                periodWeeks={roster.period_weeks}
                weekdayLabels={ch.weekdays}
              />
            {/if}
          </span>
        </label>
      {/each}
    </div>

    <!-- Name and email -->
    <div class="card stack">
      <input
        bind:value={displayName}
        type="text"
        class="input"
        placeholder={c.displayName}
        autocomplete="name"
      />
      <div class="email-row">
        <input
          bind:value={email}
          type="email"
          class="input"
          placeholder={emailPlaceholder}
          disabled={clearEmail}
          autocomplete="email"
        />
        {#if personal?.has_email}
          <button
            type="button"
            class="icon-btn"
            class:active={clearEmail}
            aria-label={clearEmail ? ch.emailKeep : ch.emailClear}
            onclick={toggleClearEmail}
          >
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <polyline points="3 6 5 6 21 6" />
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                <line x1="10" y1="11" x2="10" y2="17" />
                <line x1="14" y1="11" x2="14" y2="17" />
              </svg>
          </button>
        {/if}
      </div>
    </div>

    <div class="card">
      <details class="disclosure">
        <summary>{c.explainerTitle}</summary>
        <p class="muted">{emailDisclosure}</p>
        <p class="muted">
          {c.explainerBody}
          <a href={GITHUB_URL} target="_blank" rel="noopener">{c.explainerLink}</a>
        </p>
      </details>
    </div>

    {#if errorMsg}<p class="error">{errorMsg}</p>{/if}

    {#if status === "enrol"}
      <div class="submit-row">
        <SupportButtons />
        <button type="button" class="btn-primary" disabled={busy} onclick={enrol}>
          {ch.enrolButton}
        </button>
      </div>
    {:else}
      <PublicEditBar
        dirty={edit.dirty}
        saving={busy}
        justSaved={edit.justSaved}
        {locale}
        onsave={saveChanges}
        onrevert={edit.revert}
        onwithdraw={leave}
      />
    {/if}
  {/if}
</PublicShell>

<style>
.stack > * + * { margin-top: 0.75rem; }
h2 { margin: 0; font-size: 1.1rem; }
.chore-check {
  display: flex;
  align-items: center;
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
/* Calendar legend (vast / voorlopig), swatches matching the cell styles. */
.cal-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem 1rem;
  font-size: 0.8125rem;
  margin: 0 0 0.25rem;
}
.cal-legend span {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
}
.cal-swatch {
  width: 0.875rem;
  height: 0.875rem;
  border-radius: 4px;
  flex: none;
  border: 1px solid color-mix(in srgb, var(--brand-text-muted) 42%, var(--brand-border));
  background: var(--brand-surface);
}
.cal-swatch.tentative {
  border-style: dashed;
}
.cal-chore-emoji {
  font-size: 0.9375rem;
}
/* Time-off rows reuse the global ``.list-row`` (hover + rounding) from
 * theme.css, matching the admin editable lists. */
.avail-row { margin-bottom: 0.25rem; }
.avail-fields { display: flex; gap: 0.5rem; flex: 1; min-width: 0; flex-wrap: wrap; }
.avail-fields > :global(.dp) { flex: 1 1 8rem; min-width: 0; }
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
/* .submit-row (right-aligned action row) + .btn / .btn.ghost come from
 * ``form.css`` (shared so sub-components like PersonalCalendar get them). */
.error { color: var(--brand-red); }
</style>
