<script lang="ts" module>
/** One answer offered by a sign-up question. ``id`` is the server's,
 *  and absent on one the organiser has just typed. */
export interface EventOption {
  id?: string | null;
  label: string;
}

/** The seeded options in another language, each keeping the id it
 *  already had.
 *
 *  Translating is a rename: the sign-ups that named an option point at
 *  its row, so carrying the id across is what keeps them attached.
 *  Returning the seeded rows as they come would drop every id and turn
 *  a language switch into deleting each option and adding a new one,
 *  which takes the answers with it. */
export function translated(current: EventOption[], seeded: EventOption[]): EventOption[] {
  return seeded.map((option, i) => ({ ...option, id: current[i]?.id ?? null }));
}
</script>

<script lang="ts">
import { untrack } from "svelte";

import AppButton from "@/components/AppButton.svelte";
import AppInput from "@/components/AppInput.svelte";
import AdvancedFold from "@/components/AdvancedFold.svelte";
import FormSection from "@/components/FormSection.svelte";
import CycleGridPicker from "@/components/CycleGridPicker.svelte";
import DatePicker from "@/components/DatePicker.svelte";
import EditableList from "@/components/EditableList.svelte";
import FormPageShell from "@/components/FormPageShell.svelte";
import ImageField from "@/components/ImageField.svelte";
import LocationPicker from "@/components/LocationPicker.svelte";
import NumberStepper from "@/components/NumberStepper.svelte";
import RichTextField from "@/components/RichTextField.svelte";
import SelectField from "@/components/SelectField.svelte";
import StartAccountField from "@/components/StartAccountField.svelte";
import StartedPanel from "@/components/StartedPanel.svelte";
import { bilingualField } from "@/composables/useBilingualField.svelte";
import { chaptersQuery, sortedChapters } from "@/composables/useChapters.svelte";
import { events, updateEvent } from "@/composables/useEvents.svelte";
import { formDraft } from "@/composables/useFormDraft.svelte";
import { locationField } from "@/composables/useLocationField.svelte";
import { startMode } from "@/composables/useStartMode.svelte";
import { loadLocale, locale, t, te, tIn } from "@/i18n.svelte";
import { ApiError, firstFieldError } from "@/api/client";
import { go, route } from "@/router/navigation.svelte";
import { useToasts } from "@/lib/toasts";
import { auth } from "@/stores/auth.svelte";

/**
 * Making or changing an event: when it is, where, and which of the
 * optional questions the sign-up form asks.
 */
const { eventId }: { eventId?: string } = $props();

const toasts = useToasts();
// Opened from the root's tiles by somebody with no account: an address
// field on top, no chapter picker, and the start endpoint as the
// target. ``hasChapters`` is false for a personal account too, signed
// in or not, because it has none to pick from.
const start = startMode("event");
const chapters = chaptersQuery({ enabled: () => start.hasChapters });
const create = events.create();
const update = updateEvent();

const isEdit = $derived(Boolean(eventId));
const query = events.single(
  () => eventId ?? "",
  { enabled: () => Boolean(eventId) },
);

let imageUrl = $state<string | null>(null);
let imageField = $state<ReturnType<typeof ImageField> | null>(null);

// The chapter this event goes in. The options are the organiser's own
// memberships, admins included: the rule constrains everyone, which is
// fewer decisions and fewer misclicks.
let chapterId = $state<string | null>(null);
const chapterOptions = $derived.by(() => {
  const mine = new Set((auth.user?.chapters ?? []).map((c) => c.id));
  return sortedChapters(chapters.data).filter((c) => mine.has(c.id));
});

// The address, its coordinates, and the city the geocoder looks near.
// The bias reads the chapters list rather than the copy on the session,
// so a chapter given a city mid-session works without signing in again.
const place = locationField(
  () => chapterId,
  () => sortedChapters(chapters.data),
);

let nameNl = $state("");
let nameEn = $state("");
let topicNl = $state("");
let topicEn = $state("");
const title = bilingualField(
  () => ({ nl: nameNl, en: nameEn }),
  (next) => {
    nameNl = next.nl;
    nameEn = next.en;
  },
);
const body = bilingualField(
  () => ({ nl: topicNl, en: topicEn }),
  (next) => {
    topicNl = next.nl;
    topicEn = next.en;
  },
);

