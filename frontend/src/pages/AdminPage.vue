<script setup lang="ts">
import Button from "primevue/button";
import Dialog from "primevue/dialog";
import InputText from "primevue/inputtext";
import Tag from "primevue/tag";
import { useConfirm } from "primevue/useconfirm";
import { useToast } from "primevue/usetoast";
import { onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import AfdelingPicker from "@/components/AfdelingPicker.vue";
import AppHeader from "@/components/AppHeader.vue";
import EditableList from "@/components/EditableList.vue";
import { type Afdeling, useAfdelingenStore } from "@/stores/afdelingen";
import { useAdminStore } from "@/stores/admin";
import { useAuthStore } from "@/stores/auth";

const { t } = useI18n();
const admin = useAdminStore();
const auth = useAuthStore();
const afdelingen = useAfdelingenStore();
const toast = useToast();
const confirm = useConfirm();

// Approve / assign dialog state. Re-used for both first-time approval
// and admin-driven afdeling moves later.
type DialogMode = "approve" | "assign";
const dialogOpen = ref(false);
const dialogMode = ref<DialogMode>("approve");
const dialogTargetId = ref<string | null>(null);
const dialogTargetName = ref<string>("");
const dialogPick = ref<Afdeling | null>(null);
const dialogSubmitting = ref(false);

// Add-afdeling input state. Lives on this page for now (the only
// surface that can mutate afdelingen).
const newAfdelingPick = ref<Afdeling | null>(null);
const newAfdelingName = ref("");

onMounted(async () => {
  try {
    await Promise.all([admin.fetchUsers(), afdelingen.fetchAll()]);
  } catch {
    toast.add({ severity: "error", summary: t("admin.loadFailed"), life: 3000 });
  }
});

function openApprove(userId: string, name: string) {
  dialogMode.value = "approve";
  dialogTargetId.value = userId;
  dialogTargetName.value = name;
  dialogPick.value = null;
  dialogOpen.value = true;
}

function openAssign(userId: string, name: string, current: Afdeling | null) {
  dialogMode.value = "assign";
  dialogTargetId.value = userId;
  dialogTargetName.value = name;
  dialogPick.value = current;
  dialogOpen.value = true;
}

async function submitDialog() {
  if (!dialogTargetId.value || !dialogPick.value) return;
  dialogSubmitting.value = true;
  try {
    if (dialogMode.value === "approve") {
      await admin.approve(dialogTargetId.value, dialogPick.value.id);
      toast.add({ severity: "success", summary: t("admin.approveOk"), life: 2000 });
    } else {
      await admin.assignAfdeling(dialogTargetId.value, dialogPick.value.id);
      toast.add({ severity: "success", summary: t("admin.assignOk"), life: 2000 });
    }
    dialogOpen.value = false;
  } catch {
    toast.add({
      severity: "error",
      summary: dialogMode.value === "approve" ? t("admin.approveFail") : t("admin.assignFail"),
      life: 3000,
    });
  } finally {
    dialogSubmitting.value = false;
  }
}

async function promote(userId: string) {
  try {
    await admin.promote(userId);
    toast.add({ severity: "success", summary: t("admin.promoteOk"), life: 2000 });
  } catch {
    toast.add({ severity: "error", summary: t("admin.promoteFail"), life: 3000 });
  }
}

async function demote(userId: string) {
  try {
    await admin.demote(userId);
    toast.add({ severity: "success", summary: t("admin.demoteOk"), life: 2000 });
  } catch {
    toast.add({ severity: "error", summary: t("admin.demoteFail"), life: 3000 });
  }
}

async function addOrRestoreAfdeling() {
  // The picker emits a full Afdeling when the user selects from the
  // suggestions; if it's archived we restore, otherwise it's a no-op
  // (already exists). When the input has free text and no pick, we
  // create a new one.
  if (newAfdelingPick.value) {
    const picked = newAfdelingPick.value;
    if (picked.archived) {
      try {
        await afdelingen.restore(picked.id);
        toast.add({
          severity: "success",
          summary: t("afdelingen.restoredToast", { name: picked.name }),
          life: 2000,
        });
      } catch {
        toast.add({ severity: "error", summary: t("afdelingen.restoreFail"), life: 3000 });
      }
    }
    newAfdelingPick.value = null;
    newAfdelingName.value = "";
    return;
  }
  const name = newAfdelingName.value.trim();
  if (!name) return;
  try {
    await afdelingen.create(name);
    toast.add({ severity: "success", summary: t("afdelingen.createdToast", { name }), life: 2000 });
    newAfdelingName.value = "";
  } catch {
    toast.add({ severity: "error", summary: t("afdelingen.createFail"), life: 3000 });
  }
}

function askArchiveAfdeling(a: Afdeling) {
  confirm.require({
    header: t("afdelingen.archiveConfirmTitle"),
    message: t("afdelingen.archiveConfirmBody", { name: a.name }),
    icon: "pi pi-exclamation-triangle",
    rejectLabel: t("common.cancel"),
    acceptLabel: t("afdelingen.archive"),
    acceptProps: { severity: "danger" },
    accept: async () => {
      try {
        await afdelingen.archive(a.id);
        toast.add({ severity: "success", summary: t("afdelingen.archivedToast"), life: 2000 });
      } catch {
        toast.add({ severity: "error", summary: t("afdelingen.archiveFail"), life: 3000 });
      }
    },
  });
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
        @remove="askArchiveAfdeling"
      >
        <template #row="{ item }">
          <span>{{ (item as Afdeling).name }}</span>
        </template>
        <template #add>
          <AfdelingPicker
            v-model="newAfdelingPick"
            :show-archived="true"
            :placeholder="t('afdelingen.addPlaceholder')"
          />
          <InputText
            v-model="newAfdelingName"
            :placeholder="t('afdelingen.newName')"
            class="add-name"
            @keydown.enter.prevent="addOrRestoreAfdeling"
          />
          <Button icon="pi pi-plus" size="small" severity="secondary" @click="addOrRestoreAfdeling" />
        </template>
      </EditableList>
    </div>

    <div class="card stack">
      <h2>{{ t("admin.usersTitle") }}</h2>
      <div v-if="admin.users.length === 0">
        <p class="muted">{{ t("admin.empty") }}</p>
      </div>
      <div v-for="u in admin.users" :key="u.id" class="user-row">
        <div>
          <strong>{{ u.name }}</strong>
          <span class="muted"> · {{ u.email }}</span>
          <div class="tags">
            <Tag
              :value="u.role === 'admin' ? t('admin.roleAdmin') : t('admin.roleOrganiser')"
              :severity="u.role === 'admin' ? 'danger' : 'secondary'"
            />
            <Tag v-if="!u.is_approved" :value="t('admin.pending')" severity="warn" />
            <Tag v-if="u.afdeling_name" :value="u.afdeling_name" severity="info" />
          </div>
        </div>
        <div class="actions">
          <Button v-if="!u.is_approved" :label="t('admin.approve')" size="small" @click="openApprove(u.id, u.name)" />
          <Button
            v-if="u.is_approved"
            :label="t('admin.changeAfdeling')"
            size="small"
            severity="secondary"
            text
            @click="
              openAssign(u.id, u.name, u.afdeling_id ? { id: u.afdeling_id, name: u.afdeling_name ?? '', archived: false } : null)
            "
          />
          <Button
            v-if="u.is_approved && u.role !== 'admin'"
            :label="t('admin.promote')"
            size="small"
            severity="secondary"
            @click="promote(u.id)"
          />
          <Button
            v-if="u.role === 'admin' && u.id !== auth.user?.id"
            :label="t('admin.demote')"
            size="small"
            severity="secondary"
            text
            @click="demote(u.id)"
          />
        </div>
      </div>
    </div>

    <Dialog
      v-model:visible="dialogOpen"
      :header="dialogMode === 'approve' ? t('admin.approveDialogTitle') : t('admin.assignDialogTitle')"
      modal
      :style="{ width: '420px' }"
    >
      <p>
        {{ dialogMode === "approve"
          ? t("admin.approveDialogBody", { name: dialogTargetName })
          : t("admin.assignDialogBody", { name: dialogTargetName }) }}
      </p>
      <AfdelingPicker v-model="dialogPick" :placeholder="t('afdelingen.pickerPlaceholder')" />
      <template #footer>
        <Button :label="t('common.cancel')" severity="secondary" text @click="dialogOpen = false" />
        <Button
          :label="dialogMode === 'approve' ? t('admin.approve') : t('admin.assign')"
          :disabled="!dialogPick"
          :loading="dialogSubmitting"
          @click="submitDialog"
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
  padding: 0.625rem 0;
  border-top: 1px solid var(--brand-border);
}
.user-row:first-of-type {
  border-top: none;
  padding-top: 0;
}
.tags {
  display: flex;
  gap: 0.5rem;
  margin-top: 0.5rem;
  flex-wrap: wrap;
}
.actions {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
  justify-content: flex-end;
}
.add-name {
  flex: 1;
}
</style>
