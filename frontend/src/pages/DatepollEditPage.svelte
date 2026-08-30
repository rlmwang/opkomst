<script lang="ts">
import { untrack } from "svelte";

import AppCard from "@/components/AppCard.svelte";
import AppHeader from "@/components/AppHeader.svelte";
import AppInput from "@/components/AppInput.svelte";
import AppToggle from "@/components/AppToggle.svelte";
import DatePicker from "@/components/DatePicker.svelte";
import FormPageShell from "@/components/FormPageShell.svelte";
import ImageField from "@/components/ImageField.svelte";
import LocationPicker from "@/components/LocationPicker.svelte";
import RichTextField from "@/components/RichTextField.svelte";
import SelectField from "@/components/SelectField.svelte";
import StartAccountField from "@/components/StartAccountField.svelte";
import StartedPanel from "@/components/StartedPanel.svelte";
import TimeRangeAdder from "@/components/TimeRangeAdder.svelte";
import RouterLink from "@/router/RouterLink.svelte";
import { bilingualField } from "@/composables/useBilingualField.svelte";
import { chaptersQuery, sortedChapters } from "@/composables/useChapters.svelte";
import {
  type DatepollCreate,
  type DatepollUpdate,
  datepolls,
} from "@/composables/useDatepolls.svelte";
import { formDraft } from "@/composables/useFormDraft.svelte";
import { locationField } from "@/composables/useLocationField.svelte";
import { startMode } from "@/composables/useStartMode.svelte";
import { locale, t } from "@/i18n.svelte";
import { ApiError } from "@/api/client";
import { localeTag } from "@/lib/format";
import { go, route } from "@/router/navigation.svelte";
import { useToasts } from "@/lib/toasts";
import { auth } from "@/stores/auth.svelte";

/**
 * Making or changing a date poll: which days are on offer, and at what
 * times on each of them.
 *
 * A day with no times is a whole day. Times can be set once for every
 * day and then switched off on the days they do not hold for, which is
 * how "every evening at 19:00 except the 14th" is two clicks rather
 * than one row per day.
 */
const { datepollId }: { datepollId?: string } = $props();

const toasts = useToasts();
const start = startMode("datepoll");
const chapters = chaptersQuery({ enabled: () => start.hasChapters });
const create = datepolls.create();
const update = datepolls.update();

const isEdit = $derived(Boolean(datepollId));
const query = datepolls.single(
  () => datepollId ?? "",
  { enabled: () => Boolean(datepollId) },
);
const notFound = $derived(query.error instanceof ApiError && query.error.status === 404);

let chapterId = $state<string | null>(null);
const chapterOptions = $derived.by(() => {
  const mine = new Set((auth.user?.chapters ?? []).map((c) => c.id));
  return sortedChapters(chapters.data).filter((c) => mine.has(c.id));
});

// A restored chapter the organiser cannot actually assign goes: a draft
// saved before the database was reseeded carries an id no chapter has
// any more, which the select cannot display and the save would refuse.
$effect(() => {
  const opts = chapterOptions;
  if (chapterId && opts.length && !opts.some((c) => c.id === chapterId)) {
    chapterId = opts.length === 1 ? opts[0].id : null;
  }
});

const place = locationField(
  () => chapterId,
  () => sortedChapters(chapters.data),
);

let nameNl = $state("");
let nameEn = $state("");
let descNl = $state("");
let descEn = $state("");
const title = bilingualField(
  () => ({ nl: nameNl, en: nameEn }),
  (next) => {
    nameNl = next.nl;
    nameEn = next.en;
  },
);
const body = bilingualField(
  () => ({ nl: descNl, en: descEn }),
  (next) => {
    descNl = next.nl;
    descEn = next.en;
  },
);
let imageUrl = $state<string | null>(null);
let imageArtistInstagram = $state("");
let imageField = $state<ReturnType<typeof ImageField> | null>(null);
let pollLocale = $state<"nl" | "en">(locale() === "en" ? "en" : "nl");
let nameRequired = $state(false);
let answersEditable = $state(true);
/* The switches sit behind one fold, the same one every other edit page
 * ends with, and it starts closed every time. */
let advancedOpen = $state(false);
let submitting = $state(false);

interface TimeSlot {
  start: string;
  end: string;
}

/** The days on offer. */
let selectedDates = $state<Date[]>([]);
/** A day's own times, keyed by date. A day that is absent here is a
 *  whole day. */