function timeAt(hours: number): Date {
  const d = new Date();
  d.setHours(hours, 0, 0, 0);
  return d;
}

let eventDate = $state<Date | null>(null);
// Most events run in the evening, so the times start at 20:00 and
// 22:00 and the organiser only picks a date. The date part of these two
// is never read: ``combine`` merges them with the picked date at save.
let startTime = $state<Date | null>(timeAt(20));
let endTime = $state<Date | null>(timeAt(22));

// --- How often it comes round ----------------------------------------
//
// The date and time above fix the first session and the time of day.
// ``repeats`` reveals the rest, in one of two kinds. A pattern is a
// cycle of ``periodWeeks``, the weekday grid inside it, and how it ends:
// after a number of weeks, after a number of times, on a date, or not at
// all. Picked dates are the dates themselves, chosen on the date
// planner's calendar, and the first of them is the start. A one-off is
// ``repeats === false``. The 90-day materialisation window has no
// control; it is fixed at save.
let repeats = $state(false);
type RepeatKind = "pattern" | "picked";
let repeatKind = $state<RepeatKind>("pattern");
let pickedDates = $state<Date[]>([]);
let periodWeeks = $state(1);
let cycleSlots = $state<number[]>([]);
type EndKind = "weeks" | "sessions" | "date" | "open";
let endKind = $state<EndKind>("weeks");
let spanWeeks = $state(6);
let spanSessions = $state(6);
let spanUntil = $state<Date | null>(null);

// A shorter cycle cannot hold the later weekday offsets, so they go,
// and the payload never carries a slot the cycle has no room for.
let lastPeriod = 1;
$effect(() => {
  const next = periodWeeks;
  const prev = lastPeriod;
  lastPeriod = next;
  if (next >= prev) return;
  const hi = 7 * next;
  cycleSlots = cycleSlots.filter((s) => s < hi);
});

/** Switching to picked dates starts the calendar on the date above. */
function setRepeatKind(next: RepeatKind): void {
  repeatKind = next;
  if (next === "picked" && pickedDates.length === 0 && eventDate) pickedDates = [eventDate];
}

const byPattern = $derived(repeats && repeatKind === "pattern");
const byPicked = $derived(repeats && repeatKind === "picked");
const wirePeriodWeeks = $derived(byPattern ? Math.max(1, Math.floor(periodWeeks || 1)) : 1);
const wireCycleSlots = $derived(byPattern ? cycleSlots : []);
const wireSpanWeeks = $derived<number | null>(
  byPattern && endKind === "weeks" ? Math.max(1, Math.floor(spanWeeks || 1)) : null,
);
const wireSpanSessions = $derived<number | null>(
  byPattern && endKind === "sessions" ? Math.max(1, Math.floor(spanSessions || 1)) : null,
);
const sortedPicked = $derived([...pickedDates].sort((a, b) => a.getTime() - b.getTime()));

// Both catalogues, because the defaults are seeded in the event's own
// language and the organiser may be reading the other one. Only the one
// on screen is loaded by the time this page mounts, and the switch that
// needs the other is one click away.
void loadLocale("nl");
void loadLocale("en");

/** Ordered by how often they actually happen at a grassroots event:
 *  word of mouth dominates, posters are the long tail. */
/**
 * An option somebody can pick on the public form.
 *
 * It carries an id once it has been saved, because an answer points at
 * the row and not at the words: renaming "Flyer" to "Folder" has to
 * keep the people who picked it. A new one has no id yet, and the
 * server gives it one.
 */
interface EventOption {
  id?: string | null;
  label: string;
}

function defaultSources(loc: "nl" | "en"): EventOption[] {
  return [
    { label: tIn(loc, "event.sourceDefaults.wordOfMouth") },
    { label: tIn(loc, "event.sourceDefaults.socialMedia") },
    { label: tIn(loc, "event.sourceDefaults.flyer") },
    { label: tIn(loc, "event.sourceDefaults.poster") },
  ];
}

function defaultHelp(loc: "nl" | "en"): EventOption[] {
  return [
    { label: tIn(loc, "event.helpDefaults.setup") },
    { label: tIn(loc, "event.helpDefaults.teardown") },
  ];
}

