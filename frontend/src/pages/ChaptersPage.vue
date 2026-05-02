<script setup lang="ts">
import Button from "primevue/button";
import InputText from "primevue/inputtext";
import Select from "primevue/select";
import { useQueryClient } from "@tanstack/vue-query";
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";
import AppCard from "@/components/AppCard.vue";
import AppDialog from "@/components/AppDialog.vue";
import AppHeader from "@/components/AppHeader.vue";
import AppSkeleton from "@/components/AppSkeleton.vue";
import ChapterPicker from "@/components/ChapterPicker.vue";
import CityPicker from "@/components/CityPicker.vue";
import EditableList from "@/components/EditableList.vue";
import {
  type Chapter,
  chapterList,
  getChapterUsage,
  useArchiveChapter,
  useChapters,
  useCreateChapter,
  useRestoreChapter,
  useUpdateChapter,
} from "@/composables/useChapters";
import { useDialog } from "@/composables/useDialog";
import { can as permCan } from "@/lib/permissions";
import { useToasts } from "@/lib/toasts";
import { useAuthStore } from "@/stores/auth";

const { t } = useI18n();
const auth = useAuthStore();
const toasts = useToasts();
const qc = useQueryClient();

const canManageChapters = computed(() => permCan(auth.user, "create_chapter"));

const chaptersQuery = useChapters({ includeArchived: false });
const chapters = chapterList(chaptersQuery);
// Includes-archived list, used by ``onCreateFromAddBar`` to find a
// soft-deleted chapter whose name the admin just retyped — without
// it the restore branch couldn't see the candidate and Enter would
// 409 with "name already exists" forever.
const chaptersWithArchivedQuery = useChapters({ includeArchived: true });
const createChapter = useCreateChapter();
const updateChapter = useUpdateChapter();
const archiveChapter = useArchiveChapter();
const restoreChapter = useRestoreChapter();

const loaded = computed(() => !chaptersQuery.isLoading.value);

// --- Edit-chapter dialog (name + city) -------------------------------
const editDialog = useDialog<Chapter>();
const editName = ref<string>("");
const editCity = ref<{ city: string | null; city_lat: number | null; city_lon: number | null }>({
  city: null,
  city_lat: null,
  city_lon: null,
});

function openEditChapter(a: Chapter) {
  editName.value = a.name;
  editCity.value = { city: a.city, city_lat: a.city_lat, city_lon: a.city_lon };
  editDialog.openWith(a);
}

async function submitEditChapter() {
  const target = editDialog.target.value;
  if (!target) return;
  const trimmed = editName.value.trim();
  if (!trimmed) {
    toasts.warn(t("chapters.fillName"));
    return;
  }
  try {
    await editDialog.submit(async () => {
      await updateChapter.mutateAsync({
        id: target.id,
        payload: {
          name: trimmed,
          city: editCity.value.city,
          city_lat: editCity.value.city_lat,
          city_lon: editCity.value.city_lon,
        },
      });
      toasts.success(t("chapters.editedToast"));
    });
  } catch (e) {
    toasts.error(e instanceof Error ? e.message : t("chapters.editFail"));
  }
}

// --- Delete-chapter dialog (with optional reassignment) --------------
const deleteDialog = useDialog<Chapter>();
const deleteUsage = ref<{ users: number; events: number }>({ users: 0, events: 0 });
const deleteReassignUsersTo = ref<Chapter | null>(null);
const deleteReassignEventsTo = ref<Chapter | null>(null);
// Id of the chapter whose usage we're currently fetching, so the
// trash icon shows a spinner instead of looking frozen on slow
// connections (UX principle 11: keep the feedback gap closed).
const usageLoadingFor = ref<string | null>(null);

const otherChapters = computed(() =>
  chapters.value.filter((a) => a.id !== deleteDialog.target.value?.id),
);

async function onPickedChapterFromAddBar(a: Chapter) {
  if (!a.archived) return;
  try {
    await restoreChapter.mutateAsync(a.id);
    toasts.success(t("chapters.restoredToast", { name: a.name }));
  } catch {
    toasts.error(t("chapters.restoreFail"));
  }
}

function normaliseChapterName(name: string): string {
  // Mirror backend services.chapters.normalise_name — strip + collapse
  // internal whitespace so " Den   Haag " matches "Den Haag" exactly.
  return name.trim().split(/\s+/).join(" ");
}

async function onCreateFromAddBar(name: string) {
  // If the typed name exactly matches a soft-deleted chapter
  // (whitespace-normalised + case-insensitive), Enter restores that
  // one rather than creating a duplicate. Without this branch the
  // dupe-name guard would block the create, and the archived chapter
  // would be permanently unreachable from the keyboard.
  try {
    const normalised = normaliseChapterName(name);
    // Refresh the include-archived cache and search it for a
    // soft-deleted match — the active-only list (``chaptersQuery``)
    // never carries archived rows.
    const withArchived = await chaptersWithArchivedQuery.refetch();
    const lower = normalised.toLowerCase();
    const archivedMatch = (withArchived.data ?? []).find(
      (a) => a.archived && a.name.toLowerCase() === lower,
    );
    if (archivedMatch) {
      await restoreChapter.mutateAsync(archivedMatch.id);
      toasts.success(t("chapters.restoredToast", { name: archivedMatch.name }));
      return;
    }
    await createChapter.mutateAsync(normalised);
    toasts.success(t("chapters.createdToast", { name: normalised }));
  } catch {
    toasts.error(t("chapters.createFail"));
  }
}

