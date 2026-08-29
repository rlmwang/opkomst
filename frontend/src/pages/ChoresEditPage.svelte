<script lang="ts">
import AppButton from "@/components/AppButton.svelte";
import AppCard from "@/components/AppCard.svelte";
import AppHeader from "@/components/AppHeader.svelte";
import AppInput from "@/components/AppInput.svelte";
import AppToggle from "@/components/AppToggle.svelte";
import ChoreEditor, { type ChoreDraft } from "@/components/ChoreEditor.svelte";
import DatePicker from "@/components/DatePicker.svelte";
import { DEFAULT_CHORE_EMOJI, firstUnusedEmoji } from "@/components/EmojiPicker.svelte";
import FormPageShell from "@/components/FormPageShell.svelte";
import ImageField from "@/components/ImageField.svelte";
import NumberStepper from "@/components/NumberStepper.svelte";
import RichTextField from "@/components/RichTextField.svelte";
import SelectField from "@/components/SelectField.svelte";
import StartAccountField from "@/components/StartAccountField.svelte";
import StartedPanel from "@/components/StartedPanel.svelte";
import RouterLink from "@/router/RouterLink.svelte";
import { bilingualField } from "@/composables/useBilingualField.svelte";
import { chaptersQuery, sortedChapters } from "@/composables/useChapters.svelte";
import { rosters } from "@/composables/useChores.svelte";
import { formDraft } from "@/composables/useFormDraft.svelte";
import { orderedList } from "@/composables/useOrderedList.svelte";
import { startMode } from "@/composables/useStartMode.svelte";
import { locale, t } from "@/i18n.svelte";
import { untrack } from "svelte";

import { ApiError } from "@/api/client";
import { go, route } from "@/router/navigation.svelte";
import { useToasts } from "@/lib/toasts";
import { auth } from "@/stores/auth.svelte";
import type { ChoreIn, RosterCreate, RosterUpdate } from "@/api/types";

/**
 * Making or changing a roster: what the chores are, how often they come
 * round, and between which dates.
 */
const { rosterId }: { rosterId?: string } = $props();

const toasts = useToasts();
const start = startMode("roster");
const chapters = chaptersQuery({ enabled: () => start.hasChapters });
const create = rosters.create();
const update = rosters.update();

const isEdit = $derived(Boolean(rosterId));
const query = rosters.single(
  () => rosterId ?? "",
  { enabled: () => Boolean(rosterId) },
);
const notFound = $derived(query.error instanceof ApiError && query.error.status === 404);

let chapterId = $state<string | null>(null);
/** Only the chapters this organiser is in: assigning to one they do not
 *  belong to is refused by the server. */
const chapterOptions = $derived.by(() => {
  const mine = new Set((auth.user?.chapters ?? []).map((c) => c.id));
  return sortedChapters(chapters.data).filter((c) => mine.has(c.id));
});

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
let rosterLocale = $state<"nl" | "en">(locale() === "en" ? "en" : "nl");
let nameRequired = $state(false);
/** The switches sit behind one fold, the same one every other edit page
 *  ends with, and it starts closed every time. */
let advancedOpen = $state(false);
let periodWeeks = $state(1);
let startsOn = $state<Date | null>(null);
let endsOn = $state<Date | null>(null);
let reminderEnabled = $state(true);
let reminderDaysBefore = $state(1);
let commitHorizonDays = $state(21);
const choreList = orderedList<ChoreDraft>();
let submitting = $state(false);

// Rosters usually remind, so the switch starts on. Whether this account
// may is a separate question, and it is the one the payload asks: a
// free account has no reminder section on the form and sends no
// reminders (docs/design-paywall.md).
const sendsReminders = $derived(reminderEnabled && auth.participantMail);

const localeOptions = $derived([
  { value: "nl", label: t("chore.edit.localeNl") },
  { value: "en", label: t("chore.edit.localeEn") },
]);

