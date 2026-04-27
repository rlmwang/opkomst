<script setup lang="ts">
import Button from "primevue/button";
import Dialog from "primevue/dialog";
import InputText from "primevue/inputtext";
import Select from "primevue/select";
import Tag from "primevue/tag";
import ToggleSwitch from "primevue/toggleswitch";
import { useToast } from "primevue/usetoast";
import { computed, nextTick, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import AfdelingPicker from "@/components/AfdelingPicker.vue";
import AppHeader from "@/components/AppHeader.vue";
import EditableList from "@/components/EditableList.vue";
import { type Afdeling, useAfdelingenStore } from "@/stores/afdelingen";
import { useAdminStore } from "@/stores/admin";
import { type User, useAuthStore } from "@/stores/auth";

const { t } = useI18n();
const admin = useAdminStore();
const auth = useAuthStore();
const afdelingen = useAfdelingenStore();
const toast = useToast();

// --- Approve / change-chapter dialog ---------------------------------
type AssignMode = "approve" | "assign";
const assignDialogOpen = ref(false);
const assignDialogMode = ref<AssignMode>("approve");
const assignTargetUser = ref<User | null>(null);
const assignDialogPick = ref<Afdeling | null>(null);
const assignDialogSubmitting = ref(false);

// Lookup chapter name reactively from the store so renames flow into
// every user row without a refetch.
function chapterLabelFor(u: User): string {
  if (!u.afdeling_id) return t("admin.noChapter");
  return afdelingen.all.find((a) => a.id === u.afdeling_id)?.name ?? u.afdeling_name ?? t("admin.noChapter");
}

// --- Inline rename for a chapter row ---------------------------------
const renamingId = ref<string | null>(null);
const renameDraft = ref<string>("");

function startRename(a: Afdeling) {
  renamingId.value = a.id;
  renameDraft.value = a.name;
  // Focus the input on the next tick (after Vue swaps the DOM).
  nextTick(() => {
    const el = document.getElementById(`rename-input-${a.id}`) as HTMLInputElement | null;
    el?.focus();
    el?.select();
  });
}

function cancelRename() {
  renamingId.value = null;
  renameDraft.value = "";
}

async function commitRename(a: Afdeling) {
  const name = renameDraft.value.trim();
  if (!name || name === a.name) {
    cancelRename();
    return;
  }
  try {
    await afdelingen.rename(a.id, name);
    toast.add({ severity: "success", summary: t("afdelingen.renamedToast"), life: 2000 });
    cancelRename();
  } catch (e) {
    toast.add({
      severity: "error",
      summary: e instanceof Error ? e.message : t("afdelingen.renameFail"),
      life: 3000,
    });
  }
}

// --- Delete-chapter dialog (with optional reassignment) --------------
const deleteDialogOpen = ref(false);
const deleteTarget = ref<Afdeling | null>(null);
const deleteUsage = ref<{ users: number; events: number }>({ users: 0, events: 0 });
const deleteReassignUsersTo = ref<Afdeling | null>(null);
const deleteReassignEventsTo = ref<Afdeling | null>(null);
const deleteSubmitting = ref(false);

const otherChapters = computed(() =>
  afdelingen.all.filter((a) => a.id !== deleteTarget.value?.id),
);

onMounted(async () => {
  try {
    await Promise.all([admin.fetchUsers(), afdelingen.fetchAll()]);
  } catch {
    toast.add({ severity: "error", summary: t("admin.loadFailed"), life: 3000 });
  }
});

function openApprove(u: User) {
  assignDialogMode.value = "approve";
  assignTargetUser.value = u;
  assignDialogPick.value = null;
  assignDialogOpen.value = true;
}

function openAssign(u: User) {
  assignDialogMode.value = "assign";
  assignTargetUser.value = u;
  assignDialogPick.value = afdelingen.all.find((a) => a.id === u.afdeling_id) ?? null;
  assignDialogOpen.value = true;
}

async function submitAssignDialog() {
  if (!assignTargetUser.value || !assignDialogPick.value) return;
  assignDialogSubmitting.value = true;
  try {
    if (assignDialogMode.value === "approve") {
      await admin.approve(assignTargetUser.value.id, assignDialogPick.value.id);
      toast.add({ severity: "success", summary: t("admin.approveOk"), life: 2000 });
    } else {
      await admin.assignAfdeling(assignTargetUser.value.id, assignDialogPick.value.id);
      toast.add({ severity: "success", summary: t("admin.assignOk"), life: 2000 });
    }
    assignDialogOpen.value = false;
  } catch {
    toast.add({
      severity: "error",
      summary: assignDialogMode.value === "approve" ? t("admin.approveFail") : t("admin.assignFail"),
      life: 3000,
    });
  } finally {
    assignDialogSubmitting.value = false;
  }
}

async function toggleAdmin(u: User, on: boolean) {
  try {
    if (on) {
      await admin.promote(u.id);
      toast.add({
        severity: "success",
        summary: t("admin.promoteOk", { name: u.name }),
        life: 2000,
      });
    } else {
      await admin.demote(u.id);
      toast.add({
        severity: "success",
        summary: t("admin.demoteOk", { name: u.name }),
        life: 2000,
      });
    }
  } catch {
    toast.add({
      severity: "error",
      summary: on ? t("admin.promoteFail") : t("admin.demoteFail"),
      life: 3000,
    });
  }
}

async function onPickedAfdelingFromAddBar(a: Afdeling) {
  if (!a.archived) return;
  try {
    await afdelingen.restore(a.id);
    toast.add({
      severity: "success",
      summary: t("afdelingen.restoredToast", { name: a.name }),
      life: 2000,
    });
  } catch {
    toast.add({ severity: "error", summary: t("afdelingen.restoreFail"), life: 3000 });
  }
}

async function onCreateFromAddBar(name: string) {
  try {
    await afdelingen.create(name);
    toast.add({
      severity: "success",
      summary: t("afdelingen.createdToast", { name }),
      life: 2000,
    });
  } catch {
    toast.add({ severity: "error", summary: t("afdelingen.createFail"), life: 3000 });
  }
}

async function openDeleteDialog(a: Afdeling) {
  deleteTarget.value = a;
  deleteReassignUsersTo.value = null;
  deleteReassignEventsTo.value = null;
  try {
    deleteUsage.value = await afdelingen.getUsage(a.id);
  } catch {
    deleteUsage.value = { users: 0, events: 0 };
  }
  deleteDialogOpen.value = true;
}

async function submitDelete() {
  if (!deleteTarget.value) return;
  deleteSubmitting.value = true;
  try {
    await afdelingen.archive(deleteTarget.value.id, {
      users: deleteReassignUsersTo.value?.id ?? null,
      events: deleteReassignEventsTo.value?.id ?? null,
    });
    toast.add({ severity: "success", summary: t("afdelingen.archivedToast"), life: 2000 });
    // Refetch users so chips reflect the reassignment.
    await admin.fetchUsers();
    deleteDialogOpen.value = false;
  } catch {
    toast.add({ severity: "error", summary: t("afdelingen.archiveFail"), life: 3000 });
  } finally {
    deleteSubmitting.value = false;
  }
}
</script>

<template>
  <AppHeader />
  <div class="container stack">
    <h1>{{ t("admin.title") }}</h1>

    <div class="card stack">
      <h2>{{ t("afdelingen.title") }}</h2>
      <p class="muted">{{ t("afdelingen.intro") }}</p>
      <EditableList
        :items="afdelingen.all"
        :item-label="(a: Afdeling) => a.name"
        :item-key="(a: Afdeling) => a.id"
        @remove="openDeleteDialog"
      >
        <template #row="{ item }">
          <div class="chapter-row">
            <template v-if="renamingId === (item as Afdeling).id">
              <InputText
                :id="`rename-input-${(item as Afdeling).id}`"
                v-model="renameDraft"
                size="small"
                fluid
                @keyup.enter="commitRename(item as Afdeling)"
                @keyup.esc="cancelRename"
              />
              <Button
                icon="pi pi-check"
                size="small"
                severity="secondary"
                text
                :aria-label="t('common.save')"
                @click="commitRename(item as Afdeling)"
              />
              <Button
                icon="pi pi-times"
                size="small"
                severity="secondary"
                text
                :aria-label="t('common.cancel')"
                @click="cancelRename"
              />
            </template>
            <template v-else>
              <span class="chapter-name">{{ (item as Afdeling).name }}</span>
              <Button
                icon="pi pi-pencil"
                size="small"
                severity="secondary"
                text
                :aria-label="t('common.edit')"
                @click="startRename(item as Afdeling)"
              />
            </template>
          </div>
        </template>
        <template #add>
          <AfdelingPicker
            :placeholder="t('afdelingen.addPlaceholder')"
            :archived-only="true"
            @pick="onPickedAfdelingFromAddBar"
            @create="onCreateFromAddBar"
          />
        </template>
      </EditableList>
    </div>

    <div class="card stack">
      <h2>{{ t("admin.usersTitle") }}</h2>
      <p class="muted">{{ t("admin.usersIntro") }}</p>
      <div v-if="admin.users.length === 0">
        <p class="muted">{{ t("admin.empty") }}</p>
      </div>
      <div v-for="u in admin.users" :key="u.id" class="user-row">
        <div class="user-main">
          <strong>{{ u.name }}</strong>
          <span class="muted"> · {{ u.email }}</span>
          <div class="tags">
            <Tag v-if="!u.is_approved" :value="t('admin.pending')" severity="warn" />
          </div>
        </div>
        <div class="actions">
          <Button
            v-if="!u.is_approved"
            :label="t('admin.approve')"
            size="small"
            @click="openApprove(u)"
          />
          <!-- Single chip-button: shows the chapter, opens the assign
               dialog on click. The label resolves from the afdelingen
               store rather than the cached u.afdeling_name so renames
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
        </div>
      </div>
    </div>

    <Dialog
      v-model:visible="assignDialogOpen"
      :header="assignDialogMode === 'approve' ? t('admin.approveDialogTitle') : t('admin.assignDialogTitle')"
      modal
      :style="{ width: '420px' }"
    >
      <p class="dialog-body">
        {{
          assignDialogMode === "approve"
            ? t("admin.approveDialogBody", { name: assignTargetUser?.name ?? "" })
            : t("admin.assignDialogBody", { name: assignTargetUser?.name ?? "" })
        }}
      </p>
      <Select
        v-model="assignDialogPick"
        :options="afdelingen.all"
        option-label="name"
        :placeholder="t('afdelingen.pickerPlaceholder')"
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
    </Dialog>

    <Dialog
      v-model:visible="deleteDialogOpen"
      :header="t('afdelingen.deleteDialogTitle', { name: deleteTarget?.name ?? '' })"
      modal
      :style="{ width: '480px' }"
    >
      <div v-if="deleteUsage.users > 0" class="reassign-row">
        <label>
          {{ t("afdelingen.deleteUsersLabel", { n: deleteUsage.users }) }}
          <Select
            v-model="deleteReassignUsersTo"
            :options="otherChapters"
            option-label="name"
            show-clear
            :placeholder="t('afdelingen.deleteLeaveOrphaned')"
            fluid
          />
        </label>
      </div>
      <div v-if="deleteUsage.events > 0" class="reassign-row">
        <label>
          {{ t("afdelingen.deleteEventsLabel", { n: deleteUsage.events }) }}
          <Select
            v-model="deleteReassignEventsTo"
            :options="otherChapters"
            option-label="name"
            show-clear
            :placeholder="t('afdelingen.deleteLeaveOrphaned')"
            fluid
          />
        </label>
      </div>
      <p v-if="deleteUsage.users === 0 && deleteUsage.events === 0" class="muted small">
        {{ t("afdelingen.deleteNoDeps") }}
      </p>
      <template #footer>
        <Button :label="t('common.cancel')" severity="secondary" text @click="deleteDialogOpen = false" />
        <Button
          :label="t('afdelingen.archive')"
          severity="danger"
          :loading="deleteSubmitting"
          @click="submitDelete"
        />
      </template>
    </Dialog>
  </div>
</template>

<style scoped>
.user-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
  padding: 0.625rem 0.5rem;
  border-radius: 6px;
  transition: background 120ms ease;
}
.user-row:hover {
  background: var(--brand-bg);
}
.user-main {
  min-width: 0;
}
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
.admin-toggle {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  font-size: 0.875rem;
  color: var(--brand-text-muted);
  cursor: pointer;
}
.admin-toggle.disabled {
  cursor: not-allowed;
  opacity: 0.65;
}
.dialog-body {
  margin: 0 0 1rem;
}
.reassign-row {
  margin-bottom: 1rem;
}
.reassign-row label {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  font-size: 0.875rem;
  color: var(--brand-text);
}
.small {
  font-size: 0.875rem;
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
