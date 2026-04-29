<script setup lang="ts">
import Button from "primevue/button";
import InputText from "primevue/inputtext";
import Select from "primevue/select";
import ToggleSwitch from "primevue/toggleswitch";
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";
import ChapterPicker from "@/components/ChapterPicker.vue";
import AppCard from "@/components/AppCard.vue";
import AppDialog from "@/components/AppDialog.vue";
import AppHeader from "@/components/AppHeader.vue";
import AppSkeleton from "@/components/AppSkeleton.vue";
import CityPicker from "@/components/CityPicker.vue";
import EditableList from "@/components/EditableList.vue";
import SearchInput from "@/components/SearchInput.vue";
import {
  useApproveUser,
  useAssignChapter,
  useDemoteUser,
  usePromoteUser,
  useRemoveUser,
  userList,
  useUsers,
} from "@/composables/useAdmin";
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
import { useConfirms } from "@/lib/confirms";
import { useToasts } from "@/lib/toasts";
import { type User, useAuthStore } from "@/stores/auth";

const { t } = useI18n();
const auth = useAuthStore();
const toasts = useToasts();
const confirms = useConfirms();

// Vue Query — server state. Replaces the old admin + chapters
// stores' hand-rolled list mutations.
const usersQuery = useUsers();
const users = userList(usersQuery);
const approveMutation = useApproveUser();
const assignMutation = useAssignChapter();
const promoteMutation = usePromoteUser();
const demoteMutation = useDemoteUser();
const removeMutation = useRemoveUser();

const chaptersQuery = useChapters({ includeArchived: false });
const chapters = chapterList(chaptersQuery);
const createChapter = useCreateChapter();
const updateChapter = useUpdateChapter();
const archiveChapter = useArchiveChapter();
const restoreChapter = useRestoreChapter();

// --- Approve / change-chapter dialog ---------------------------------
type AssignMode = "approve" | "assign";
const assignDialogOpen = ref(false);
const assignDialogMode = ref<AssignMode>("approve");
const assignTargetUser = ref<User | null>(null);
const assignDialogPick = ref<Chapter | null>(null);
const assignDialogSubmitting = ref(false);

// Lookup chapter name reactively from the store so renames flow into
// every user row without a refetch.
function chapterLabelFor(u: User): string {
  if (!u.chapter_id) return t("admin.noChapter");
  return chapters.value.find((a) => a.id === u.chapter_id)?.name ?? u.chapter_name ?? t("admin.noChapter");
}

// --- Edit-chapter dialog (name + city) -------------------------------
const editDialogOpen = ref(false);
const editTarget = ref<Chapter | null>(null);
const editName = ref<string>("");
const editCity = ref<{ city: string | null; city_lat: number | null; city_lon: number | null }>({
  city: null,
  city_lat: null,
  city_lon: null,
});
const editSubmitting = ref(false);

function openEditChapter(a: Chapter) {
  editTarget.value = a;
  editName.value = a.name;
  editCity.value = { city: a.city, city_lat: a.city_lat, city_lon: a.city_lon };
  editDialogOpen.value = true;
}

async function submitEditChapter() {
  if (!editTarget.value) return;
  const target = editTarget.value;
  const trimmed = editName.value.trim();
  if (!trimmed) {
    toasts.warn(t("chapters.fillName"));
    return;
  }
  editSubmitting.value = true;
  try {
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
    editDialogOpen.value = false;
  } catch (e) {
    toasts.error(e instanceof Error ? e.message : t("chapters.editFail"));
  } finally {
    editSubmitting.value = false;
  }
}

// --- Delete-chapter dialog (with optional reassignment) --------------
const deleteDialogOpen = ref(false);
const deleteTarget = ref<Chapter | null>(null);
const deleteUsage = ref<{ users: number; events: number }>({ users: 0, events: 0 });
const deleteReassignUsersTo = ref<Chapter | null>(null);
const deleteReassignEventsTo = ref<Chapter | null>(null);
const deleteSubmitting = ref(false);

const otherChapters = computed(() =>
  chapters.value.filter((a) => a.id !== deleteTarget.value?.id),
);

// --- User search -----------------------------------------------------
const userQuery = ref("");

const filteredUsers = computed(() => {
  const q = userQuery.value.trim().toLowerCase();
  if (!q) return users.value;
  return users.value.filter((u) => {
    const chapter = chapterLabelFor(u).toLowerCase();
    return (
      u.name.toLowerCase().includes(q) ||
      u.email.toLowerCase().includes(q) ||
      chapter.includes(q)
    );
  });
});

const loaded = computed(() => !usersQuery.isLoading.value);

// chaptersQuery + usersQuery auto-fetch on first use; no need to
// kick them off here. ``isLoading`` reflects the in-flight status
// for the skeleton.

function openApprove(u: User) {
  assignDialogMode.value = "approve";
  assignTargetUser.value = u;
  assignDialogPick.value = null;
  assignDialogOpen.value = true;
}