/** The same words in the same order. Ids are not compared: what makes
 *  a list "still the default one" is what it says. */
function sameLabels(a: EventOption[], b: EventOption[]): boolean {
  return a.length === b.length && a.every((o, i) => o.label === b[i].label);
}

const startLocale: "nl" | "en" = locale() === "en" ? "en" : "nl";

// The two optional questions on the public form, each with its own
// switch. Off means the question is not asked at all; the options stay
// where they are, so switching one back on brings the organiser's own
// list back rather than an empty one.
let sources = $state<EventOption[]>(defaultSources(startLocale));
let newSource = $state("");
let sourceEnabled = $state(false);
let helpOptions = $state<EventOption[]>(defaultHelp(startLocale));
let newHelp = $state("");
let helpEnabled = $state(false);

/** Stored without the ``@``. The schema strips one if it is there, so
 *  pasting a handle works either way. */
let imageArtistInstagram = $state("");
let feedbackEnabled = $state(false);
let reminderEnabled = $state(false);
let listed = $state(false);
let nameRequired = $state(false);
let answersEditable = $state(true);

/* The switched sections are folded away behind one summary. A new event
 * is a name, a date, a place and a picture; everything in the fold is a
 * choice most events never make, and a row of switches in front of
 * somebody filling in their first one reads as decisions they have to
 * take before they can save.
 *
 * Closed on arrival, always: an organiser opens it when they are
 * looking for a setting, and a form that decides for itself when to
 * unfold is a form whose length changes for reasons nobody asked for. */
let eventLocale = $state<"nl" | "en">(startLocale);
let submitting = $state(false);
// Armed by a 409 and spent on the next Save. Removing an option people
// already answered destroys those answers, so the server refuses once
// with a count and the second Save is the organiser confirming
// (``docs/design-question-edits.md``).
let confirmDestructive = $state(false);

// Flipping the event's language swaps the seeded options with it, but
// only while they are still the seeded ones. An organiser who has added
// or removed one has thought about the wording, and that is not ours to
// overwrite.
//
// Translating keeps each option's id, so it is a rename and the
// sign-ups that named it stay attached (``translated``, above).
let lastEventLocale = startLocale;
$effect(() => {
  const next = eventLocale;
  const prev = lastEventLocale;
  if (next === prev) return;
  lastEventLocale = next;
  if (sameLabels(sources, defaultSources(prev))) sources = translated(sources, defaultSources(next));
  if (sameLabels(helpOptions, defaultHelp(prev))) {
    helpOptions = translated(helpOptions, defaultHelp(next));
  }
});

// --- Times on the wire ------------------------------------------------
//
// The backend stores the date and both times as wall clock: the
// organiser types 18:00, 18:00 goes up, and the email says 18:00. No
// zone, ever. ``sv-SE`` is the locale that formats as YYYY-MM-DD and
// HH:MM:SS.
function dateFromString(ymd: string): Date {
  const [y, m, d] = ymd.split("-").map(Number);
  return new Date(y, m - 1, d);
}

function timeFromString(hms: string): Date {
  const [h, m] = hms.split(":").map(Number);
  const d = new Date();
  d.setHours(h, m, 0, 0);
  return d;
}

function combine(date: Date, time: Date): Date {
  const d = new Date(date);
  d.setHours(time.getHours(), time.getMinutes(), 0, 0);
  return d;
}

const naiveDate = (d: Date) => d.toLocaleDateString("sv-SE");
const naiveTime = (d: Date) => d.toLocaleTimeString("sv-SE");

// --- The draft --------------------------------------------------------
interface EventFormDraft {
  nameNl: string;
  nameEn: string;
  chapterId: string | null;
  topicNl: string;
  topicEn: string;
  location: string;
  latitude: number | null;
  longitude: number | null;
  eventDate: string | null;
  startTime: string | null;
  endTime: string | null;
  repeats: boolean;
  repeatKind: RepeatKind;
  pickedDates: string[];
  periodWeeks: number;
  cycleSlots: number[];
  endKind: EndKind;
  spanWeeks: number;
  spanSessions: number;
  spanUntil: string | null;
  sources: EventOption[];
  newSource: string;
  sourceEnabled: boolean;
  helpOptions: EventOption[];
  newHelp: string;
  helpEnabled: boolean;
  feedbackEnabled: boolean;
  reminderEnabled: boolean;
  listed: boolean;
  eventLocale: "nl" | "en";
  imageArtistInstagram: string;
}