// --- Date and "YYYY-MM-DD", locally, with no drift through UTC -------
function isoDate(d: Date | null): string | null {
  if (!d) return null;
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${month}-${day}`;
}

function parseDate(s: string | null | undefined): Date | null {
  if (!s) return null;
  const [y, m, d] = s.split("-").map(Number);
  if (!y || !m || !d) return null;
  return new Date(y, m - 1, d);
}

// A shorter cycle leaves some days out of range, so they are dropped
// and the chores that lost one are named. The server clamps too; this
// keeps the form honest about it.
let lastPeriod = 1;
$effect(() => {
  const next = periodWeeks;
  const prev = lastPeriod;
  lastPeriod = next;
  if (next >= prev) return;
  const hi = 7 * next;
  const affected: string[] = [];
  for (const c of choreList.items) {
    const kept = c.cycle_slots.filter((s) => s < hi);
    if (kept.length !== c.cycle_slots.length) {
      affected.push(c.name || t("chore.edit.untitledChore"));
      c.cycle_slots = kept;
    }
  }
  if (affected.length) toasts.warn(t("chore.edit.slotsCleared", { names: affected.join(", ") }));
});

// --- The draft, with the dates as strings ---------------------------
interface RosterEditDraft {
  nameNl: string;
  nameEn: string;
  descNl: string;
  descEn: string;
  imageArtistInstagram: string;
  chapterId: string | null;
  rosterLocale: "nl" | "en";
  periodWeeks: number;
  startsOn: string | null;
  endsOn: string | null;
  reminderEnabled: boolean;
  reminderDaysBefore: number;
  commitHorizonDays: number;
  chores: ChoreDraft[];
}

function snapshot(): RosterEditDraft {
  return {
    nameNl,
    nameEn,
    descNl,
    descEn,
    imageArtistInstagram,
    chapterId,
    rosterLocale,
    periodWeeks,
    startsOn: isoDate(startsOn),
    endsOn: isoDate(endsOn),
    reminderEnabled,
    reminderDaysBefore,
    commitHorizonDays,
    chores: choreList.items,
  };
}

function applyDraft(d: RosterEditDraft): void {
  nameNl = d.nameNl ?? "";
  nameEn = d.nameEn ?? "";
  descNl = d.descNl ?? "";
  descEn = d.descEn ?? "";
  imageArtistInstagram = d.imageArtistInstagram ?? "";
  chapterId = d.chapterId ?? null;
  rosterLocale = d.rosterLocale ?? "nl";
  periodWeeks = d.periodWeeks ?? 1;
  startsOn = parseDate(d.startsOn);
  endsOn = parseDate(d.endsOn);
  reminderEnabled = d.reminderEnabled ?? true;
  reminderDaysBefore = d.reminderDaysBefore ?? 1;
  commitHorizonDays = d.commitHorizonDays ?? 21;
  choreList.items = (d.chores ?? []).map((c) => ({
    ...c,
    cycle_slots: [...(c.cycle_slots ?? [])],
    emoji: c.emoji ?? DEFAULT_CHORE_EMOJI,
  }));
}

const draft = formDraft<RosterEditDraft>({
  key: () => `chore-edit-draft:${rosterId ?? "new"}`,
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

// The roster arrives, its values go in, and then anything the organiser
// had half-typed goes on top: a draft is newer than what was saved.
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
  rosterLocale = existing.locale;
  nameRequired = existing.name_required;
  chapterId = existing.chapter_id;
  periodWeeks = existing.period_weeks;
  startsOn = parseDate(existing.starts_on);
  endsOn = parseDate(existing.ends_on);
  reminderEnabled = existing.reminder_enabled;
  reminderDaysBefore = existing.reminder_days_before;
  commitHorizonDays = existing.commit_horizon_days;
  choreList.items = (existing.chores ?? []).map((c) => ({
    id: c.id,
    name: c.name,
    description: c.description ?? null,
    cycle_slots: [...c.cycle_slots],
    people_per_shift: c.people_per_shift,
    emoji: c.emoji ?? DEFAULT_CHORE_EMOJI,
  }));
  restoreDraftOnce();
});

// A new roster: the chapter is the one the organiser came from, or the
// only one they are in. Read once, at mount, which is what ``untrack``
// says: this is the form's starting state, not something that follows
// the route afterwards.
untrack(() => {
  if (isEdit) return;
  const fromQuery = route.query.get("chapter");
  const mine = new Set((auth.user?.chapters ?? []).map((c) => c.id));
  if (fromQuery && mine.has(fromQuery)) chapterId = fromQuery;
  else if (auth.user?.chapters?.length === 1) chapterId = auth.user.chapters[0].id;
  restoreDraftOnce();
});

// --- The chore list --------------------------------------------------
function addChore(): void {
  choreList.add({
    id: null,
    name: "",
    description: null,
    cycle_slots: [],
    people_per_shift: 1,
    // A new chore starts on an emoji no other chore is using.
    emoji: firstUnusedEmoji(choreList.items.map((c) => c.emoji)),
  });
}

function setChore(index: number, next: ChoreDraft): void {
  const prev = choreList.items[index];
  // Emojis stay unique: picking one another chore already has swaps
  // them, handing that chore this one's previous emoji.
  if (next.emoji !== prev.emoji) {
    const clash = choreList.items.findIndex((c, i) => i !== index && c.emoji === next.emoji);
    if (clash !== -1) {
      choreList.replaceAt(clash, { ...choreList.items[clash], emoji: prev.emoji });
    }
  }
  choreList.replaceAt(index, next);
}

// --- Leaving, and saving ---------------------------------------------
function cancel(): void {
  draft.clear();
  if (start.cancel()) return;
  void go(isEdit && rosterId ? `/chore/${rosterId}/details` : "/chore");
}

async function submit(): Promise<void> {
  // The title is required in the roster's own language; the other one
  // is an optional translation.
  const primaryName = (rosterLocale === "en" ? nameEn : nameNl).trim();
  if (!primaryName) {
    toasts.warn(t("chore.edit.fillName"));
    return;
  }
  if (start.hasChapters && !chapterId) {
    toasts.warn(t("chore.edit.fillChapter"));
    return;
  }
  if (start.active && !start.validate()) return;
  if (!startsOn) {
    toasts.warn(t("chore.edit.fillStartsOn"));
    return;
  }
  if (choreList.items.some((c) => !c.name.trim())) {
    toasts.warn(t("chore.edit.fillChoreName"));
    return;
  }

  submitting = true;
  try {
    const payload: RosterCreate | RosterUpdate = {
      chapter_id: start.chapterFor(chapterId),
      name_nl: nameNl.trim() || null,
      name_en: nameEn.trim() || null,
      description_nl: descNl.trim() || null,
      description_en: descEn.trim() || null,
      image_artist_instagram: imageArtistInstagram.trim() || null,
      locale: rosterLocale,
      location: null,
      latitude: null,
      longitude: null,
      period_weeks: periodWeeks,
      starts_on: isoDate(startsOn) as string,
      ends_on: isoDate(endsOn),
      name_required: nameRequired,
      reminder_enabled: sendsReminders,
      reminder_days_before: reminderDaysBefore,
      commit_horizon_days: commitHorizonDays,
      chores: choreList.items.map(
        (c): ChoreIn => ({
          id: c.id,
          name: c.name.trim(),
          description: c.description,
          cycle_slots: c.cycle_slots,
          people_per_shift: c.people_per_shift,
          emoji: c.emoji,
        }),
      ),
    };

    if (start.active) {
      // No session: the public link in the answer is the whole result,
      // and there is no details page to land on. A refusal has already
      // been explained, and the draft stays so it can be tried again.
      if (await start.submit(payload)) draft.clear();
      return;
    }

    const result =
      isEdit && rosterId
        ? await update.run({ id: rosterId, payload })
        : await create.run(payload);
    await imageField?.flushPendingUpload(result.id);
    draft.clear();
    void go(`/chore/${result.id}/details`);
  } catch {
    toasts.error(t("chore.edit.saveFailed"));
  } finally {
    submitting = false;
  }
}
</script>

{#if notFound}
  <AppHeader />
  <div class="container-wide stack">
    <AppCard>
      <h2>{t("chore.edit.notFoundTitle")}</h2>
      <p class="muted">{t("chore.edit.notFoundBody")}</p>
      <RouterLink to="/chore" class="back-link">{t("chore.edit.backToList")}</RouterLink>
    </AppCard>
  </div>
{:else if query.error}
  <AppHeader />
  <div class="container-wide stack">
    <AppCard>
      <p>{t("chore.edit.loadFailed")}</p>
    </AppCard>
  </div>
{:else if start.started}
  <StartedPanel started={start.started} email={start.email} />
{:else}
  <FormPageShell
    title={isEdit ? t("chore.edit.editTitle") : t("chore.edit.newTitle")}
    submitLabel={isEdit ? t("chore.edit.save") : t("chore.edit.create")}
    {submitting}
    onsubmit={submit}
    oncancel={cancel}
  >
    <section class="form-section">
      {#if start.active}<StartAccountField bind:value={start.email} />{/if}
      <AppInput
        bind:value={title.value}
        placeholder={title.fallback || t("chore.edit.namePlaceholder")}
        fluid
      />
      <RichTextField
        bind:value={body.value}
        placeholder={t("chore.edit.descriptionPlaceholder")}
        fallbackHtml={body.fallback || null}
      />
      {#if start.hasChapters}
        <SelectField
          bind:value={chapterId}
          options={chapterOptions}
          optionLabel="name"
          optionValue="id"
          placeholder={t("chore.edit.chapterPlaceholder")}
          disabled={chapterOptions.length === 1 && chapterId !== null}
          fluid
        />
      {/if}
    </section>

    <!-- Uploading writes to the row it belongs to, which takes a
         session the visitor does not have yet. -->
    {#if !start.active}
      <ImageField
        bind:this={imageField}
        resource="chore"
        entityId={rosterId ?? null}
        bind:imageUrl
        bind:artist={imageArtistInstagram}
      />
    {/if}

    <section class="form-section">
      <h2 class="section-heading">{t("chore.edit.recurrenceHeading")}</h2>
      <p class="muted section-explainer">{t("chore.edit.recurrenceExplainer")}</p>

      <div class="stepper-row">
        <NumberStepper
          bind:value={periodWeeks}
          min={1}
          max={8}
          ariaLabel={t("chore.edit.periodWeeks")}
        />
      </div>

      <div class="date-row">
        <div class="field">
          <DatePicker
            bind:modelValue={startsOn}
            locale={locale()}
            dateFormat="dd-mm-yy"
            placeholder={t("chore.edit.startDatePlaceholder")}
            fluid
          />
        </div>
        <div class="field">
          <DatePicker
            bind:modelValue={endsOn}
            locale={locale()}
            dateFormat="dd-mm-yy"
            showButtonBar
            placeholder={t("chore.edit.endsOnPlaceholder")}
            fluid
          />
        </div>
      </div>
    </section>

    <section class="form-section">
      <h2 class="section-heading">{t("chore.edit.choresHeading")}</h2>
      <p class="muted section-explainer">{t("chore.edit.choresExplainer")}</p>

      {#if choreList.items.length === 0}
        <div class="empty muted">{t("chore.edit.noChoresYet")}</div>
      {/if}

      <div class="chores-stack">
        {#each choreList.items as c, idx (c.id ?? `new-${idx}`)}
          <ChoreEditor
            value={c}
            {periodWeeks}
            canMoveUp={idx > 0}
            canMoveDown={idx < choreList.items.length - 1}
            onchange={(next) => setChore(idx, next)}
            ondelete={() => choreList.removeAt(idx)}
            onmoveUp={() => choreList.move(idx, -1)}
            onmoveDown={() => choreList.move(idx, 1)}
          />
        {/each}
      </div>

      <AppButton
        type="button"
        label={t("chore.edit.addChore")}
        icon="plus"
        severity="secondary"
        onclick={addChore}
      />
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
           offers, so an empty box is an answer. A roster is the one
           place a nameless sign-up is hard to use, which makes this the
           switch an organiser is likeliest to reach for. -->
      <section class="form-section">
        <label class="toggle-row" for="nameRequiredToggle">
          <AppToggle bind:checked={nameRequired} inputId="nameRequiredToggle" />
          <h2 class="section-heading">{t("common.nameRequired")}</h2>
        </label>
        <p class="muted section-explainer">{t("common.nameRequiredExplainer")}</p>
      </section>

      <!-- Mailing volunteers is the paid plan
           (docs/design-paywall.md). A free roster keeps its page and its
           calendar, so the section is not here at all. -->
      {#if auth.participantMail}
        <section class="form-section">
          <label class="toggle-row" for="reminderToggle">
            <AppToggle bind:checked={reminderEnabled} inputId="reminderToggle" />
            <h2 class="section-heading">{t("chore.edit.reminderEnabled")}</h2>
          </label>
          <p class="muted section-explainer">{t("chore.edit.remindersExplainer")}</p>

          {#if reminderEnabled}
            <div class="field">
              <span class="field-label">{t("chore.edit.reminderDaysBefore")}</span>
              <NumberStepper
                bind:value={reminderDaysBefore}
                min={0}
                max={14}
                ariaLabel={t("chore.edit.reminderDaysBefore")}
              />
            </div>
          {/if}
        </section>
      {/if}

      <!-- How far ahead the schedule is pinned. A setting rather than
           part of the roster, so it belongs with the switches. -->
      <section class="form-section">
        <h2 class="section-heading">{t("chore.edit.commitHorizonDays")}</h2>
        <p class="muted section-explainer">{t("chore.edit.commitHorizonHint")}</p>
        <NumberStepper
          bind:value={commitHorizonDays}
          min={reminderEnabled ? reminderDaysBefore : 1}
          max={365}
          ariaLabel={t("chore.edit.commitHorizonDays")}
        />
      </section>
    </details>

    <section class="form-section">
      <h2 class="section-heading">{t("chore.edit.languageHeading")}</h2>
      <p class="muted section-explainer">{t("chore.edit.languageExplainer")}</p>
      <SelectField
        bind:value={rosterLocale}
        options={localeOptions}
        optionLabel="label"
        optionValue="value"
        fluid
      />
    </section>
  </FormPageShell>
{/if}

<style>
/* The shared form chrome lives in ``src/assets/forms.css``. Only the
 * roster's own rules are here. */
.stepper-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}
.date-row {
  display: flex;
  gap: 1rem;
  flex-wrap: wrap;
}
.date-row .field {
  /* ``min-width: 0`` so both fields shrink to the same basis instead of
   * being sized by their placeholders, which are different lengths. */
  flex: 1 1 12rem;
  min-width: 0;
}
.chores-stack {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
</style>
