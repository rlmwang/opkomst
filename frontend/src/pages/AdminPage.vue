<script setup lang="ts">
import Button from "primevue/button";
import Tag from "primevue/tag";
import { useToast } from "primevue/usetoast";
import { onMounted } from "vue";
import AppHeader from "@/components/AppHeader.vue";
import { useAdminStore } from "@/stores/admin";

const admin = useAdminStore();
const toast = useToast();

onMounted(async () => {
  try {
    await admin.fetchUsers();
  } catch {
    toast.add({ severity: "error", summary: "Kon gebruikers niet laden", life: 3000 });
  }
});

async function approve(userId: string) {
  try {
    await admin.approve(userId);
    toast.add({ severity: "success", summary: "Goedgekeurd", life: 2000 });
  } catch {
    toast.add({ severity: "error", summary: "Goedkeuren mislukt", life: 3000 });
  }
}

async function promote(userId: string) {
  try {
    await admin.promote(userId);
    toast.add({ severity: "success", summary: "Tot admin gepromoveerd", life: 2000 });
  } catch {
    toast.add({ severity: "error", summary: "Promoveren mislukt", life: 3000 });
  }
}
</script>

<template>
  <AppHeader />
  <div class="container stack">
    <h1>Admin — gebruikers</h1>
    <div v-if="admin.users.length === 0" class="card">
      <p class="muted">Geen gebruikers.</p>
    </div>
    <div v-for="u in admin.users" :key="u.id" class="card user-row">
      <div>
        <strong>{{ u.name }}</strong>
        <span class="muted"> · {{ u.email }}</span>
        <div class="tags">
          <Tag :value="u.role" :severity="u.role === 'admin' ? 'danger' : 'secondary'" />
          <Tag v-if="!u.is_approved" value="in afwachting" severity="warn" />
        </div>
      </div>
      <div class="actions">
        <Button v-if="!u.is_approved" label="Goedkeuren" size="small" @click="approve(u.id)" />
        <Button
          v-if="u.is_approved && u.role !== 'admin'"
          label="Maak admin"
          size="small"
          severity="secondary"
          @click="promote(u.id)"
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