function snapshot(): EventFormDraft {
  return {
    nameNl,
    nameEn,
    chapterId,
    topicNl,
    topicEn,
    location: place.location,
    latitude: place.latitude,
    longitude: place.longitude,
    eventDate: eventDate?.toISOString() ?? null,
    startTime: startTime?.toISOString() ?? null,
    endTime: endTime?.toISOString() ?? null,
    repeats,
    repeatKind,
    pickedDates: pickedDates.map((d) => d.toISOString()),
    periodWeeks,
    cycleSlots: [...cycleSlots],
    endKind,
    spanWeeks,
    spanSessions,
    spanUntil: spanUntil?.toISOString() ?? null,
    sources: sources.map((o) => ({ ...o })),
    newSource,
    sourceEnabled,
    helpOptions: helpOptions.map((o) => ({ ...o })),
    newHelp,
    helpEnabled,
    feedbackEnabled,
    reminderEnabled,
    listed,
    eventLocale,
    imageArtistInstagram,
  };
}

function applyDraft(d: EventFormDraft): void {
  nameNl = d.nameNl ?? "";
  nameEn = d.nameEn ?? "";
  chapterId = d.chapterId ?? null;
  topicNl = d.topicNl ?? "";
  topicEn = d.topicEn ?? "";
  place.set(d.location, d.latitude, d.longitude);
  eventDate = d.eventDate ? new Date(d.eventDate) : null;
  startTime = d.startTime ? new Date(d.startTime) : null;
  endTime = d.endTime ? new Date(d.endTime) : null;
  repeats = d.repeats ?? false;
  repeatKind = d.repeatKind ?? "pattern";
  pickedDates = (d.pickedDates ?? []).map((iso) => new Date(iso));
  periodWeeks = d.periodWeeks ?? 1;
  cycleSlots = [...(d.cycleSlots ?? [])];
  endKind = d.endKind ?? "weeks";
  spanWeeks = d.spanWeeks ?? 6;
  spanSessions = d.spanSessions ?? 6;
  spanUntil = d.spanUntil ? new Date(d.spanUntil) : null;
  sources = (d.sources ?? []).map((o) => ({ ...o }));
  newSource = d.newSource;
  sourceEnabled = d.sourceEnabled ?? false;
  helpOptions = (d.helpOptions ?? []).map((o) => ({ ...o }));
  newHelp = d.newHelp ?? "";
  helpEnabled = d.helpEnabled ?? false;
  feedbackEnabled = d.feedbackEnabled;
  reminderEnabled = d.reminderEnabled ?? false;
  listed = d.listed ?? false;
  eventLocale = d.eventLocale ?? "nl";
  imageArtistInstagram = d.imageArtistInstagram ?? "";
}

const draft = formDraft<EventFormDraft>({
  key: () => `event-form-draft:${eventId ?? "new"}`,
  snapshot,
  track: snapshot,
});

let draftRestored = false;
function restoreDraftOnce(): void {
  if (draftRestored) return;
  draftRestored = true;
  const saved = draft.load();
  if (saved) applyDraft(saved);
}