function openAssign(u: User) {
  assignDialogMode.value = "assign";
  assignTargetUser.value = u;
  assignDialogPick.value = chapters.value.find((a) => a.id === u.chapter_id) ?? null;
  assignDialogOpen.value = true;
}

async function submitAssignDialog() {
  if (!assignTargetUser.value || !assignDialogPick.value) return;
  assignDialogSubmitting.value = true;
  try {
    const vars = {
      userId: assignTargetUser.value.id,
      chapterId: assignDialogPick.value.id,
    };
    if (assignDialogMode.value === "approve") {
      await approveMutation.mutateAsync(vars);
      toasts.success(t("admin.approveOk"));
    } else {
      await assignMutation.mutateAsync(vars);
      toasts.success(t("admin.assignOk"));
    }
    assignDialogOpen.value = false;
  } catch {
    toasts.error(assignDialogMode.value === "approve" ? t("admin.approveFail") : t("admin.assignFail"));
  } finally {
    assignDialogSubmitting.value = false;
  }
}

function askDeleteUser(u: User) {
  confirms.ask({
    header: t("admin.deleteUserConfirmTitle"),
    message: t("admin.deleteUserConfirmBody", { name: u.name }),
    icon: "pi pi-exclamation-triangle",
    rejectLabel: t("common.cancel"),
    acceptLabel: t("admin.deleteUser"),
    accept: async () => {
      try {
        await removeMutation.mutateAsync(u.id);
        toasts.success(t("admin.deleteUserOk", { name: u.name }));
      } catch {
        toasts.error(t("admin.deleteUserFail"));
      }
    },
  });
}

async function toggleAdmin(u: User, on: boolean) {
  try {
    if (on) {
      await promoteMutation.mutateAsync(u.id);
      toasts.success(t("admin.promoteOk", { name: u.name }));
    } else {
      await demoteMutation.mutateAsync(u.id);
      toasts.success(t("admin.demoteOk", { name: u.name }));
    }
  } catch {
    toasts.error(on ? t("admin.promoteFail") : t("admin.demoteFail"));
  }
}

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
    // Refresh the cache then search the cached list for an archived
    // match. Cheaper than a second HTTP call now that the include-
    // archived list is one query away.
    const archivedQuery = await chaptersQuery.refetch();
    const lower = normalised.toLowerCase();
    const archivedMatch = (archivedQuery.data ?? []).find(
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
  deleteTarget.value = a;
  deleteReassignUsersTo.value = null;
  deleteReassignEventsTo.value = null;
  try {
    deleteUsage.value = await getChapterUsage(a.id);
  } catch {
    deleteUsage.value = { users: 0, events: 0 };
  }
  deleteDialogOpen.value = true;
}

async function submitDelete() {
  if (!deleteTarget.value) return;
  deleteSubmitting.value = true;
  try {
    await archiveChapter.mutateAsync({
      id: deleteTarget.value.id,
      reassign: {
        users: deleteReassignUsersTo.value?.id ?? null,
        events: deleteReassignEventsTo.value?.id ?? null,
      },
    });
    toasts.success(t("chapters.archivedToast"));
    // Refetch users so chips reflect the reassignment.
    await usersQuery.refetch();
    deleteDialogOpen.value = false;
  } catch {
    toasts.error(t("chapters.archiveFail"));
  } finally {
    deleteSubmitting.value = false;
  }
}
</script>

