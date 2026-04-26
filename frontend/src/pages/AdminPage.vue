<script setup lang="ts">
import Button from "primevue/button";
import Tag from "primevue/tag";
import { useToast } from "primevue/usetoast";
import { onMounted } from "vue";
import { useI18n } from "vue-i18n";
import AppHeader from "@/components/AppHeader.vue";
import { useAdminStore } from "@/stores/admin";
import { useAuthStore } from "@/stores/auth";

const { t } = useI18n();
const admin = useAdminStore();
const auth = useAuthStore();
const toast = useToast();

onMounted(async () => {
  try {
    await admin.fetchUsers();
  } catch {
    toast.add({ severity: "error", summary: t("admin.loadFailed"), life: 3000 });
  }
});

async function approve(userId: string) {
  try {
    await admin.approve(userId);
    toast.add({ severity: "success", summary: t("admin.approveOk"), life: 2000 });
  } catch {
    toast.add({ severity: "error", summary: t("admin.approveFail"), life: 3000 });
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
</script>

<template>
  <AppHeader />
  <div class="container stack">
    <h1>{{ t("admin.title") }}</h1>
    <div v-if="admin.users.length === 0" class="card">
      <p class="muted">{{ t("admin.empty") }}</p>
    </div>
    <div v-for="u in admin.users" :key="u.id" class="card user-row">
      <div>
        <strong>{{ u.name }}</strong>
        <span class="muted"> · {{ u.email }}</span>
        <div class="tags">
          <Tag
            :value="u.role === 'admin' ? t('admin.roleAdmin') : t('admin.roleOrganiser')"
            :severity="u.role === 'admin' ? 'danger' : 'secondary'"
          />
          <Tag v-if="!u.is_approved" :value="t('admin.pending')" severity="warn" />
        </div>
      </div>
      <div class="actions">
        <Button v-if="!u.is_approved" :label="t('admin.approve')" size="small" @click="approve(u.id)" />
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
</template>

<style scoped>
.user-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
}
.tags {
  display: flex;
  gap: 0.5rem;
  margin-top: 0.5rem;
}
.actions {
  display: flex;
  gap: 0.5rem;
}
</style>
