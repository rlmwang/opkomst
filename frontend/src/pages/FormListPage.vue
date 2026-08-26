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
import { type FormListOut, formList, useFormsApi } from "@/composables/useForms";
import { useConfirms } from "@/lib/confirms";
import { formQrUrl, publicFormUrl } from "@/lib/form-urls";
import { useToasts } from "@/lib/toasts";
import { useAuthStore } from "@/stores/auth";

const { t, te } = useI18n();
const lt = useLocalizedText();
const auth = useAuthStore();
const toasts = useToasts();
// One page, two products; the route says which (``useForms``).
const api = useFormsApi();
/** ``quizzes.<key>`` when there is one, ``forms.<key>`` otherwise: the
 *  two products share every string that is not about scoring. */
const L = (key: string, params?: Record<string, unknown>) => {
  const full = api.resource === "quizzes" && te(`quizzes.${key}`) ? `quizzes.${key}` : `forms.${key}`;
  return params ? t(full, params) : t(full);
};
const confirms = useConfirms();
const qc = useQueryClient();
const { copyLink, copyQr } = useFormClipboard();

// Chapter filter — same URL-param shape as Events so the filter
// survives navigation between active and archived list pages.
const { chapterFilter, setChapterFilter, chapterOptions } = useChapterUrlFilter();

const formsQuery = api.useList({
  enabled: computed(() => auth.isApproved),
  chapterId: chapterFilter,
});
const forms = formList(formsQuery);
const archiveMutation = api.useArchive();

// Pending approval and no-chapters short-circuits: neither state has
// any business showing the list shell. ``auth.needsChapters`` is the
// one definition of the second, shared with every other list page.

watch(formsQuery.isError, (isError) => {
  if (isError) toasts.error(L("list.loadFailed"));
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
    queryFn: () => get(`/api/v1/${api.resource}/${formId}`),
  });
  void qc.prefetchQuery({
    queryKey: ["forms", formId, "summary"],
    queryFn: () => get(`/api/v1/${api.resource}/${formId}/summary`),
  });
}

function askArchive(f: FormListOut) {
  confirms.ask({
    header: L("list.archiveConfirmTitle"),
    message: L("list.archiveConfirmBody", { name: lt(f.name_nl, f.name_en) ?? "" }),
    icon: "pi pi-exclamation-triangle",
    rejectLabel: t("common.cancel"),
    acceptLabel: L("list.archive"),
    accept: async () => {
      try {
        await archiveMutation.mutateAsync(f.id);
        toasts.success(L("list.archived"));
      } catch {
        toasts.error(L("list.archiveFail"));
      }
    },
  });
}
</script>

<template>
  <!-- Same pre-list short-circuits as Dashboard: render the
       banner state inline rather than around the shell. -->
  <template v-if="auth.needsChapters">
    <AppHeader />
    <div class="container-wide stack">
      <h1>{{ L("list.title") }}</h1>
      <p class="muted">{{ L("list.intro") }}</p>
      <AppCard>
        <h2>{{ t("dashboard.noChaptersTitle") }}</h2>
        <p class="muted">{{ t("dashboard.noChaptersBody") }}</p>
      </AppCard>
    </div>
  </template>

  <ListPageView
    v-else
    :title="L('list.title')"
    :intro="L('list.intro')"
    :items="sortedForms"
    :loaded="loaded"
    :chapter-filter="chapterFilter"
    :chapter-options="chapterOptions"
    :search-placeholder="L('list.searchPlaceholder')"
    :search-keys="(f: FormListOut) => [lt(f.name_nl, f.name_en) ?? '']"
    :empty-copy="L('list.empty')"
    :no-matches-copy="L('list.noMatches')"
    :skeleton-rows="2"
    @update:chapter-filter="setChapterFilter"
  >
    <template #actions-leading>
      <router-link
        :to="{
          path: `/${api.resource}/new`,
          query: chapterFilter ? { chapter: chapterFilter } : undefined,
        }"
      >
        <Button :label="L('list.newForm')" icon="pi pi-plus" />
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
          <router-link :to="`/${api.resource}/${f.id}/details`">
            <Button :label="L('list.details')" icon="pi pi-info-circle" size="small" severity="secondary" />
          </router-link>
          <Button
            :label="L('list.archive')"
            icon="pi pi-archive"
            size="small"
            severity="secondary"
            text
            @click="askArchive(f)"
          />
        </template>

        <template #count>{{ L("list.submissionCount", { n: f.submission_count }) }}</template>
      </EntityCard>
    </template>
  </ListPageView>
</template>