<template>
  <AppHeader />
  <div class="container stack">
    <h1>{{ t("admin.title") }}</h1>

    <AppCard>
      <h2>{{ t("chapters.title") }}</h2>
      <p class="muted">{{ t("chapters.intro") }}</p>
      <AppSkeleton v-if="!loaded" :rows="3" />
      <EditableList
        v-else
        :items="chapters"
        :item-label="(a: Chapter) => a.name"
        :item-key="(a: Chapter) => a.id"
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
              :aria-label="t('common.edit')"
              @click="openEditChapter(item as Chapter)"
            />
          </div>
        </template>
        <template #add>
          <ChapterPicker
            :placeholder="t('chapters.addPlaceholder')"
            :archived-only="true"
            @pick="onPickedChapterFromAddBar"
            @create="onCreateFromAddBar"
          />
        </template>
      </EditableList>
    </AppCard>

    <AppCard>
      <h2>{{ t("usersTitle") }}</h2>
      <p class="muted">{{ t("usersIntro") }}</p>
      <AppSkeleton v-if="!loaded" :rows="4" />
      <template v-else>
        <SearchInput
          v-if="users.length > 0"
          v-model="userQuery"
          :placeholder="t('admin.searchPlaceholder')"
        />
        <div v-if="users.length === 0">
          <p class="muted">{{ t("admin.empty") }}</p>
        </div>
        <p v-else-if="filteredUsers.length === 0" class="muted">
          {{ t("admin.noMatches") }}
        </p>
        <div v-for="u in filteredUsers" :key="u.id" class="list-row">
        <div class="list-row-label">
          <strong>{{ u.name }}</strong>
          <span class="muted"> · {{ u.email }}</span>
        </div>
        <div class="actions">
          <Button
            v-if="!u.is_approved"
            :label="t('admin.approve')"
            size="small"
            @click="openApprove(u)"
          />
          <!-- Single chip-button: shows the chapter, opens the assign
               dialog on click. The label resolves from the chapters
               store rather than the cached u.chapter_name so renames
               update reactively without a page refresh. -->
          <Button
            v-if="u.is_approved"
            :label="chapterLabelFor(u)"
            icon="pi pi-pencil"
            icon-pos="right"
            size="small"
            severity="secondary"
            @click="openAssign(u)"
          />
          <label v-if="u.is_approved" class="admin-toggle" :class="{ disabled: u.id === auth.user?.id }">
            <!-- Self-toggle is shown but disabled — users can't flip
                 their own admin off (server enforces too); rendering
                 the same widget keeps the row layout stable. -->
            <ToggleSwitch
              :model-value="u.role === 'admin'"
              :disabled="u.id === auth.user?.id"
              @update:model-value="toggleAdmin(u, $event)"
            />
            <span>{{ t("admin.adminToggle") }}</span>
          </label>
          <Button
            icon="pi pi-trash"
            size="small"
            severity="secondary"
            text
            :disabled="u.id === auth.user?.id"
            :aria-label="t('admin.deleteUser')"
            @click="askDeleteUser(u)"
          />
        </div>
        </div>
      </template>
    </AppCard>

    <AppDialog
      v-model:visible="assignDialogOpen"
      :header="assignDialogMode === 'approve' ? t('admin.approveDialogTitle') : t('admin.assignDialogTitle')"
    >
      <p class="muted dialog-text">
        {{
          assignDialogMode === "approve"
            ? t("admin.approveDialogBody", { name: assignTargetUser?.name ?? "" })
            : t("admin.assignDialogBody", { name: assignTargetUser?.name ?? "" })
        }}
      </p>
      <Select
        v-model="assignDialogPick"
        :options="chapters"
        option-label="name"
        :placeholder="t('chapters.pickerPlaceholder')"
        fluid
      />
      <template #footer>
        <Button :label="t('common.cancel')" severity="secondary" text @click="assignDialogOpen = false" />
        <Button
          :label="assignDialogMode === 'approve' ? t('admin.approve') : t('admin.assign')"
          :disabled="!assignDialogPick"
          :loading="assignDialogSubmitting"
          @click="submitAssignDialog"
        />
      </template>
    </AppDialog>

    <AppDialog
      v-model:visible="deleteDialogOpen"
      :header="t('chapters.deleteDialogTitle', { name: deleteTarget?.name ?? '' })"
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
        <Button :label="t('common.cancel')" severity="secondary" text @click="deleteDialogOpen = false" />
        <Button :label="t('chapters.archive')" :loading="deleteSubmitting" @click="submitDelete" />
      </template>
    </AppDialog>

    <AppDialog
      v-model:visible="editDialogOpen"
      :header="t('chapters.editDialogTitle', { name: editTarget?.name ?? '' })"
    >
      <p class="muted dialog-text">{{ t("chapters.editDialogBody") }}</p>
      <InputText v-model="editName" :placeholder="t('chapters.namePlaceholder')" fluid />
      <CityPicker v-model="editCity" :placeholder="t('chapters.cityPlaceholder')" />
      <template #footer>
        <Button :label="t('common.cancel')" severity="secondary" text @click="editDialogOpen = false" />
        <Button :label="t('common.save')" :loading="editSubmitting" @click="submitEditChapter" />
      </template>
    </AppDialog>
  </div>
</template>

<style scoped>
.tags {
  display: flex;
  gap: 0.5rem;
  margin-top: 0.5rem;
  flex-wrap: wrap;
}
.actions {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
  justify-content: flex-end;
  align-items: center;
}
/* Mobile: the user row's name+email block and the actions cluster
 * each take a full row, with the actions wrapping below the name. */
@media (max-width: 540px) {
  .list-row {
    flex-wrap: wrap;
  }
  .actions {
    justify-content: flex-start;
    width: 100%;
  }
}
.admin-toggle {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  font-size: 0.875rem;
  color: var(--brand-text-muted);
  cursor: pointer;
}
.admin-toggle.disabled {
  cursor: default;
  opacity: 0.65;
}
/* PrimeVue's disabled ToggleSwitch defaults to ``not-allowed``; force
 * the default arrow so hovering the user's own self-toggle doesn't
 * flash a "blocked" cursor. */
.admin-toggle.disabled :deep(.p-toggleswitch) {
  cursor: default;
}
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
