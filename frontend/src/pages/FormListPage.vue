<script setup lang="ts">
import Button from "primevue/button";
import { computed, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute, useRouter } from "vue-router";
import AppCard from "@/components/AppCard.vue";
import AppHeader from "@/components/AppHeader.vue";
import ListPageView from "@/components/ListPageView.vue";
import { type FormOut, formList, useArchiveForm, useFormList } from "@/composables/useForms";
import { useConfirms } from "@/lib/confirms";
import { publicFormUrl } from "@/lib/form-urls";
import { useToasts } from "@/lib/toasts";
import { useAuthStore } from "@/stores/auth";

const { t } = useI18n();
const auth = useAuthStore();
const toasts = useToasts();
const confirms = useConfirms();
const router = useRouter();
const route = useRoute();

// Chapter filter — same URL-param shape as Events so the filter
// survives navigation between active and archived list pages.
const chapterFilter = computed<string | null>(() => {
  const v = route.query.chapter;
  return typeof v === "string" && v ? v : null;
});

function setChapterFilter(value: string | null) {
  void router.replace({
    query: { ...route.query, chapter: value ?? undefined },
  });
}

const formsQuery = useFormList({
  enabled: computed(() => auth.isApproved),
  chapterId: chapterFilter,
});
const forms = formList(formsQuery);
const archiveMutation = useArchiveForm();

const chapterOptions = computed(() => auth.user?.chapters ?? []);

// Pending approval + no-chapters short-circuits — mirror Dashboard
// exactly: neither state has any business showing the list shell.
const noChapters = computed(
  () => auth.isApproved && (auth.user?.chapters?.length ?? 0) === 0,
);

watch(formsQuery.isError, (isError) => {
  if (isError) toasts.error(t("forms.list.loadFailed"));
});

const loaded = computed(() => !auth.isApproved || !formsQuery.isPending.value);

const sortedForms = computed(() =>
  [...forms.value].sort((a, b) => b.created_at.localeCompare(a.created_at)),
);

async function copyLink(slug: string) {
  try {
    await navigator.clipboard.writeText(publicFormUrl(slug));
    toasts.success(t("forms.list.linkCopied"));
  } catch {
    /* clipboard unavailable — user can copy the URL by hand */
  }
}

function askArchive(f: FormOut) {
  confirms.ask({
    header: t("forms.list.archiveConfirmTitle"),
    message: t("forms.list.archiveConfirmBody", { name: f.name }),
    icon: "pi pi-exclamation-triangle",
    rejectLabel: t("common.cancel"),
    acceptLabel: t("forms.list.archive"),
    accept: async () => {
      try {
        await archiveMutation.mutateAsync(f.id);
        toasts.success(t("forms.list.archived"));
      } catch {
        toasts.error(t("forms.list.archiveFail"));
      }
    },
  });
}
</script>

<template>
  <!-- Same pre-list short-circuits as Dashboard: render the
       banner state inline rather than around the shell. -->
  <template v-if="!auth.isApproved">
    <AppHeader />
    <div class="container stack">
      <h1>{{ t("forms.list.title") }}</h1>
      <p class="muted">{{ t("forms.list.intro") }}</p>
      <AppCard>
        <h2>{{ t("dashboard.pendingTitle") }}</h2>
        <p>{{ t("dashboard.pendingBody") }}</p>
      </AppCard>
    </div>
  </template>

  <template v-else-if="noChapters">
    <AppHeader />
    <div class="container stack">
      <h1>{{ t("forms.list.title") }}</h1>
      <p class="muted">{{ t("forms.list.intro") }}</p>
      <AppCard>
        <h2>{{ t("dashboard.noChaptersTitle") }}</h2>
        <p class="muted">{{ t("dashboard.noChaptersBody") }}</p>
      </AppCard>
    </div>
  </template>

  <ListPageView
    v-else
    :title="t('forms.list.title')"
    :intro="t('forms.list.intro')"
    :items="sortedForms"
    :loaded="loaded"
    :chapter-filter="chapterFilter"
    :chapter-options="chapterOptions"
    :search-placeholder="t('forms.list.searchPlaceholder')"
    :search-keys="(f: FormOut) => [f.name]"
    :empty-copy="t('forms.list.empty')"
    :no-matches-copy="t('forms.list.noMatches')"
    :skeleton-rows="2"
    @update:chapter-filter="setChapterFilter"
  >
    <template #actions-leading>
      <router-link
        :to="{
          path: '/forms/new',
          query: chapterFilter ? { chapter: chapterFilter } : undefined,
        }"
      >
        <Button :label="t('forms.list.newForm')" icon="pi pi-plus" />
      </router-link>
    </template>

    <template #row="{ item: f }">
      <AppCard :stack="false" class="form-card">
        <div class="form-summary">
          <h3>
            {{ f.name }}
            <span v-if="f.chapter_name" class="event-chapter-chip">{{ f.chapter_name }}</span>
          </h3>
          <div class="link-row">
            <a :href="publicFormUrl(f.slug)" target="_blank" rel="noopener">{{ publicFormUrl(f.slug) }}</a>
            <Button
              icon="pi pi-copy"
              size="small"
              severity="secondary"
              text
              :aria-label="t('forms.list.copyLink')"
              @click="copyLink(f.slug)"
            />
          </div>
        </div>

        <div class="form-actions">
          <router-link :to="`/forms/${f.id}/details`">
            <Button :label="t('forms.list.details')" icon="pi pi-info-circle" size="small" severity="secondary" />
          </router-link>
          <Button
            :label="t('forms.list.archive')"
            icon="pi pi-archive"
            size="small"
            severity="secondary"
            text
            @click="askArchive(f)"
          />
        </div>
      </AppCard>
    </template>
  </ListPageView>
</template>

<style scoped>
.form-card {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 1.25rem;
  align-items: center;
}
.form-summary { min-width: 0; }
.form-summary h3 { margin: 0 0 0.25rem; }
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
.link-row {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  min-width: 0;
}
.link-row a {
  font-size: 0.9375rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
.form-actions {
  display: flex;
  gap: 0.5rem;
}
@media (max-width: 540px) {
  .form-card {
    grid-template-columns: 1fr;
  }
}
</style>
