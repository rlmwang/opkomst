<script lang="ts">
import MonthGrid from "@/components/MonthGrid.svelte";
import BrandedSelect from "./BrandedSelect.svelte";
import SupportButtons from "@/public_shared/SupportButtons.svelte";
import PublicConfirmation from "@/public_shared/PublicConfirmation.svelte";
import PublicEditBar from "@/public_shared/PublicEditBar.svelte";
import RecoveredNotice from "@/public_shared/RecoveredNotice.svelte";
import PublicMetaRow from "@/public_shared/PublicMetaRow.svelte";
import PublicNotice from "@/public_shared/PublicNotice.svelte";
import PublicShell from "@/public_shared/PublicShell.svelte";
import PublicTopCard from "@/public_shared/PublicTopCard.svelte";
import { chromeStrings } from "@/public_shared/strings";
import { resolveText } from "@/public_shared/bilingual";
import { stripHtml } from "@/public_shared/stripHtml";
import { useEditForm } from "@/public_shared/useEditForm.svelte";
import { useEditLink } from "@/public_shared/useEditLink.svelte";
import { showToast } from "@/lib/toast";
import { mapLink } from "@/lib/map-link";
import { isValidEmail } from "@/lib/validate";
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
import { formatDate, formatTimeRange } from "@/lib/format";

