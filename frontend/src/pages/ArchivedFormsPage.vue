<script setup lang="ts">
import Button from "primevue/button";
import { computed, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute, useRouter } from "vue-router";
import AppCard from "@/components/AppCard.vue";
import ListPageView from "@/components/ListPageView.vue";
import {
  type FormOut,
  useArchivedForms,
  useDeleteForm,
  useRestoreForm,
} from "@/composables/useForms";
import { useGuardedMutation } from "@/composables/useGuardedMutation";
import { useToasts } from "@/lib/toasts";
import { useAuthStore } from "@/stores/auth";

const { t } = useI18n();
const toasts = useToasts();
const auth = useAuthStore();
const router = useRouter();
const route = useRoute();

const chapterFilter = computed<string | null>(() => {
  const v = route.query.chapter;
  return typeof v === "string" && v ? v : null;
});

function setChapterFilter(value: string | null) {
  void router.replace({
    query: { ...route.query, chapter: value ?? undefined },
  });
}

const chapterOptions = computed(() => auth.user?.chapters ?? []);

const archivedQuery = useArchivedForms({ chapterId: chapterFilter });
const archived = computed<FormOut[]>(() => archivedQuery.data.value ?? []);
const restoreMutation = useRestoreForm();
const deleteMutation = useDeleteForm();

const askDelete = useGuardedMutation(deleteMutation, (f: FormOut) => ({
  vars: f.id,
  ok: t("forms.archived.deleteOk", { name: f.name }),
  fail: t("forms.archived.deleteFail"),
  confirm: {
    header: t("forms.archived.deleteConfirmTitle"),
    message: t("forms.archived.deleteConfirmBody", { name: f.name }),
    icon: "pi pi-exclamation-triangle",
    rejectLabel: t("common.cancel"),
    acceptLabel: t("forms.archived.delete"),
  },
}));

watch(archivedQuery.isError, (isError) => {
  if (isError) toasts.error(t("forms.archived.loadFailed"));
});

const loaded = computed(() => !archivedQuery.isPending.value);

async function restore(f: FormOut) {
  try {
    await restoreMutation.mutateAsync(f.id);
    toasts.success(t("forms.archived.restored", { name: f.name }));
  } catch {
    toasts.error(t("forms.archived.restoreFail"));
  }
}
</script>

<template>
  <ListPageView
    :title="t('forms.archived.title')"
    :intro="t('forms.archived.intro')"
    :items="archived"
    :loaded="loaded"
    :chapter-filter="chapterFilter"
    :chapter-options="chapterOptions"
    :search-placeholder="t('forms.archived.searchPlaceholder')"
    :search-keys="(f: FormOut) => [f.name]"
    :empty-copy="t('forms.archived.empty')"
    :no-matches-copy="t('forms.archived.noMatches')"
    :skeleton-rows="2"
    @update:chapter-filter="setChapterFilter"
  >
    <template #row="{ item: f }">
      <AppCard :stack="false" class="row">
        <div>
          <h3>
            {{ f.name }}
            <span v-if="f.chapter_name" class="event-chapter-chip">{{ f.chapter_name }}</span>
          </h3>
        </div>
        <div class="row-actions">
          <Button :label="t('forms.archived.restore')" icon="pi pi-replay" size="small" severity="secondary" @click="restore(f)" />
          <Button
            icon="pi pi-trash"
            size="small"
            severity="secondary"
            text
            v-tooltip.top="t('forms.archived.delete')"
            :aria-label="t('forms.archived.delete')"
            @click="askDelete(f)"
          />
        </div>
      </AppCard>
    </template>
  </ListPageView>
</template>

<style scoped>
.row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
}
.row h3 { margin: 0; }
.row-actions {
  display: flex;
  align-items: center;
  gap: 0.25rem;
}
.event-chapter-chip {
  display: inline-flex;
  align-items: center;
  margin-left: 0.5rem;
  padding: 0.125rem 0.5rem;
  border-radius: 999px;
  background: var(--brand-surface-subtle, rgba(0, 0, 0, 0.05));
  color: var(--brand-text-muted);
  font-size: 0.75rem;
  white-space: nowrap;
  vertical-align: baseline;
}
</style>
