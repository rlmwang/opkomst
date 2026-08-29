<script lang="ts">
import AppButton from "@/components/AppButton.svelte";
import AppCard from "@/components/AppCard.svelte";
import AppDialog from "@/components/AppDialog.svelte";
import AppHeader from "@/components/AppHeader.svelte";
import AppInput from "@/components/AppInput.svelte";
import AppSkeleton from "@/components/AppSkeleton.svelte";
import ChapterPicker from "@/components/ChapterPicker.svelte";
import CityPicker from "@/components/CityPicker.svelte";
import EditableList from "@/components/EditableList.svelte";
import SelectField from "@/components/SelectField.svelte";
import {
  archiveChapter,
  type Chapter,
  chapterUsage,
  chaptersQuery,
  createChapter,
  restoreChapter,
  sortedChapters,
  updateChapter,
} from "@/composables/useChapters.svelte";
import { dialog } from "@/composables/useDialog.svelte";
import { t } from "@/i18n.svelte";
import { brand } from "@/lib/branding";
import { can } from "@/lib/permissions";
import { queryClient } from "@/lib/query-client";
import { useToasts } from "@/lib/toasts";
import { auth } from "@/stores/auth.svelte";

/** The organisation's chapters: add, rename, give a city, archive. */
const toasts = useToasts();
const canManage = $derived(can(auth.user, "create_chapter"));

// One list, archived rows included. The add bar needs them to find a
// chapter whose name an admin just retyped: without that the restore
// branch could not see the candidate and Enter would refuse the name
// forever. The table wants the live ones, and every row says whether it
// is archived, so that is a filter rather than a second request for
// part of what is already in hand.
const query = chaptersQuery({ includeArchived: true });
const chapters = $derived(sortedChapters(query.data).filter((c) => !c.archived));

const create = createChapter();
const update = updateChapter();
const archive = archiveChapter();
const restore = restoreChapter();

// --- Rename, and give it a city -------------------------------------
const editDialog = dialog<Chapter>();
let editName = $state("");
let editSlug = $state("");
let editCity = $state<{ city: string | null; city_lat: number | null; city_lon: number | null }>({
  city: null,
  city_lat: null,
  city_lon: null,
});

function openEdit(c: Chapter): void {
  editName = c.name;
  editSlug = c.slug;
  editCity = { city: c.city, city_lat: c.city_lat, city_lon: c.city_lon };
  editDialog.openWith(c);
}

async function submitEdit(): Promise<void> {
  const target = editDialog.target;
  if (!target) return;
  const trimmed = editName.trim();
  if (!trimmed) {
    toasts.warn(t("chapters.fillName"));
    return;
  }
  try {
    await editDialog.submit(async () => {
      await update.run({
        id: target.id,
        payload: {
          name: trimmed,
          slug: editSlug.trim(),
          city: editCity.city,
          city_lat: editCity.city_lat,
          city_lon: editCity.city_lon,
        },
      });
      toasts.success(t("chapters.editedToast"));
    });
  } catch (e) {
    toasts.error(e instanceof Error ? e.message : t("chapters.editFail"));
  }
}

// --- Archive, and hand on what pointed at it -------------------------
const deleteDialog = dialog<Chapter>();
let usage = $state<{ users: number; events: number }>({ users: 0, events: 0 });
let reassignUsersTo = $state<Chapter | null>(null);
let reassignEventsTo = $state<Chapter | null>(null);
/** The chapter whose usage is being fetched, so its trash button spins
 *  rather than looking frozen on a slow connection. */
let usageLoadingFor = $state<string | null>(null);

const otherChapters = $derived(chapters.filter((c) => c.id !== deleteDialog.target?.id));

async function openDelete(c: Chapter): Promise<void> {
  reassignUsersTo = null;
  reassignEventsTo = null;
  usageLoadingFor = c.id;
  try {
    usage = await chapterUsage(c.id);
  } catch {
    usage = { users: 0, events: 0 };
  } finally {
    usageLoadingFor = null;
  }
  deleteDialog.openWith(c);
}

async function submitDelete(): Promise<void> {
  const target = deleteDialog.target;
  if (!target) return;
  try {
    await deleteDialog.submit(async () => {
      await archive.run({
        id: target.id,
        reassign: { users: reassignUsersTo?.id ?? null, events: reassignEventsTo?.id ?? null },
      });
      toasts.success(t("chapters.archivedToast"));
      // Handing rows on changes who belongs to what, so the users page
      // refetches on its next visit.
      void queryClient.invalidateQueries({ queryKey: ["users"] });
    });
  } catch {
    toasts.error(t("chapters.archiveFail"));
  }
}

// --- The add bar -----------------------------------------------------
async function onPicked(c: Chapter): Promise<void> {
  if (!c.archived) return;
  try {
    await restore.run(c.id);
    toasts.success(t("chapters.restoredToast", { name: c.name }));
  } catch {
    toasts.error(t("chapters.restoreFail"));
  }
}

/** The same normalisation the backend does, so " Den   Haag " and
 *  "Den Haag" are one name here too. */