// The event arrives, its values go in, and anything half-typed goes on
// top: a draft is newer than what was saved.
let seeded: unknown = undefined;
$effect(() => {
  const existing = query.data;
  if (!existing || existing === seeded) return;
  seeded = existing;
  nameNl = existing.name_nl ?? "";
  nameEn = existing.name_en ?? "";
  chapterId = existing.chapter_id ?? null;
  topicNl = existing.topic_nl ?? "";
  topicEn = existing.topic_en ?? "";
  place.set(existing.location, existing.latitude, existing.longitude);
  eventDate = dateFromString(existing.starts_on);
  startTime = timeFromString(existing.start_time);
  endTime = timeFromString(existing.end_time);
  // The recurrence rule, read back onto the controls.
  repeats = existing.cycle_slots.length > 0 || existing.picked_dates.length > 0;
  repeatKind = existing.picked_dates.length > 0 ? "picked" : "pattern";
  pickedDates = existing.picked_dates.map(dateFromString);
  periodWeeks = existing.period_weeks;
  lastPeriod = existing.period_weeks;
  cycleSlots = [...existing.cycle_slots];
  endKind =
    existing.span_weeks !== null
      ? "weeks"
      : existing.span_sessions !== null
        ? "sessions"
        : existing.span_until !== null
          ? "date"
          : "open";
  spanWeeks = existing.span_weeks ?? 6;
  spanSessions = existing.span_sessions ?? 6;
  spanUntil = existing.span_until ? dateFromString(existing.span_until) : null;
  sources = existing.source_options.map((o) => ({ ...o }));
  sourceEnabled = existing.source_enabled;
  helpOptions = existing.help_options.map((o) => ({ ...o }));
  helpEnabled = existing.help_enabled;
  feedbackEnabled = existing.feedback_enabled;
  nameRequired = existing.name_required;
  answersEditable = existing.answers_editable;
  reminderEnabled = existing.reminder_enabled;
  listed = existing.listed;
  eventLocale = existing.locale;
  lastEventLocale = existing.locale;
  imageUrl = existing.image_url;
  imageArtistInstagram = existing.image_artist_instagram ?? "";
  restoreDraftOnce();
});

// An id that is not this organiser's event, said once. The form stays
// on screen empty rather than swapped for a card, because in edit mode
// there is nothing else to put there.
let toldNotFound = false;
$effect(() => {
  if (!query.error || toldNotFound) return;
  toldNotFound = true;
  toasts.error(t("event.notFound"));
});

// A new event: the chapter is the one the organiser came from, or the
// only one they are in. Read once, at mount.
untrack(() => {
  if (isEdit) return;
  const fromQuery = route.query.get("chapter");
  const mine = new Set((auth.user?.chapters ?? []).map((c) => c.id));
  if (fromQuery && mine.has(fromQuery)) chapterId = fromQuery;
  else if (auth.user?.chapters?.length === 1) chapterId = auth.user.chapters[0].id;
  restoreDraftOnce();
});

// --- The two option lists ---------------------------------------------
function addSource(): void {
  const label = newSource.trim();
  if (!label || sources.some((o) => o.label === label)) return;
  // No id: the server mints one, and from then on the option keeps its
  // answers through a rename.
  sources.push({ label });
  newSource = "";
}

function addHelp(): void {
  const label = newHelp.trim();
  if (!label || helpOptions.some((o) => o.label === label)) return;
  helpOptions.push({ label });
  newHelp = "";
}

// --- Leaving, and saving ----------------------------------------------
function cancel(): void {
  draft.clear();
  if (start.cancel()) return;
  // Editing goes back to the details page, creating to the list, so the
  // way back is predictable rather than whatever the history holds.
  void go(isEdit && eventId ? `/event/${eventId}/details` : "/event");
}