let slots = $state<Record<string, TimeSlot[]>>({});
/** Times that hold for every day on offer. They show on each day's card
 *  and merge into the payload; a day's own times are extras on top. */
let commonSlots = $state<TimeSlot[]>([]);
/** Which of the common times are switched off, per day. That is how
 *  "every day at 19:00 except the 14th" stays one time and one
 *  exception. */
let excluded = $state<Record<string, string[]>>({});

// --- Dates -----------------------------------------------------------
//
// A date on the wire is a whole calendar day, so it is built from the
// local year, month and day and never crosses midnight in UTC on the
// way.
function toISODate(d: Date): string {
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${month}-${day}`;
}

function fromISODate(iso: string): Date {
  return new Date(`${iso}T00:00:00`);
}

const sortedISODates = $derived([...selectedDates].map(toISODate).sort());

function removeDate(iso: string): void {
  selectedDates = selectedDates.filter((d) => toISODate(d) !== iso);
  delete slots[iso];
  delete excluded[iso];
}

// A day taken off the calendar takes its times with it.
$effect(() => {
  const live = new Set(sortedISODates);
  for (const iso of Object.keys(slots)) if (!live.has(iso)) delete slots[iso];
  for (const iso of Object.keys(excluded)) if (!live.has(iso)) delete excluded[iso];
});

// --- Times -----------------------------------------------------------
const slotKey = (s: TimeSlot) => `${s.start}-${s.end}`;
const slotLabel = (s: TimeSlot) => `${s.start}–${s.end}`;

/** A finished pair, or null with the reason said out loud. */
function buildSlot(draft: TimeSlot, existing: TimeSlot[]): TimeSlot | null {
  if (!draft.start || !draft.end) return null;
  if (draft.end <= draft.start) {
    toasts.warn(t("datepoll.edit.slotRangeInvalid"));
    return null;
  }
  if (existing.some((s) => s.start === draft.start && s.end === draft.end)) {
    toasts.warn(t("datepoll.edit.slotDuplicate"));
    return null;
  }
  return draft;
}

function addSlot(iso: string, draft: TimeSlot): boolean {
  // A day's own times cannot repeat one that already holds for every
  // day either.
  const slot = buildSlot(draft, [...commonSlots, ...(slots[iso] ?? [])]);
  if (!slot) return false;
  const list = (slots[iso] ??= []);
  list.push(slot);
  list.sort((a, b) => a.start.localeCompare(b.start));
  return true;
}

function removeSlot(iso: string, index: number): void {
  slots[iso]?.splice(index, 1);
  if (slots[iso]?.length === 0) delete slots[iso];
}

function addCommonSlot(draft: TimeSlot): boolean {
  const slot = buildSlot(draft, commonSlots);
  if (!slot) return false;
  commonSlots = [...commonSlots, slot].sort((a, b) => a.start.localeCompare(b.start));
  // It holds for every day now, so a day's own copy of the same range
  // goes rather than showing as both an every-day pill and a this-day
  // one.
  dropPerDayCommonDupes();
  return true;
}

/** Is this every-day time on for this day? */
function isCommonOn(iso: string, s: TimeSlot): boolean {
  return !(excluded[iso] ?? []).includes(slotKey(s));
}

/**
 * The one rule that keeps a range from being drawn twice: a range an
 * active every-day time already covers must not also sit in that day's
 * own list. Run after anything that can introduce the overlap, which
 * also heals a draft saved before the rule existed.
 */
function dropPerDayCommonDupes(): void {
  const keys = new Set(commonSlots.map(slotKey));
  for (const iso of Object.keys(slots)) {
    slots[iso] = slots[iso].filter((s) => !(keys.has(slotKey(s)) && isCommonOn(iso, s)));
    if (slots[iso].length === 0) delete slots[iso];
  }
}

function toggleCommon(iso: string, s: TimeSlot): void {
  const key = slotKey(s);
  const list = (excluded[iso] ??= []);
  const i = list.indexOf(key);
  if (i >= 0) list.splice(i, 1);
  else list.push(key);
  if (list.length === 0) delete excluded[iso];
}

function removeCommonSlot(index: number): void {
  const removed = commonSlots[index];
  commonSlots = commonSlots.filter((_, i) => i !== index);
  if (!removed) return;
  // The exceptions to it have nothing left to except.
  const key = slotKey(removed);
  for (const iso of Object.keys(excluded)) {
    excluded[iso] = excluded[iso].filter((k) => k !== key);
    if (excluded[iso].length === 0) delete excluded[iso];
  }
}

/** Everything that holds for a day: the every-day times still on here,
 *  plus the day's own, in time order. */
function effectiveSlots(iso: string): TimeSlot[] {
  const common = commonSlots.filter((s) => isCommonOn(iso, s));
  return [...common, ...(slots[iso] ?? [])].sort((a, b) => a.start.localeCompare(b.start));
}

/**
 * Rebuild the times from a saved poll.
 *
 * The wire has no every-day idea: saving flattens them into one row per
 * day. So it is reconstructed on the way back in. A range present on
 * every day on offer becomes one every-day time, which is only worth
 * doing when there is more than one day, and the rest stay their day's
 * own. Building the two lists apart is what stops a range appearing as
 * both. Authoritative: it replaces all three pieces of state.
 */
function hydrateSlotState(
  serverSlots: { on_date: string; start_time?: string | null; end_time?: string | null }[],
  isos: string[],
): void {
  const perDay: Record<string, TimeSlot[]> = {};
  for (const s of serverSlots) {
    if (s.start_time && s.end_time) {
      (perDay[s.on_date] ??= []).push({
        start: s.start_time.slice(0, 5),
        end: s.end_time.slice(0, 5),
      });
    }
  }

  const counts = new Map<string, { slot: TimeSlot; n: number }>();
  for (const iso of isos) {
    for (const s of perDay[iso] ?? []) {
      const e = counts.get(slotKey(s)) ?? { slot: s, n: 0 };
      e.n += 1;
      counts.set(slotKey(s), e);
    }
  }

  const commonKeys = new Set<string>();
  const common: TimeSlot[] = [];
  if (isos.length > 1) {
    for (const { slot, n } of counts.values()) {
      if (n === isos.length) {
        common.push(slot);
        commonKeys.add(slotKey(slot));
      }
    }
  }

  commonSlots = common.sort((a, b) => a.start.localeCompare(b.start));
  slots = {};
  excluded = {};
  for (const iso of isos) {
    const extras = (perDay[iso] ?? []).filter((s) => !commonKeys.has(slotKey(s)));
    if (extras.length) slots[iso] = extras.sort((a, b) => a.start.localeCompare(b.start));
  }
}

/** "za 12 jul". The long form is too wide for a card's heading. */
function chipLabel(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString(localeTag(locale()), {
    weekday: "short",
    day: "numeric",
    month: "short",
  });
}

// --- The draft --------------------------------------------------------
interface DatepollDraft {
  nameNl: string;
  nameEn: string;
  descNl: string;
  descEn: string;
  location: string;
  latitude: number | null;
  longitude: number | null;
  imageArtistInstagram: string;
  chapterId: string | null;
  pollLocale: "nl" | "en";
  dates: string[];
  slots: Record<string, TimeSlot[]>;
  commonSlots: TimeSlot[];
  excluded: Record<string, string[]>;
}

function snapshot(): DatepollDraft {
  return {
    nameNl,
    nameEn,
    descNl,
    descEn,
    location: place.location,
    latitude: place.latitude,
    longitude: place.longitude,
    imageArtistInstagram,
    chapterId,
    pollLocale,
    dates: sortedISODates,
    slots: structuredClone($state.snapshot(slots)),
    commonSlots: commonSlots.map((s) => ({ ...s })),
    excluded: structuredClone($state.snapshot(excluded)),
  };
}

function applyDraft(d: DatepollDraft): void {
  nameNl = d.nameNl ?? "";
  nameEn = d.nameEn ?? "";
  descNl = d.descNl ?? "";
  descEn = d.descEn ?? "";
  place.set(d.location ?? null, d.latitude ?? null, d.longitude ?? null);
  imageArtistInstagram = d.imageArtistInstagram ?? "";
  chapterId = d.chapterId ?? null;
  pollLocale = d.pollLocale ?? "nl";
  selectedDates = (d.dates ?? []).map(fromISODate);
  slots = {};
  for (const [iso, list] of Object.entries(d.slots ?? {})) slots[iso] = list.map((s) => ({ ...s }));
  commonSlots = (d.commonSlots ?? []).map((s) => ({ ...s }));
  excluded = {};
  for (const [iso, keys] of Object.entries(d.excluded ?? {})) excluded[iso] = [...keys];
  dropPerDayCommonDupes();
}

const draft = formDraft<DatepollDraft>({
  key: () => `datepoll-edit-draft:${datepollId ?? "new"}`,
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

// The poll arrives, its values go in, and anything half-typed goes on
// top: a draft is newer than what was saved.
let seeded: unknown = undefined;
$effect(() => {
  const existing = query.data;
  if (!existing || existing === seeded) return;
  seeded = existing;
  nameNl = existing.name_nl ?? "";
  nameEn = existing.name_en ?? "";
  descNl = existing.description_nl ?? "";
  descEn = existing.description_en ?? "";
  imageUrl = existing.image_url ?? null;
  imageArtistInstagram = existing.image_artist_instagram ?? "";
  pollLocale = existing.locale;
  nameRequired = existing.name_required;
  answersEditable = existing.answers_editable;
  chapterId = existing.chapter_id;
  place.set(existing.location ?? null, existing.latitude ?? null, existing.longitude ?? null);
  const existingSlots = existing.slots ?? [];
  const isos = [...new Set(existingSlots.map((s) => s.on_date))].sort();
  selectedDates = isos.map(fromISODate);
  hydrateSlotState(existingSlots, isos);
  restoreDraftOnce();
});

// A new poll: the chapter is the one the organiser came from, or the
// only one they are in. Read once, at mount.
untrack(() => {
  if (isEdit) return;
  const fromQuery = route.query.get("chapter");
  const mine = new Set((auth.user?.chapters ?? []).map((c) => c.id));
  if (fromQuery && mine.has(fromQuery)) chapterId = fromQuery;
  else if (auth.user?.chapters?.length === 1) chapterId = auth.user.chapters[0].id;
  restoreDraftOnce();
});

// --- Leaving, and saving ----------------------------------------------
function cancel(): void {
  draft.clear();
  if (start.cancel()) return;
  void go(isEdit && datepollId ? `/datepoll/${datepollId}/details` : "/datepoll");
}

async function submit(): Promise<void> {
  // The title is required in the poll's own language.
  const primaryName = (pollLocale === "en" ? nameEn : nameNl).trim();
  if (!primaryName) {
    toasts.warn(t("datepoll.edit.fillName"));
    return;
  }
  if (start.hasChapters && !chapterId) {
    toasts.warn(t("datepoll.edit.fillChapter"));
    return;
  }
  if (start.active && !start.validate()) return;

  submitting = true;
  try {
    // A day with times emits one row per range; a day with none emits a
    // single whole-day row.
    const slotsPayload = sortedISODates.flatMap((iso) => {
      const timed = effectiveSlots(iso);
      return timed.length === 0
        ? [{ on_date: iso }]
        : timed.map((s) => ({ on_date: iso, start_time: s.start, end_time: s.end }));
    });

    const payload: DatepollCreate | DatepollUpdate = {
      chapter_id: start.chapterFor(chapterId),
      name_nl: nameNl.trim() || null,
      name_en: nameEn.trim() || null,
      description_nl: descNl.trim() || null,
      description_en: descEn.trim() || null,
      location: place.location.trim() || null,
      latitude: place.latitude,
      longitude: place.longitude,
      image_artist_instagram: imageArtistInstagram.trim() || null,
      locale: pollLocale,
      name_required: nameRequired,
      answers_editable: answersEditable,
      slots: slotsPayload,
    };

    if (start.active) {
      // No session: the public link in the answer is the whole result,
      // and there is no details page to land on. A refusal has already
      // been explained, and the draft stays so it can be tried again.
      if (await start.submit(payload)) draft.clear();
      return;
    }

    const result =
      isEdit && datepollId
        ? await update.run({ id: datepollId, payload })
        : await create.run(payload);
    await imageField?.flushPendingUpload(result.id);
    draft.clear();
    void go(`/datepoll/${result.id}/details`);
  } catch {
    toasts.error(t("datepoll.edit.saveFailed"));
  } finally {
    submitting = false;
  }
}
</script>

{#if notFound}
  <AppHeader />
  <div class="container-wide stack">
    <AppCard>
      <h2>{t("datepoll.edit.notFoundTitle")}</h2>
      <p class="muted">{t("datepoll.edit.notFoundBody")}</p>
      <RouterLink to="/datepoll" class="back-link">{t("datepoll.edit.backToList")}</RouterLink>
    </AppCard>
  </div>
{:else if query.error}
  <AppHeader />
  <div class="container-wide stack">
    <AppCard>
      <p>{t("datepoll.edit.loadFailed")}</p>
    </AppCard>
  </div>
{:else if start.started}
  <StartedPanel started={start.started} email={start.email} />
{:else}
  <FormPageShell
    title={isEdit ? t("datepoll.edit.editTitle") : t("datepoll.edit.newTitle")}
    submitLabel={isEdit ? t("datepoll.edit.save") : t("datepoll.edit.create")}
    {submitting}
    onsubmit={submit}
    oncancel={cancel}
  >
    <section class="form-section">
      {#if start.active}<StartAccountField bind:value={start.email} />{/if}
      <AppInput
        bind:value={title.value}
        placeholder={title.fallback || t("datepoll.edit.namePlaceholder")}
        fluid
      />
      <RichTextField
        bind:value={body.value}
        placeholder={t("datepoll.edit.descriptionPlaceholder")}
        fallbackHtml={body.fallback || null}
      />
      {#if start.hasChapters}
        <SelectField
          bind:value={chapterId}
          options={chapterOptions}
          optionLabel="name"
          optionValue="id"
          placeholder={t("datepoll.edit.chapterPlaceholder")}
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
    </section>

    <!-- Uploading writes to the row it belongs to, which takes a
         session the visitor does not have yet. -->
    {#if !start.active}
      <ImageField
        bind:this={imageField}
        resource="datepoll"
        entityId={datepollId ?? null}
        bind:imageUrl
        bind:artist={imageArtistInstagram}
      />
    {/if}

    <section class="form-section">
      <h2 class="section-heading">{t("datepoll.edit.datesHeading")}</h2>
      <p class="muted section-explainer">{t("datepoll.edit.datesExplainer")}</p>

      <div class="dates-stack">
        <div class="picker-row">
          <DatePicker
            bind:modelValue={selectedDates}
            locale={locale()}
            selectionMode="multiple"
            inline
            manualInput={false}
          />

          <!-- The times that hold for every day, made once here and
               shown on each day's card below. -->
          <div class="common-panel">
            <p class="common-title">{t("datepoll.edit.commonSlotsTitle")}</p>
            <p class="muted common-hint">{t("datepoll.edit.commonSlotsHint")}</p>
            {#if commonSlots.length}
              <div class="slot-pills">
                {#each commonSlots as s, idx (slotKey(s))}
                  <button
                    type="button"
                    class="slot-pill"
                    aria-label={`${t("datepoll.edit.removeSlot")}: ${slotLabel(s)}`}
                    onclick={() => removeCommonSlot(idx)}
                  >
                    <span>{slotLabel(s)}</span>
                    <span class="x" aria-hidden="true">×</span>
                  </button>
                {/each}
              </div>
            {/if}
            <TimeRangeAdder onadd={addCommonSlot} />
          </div>
        </div>

        {#if sortedISODates.length === 0}
          <p class="empty muted">{t("datepoll.edit.noDatesYet")}</p>
        {:else}
          <!-- One card per day: the day, its times, and a row to add
               one. A day with no times is a whole day, and says nothing
               about it. -->
          <ul class="day-cards">
            {#each sortedISODates as iso (iso)}
              <li class="day-card">
                <div class="day-head">
                  <span class="day-label">{chipLabel(iso)}</span>
                  <button
                    type="button"
                    class="remove-day"
                    aria-label={`${t("datepoll.edit.removeDate")}: ${chipLabel(iso)}`}
                    onclick={() => removeDate(iso)}>×</button
                  >
                </div>

                {#if commonSlots.length || slots[iso]?.length}
                  <div class="slot-pills">
                    <!-- An every-day time. Tap it to switch it off for
                         this day alone. -->
                    {#each commonSlots as s (slotKey(s))}
                      <button
                        type="button"
                        class="slot-pill common"
                        class:off={!isCommonOn(iso, s)}
                        aria-pressed={isCommonOn(iso, s)}
                        onclick={() => toggleCommon(iso, s)}
                      >
                        {slotLabel(s)}
                      </button>
                    {/each}
                    {#each slots[iso] ?? [] as s, idx (slotKey(s))}
                      <button
                        type="button"
                        class="slot-pill"
                        aria-label={`${t("datepoll.edit.removeSlot")}: ${slotLabel(s)}`}
                        onclick={() => removeSlot(iso, idx)}
                      >
                        <span>{slotLabel(s)}</span>
                        <span class="x" aria-hidden="true">×</span>
                      </button>
                    {/each}
                  </div>
                {/if}

                <TimeRangeAdder onadd={(slot) => addSlot(iso, slot)} />
              </li>
            {/each}
          </ul>
        {/if}
      </div>
    </section>

    <!-- Every switch, folded away: the thing itself above it, the page
         language below. One fold on all six products. -->
    <details
      class="advanced"
      open={advancedOpen}
      ontoggle={(e) => (advancedOpen = (e.target as HTMLDetailsElement).open)}
    >
      <summary>{advancedOpen ? t("common.advancedHide") : t("common.advancedShow")}</summary>

      <!-- Off by default: a name real or not is what the contract
           offers, so an empty box is an answer. On when the answers are
           only useful attached to somebody. -->
      <section class="form-section">
        <label class="toggle-row" for="nameRequiredToggle">
          <AppToggle bind:checked={nameRequired} inputId="nameRequiredToggle" />
          <h2 class="section-heading">{t("common.nameRequired")}</h2>
        </label>
        <p class="muted section-explainer">{t("common.nameRequiredExplainer")}</p>
      </section>

      <section class="form-section">
        <label class="toggle-row" for="editableToggle">
          <AppToggle bind:checked={answersEditable} inputId="editableToggle" />
          <h2 class="section-heading">{t("form.edit.editableHeading")}</h2>
        </label>
        <p class="muted section-explainer">{t("form.edit.editableExplainer")}</p>
      </section>
    </details>

    <section class="form-section">
      <h2 class="section-heading">{t("datepoll.edit.localeHeading")}</h2>
      <p class="muted section-explainer">{t("datepoll.edit.localeExplainer")}</p>
      <SelectField
        bind:value={pollLocale}
        options={[
          { value: "nl", label: t("datepoll.edit.localeNl") },
          { value: "en", label: t("datepoll.edit.localeEn") },
        ]}
        optionLabel="label"
        optionValue="value"
        fluid
      />
    </section>
  </FormPageShell>
{/if}

<style>
/* The shared form chrome lives in ``src/assets/forms.css``. The
 * calendar draws six week rows in every month, so its height does not
 * shift as you navigate it. */
.dates-stack {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  align-items: flex-start;
}
/* The calendar and the every-day times side by side, stacked on a
 * narrow screen. */
.picker-row {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem 1.5rem;
  align-items: flex-start;
  width: 100%;
}
.common-panel {
  flex: 1 1 14rem;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.common-title {
  margin: 0;
  font-weight: 600;
  font-size: 0.875rem;
}
.common-hint {
  margin: 0;
  font-size: 0.8125rem;
}
/* An every-day time on a day's card. On means it holds here; off,
 * struck through, means this day is the exception. */
.slot-pill.common.off {
  text-decoration: line-through;
  opacity: 0.55;
  border-style: dashed;
  color: var(--brand-text-muted);
}
.day-cards {
  list-style: none;
  margin: 0;
  padding: 0;
  width: 100%;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.day-card {
  border: 1px solid var(--brand-border);
  border-radius: 10px;
  padding: 0.625rem 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.day-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}
.day-label {
  font-weight: 600;
  font-size: 0.875rem;
  text-transform: capitalize;
}
.remove-day {
  border: none;
  background: none;
  color: var(--brand-text-muted);
  font-size: 1.25rem;
  line-height: 1;
  cursor: pointer;
  padding: 0 0.25rem;
}
.remove-day:hover {
  color: var(--brand-red);
}
.slot-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
}
.slot-pill {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.25rem 0.5rem 0.25rem 0.625rem;
  border: 1px solid var(--brand-border);
  border-radius: 999px;
  background: var(--brand-surface);
  color: var(--brand-text);
  font: inherit;
  font-size: 0.8125rem;
  font-variant-numeric: tabular-nums;
  cursor: pointer;
  white-space: nowrap;
}
.slot-pill:hover {
  border-color: var(--brand-red);
}
.slot-pill .x {
  color: var(--brand-text-muted);
  font-size: 1rem;
  line-height: 1;
}
.slot-pill:hover .x {
  color: var(--brand-red);
}
</style>