function normaliseName(name: string): string {
  return name.trim().split(/\s+/).join(" ");
}

async function onCreate(name: string): Promise<void> {
  // A typed name that matches an archived chapter restores that one
  // rather than making a second. Without this the duplicate-name guard
  // would refuse the create, and the archived chapter would be
  // unreachable from the keyboard for good.
  try {
    const normalised = normaliseName(name);
    const lower = normalised.toLowerCase();
    // Asked again rather than read from the cache: the chapter being
    // retyped may have been archived from another tab a moment ago.
    const archivedMatch = ((await query.refetch()) ?? []).find(
      (c) => c.archived && c.name.toLowerCase() === lower,
    );
    if (archivedMatch) {
      await restore.run(archivedMatch.id);
      toasts.success(t("chapters.restoredToast", { name: archivedMatch.name }));
      return;
    }
    await create.run(normalised);
    toasts.success(t("chapters.createdToast", { name: normalised }));
  } catch {
    toasts.error(t("chapters.createFail"));
  }
}
</script>

<AppHeader />
<div class="container-wide stack">
  <h1>{t("chapters.title")}</h1>
  <p class="muted">{t("chapters.intro")}</p>

  <AppCard>
    {#if query.isPending}
      <AppSkeleton rows={3} />
    {:else}
      <ChapterPicker
        placeholder={t("chapters.addPlaceholder")}
        archivedOnly
        disabled={!canManage}
        leadingIcon="plus"
        onpick={onPicked}
        oncreate={onCreate}
      />
      <EditableList
        items={chapters}
        itemLabel={(c) => c.name}
        itemKey={(c) => c.id}
        loadingKey={usageLoadingFor}
        readonly={!canManage}
        onremove={openDelete}
      >
        {#snippet row({ item })}
          <div class="chapter-row">
            <span class="chapter-name">
              {item.name}
              {#if item.city}<span class="muted chapter-city"> · {item.city}</span>{/if}
            </span>
            <AppButton
              icon="pencil"
              size="small"
              severity="secondary"
              text
              disabled={!canManage}
              ariaLabel={t("common.edit")}
              onclick={() => openEdit(item)}
            />
          </div>
        {/snippet}
      </EditableList>
    {/if}
  </AppCard>

  <AppDialog
    bind:visible={deleteDialog.open}
    header={t("chapters.deleteDialogTitle", { name: deleteDialog.target?.name ?? "" })}
    width="480px"
  >
    <p class="muted dialog-text">{t("chapters.deleteDialogBody")}</p>
    {#if usage.users > 0}
      <label class="reassign-label">
        {t("chapters.deleteUsersLabel", { n: usage.users })}
        <SelectField
          bind:value={reassignUsersTo}
          options={otherChapters}
          optionLabel="name"
          showClear
          placeholder={t("chapters.deleteLeaveOrphaned")}
          fluid
        />
      </label>
    {/if}
    {#if usage.events > 0}
      <label class="reassign-label">
        {t("chapters.deleteEventsLabel", { n: usage.events })}
        <SelectField
          bind:value={reassignEventsTo}
          options={otherChapters}
          optionLabel="name"
          showClear
          placeholder={t("chapters.deleteLeaveOrphaned")}
          fluid
        />
      </label>
    {/if}
    {#if usage.users === 0 && usage.events === 0}
      <p class="muted dialog-text">{t("chapters.deleteNoDeps")}</p>
    {/if}
    {#snippet footer()}
      <AppButton
        label={t("common.cancel")}
        severity="secondary"
        text
        onclick={() => deleteDialog.close()}
      />
      <AppButton
        label={t("chapters.archive")}
        loading={deleteDialog.submitting}
        onclick={submitDelete}
      />
    {/snippet}
  </AppDialog>

  <AppDialog
    bind:visible={editDialog.open}
    header={t("chapters.editDialogTitle", { name: editDialog.target?.name ?? "" })}
  >
    <p class="muted dialog-text">{t("chapters.editDialogBody")}</p>
    <AppInput bind:value={editName} placeholder={t("chapters.namePlaceholder")} fluid />
    <AppInput bind:value={editSlug} placeholder={t("chapters.slugPlaceholder")} fluid />
    <p class="muted dialog-text">
      {t("chapters.slugHelp", { tenant: brand().slug, slug: editSlug || "…" })}
    </p>
    <CityPicker bind:value={editCity} placeholder={t("chapters.cityPlaceholder")} />
    {#snippet footer()}
      <AppButton
        label={t("common.cancel")}
        severity="secondary"
        text
        onclick={() => editDialog.close()}
      />
      <AppButton label={t("common.save")} loading={editDialog.submitting} onclick={submitEdit} />
    {/snippet}
  </AppDialog>
</div>

<style>
.dialog-text {
  margin: 0;
}
.reassign-label {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  font-size: 0.875rem;
  color: var(--brand-text);
}
.chapter-row {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  width: 100%;
}
.chapter-name {
  flex: 1;
  min-width: 0;
}
</style>