async function submit(): Promise<void> {
  // The title is required in the event's own language.
  const primaryName = (eventLocale === "en" ? nameEn : nameNl).trim();
  if (!primaryName) {
    toasts.warn(t("event.fillName"));
    return;
  }
  if (byPicked && pickedDates.length === 0) {
    toasts.warn(t("event.repeat.fillDates"));
    return;
  }
  // Picked dates carry their own first date; the field above only seeds them.
  const firstDate = byPicked ? sortedPicked[0] : eventDate;
  if (!firstDate) {
    toasts.warn(t("event.fillDate"));
    return;
  }
  if (!startTime) {
    toasts.warn(t("event.fillStartTime"));
    return;
  }
  if (!endTime) {
    toasts.warn(t("event.fillEndTime"));
    return;
  }
  // A question being asked needs something to pick; one switched off
  // needs nothing.
  if (sourceEnabled && sources.length === 0) {
    toasts.warn(t("event.fillSources"));
    return;
  }
  if (helpEnabled && helpOptions.length === 0) {
    toasts.warn(t("event.fillHelp"));
    return;
  }
  if (start.hasChapters && !chapterId) {
    toasts.warn(t("event.fillChapter"));
    return;
  }
  if (start.active && !start.validate()) return;

  const startsAt = combine(firstDate, startTime);
  const endsAt = combine(firstDate, endTime);
  if (endsAt <= startsAt) {
    toasts.warn(t("event.endAfterStart"));
    return;
  }
  if (byPattern && wireCycleSlots.length === 0) {
    toasts.warn(t("event.fillCycleSlots"));
    return;
  }
  if (byPattern && endKind === "date") {
    if (!spanUntil) {
      toasts.warn(t("event.span.fillUntil"));
      return;
    }
    if (naiveDate(spanUntil) < naiveDate(firstDate)) {
      toasts.warn(t("event.span.untilAfterStart"));
      return;
    }
  }

  submitting = true;
  try {
    const payload = {
      name_nl: nameNl.trim() || null,
      name_en: nameEn.trim() || null,
      chapter_id: start.chapterFor(chapterId),
      topic_nl: topicNl.trim() || null,
      topic_en: topicEn.trim() || null,
      location: place.location.trim() || null,
      latitude: place.latitude,
      longitude: place.longitude,
      starts_on: naiveDate(firstDate),
      start_time: naiveTime(startTime),
      end_time: naiveTime(endTime),
      period_weeks: wirePeriodWeeks,
      cycle_slots: wireCycleSlots,
      picked_dates: byPicked ? sortedPicked.map(naiveDate) : [],
      span_weeks: wireSpanWeeks,
      span_sessions: wireSpanSessions,
      span_until: byPattern && endKind === "date" && spanUntil ? naiveDate(spanUntil) : null,
      horizon_days: 90,
      source_options: sources,
      source_enabled: sourceEnabled,
      help_options: helpOptions,
      help_enabled: helpEnabled,
      feedback_enabled: feedbackEnabled,
      reminder_enabled: reminderEnabled,
      name_required: nameRequired,
      answers_editable: answersEditable,
      listed,
      locale: eventLocale,
      image_artist_instagram: imageArtistInstagram.trim() || null,
      confirm_destructive: confirmDestructive,
    };

    if (start.active) {
      // No session, so no details page to land on and no image to put
      // on the new row: the public link in the answer is the whole
      // result. A refusal has already been explained, and the draft
      // stays so the visitor can act on it and try again.
      if (await start.submit(payload)) draft.clear();
      return;
    }

    const result =
      isEdit && eventId
        ? await update.run({ eventId, payload })
        : await create.run(payload);
    // An image held while the row did not exist yet goes up now.
    await imageField?.flushPendingUpload(result.id);
    draft.clear();
    void go(`/event/${result.id}/details`);
  } catch (err) {
    // Nearly everything is caught above. A field-level refusal that
    // still gets through, a paste over the length cap say, is named in
    // the organiser's own language rather than in Pydantic's English.
    // The one refusal the organiser can answer: this save would delete
    // answers people gave, and the server says how many.
    if (err instanceof ApiError && err.status === 409) {
      confirmDestructive = true;
      toasts.error(err.message);
      return;
    }
    const fe = firstFieldError(err);
    const label = fe && te(`event.fields.${fe.field}`) ? t(`event.fields.${fe.field}`) : null;
    if (fe && label && fe.type === "string_too_long" && fe.limit != null) {
      toasts.error(t("event.tooLong", { field: label, max: fe.limit }));
    } else if (fe && label) {
      toasts.error(t("event.invalidField", { field: label }));
    } else {
      toasts.error(t("event.saveFailed"));
    }
  } finally {
    submitting = false;
  }
}
</script>