const slug = window.location.pathname.replace(/^\/e\/+/, "").split(/[/?#]/)[0];
// ``?s={token}`` puts the page in booking-edit mode: fetch the whole
// booking by token, edit name + party size, and manage per-occurrence
// withdrawals. ``confirmSaved`` records the token AND routes the URL onto
// it so a refresh reopens the edit page.
// Held whole, not spread: ``editUrl`` is a getter.
const link = useEditLink("e", () => slug);
const editToken = link.editToken;
const editing = editToken !== null;

// Server-side-injected event payload (per-occurrence). Synchronous, no
// round-trip on first paint. ``null`` = unknown slug (render not-found);
// ``undefined`` = dev mode without the SPA handler → fall back to fetch.
const initial = window.__OPKOMST_EVENT__;
let event = $state<PublicEvent | null>(initial ?? null);
let notFound = $state(initial === null);
let loadFailed = $state(false);

if (initial === undefined) {
  fetchEventBySlug(slug)
    .then((e) => {
      event = e;
    })
    .catch((err) => {
      if (err instanceof ApiError && err.status === 404) {
        notFound = true;
      } else {
        loadFailed = true;
      }
    });
}

let locale = $state<Locale>(pickLocale(initial?.locale));
// Title + topic resolved to the active language with fallback; both
// depend on ``locale`` so flipping the flag re-renders them live.
const eventTitle = $derived(event ? resolveText(event.name_nl, event.name_en, locale) : null);
const eventTopic = $derived(event ? resolveText(event.topic_nl, event.topic_en, locale) : null);
// The event arriving late (dev mode has no server injection) settles the
// language, and pre-checks the landing occurrence when the form had no
// stored draft. Production injects the event synchronously, so the
// initial draft already carries ``current.id``.
let settledEvent: PublicEvent | null = null;
$effect(() => {
  const e = event;
  if (!e || e === settledEvent) return;
  settledEvent = e;
  locale = pickLocale(e.locale);
  if (!editing && !hadStoredDraft && selectedIds.length === 0 && !allUpcoming) {
    selectedIds = [e.current.id];
  }
});
const t = $derived(strings(locale));
const c = $derived(chromeStrings(locale));

// A one-off event skips the calendar picker and behaves like a plain
// single sign-up.
const isOneOff = $derived(!event?.is_recurring);

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
    occurrenceIds: initial ? [initial.current.id] : [],
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
let displayName = $state(initialDraft.displayName);
let partySize = $state(initialDraft.partySize);
let sourceChoice = $state<string | null>(initialDraft.sourceChoice);
let helpChoices = $state<string[]>(initialDraft.helpChoices);
let email = $state(initialDraft.email);
// Checked occurrence ids + the "all upcoming" shortcut.
let selectedIds = $state<string[]>(initialDraft.occurrenceIds);
let allUpcoming = $state(initialDraft.allUpcoming);

// The draft, written on every change so a refresh on flaky mobile does
// not empty the form. Reading each field is what subscribes the effect
// to it.
$effect(() => {
  const draft: Draft = {
    displayName,
    partySize,
    sourceChoice,
    helpChoices: [...helpChoices],
    email,
    occurrenceIds: [...selectedIds],
    allUpcoming,
  };
  try {
    sessionStorage.setItem(draftKey, JSON.stringify(draft));
  } catch { /* ignore quota / private-mode */ }
});
function clearDraft() {
  try { sessionStorage.removeItem(draftKey); } catch { /* ignore */ }
}

let submitting = $state(false);
let submitted = $state(false);
let withdrawn = $state(false);
let errorMsg = $state<string | null>(null);

// --- booking edit mode ---------------------------------------------
let booking = $state<Booking | null>(null);
let recoveredAt = $state<string | null>(null);

// Dirty/revert/saved state for the shared edit bar (edit mode only).
const edit = useEditForm({
  // Dirty tracks name, party size, AND the future session selection, so the
  // edit bar's Save/Revert cover calendar changes too.
  snapshot: () => ({
    name: displayName,
    party: partySize,
    sessions: [...selectedIds].sort().join(","),
  }),
  apply: (s) => {
    displayName = s.name;
    partySize = s.party;
    selectedIds = s.sessions ? s.sessions.split(",") : [];
  },
});

// The booking's future sessions (pre-selection) vs its past sessions (frozen
// history, shown locked on the calendar).
function bookedFutureIds(b: Booking): string[] {
  return b.occurrences.filter((o) => !o.is_past).map((o) => o.occurrence_id);
}
const pastBookedIsos = $derived(
  new Set((booking?.occurrences ?? []).filter((o) => o.is_past).map((o) => o.starts_at.slice(0, 10))),
);

if (editing) {
  fetchBooking(editToken!)
    .then((b) => {
      booking = b;
      recoveredAt = b.link_recovered_at ?? null;
      displayName = b.display_name ?? "";
      partySize = b.party_size;
      locale = pickLocale(b.locale);
      selectedIds = bookedFutureIds(b);
      allUpcoming = false;
      edit.captureBaseline();
    })
    .catch((err) => {
      if (err instanceof ApiError && (err.status === 404 || err.status === 410)) {
        notFound = true;
      } else {
        loadFailed = true;
      }
    });
}

// The landing occurrence and its date/time.
const current = $derived(event?.current ?? null);

// Session badge for one occurrence ("sessie i van N", or "sessie i" for
// an open-ended series).
function sessionBadge(index: number): string {
  const count = event?.total_sessions ?? null;
  return count === null ? t.sessionOpen(index + 1) : t.sessionOf(index + 1, count);
}

function toggleOccurrence(id: string, on: boolean) {
  if (on) {
    if (!selectedIds.includes(id)) selectedIds = [...selectedIds, id];
  } else {
    selectedIds = selectedIds.filter((x) => x !== id);
  }
}

// --- calendar date picker (recurring events) -----------------------
const isoDate = (dt: string) => dt.slice(0, 10);
const upcomingByIso = $derived.by(() => {
  const m = new Map<string, PublicEvent["upcoming"][number]>();
  for (const o of event?.upcoming ?? []) m.set(isoDate(o.starts_at), o);
  return m;
});
const projectedIsos = $derived(new Set((event?.projected ?? []).map((p) => isoDate(p.starts_at))));
// ``selectedIds`` is the single source of truth in both modes; the calendar
// just reflects it. The "select all" toggle is opt-in vs opt-out: flipping
// it seeds the selection (all / just the landing date), then the visitor
// adds or deselects individual days on top of that.
const upcomingIds = $derived((event?.upcoming ?? []).map((o) => o.id));
const selectedIsos = $derived.by(() => {
  const s = new Set<string>();
  for (const o of event?.upcoming ?? []) {
    if (selectedIds.includes(o.id)) s.add(isoDate(o.starts_at));
  }
  return s;
});
/** The select-all toggle is opt-in against opt-out: flipping it seeds
 *  the selection (all, or just the landing date), and the visitor adds
 *  or deselects individual days on top of that. A plain effect would
 *  also fire on the initial read and wipe a restored draft, so this is a
 *  handler on the switch rather than a watcher on the value. */
function onAllUpcoming(on: boolean) {
  allUpcoming = on;
  if (on) {
    selectedIds = [...upcomingIds];
  } else {
    // Off: sign-up falls back to the landing date; manage deselects every
    // future session (past ones are frozen and unaffected).
    selectedIds = editing ? [] : current ? [current.id] : [];
  }
}

// Monday-first short weekday labels, locale-aware — no extra i18n keys.
const weekdayLabels = $derived.by(() => {
  const fmt = new Intl.DateTimeFormat(locale === "en" ? "en-GB" : "nl-NL", { weekday: "short" });
  return [...Array(7)].map((_, i) => fmt.format(new Date(2024, 0, 1 + i))); // 2024-01-01 is a Monday
});

// Which month the picker shows: whatever the visitor paged to, and
// until then the month the landing date is in. ``MonthGrid`` binds it
// through a getter and a setter, because the value read is derived and
// the value written is the state behind it.
let pickerMonth = $state<string | null>(null);
const shownMonth = $derived(
  pickerMonth ?? isoDate(current?.starts_at ?? new Date().toISOString()).slice(0, 7),
);

function dayClass(iso: string): Record<string, boolean> {
  return {
    "has-occurrence": upcomingByIso.has(iso),
    selected: selectedIsos.has(iso),
    projected: projectedIsos.has(iso),
    // Past sessions this booking attended: shown locked (manage mode only).
    attended: pastBookedIsos.has(iso),
  };
}
// Every available date is toggleable in both modes (opt-in adds, opt-out
// deselects) — never locked.
const dayClickable = (iso: string) => upcomingByIso.has(iso);
function onDayClick(iso: string) {
  const occ = upcomingByIso.get(iso);
  if (occ) toggleOccurrence(occ.id, !selectedIds.includes(occ.id));
}

// The reminder shown behind the select-all toggle depends on the mode.
const reminder = $derived(allUpcoming ? t.reminderOptOut : t.reminderOptIn);

// --- email transparency --------------------------------------------
interface EmailUseBullet {
  text: string;
  previewUrl: string;
}
// Only the channels this event actually sends. A switched-off channel
// has no preview to link to and no use to disclose, so it isn't named:
// the same rule the source and help questions follow.
const emailUseBullets = $derived.by<EmailUseBullet[]>(() => {
  const e = event;
  if (!e) return [];
  const bullets: EmailUseBullet[] = [];
  if (e.reminder_enabled) {
    bullets.push({ text: t.emailUses.reminder, previewUrl: `/api/v1/event/by-slug/${slug}/email-preview/reminder` });
  }
  if (e.feedback_enabled) {
    bullets.push({ text: t.emailUses.feedback, previewUrl: `/api/v1/event/by-slug/${slug}/email-preview/feedback` });
  }
  return bullets;
});

// With every channel off, nothing would ever read the address, so the
// form doesn't ask for it and the disclosure says nothing about it.
// With one of the two on, the placeholder names that one rather than
// promising mail this event will never send.
// The two sentences that mention the address are joined here rather
// than in the template, where Vue would eat the space between them.
const asksEmail = $derived(emailUseBullets.length > 0);
const explainerOpening = $derived(
  asksEmail ? `${t.explainerIntro} ${t.explainerEmailIntro}` : t.explainerIntro,
);
const emailPlaceholder = $derived.by(() => {
  const e = event;
  if (!e) return "";
  if (e.reminder_enabled && e.feedback_enabled) return t.emailPlaceholder.both;
  return e.reminder_enabled ? t.emailPlaceholder.reminder : t.emailPlaceholder.feedback;
});
const explainerClosing = $derived(
  asksEmail ? `${t.explainerEmailOutro} ${t.explainerSource}` : t.explainerSource,
);

// --- add-to-calendar dropdown (native ``<details>`` for the popup) ---
const calLinks = $derived.by(() => {
  const e = event;
  if (!e) return null;
  const enc = encodeURIComponent;
  const utc = (iso: string) =>
    new Date(iso).toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");
  const publicUrl = `${window.location.origin}/e/${e.current.slug}`;
  const desc = [stripHtml(eventTopic ?? ""), publicUrl].filter(Boolean).join("\n\n");
  const ics = `/api/v1/event/by-slug/${e.current.slug}/event.ics`;
  const google =
    `https://calendar.google.com/calendar/render?action=TEMPLATE` +
    `&text=${enc(eventTitle ?? "")}` +
    `&dates=${utc(e.current.starts_at)}/${utc(e.current.ends_at)}` +
    `&details=${enc(desc)}` +
    (e.location ? `&location=${enc(e.location)}` : "");
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
  if (Number.isFinite(n)) partySize = Math.min(50, Math.max(1, n));
}
function normalisePartySize(ev: FocusEvent) {
  let n = partySize;
  if (typeof n !== "number" || !Number.isFinite(n) || n < 1) n = 1;
  else n = Math.min(50, Math.max(1, Math.floor(n)));
  partySize = n;
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
  errorMsg = null;
  if (!event) return;
  const trimmedName = displayName.trim();
  if (event.name_required && !trimmedName) {
    showToast(c.nameRequired);
    return;
  }
  const trimmedEmail = email.trim();
  if (trimmedEmail && !isValidEmail(trimmedEmail)) {
    showToast(c.invalidEmail);
    return;
  }
  // One-off: the single current occurrence is implied.
  const ids = isOneOff ? [event.current.id] : selectedIds;
  // Opt-out with nothing deselected → let the server resolve "every future
  // occurrence" (robust to a stale page). Any deselection, or opt-in, sends
  // the explicit picks.
  const fullOptOut =
    allUpcoming && upcomingIds.length > 0 && upcomingIds.every((id) => ids.includes(id));
  if (!isOneOff && !fullOptOut && ids.length === 0) {
    showToast(t.pickSession);
    return;
  }
  submitting = true;
  try {
    const ack = await postSignup(event.current.slug, {
      display_name: trimmedName || null,
      party_size: partySize,
      // Only answers to questions this page is actually asking. A
      // saved draft can outlive the organiser switching one off, and
      // the API refuses an answer to a question that isn't asked.
      source_choice: event.source_options.length > 0 ? sourceChoice : null,
      help_choices: event.help_options.length > 0 ? helpChoices : [],
      email: trimmedEmail || null,
      occurrence_ids: fullOptOut ? [] : ids,
      all_upcoming: fullOptOut,
    });
    link.confirmSaved(ack.edit_token);
    submitted = true;
    clearDraft();
  } catch (e) {
    // 409 is the one refusal a visitor can understand and act on: the
    // event has no places left. Everything else is a failure to submit.
    errorMsg = e instanceof ApiError && e.status === 409 ? c.full : t.submitFail;
  } finally {
    submitting = false;
  }
}

async function saveBooking() {
  errorMsg = null;
  const trimmedName = displayName.trim();
  if (event?.name_required && !trimmedName) {
    showToast(c.nameRequired);
    return;
  }
  submitting = true;
  try {
    let b = await putBooking(editToken!, {
      display_name: trimmedName || null,
      party_size: partySize,
    });
    // Recurring event: also persist the future session selection from the
    // calendar (one-off has no editable session set).
    if (!isOneOff) {
      const fullOptOut =
        allUpcoming && upcomingIds.length > 0 && upcomingIds.every((id) => selectedIds.includes(id));
      b = await putBookingOccurrences(editToken!, {
        occurrence_ids: fullOptOut ? [] : selectedIds,
        all_upcoming: fullOptOut,
      });
      selectedIds = bookedFutureIds(b);
      allUpcoming = false;
    }
    booking = b;
    edit.captureBaseline();
    edit.flashSaved();
  } catch {
    errorMsg = t.submitFail;
  } finally {
    submitting = false;
  }
}

async function withdrawAll() {
  if (!editing) return;
  const confirmation = asksEmail
    ? `${t.withdrawConfirm} ${t.pendingMailWarning}`
    : t.withdrawConfirm;
  if (!window.confirm(confirmation)) return;
  submitting = true;
  try {
    await withdrawBooking(editToken!);
    withdrawn = true;
  } catch {
    errorMsg = t.submitFail;
  } finally {
    submitting = false;
  }
}

$effect(() => {
  document.title = eventTitle ? `${eventTitle} · opkomst.nu` : "opkomst.nu";
});
</script>

<PublicShell bind:locale hideAds={submitted || withdrawn}>
  {#if loadFailed}
    <PublicNotice message={c.loadFailed} />
  {:else if notFound}
    <PublicNotice message={c.unavailable} />
  {:else if withdrawn}
    <PublicNotice message={t.withdrawn} />
  {:else if event?.archived}
    <PublicNotice title={eventTitle ?? undefined} message={c.unavailable} />
  {:else}
    {#if !submitted}
      <PublicTopCard
        title={eventTitle}
        imageUrl={event?.image_url ?? null}
        artist={event?.image_artist_instagram ?? null}
        creditLabel={t.imageCredit}
        descriptionHtml={eventTopic}
      >
        {#snippet meta()}
          {#if event && current}
            <PublicMetaRow>
              {#snippet icon()}<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>{/snippet}
              {formatDate(current.starts_at, locale)}
              {#if !isOneOff}<span class="session-tag">{sessionBadge(current.index)}</span>{/if}
            </PublicMetaRow>
            <PublicMetaRow>
              {#snippet icon()}<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>{/snippet}
              {formatTimeRange(current.starts_at, current.ends_at, locale)}
            </PublicMetaRow>
            {#if event.location}
              <PublicMetaRow
                href={mapLink({ location: event.location, latitude: event.latitude, longitude: event.longitude })}
              >
                {#snippet icon()}<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>{/snippet}
                {event.location}
              </PublicMetaRow>
            {/if}
          {/if}
        {/snippet}

        {#snippet actions()}
          {#if event && calLinks}
            <div class="event-actions">
              <details class="cal">
                <summary class="cal-button">
                  <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/><line x1="12" y1="14" x2="12" y2="20"/><line x1="9" y1="17" x2="15" y2="17"/></svg>
                  {t.addToCalendar}
                </summary>
                <ul class="cal-menu" role="menu">
                  <li role="none"><a href={calLinks.google} target="_blank" rel="noopener" role="menuitem">Google</a></li>
                  <li role="none"><a href={calLinks.ics} role="menuitem">{t.calIcs}</a></li>
                </ul>
              </details>
            </div>
          {/if}
        {/snippet}
      </PublicTopCard>
    {/if}

    <!-- Privacy and open-source disclosure (create mode). -->
    {#if event && !editing && !submitted}
      <div class="card privacy-card">
        <details>
          <summary>{t.explainerTitle}</summary>
          <p class="privacy-body">{explainerOpening}</p>
          {#if asksEmail}
            <ul class="privacy-bullets">
              {#each emailUseBullets as b (b.previewUrl)}
                <li>
                  <a href={b.previewUrl} target="_blank" rel="noopener" class="meta-link">
                    {b.text}
                    <svg class="external" viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
                  </a>
                </li>
              {/each}
            </ul>
          {/if}
          <p class="privacy-body">
            {explainerClosing}
            <a href="https://github.com/rlmwang/opkomst" target="_blank" rel="noopener">{t.explainerLink}</a>.
          </p>
        </details>
      </div>
    {/if}

    <!-- Thanks screen (create-mode submit): a single confirmation card,
         nothing else, so saving the secret link stands alone. -->
    {#if submitted}
      <PublicConfirmation url={link.editUrl} {locale} />
    {/if}

    <!-- ================= CREATE MODE ================= -->
    {#if event && !editing && !submitted}
      <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
      <form
        class="card stack signup-form"
        novalidate
        onsubmit={(e) => { e.preventDefault(); void submit(); }}
        onkeydown={onFormKeydown}
      >
        <h2>{t.essentialsTitle}</h2>

        <section class="form-section">
          <input
            bind:value={displayName}
            type="text"
            class="input"
            placeholder={t.displayName}
            autocomplete="name"
          />
          <div class="number-field">
            <button type="button" class="num-step" aria-label="−" disabled={partySize <= 1} onclick={() => (partySize = Math.max(1, (partySize || 1) - 1))}>−</button>
            <input
              value={partySize}
              type="number"
              class="input num-input"
              min="1"
              max="50"
              step="1"
              inputmode="numeric"
              placeholder={t.partySize}
              onbeforeinput={(e) => onPartyBeforeInput(e as InputEvent)}
              oninput={onPartyInput}
              onblur={(e) => normalisePartySize(e as FocusEvent)}
            />
            <button type="button" class="num-step" aria-label="+" disabled={partySize >= 50} onclick={() => (partySize = Math.min(50, (partySize || 0) + 1))}>+</button>
          </div>
        </section>

        <!-- Multi-occurrence calendar picker (hidden for a one-off). Pick
             the sessions you want, or flip the toggle to take every
             upcoming one at once. -->
        {#if !isOneOff}
          <section class="form-section session-section">
            <h2>{t.sessionsTitle}</h2>
            <p class="muted picker-explainer">{t.pickerExplainer}</p>
          <label class="all-upcoming-row">
            <input
              type="checkbox"
              role="switch"
              class="switch"
              checked={allUpcoming}
              onchange={(e) => onAllUpcoming((e.currentTarget as HTMLInputElement).checked)}
            />
            <span class="all-upcoming-label">{t.allUpcoming}</span>
          </label>
          <p class="muted picker-reminder">{reminder}</p>
          <MonthGrid
            bind:month={() => shownMonth, (v) => (pickerMonth = v)}
            {locale}
            weekdays={weekdayLabels}
            {dayClass}
            clickable={dayClickable}
            prevLabel={t.prevMonth}
            nextLabel={t.nextMonth}
            ondayClick={onDayClick}
          />
          </section>
        {/if}

        {#if event.help_options.length > 0}
          <section class="form-section help-section">
            <h2 id="help-heading">{t.helpHeading}</h2>
            <div class="help-choices" role="group" aria-labelledby="help-heading">
              {#each event.help_options as opt (opt)}
                <label class="help-row">
                  <input type="checkbox" bind:group={helpChoices} value={opt} />
                  <span>{opt}</span>
                </label>
              {/each}
            </div>
          </section>
        {/if}

        <!-- Both fields here are optional and independently switchable:
             no source options means the organiser switched that question
             off, and no enabled mail channel means nothing would ever
             read an address. With neither, the whole block goes. -->
        {#if event.source_options.length > 0 || asksEmail}
          <hr class="section-divider" />

          <h2>{t.feedbackTitle}</h2>

          <section class="form-section">
            {#if event.source_options.length > 0}
              <BrandedSelect
                bind:value={sourceChoice}
                options={event.source_options}
                placeholder={t.sourcePlaceholder}
                ariaLabel={t.sourcePlaceholder}
              />
            {/if}
            {#if asksEmail}
              <input
                bind:value={email}
                type="email"
                class="input"
                placeholder={emailPlaceholder}
                autocomplete="email"
              />
            {/if}
          </section>
        {/if}

        {#if errorMsg}<p class="error" role="alert">{errorMsg}</p>{/if}

        <div class="submit-row">
          <SupportButtons />
          <button type="submit" class="btn-primary" disabled={submitting} aria-busy={submitting}>
            <span class="btn-label" class:hidden={submitting}>{t.submit}</span>
            {#if submitting}
              <span class="btn-spinner" aria-hidden="true">
                <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
                  <circle cx="12" cy="12" r="9" stroke-opacity="0.25"/>
                  <path d="M21 12a9 9 0 0 0-9-9"/>
                </svg>
              </span>
            {/if}
          </button>
        </div>
      </form>
    {/if}

    <!-- ================= EDIT MODE (booking) ================= -->
    {#if editing && !submitted}
      <RecoveredNotice {recoveredAt} {locale} />

      {#if booking}
        <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
        <form
          class="card stack signup-form"
          novalidate
          onsubmit={(e) => { e.preventDefault(); void saveBooking(); }}
          onkeydown={onFormKeydown}
        >
          <h2>{t.essentialsTitle}</h2>
          <section class="form-section">
            <input bind:value={displayName} type="text" class="input" placeholder={t.displayName} autocomplete="name" />
            <div class="number-field">
            <button type="button" class="num-step" aria-label="−" disabled={partySize <= 1} onclick={() => (partySize = Math.max(1, (partySize || 1) - 1))}>−</button>
            <input
              value={partySize}
              type="number"
              class="input num-input"
              min="1"
              max="50"
              step="1"
              inputmode="numeric"
              placeholder={t.partySize}
              onbeforeinput={(e) => onPartyBeforeInput(e as InputEvent)}
              oninput={onPartyInput}
              onblur={(e) => normalisePartySize(e as FocusEvent)}
            />
            <button type="button" class="num-step" aria-label="+" disabled={partySize >= 50} onclick={() => (partySize = Math.min(50, (partySize || 0) + 1))}>+</button>
          </div>
          </section>

          <!-- Manage sessions: the same calendar and toggle as sign-up,
               pre-filled with the booking. Past sessions show locked
               (attended); future ones are added or deselected freely. -->
          {#if event && !isOneOff}
            <section class="form-section session-section">
              <h2>{t.bookingSessions}</h2>
              <p class="muted picker-explainer">{t.pickerExplainer}</p>
          <label class="all-upcoming-row">
            <input
              type="checkbox"
              role="switch"
              class="switch"
              checked={allUpcoming}
              onchange={(e) => onAllUpcoming((e.currentTarget as HTMLInputElement).checked)}
            />
            <span class="all-upcoming-label">{t.allUpcoming}</span>
          </label>
          <p class="muted picker-reminder">{reminder}</p>
          <MonthGrid
            bind:month={() => shownMonth, (v) => (pickerMonth = v)}
            {locale}
            weekdays={weekdayLabels}
            {dayClass}
            clickable={dayClickable}
            prevLabel={t.prevMonth}
            nextLabel={t.nextMonth}
            ondayClick={onDayClick}
          />
            </section>
          {/if}

          {#if errorMsg}<p class="error" role="alert">{errorMsg}</p>{/if}
        </form>

        <PublicEditBar
          canEdit={event?.answers_editable ?? true}
          dirty={edit.dirty}
          saving={submitting}
          justSaved={edit.justSaved}
          {locale}
          onsave={saveBooking}
          onrevert={edit.revert}
          onwithdraw={withdrawAll}
        />
      {/if}
    {/if}
  {/if}
</PublicShell>

<style>
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
  appearance: none;
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
.cal-button:hover { border-color: var(--brand-text-muted); }
.cal[open] .cal-button {
  border-color: var(--brand-text-muted);
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
  appearance: none;
  margin: 0;
}
.num-input {
  -moz-appearance: textfield;
  appearance: textfield;
}

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