async function openDeleteDialog(a: Chapter) {
  deleteReassignUsersTo.value = null;
  deleteReassignEventsTo.value = null;
  usageLoadingFor.value = a.id;
  try {
    deleteUsage.value = await getChapterUsage(a.id);
  } catch {
    deleteUsage.value = { users: 0, events: 0 };
  } finally {
    usageLoadingFor.value = null;
  }
  deleteDialog.openWith(a);
}

async function submitDelete() {
  const target = deleteDialog.target.value;
  if (!target) return;
  try {
    await deleteDialog.submit(async () => {
      await archiveChapter.mutateAsync({
        id: target.id,
        reassign: {
          users: deleteReassignUsersTo.value?.id ?? null,
          events: deleteReassignEventsTo.value?.id ?? null,
        },
      });
      toasts.success(t("chapters.archivedToast"));
      // Reassignment changes user→chapter membership server-side;
      // invalidate so the Users page refetches on next visit.
      void qc.invalidateQueries({ queryKey: ["users"] });
    });
  } catch {
    toasts.error(t("chapters.archiveFail"));
  }
}
</script>

<template>
  <AppHeader />
  <div class="container stack">
    <h1>{{ t("chapters.title") }}</h1>
    <p class="muted">{{ t("chapters.intro") }}</p>

    <AppCard>
      <AppSkeleton v-if="!loaded" :rows="3" />
      <template v-else>
        <ChapterPicker
        :placeholder="t('chapters.addPlaceholder')"
        :archived-only="true"
        :disabled="!canManageChapters"
        leading-icon="pi pi-plus"
        @pick="onPickedChapterFromAddBar"
        @create="onCreateFromAddBar"
      />
      <EditableList
        :items="chapters"
        :item-label="(a: Chapter) => a.name"
        :item-key="(a: Chapter) => a.id"
        :loading-key="usageLoadingFor"
        :readonly="!canManageChapters"
        @remove="openDeleteDialog"
      >
        <template #row="{ item }">
          <div class="chapter-row">
            <span class="chapter-name">
              {{ (item as Chapter).name }}
              <span v-if="(item as Chapter).city" class="muted chapter-city">
                · {{ (item as Chapter).city }}
              </span>
            </span>
            <Button
              icon="pi pi-pencil"
              size="small"
              severity="secondary"
              text
              :disabled="!canManageChapters"
              :aria-label="t('common.edit')"
              @click="openEditChapter(item as Chapter)"
            />
          </div>
        </template>
      </EditableList>
      </template>
    </AppCard>

    <AppDialog
      v-model:visible="deleteDialog.open.value"
      :header="t('chapters.deleteDialogTitle', { name: deleteDialog.target.value?.name ?? '' })"
      width="480px"
    >
      <p class="muted dialog-text">{{ t("chapters.deleteDialogBody") }}</p>
      <label v-if="deleteUsage.users > 0" class="reassign-label">
        {{ t("chapters.deleteUsersLabel", { n: deleteUsage.users }) }}
        <Select
          v-model="deleteReassignUsersTo"
          :options="otherChapters"
          option-label="name"
          show-clear
          :placeholder="t('chapters.deleteLeaveOrphaned')"
          fluid
        />
      </label>
      <label v-if="deleteUsage.events > 0" class="reassign-label">
        {{ t("chapters.deleteEventsLabel", { n: deleteUsage.events }) }}
        <Select
          v-model="deleteReassignEventsTo"
          :options="otherChapters"
          option-label="name"
          show-clear
          :placeholder="t('chapters.deleteLeaveOrphaned')"
          fluid
        />
      </label>
      <p v-if="deleteUsage.users === 0 && deleteUsage.events === 0" class="muted dialog-text">
        {{ t("chapters.deleteNoDeps") }}
      </p>
      <template #footer>
        <Button :label="t('common.cancel')" severity="secondary" text @click="deleteDialog.close()" />
        <Button :label="t('chapters.archive')" :loading="deleteDialog.submitting.value" @click="submitDelete" />
      </template>
    </AppDialog>

    <AppDialog
      v-model:visible="editDialog.open.value"
      :header="t('chapters.editDialogTitle', { name: editDialog.target.value?.name ?? '' })"
    >
      <p class="muted dialog-text">{{ t("chapters.editDialogBody") }}</p>
      <InputText v-model="editName" :placeholder="t('chapters.namePlaceholder')" fluid />
      <CityPicker v-model="editCity" :placeholder="t('chapters.cityPlaceholder')" />
      <template #footer>
        <Button :label="t('common.cancel')" severity="secondary" text @click="editDialog.close()" />
        <Button :label="t('common.save')" :loading="editDialog.submitting.value" @click="submitEditChapter" />
      </template>
    </AppDialog>
  </div>
</template>

<style scoped>
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
