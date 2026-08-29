<script lang="ts">
import { untrack } from "svelte";

import AppButton from "@/components/AppButton.svelte";
import AppInput from "@/components/AppInput.svelte";
import AppToggle from "@/components/AppToggle.svelte";
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
import { firstFieldError } from "@/api/client";
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
// ``repeats`` reveals the rest: a cycle of ``periodWeeks``, the weekday
// grid inside it, and how long it runs for, unless it is open ended. A
// one-off is ``repeats === false``, which is an empty weekday grid. The
// 90-day materialisation window has no control; it is fixed at save.
let repeats = $state(false);
let periodWeeks = $state(1);
let cycleSlots = $state<number[]>([]);
let spanWeeks = $state(6);
let openEnded = $state(false);

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

const wirePeriodWeeks = $derived(repeats ? Math.max(1, Math.floor(periodWeeks || 1)) : 1);
const wireCycleSlots = $derived(repeats ? cycleSlots : []);
const wireSpanWeeks = $derived<number | null>(
  !repeats || openEnded ? null : Math.max(1, Math.floor(spanWeeks || 1)),
);

// Both catalogues, because the defaults are seeded in the event's own
// language and the organiser may be reading the other one. Only the one
// on screen is loaded by the time this page mounts, and the switch that
// needs the other is one click away.
void loadLocale("nl");
void loadLocale("en");

/** Ordered by how often they actually happen at a grassroots event:
 *  word of mouth dominates, posters are the long tail. */
function defaultSources(loc: "nl" | "en"): string[] {
  return [
    tIn(loc, "event.sourceDefaults.wordOfMouth"),
    tIn(loc, "event.sourceDefaults.socialMedia"),
    tIn(loc, "event.sourceDefaults.flyer"),
    tIn(loc, "event.sourceDefaults.poster"),
  ];
}

function defaultHelp(loc: "nl" | "en"): string[] {
  return [tIn(loc, "event.helpDefaults.setup"), tIn(loc, "event.helpDefaults.teardown")];
}

function arraysEqual(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((v, i) => v === b[i]);
}

const startLocale: "nl" | "en" = locale() === "en" ? "en" : "nl";

// The two optional questions on the public form, each with its own
// switch. Off means the question is not asked at all; the options stay
// where they are, so switching one back on brings the organiser's own
// list back rather than an empty one.
let sources = $state<string[]>(defaultSources(startLocale));
let newSource = $state("");
let sourceEnabled = $state(false);
let helpOptions = $state<string[]>(defaultHelp(startLocale));
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
let advancedOpen = $state(false);
let eventLocale = $state<"nl" | "en">(startLocale);
let submitting = $state(false);

// Flipping the event's language swaps the seeded options with it, but
// only while they are still the seeded ones. An organiser who has added
// or removed one has thought about the wording, and that is not ours to
// overwrite.
let lastEventLocale = startLocale;
$effect(() => {
  const next = eventLocale;
  const prev = lastEventLocale;
  if (next === prev) return;
  lastEventLocale = next;
  if (arraysEqual(sources, defaultSources(prev))) sources = defaultSources(next);
  if (arraysEqual(helpOptions, defaultHelp(prev))) helpOptions = defaultHelp(next);
});

// --- Times on the wire ------------------------------------------------
//
// The backend stores the date and both times as wall clock: the
// organiser types 18:00, 18:00 goes up, and the email says 18:00. No
// zone, ever. ``sv-SE`` is the locale that formats as YYYY-MM-DD and
// HH:MM:SS.
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
  periodWeeks: number;
  cycleSlots: number[];
  spanWeeks: number;
  openEnded: boolean;
  sources: string[];
  newSource: string;
  sourceEnabled: boolean;
  helpOptions: string[];
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
    periodWeeks,
    cycleSlots: [...cycleSlots],
    spanWeeks,
    openEnded,
    sources: [...sources],
    newSource,
    sourceEnabled,
    helpOptions: [...helpOptions],
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
  periodWeeks = d.periodWeeks ?? 1;
  cycleSlots = [...(d.cycleSlots ?? [])];
  spanWeeks = d.spanWeeks ?? 6;
  openEnded = d.openEnded ?? false;
  sources = [...d.sources];
  newSource = d.newSource;
  sourceEnabled = d.sourceEnabled ?? false;
  helpOptions = [...(d.helpOptions ?? [])];
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
  const [y, m, d] = existing.starts_on.split("-").map(Number);
  eventDate = new Date(y, m - 1, d);
  startTime = timeFromString(existing.start_time);
  endTime = timeFromString(existing.end_time);
  // The recurrence rule, read back onto the controls.
  repeats = existing.cycle_slots.length > 0;
  periodWeeks = existing.period_weeks;
  lastPeriod = existing.period_weeks;
  cycleSlots = [...existing.cycle_slots];
  openEnded = existing.span_weeks === null;
  spanWeeks = existing.span_weeks ?? 6;
  sources = [...existing.source_options];
  sourceEnabled = existing.source_enabled;
  helpOptions = [...existing.help_options];
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
  const v = newSource.trim();
  if (!v || sources.includes(v)) return;
  sources.push(v);
  newSource = "";
}