{#if start.started}
  <StartedPanel started={start.started} email={start.email} />
{:else}
  <FormPageShell
    title={isEdit ? t("event.editTitle") : t("event.newTitle")}
    submitLabel={isEdit ? t("event.save") : t("event.create")}
    {submitting}
    onsubmit={submit}
    oncancel={cancel}
  >
    <FormSection anchor="form.section.first">
      {#if start.active}<StartAccountField bind:value={start.email} />{/if}
      <AppInput bind:value={title.value} placeholder={title.fallback || t("event.name")} fluid />
      <RichTextField
        bind:value={body.value}
        placeholder={t("event.topic")}
        fallbackHtml={body.fallback || null}
      />
      {#if start.hasChapters}
        <SelectField
          bind:value={chapterId}
          options={chapterOptions}
          optionLabel="name"
          optionValue="id"
          placeholder={t("event.chapter")}
          disabled={chapterOptions.length === 1 && chapterId !== null}
          fluid
        />
      {/if}
      <LocationPicker
        bind:value={place.location}
        latitude={place.latitude}
        longitude={place.longitude}
        biasLat={place.bias.lat}
        biasLon={place.bias.lon}
        oncoords={(coords) => place.setCoords(coords)}
      />
      <DatePicker
        bind:modelValue={eventDate}
        locale={locale()}
        dateFormat="dd-mm-yy"
        placeholder={t("event.date")}
        fluid
      />
      <div class="time-row">
        <DatePicker
          bind:modelValue={startTime}
          locale={locale()}
          timeOnly
          hourFormat="24"
          stepMinute={15}
          placeholder={t("event.startTime")}
          fluid
        />
        <DatePicker
          bind:modelValue={endTime}
          locale={locale()}
          timeOnly
          hourFormat="24"
          stepMinute={15}
          placeholder={t("event.endTime")}
          fluid
        />
      </div>
    </FormSection>

    <!-- Uploading a picture writes to the row it belongs to, which
         takes a session; a visitor starting from the root does not have
         one yet. They add it after signing in through the link they
         were mailed. -->
    {#if !start.active}
      <ImageField
        bind:this={imageField}
        resource="event"
        entityId={eventId ?? null}
        bind:imageUrl
        bind:artist={imageArtistInstagram}
      />
    {/if}

    <!-- The agenda this lists on is a chapter's. An account with no
         chapters has no agenda to be on, so there is no choice to
         offer. -->
    {#if start.hasChapters}
      <FormSection
        heading={t("event.listedToggle")}
        bind:enabled={listed}
        explainer={t("event.listedHelp")}
      />
    {/if}

    <!-- Everything else with a switch on it lives in here. A
         ``details`` and not a button plus a branch: it is a disclosure,
         the browser already knows how to open and close one, and it
         tells a screen reader so without any aria of ours. -->
    <AdvancedFold>
      <FormSection
        heading={t("event.repeatHeading")}
        bind:enabled={repeats}
        explainer={t("event.repeatExplainer")}
        anchor="form.fold.first"
      >
        {#if repeats}
          <SelectField
            bind:value={() => repeatKind, setRepeatKind}
            options={[
              { value: "pattern", label: t("event.repeat.byPattern") },
              { value: "picked", label: t("event.repeat.byPicked") },
            ]}
            optionLabel="label"
            optionValue="value"
            fluid
          />
          {#if repeatKind === "picked"}
            <DatePicker
              bind:modelValue={pickedDates}
              locale={locale()}
              selectionMode="multiple"
              inline
              manualInput={false}
            />
          {:else}
            <div class="repeat-row">
              <span class="muted">{t("event.repeat.everyLead")}</span>
              <NumberStepper
                bind:value={periodWeeks}
                min={1}
                max={8}
                ariaLabel={t("event.repeat.everyWeeks")}
              />
              <span class="muted">{t("event.repeat.everyTrail")}</span>
            </div>

            <CycleGridPicker bind:value={cycleSlots} {periodWeeks} />

            <SelectField
              bind:value={endKind}
              options={[
                { value: "weeks", label: t("event.span.byWeeks") },
                { value: "sessions", label: t("event.span.bySessions") },
                { value: "date", label: t("event.span.byDate") },
                { value: "open", label: t("event.span.openEnded") },
              ]}
              optionLabel="label"
              optionValue="value"
              fluid
            />
            {#if endKind === "weeks"}
              <div class="repeat-row">
                <NumberStepper
                  bind:value={spanWeeks}
                  min={1}
                  max={104}
                  ariaLabel={t("event.span.weeks")}
                />
                <span class="muted">{t("event.span.weeksTrail")}</span>
              </div>
            {:else if endKind === "sessions"}
              <div class="repeat-row">
                <NumberStepper
                  bind:value={spanSessions}
                  min={1}
                  max={104}
                  ariaLabel={t("event.span.sessions")}
                />
                <span class="muted">{t("event.span.sessionsTrail")}</span>
              </div>
            {:else if endKind === "date"}
              <DatePicker
                bind:modelValue={spanUntil}
                locale={locale()}
                dateFormat="dd-mm-yy"
                placeholder={t("event.span.until")}
                fluid
              />
            {:else}
              <p class="muted section-explainer">{t("event.span.openEndedHelp")}</p>
            {/if}
          {/if}
        {/if}
      </FormSection>

      <!-- What people can offer comes before where they heard about it:
           one is about the event itself, the other is about us. -->
      <FormSection
        heading={t("event.helpHeading")}
        bind:enabled={helpEnabled}
        explainer={t("event.helpExplainer")}
      >
        {#if helpEnabled}
          <EditableList
            items={helpOptions}
            itemLabel={(o) => o.label}
            itemKey={(o) => o.id ?? o.label}
            onremove={(o) => helpOptions.splice(helpOptions.indexOf(o), 1)}
          >
            {#snippet add()}
              <AppInput
                bind:value={newHelp}
                placeholder={t("event.newHelp")}
                fluid
                onkeydown={(e: KeyboardEvent) => {
                  if (e.key !== "Enter") return;
                  e.preventDefault();
                  addHelp();
                }}
              />
              <AppButton
                type="button"
                icon="plus"
                size="small"
                severity="secondary"
                ariaLabel={t("event.newHelp")}
                onclick={addHelp}
              />
            {/snippet}
          </EditableList>
        {/if}
      </FormSection>

      <FormSection
        heading={t("event.sourcesHeading")}
        bind:enabled={sourceEnabled}
        explainer={t("event.sourcesExplainer")}
      >
        {#if sourceEnabled}
          <EditableList
            items={sources}
            itemLabel={(o) => o.label}
            itemKey={(o) => o.id ?? o.label}
            onremove={(o) => sources.splice(sources.indexOf(o), 1)}
          >
            {#snippet add()}
              <AppInput
                bind:value={newSource}
                placeholder={t("event.newSource")}
                fluid
                onkeydown={(e: KeyboardEvent) => {
                  if (e.key !== "Enter") return;
                  e.preventDefault();
                  addSource();
                }}
              />
              <AppButton
                type="button"
                icon="plus"
                size="small"
                severity="secondary"
                ariaLabel={t("event.newSource")}
                onclick={addSource}
              />
            {/snippet}
          </EditableList>
        {/if}
      </FormSection>

      <!-- Mailing the people who sign up is the paid plan
           (docs/design-paywall.md). Hidden, not disabled: a switch
           somebody cannot use is an advertisement on every form they
           fill in. -->
      {#if auth.participantMail}
        <FormSection
          heading={t("event.reminderToggle")}
          bind:enabled={reminderEnabled}
          explainer={t("event.reminderHelp")}
        />

        <FormSection
          heading={t("event.questionnaireToggle")}
          bind:enabled={feedbackEnabled}
          explainer={t("event.questionnaireHelp")}
        />
      {/if}

      <!-- Off by default: a name real or not is what the contract
           offers, so an empty box is an answer. On when the sign-ups
           are only useful attached to somebody. -->
      <FormSection
        heading={t("common.nameRequired")}
        bind:enabled={nameRequired}
        explainer={t("common.nameRequiredExplainer")}
      />

      <!-- A sign-up nobody can correct becomes a sign-up nobody cancels
           either, so this starts on. Off when the headcount is being
           acted on and has to stop moving. -->
      <FormSection
        heading={t("form.edit.editableHeading")}
        bind:enabled={answersEditable}
        explainer={t("form.edit.editableExplainer")}
      />
    </AdvancedFold>

    <FormSection heading={t("event.localeHeading")} explainer={t("event.localeExplainer")}>
      <SelectField
        bind:value={eventLocale}
        options={[
          { value: "nl", label: t("event.localeNl") },
          { value: "en", label: t("event.localeEn") },
        ]}
        optionLabel="label"
        optionValue="value"
        fluid
      />
    </FormSection>
  </FormPageShell>
{/if}

<style>
/* The shared form chrome lives in ``src/assets/forms.css``, and the
 * footer belongs to ``FormPageShell``. Only the event's own rules are
 * here. */
.time-row {
  display: flex;
  gap: 0.5rem;
}
.time-row > :global(*) {
  flex: 1;
}
/* A stepper with a word on either side: "elke … weken". */
.repeat-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}
</style>
