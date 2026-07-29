<script setup lang="ts">
import { useQueryClient } from "@tanstack/vue-query";
import Button from "primevue/button";
import { computed, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useLocalizedText } from "@/composables/useLocalizedText";
import AppCard from "@/components/AppCard.vue";
import AppHeader from "@/components/AppHeader.vue";
import EntityCard from "@/components/EntityCard.vue";
import ListPageView from "@/components/ListPageView.vue";
import { get } from "@/api/client";
import { useChapterUrlFilter } from "@/composables/useChapterUrlFilter";
import { useFormClipboard } from "@/composables/useFormClipboard";
import { type FormListOut, formList, useArchiveForm, useFormList } from "@/composables/useForms";
import { useConfirms } from "@/lib/confirms";
import { formQrUrl, publicFormUrl } from "@/lib/form-urls";
import { useToasts } from "@/lib/toasts";
import { useAuthStore } from "@/stores/auth";

const { t } = useI18n();
const lt = useLocalizedText();
const auth = useAuthStore();
const toasts = useToasts();
const confirms = useConfirms();
const qc = useQueryClient();
const { copyLink, copyQr } = useFormClipboard();

// Chapter filter — same URL-param shape as Events so the filter
// survives navigation between active and archived list pages.
const { chapterFilter, setChapterFilter, chapterOptions } = useChapterUrlFilter();

const formsQuery = useFormList({
  enabled: computed(() => auth.isApproved),
  chapterId: chapterFilter,
});
const forms = formList(formsQuery);
const archiveMutation = useArchiveForm();

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

// Prefetch the details + summary queries when an organiser
// hovers a row. Same pattern Dashboard uses for its event cards
// — by the time the click resolves and FormDetailsPage mounts,
// both queries are already in cache so the page paints without
// a skeleton flash.
const prefetched = new Set<string>();
function prefetchDetails(formId: string) {
  if (prefetched.has(formId)) return;
  prefetched.add(formId);
  void qc.prefetchQuery({
    queryKey: ["forms", "single", formId],
    queryFn: () => get(`/api/v1/forms/${formId}`),
  });
  void qc.prefetchQuery({
    queryKey: ["forms", formId, "summary"],
    queryFn: () => get(`/api/v1/forms/${formId}/summary`),
  });
}

function askArchive(f: FormListOut) {
  confirms.ask({
    header: t("forms.list.archiveConfirmTitle"),
    message: t("forms.list.archiveConfirmBody", { name: lt(f.name_nl, f.name_en) ?? "" }),
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
    :search-keys="(f: FormListOut) => [lt(f.name_nl, f.name_en) ?? '']"
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
      <EntityCard
        :qr-src="formQrUrl(f.slug)"
        :qr-label="t('forms.share.copyQr')"
        @mouseenter="prefetchDetails(f.id)"
        @focusin="prefetchDetails(f.id)"
        @copy-qr="copyQr(f.slug)"
      >
        <template #title>
          <h3>
            {{ lt(f.name_nl, f.name_en) }}
            <span v-if="f.chapter_name" class="chapter-chip">{{ f.chapter_name }}</span>
          </h3>
        </template>

        <template #link>
          <div class="link-row">
            <a :href="publicFormUrl(f.slug)" target="_blank" rel="noopener">{{ publicFormUrl(f.slug) }}</a>
            <Button
              icon="pi pi-copy"
              size="small"
              severity="secondary"
              text
              v-tooltip.top="t('forms.share.copyLink')"
              :aria-label="t('forms.share.copyLink')"
              @click="copyLink(f.slug)"
            />
          </div>
        </template>

        <template #actions>
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
        </template>

        <template #count>{{ t("forms.list.submissionCount", { n: f.submission_count }) }}</template>
      </EntityCard>
    </template>
  </ListPageView>
</template>
