<script setup lang="ts">
import { useQueryClient } from "@tanstack/vue-query";
import Button from "primevue/button";
import { computed, watch } from "vue";
import { useI18n } from "vue-i18n";
import AppCard from "@/components/AppCard.vue";
import AppHeader from "@/components/AppHeader.vue";
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
    :search-keys="(f: FormListOut) => [f.name]"
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
      <AppCard
        :stack="false"
        class="form-card"
        @mouseenter="prefetchDetails(f.id)"
        @focusin="prefetchDetails(f.id)"
      >
        <div class="form-main">
          <div class="form-summary">
            <h3>
              {{ f.name }}
              <span v-if="f.chapter_name" class="chapter-chip">{{ f.chapter_name }}</span>
            </h3>
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
          </div>

          <div class="actions">
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
        </div>

        <div class="form-side">
          <button
            type="button"
            class="qr-button"
            v-tooltip.top="t('forms.share.copyQr')"
            :aria-label="t('forms.share.copyQr')"
            @click="copyQr(f.slug)"
          >
            <img :src="formQrUrl(f.slug)" alt="" class="qr" />
          </button>
        </div>
      </AppCard>
    </template>
  </ListPageView>
</template>

<style scoped>
/* Mirrors ``DashboardPage``'s ``.event-card`` shape one-to-one:
 * two-column grid with main content on the left and the QR
 * thumbnail on the right. Forms don't have an attendee count to
 * sit above the QR (no signups model), so the side column carries
 * just the QR button. */
.form-card {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 1.25rem;
  align-items: stretch;
}
.form-main {
  display: flex;
  flex-direction: column;
  gap: 0.875rem;
  min-width: 0;
}
.form-summary h3 { margin: 0 0 0.25rem; }
.form-summary .link-row { margin-top: 0.25rem; }
.chapter-chip {
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
.actions {
  display: flex;
  gap: 0.5rem;
  margin-top: auto;
}

.form-side {
  display: flex;
  align-items: center;
  justify-content: flex-end;
}
.qr-button {
  align-self: center;
  line-height: 0;
  background: none;
  border: 0;
  padding: 0;
  cursor: pointer;
  border-radius: 6px;
  transition: transform 120ms ease, box-shadow 120ms ease;
}
.qr-button:hover {
  transform: scale(1.03);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}
.qr {
  width: 96px;
  height: 96px;
  background: white;
  border: 1px solid var(--brand-border);
  border-radius: 6px;
  padding: 4px;
  display: block;
}

@media (max-width: 540px) {
  .form-card {
    grid-template-columns: 1fr;
  }
  .form-side {
    justify-content: flex-end;
  }
}
</style>