function addHelp(): void {
  const v = newHelp.trim();
  if (!v || helpOptions.includes(v)) return;
  helpOptions.push(v);
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
  if (!eventDate) {
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

  const startsAt = combine(eventDate, startTime);
  const endsAt = combine(eventDate, endTime);
  if (endsAt <= startsAt) {
    toasts.warn(t("event.endAfterStart"));
    return;
  }
  if (repeats && wireCycleSlots.length === 0) {
    toasts.warn(t("event.fillCycleSlots"));
    return;
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
      starts_on: naiveDate(eventDate),
      start_time: naiveTime(startTime),
      end_time: naiveTime(endTime),
      period_weeks: wirePeriodWeeks,
      cycle_slots: wireCycleSlots,
      span_weeks: wireSpanWeeks,
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
    <section class="form-section">
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
    </section>

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
      <section class="form-section">
        <label class="toggle-row" for="listedToggle">
          <AppToggle bind:checked={listed} inputId="listedToggle" />
          <h2 class="section-heading">{t("event.listedToggle")}</h2>
        </label>
        <p class="muted section-explainer">{t("event.listedHelp")}</p>
      </section>
    {/if}

    <!-- Everything else with a switch on it lives in here. A
         ``details`` and not a button plus a branch: it is a disclosure,
         the browser already knows how to open and close one, and it
         tells a screen reader so without any aria of ours. -->
    <details
      class="advanced"
      open={advancedOpen}
      ontoggle={(e) => (advancedOpen = (e.target as HTMLDetailsElement).open)}
    >
      <summary>{advancedOpen ? t("common.advancedHide") : t("common.advancedShow")}</summary>

      <section class="form-section">
        <!-- The switch turns the whole block on, so it sits in front of
             the heading rather than on a line of its own under it. -->
        <label class="toggle-row" for="repeatToggle">
          <AppToggle bind:checked={repeats} inputId="repeatToggle" />
          <h2 class="section-heading">{t("event.repeatHeading")}</h2>
        </label>
        <p class="muted section-explainer">{t("event.repeatExplainer")}</p>

        {#if repeats}
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

          <p class="muted section-explainer">{t("event.repeat.gridExplainer")}</p>
          <CycleGridPicker bind:value={cycleSlots} {periodWeeks} />

          <label class="toggle-row">
            <AppToggle bind:checked={openEnded} />
            <span class="toggle-label">{t("event.span.openEnded")}</span>
          </label>
          {#if !openEnded}
            <div class="repeat-row">
              <span class="muted">{t("event.span.forLead")}</span>
              <NumberStepper
                bind:value={spanWeeks}
                min={1}
                max={104}
                ariaLabel={t("event.span.weeks")}
              />
              <span class="muted">{t("event.span.weeksTrail")}</span>
            </div>
          {:else}
            <p class="muted section-explainer">{t("event.span.openEndedHelp")}</p>
          {/if}
        {/if}
      </section>

      <!-- What people can offer comes before where they heard about it:
           one is about the event itself, the other is about us. -->
      <section class="form-section">
        <label class="toggle-row" for="helpToggle">
          <AppToggle bind:checked={helpEnabled} inputId="helpToggle" />
          <h2 class="section-heading">{t("event.helpHeading")}</h2>
        </label>
        <p class="muted section-explainer">{t("event.helpExplainer")}</p>
        {#if helpEnabled}
          <EditableList
            items={helpOptions}
            itemLabel={(s: string) => s}
            itemKey={(s: string) => s}
            onremove={(s: string) => helpOptions.splice(helpOptions.indexOf(s), 1)}
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
      </section>

      <section class="form-section">
        <label class="toggle-row" for="sourcesToggle">
          <AppToggle bind:checked={sourceEnabled} inputId="sourcesToggle" />
          <h2 class="section-heading">{t("event.sourcesHeading")}</h2>
        </label>
        <p class="muted section-explainer">{t("event.sourcesExplainer")}</p>
        {#if sourceEnabled}
          <EditableList
            items={sources}
            itemLabel={(s: string) => s}
            itemKey={(s: string) => s}
            onremove={(s: string) => sources.splice(sources.indexOf(s), 1)}
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
      </section>

      <!-- Mailing the people who sign up is the paid plan
           (docs/design-paywall.md). Hidden, not disabled: a switch
           somebody cannot use is an advertisement on every form they
           fill in. -->
      {#if auth.participantMail}
        <section class="form-section">
          <label class="toggle-row" for="reminderToggle">
            <AppToggle bind:checked={reminderEnabled} inputId="reminderToggle" />
            <h2 class="section-heading">{t("event.reminderToggle")}</h2>
          </label>
          <p class="muted section-explainer">{t("event.reminderHelp")}</p>
        </section>

        <section class="form-section">
          <label class="toggle-row" for="questionnaireToggle">
            <AppToggle bind:checked={feedbackEnabled} inputId="questionnaireToggle" />
            <h2 class="section-heading">{t("event.questionnaireToggle")}</h2>
          </label>
          <p class="muted section-explainer">{t("event.questionnaireHelp")}</p>
        </section>
      {/if}

      <!-- Off by default: a name real or not is what the contract
           offers, so an empty box is an answer. On when the sign-ups
           are only useful attached to somebody. -->
      <section class="form-section">
        <label class="toggle-row" for="nameRequiredToggle">
          <AppToggle bind:checked={nameRequired} inputId="nameRequiredToggle" />
          <h2 class="section-heading">{t("common.nameRequired")}</h2>
        </label>
        <p class="muted section-explainer">{t("common.nameRequiredExplainer")}</p>
      </section>

      <!-- A sign-up nobody can correct becomes a sign-up nobody cancels
           either, so this starts on. Off when the headcount is being
           acted on and has to stop moving. -->
      <section class="form-section">
        <label class="toggle-row" for="editableToggle">
          <AppToggle bind:checked={answersEditable} inputId="editableToggle" />
          <h2 class="section-heading">{t("form.edit.editableHeading")}</h2>
        </label>
        <p class="muted section-explainer">{t("form.edit.editableExplainer")}</p>
      </section>
    </details>

    <section class="form-section">
      <h2 class="section-heading">{t("event.localeHeading")}</h2>
      <p class="muted section-explainer">{t("event.localeExplainer")}</p>
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
    </section>
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
