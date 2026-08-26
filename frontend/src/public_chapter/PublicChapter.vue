<script setup lang="ts">
import { computed, ref } from "vue";
import { brand } from "@/lib/branding";
import PublicIdentity from "@/public_shared/PublicIdentity.vue";
import PublicNotice from "@/public_shared/PublicNotice.vue";
import PublicShell from "@/public_shared/PublicShell.vue";
import { chromeStrings, type Locale } from "@/public_shared/strings";
import { ApiError, type ChapterAgenda, fetchChapterAgenda } from "./api";
import EventCard from "./EventCard.vue";
import { pickLocale, strings } from "./i18n";

// Tri-state payload convention (same as the other mini-apps): an object
// renders, ``null`` is "chapter not found", ``undefined`` is the dev
// server (no server injection) → fetch over the API proxy.
// ``/{tenant}/{chapter}`` — the organisation owns the URL, so the
// chapter is the second segment. The tenant is the brand the server
// already injected, not a re-parse of the first one.
const slug = window.location.pathname.split("/").filter(Boolean)[1] ?? "";
const locale = ref<Locale>(pickLocale());
const t = computed(() => strings(locale.value));
const c = computed(() => chromeStrings(locale.value));

const b = brand();

const initial = window.__OPKOMST_CHAPTER__;
const agenda = ref<ChapterAgenda | null>(initial ?? null);
const notFound = ref(initial === null);
const loadFailed = ref(false);

if (initial === undefined) {
  fetchChapterAgenda(b.slug, slug)
    .then((a) => {
      agenda.value = a;
    })
    .catch((err) => {
      if (err instanceof ApiError && err.status === 404) notFound.value = true;
      else loadFailed.value = true;
    });
}
</script>

<template>
  <PublicShell v-model:locale="locale" wide>
    <template #brand>
      <!-- Until the agenda loads there is no chapter to name, so the
           header shows the organisation alone — exactly what its front
           page shows. -->
      <PublicIdentity
        v-if="agenda"
        :eyebrow="b.wordmark"
        :title="agenda.chapter.name"
        :subtitle="agenda.chapter.city"
      />
      <PublicIdentity v-else :title="b.wordmark" />
    </template>

    <PublicNotice v-if="loadFailed" :message="c.loadFailed" />
    <PublicNotice v-else-if="notFound" :message="t.notFound" />

    <template v-else-if="agenda">
      <section class="agenda-section">
        <p v-if="!agenda.upcoming.length" class="muted">{{ t.emptyUpcoming }}</p>
        <div v-else class="agenda-grid">
          <EventCard
            v-for="e in agenda.upcoming"
            :key="e.slug"
            :event="e"
            :locale="locale"
          />
        </div>
      </section>

      <section v-if="agenda.past.length" class="agenda-section">
        <h2 class="section-heading">{{ t.pastHeading }}</h2>
        <div class="agenda-grid past-grid">
          <EventCard
            v-for="e in agenda.past"
            :key="e.slug"
            :event="e"
            :locale="locale"
            past
          />
        </div>
      </section>
    </template>
  </PublicShell>
</template>

<style scoped>
.agenda-section {
  margin-top: 1.5rem;
}
/* An ``h2`` at the app's own size (theme.css); only the spacing under
   it is this page's business. */
.section-heading {
  margin: 0 0 0.75rem;
}
.agenda-grid {
  display: grid;
  /* Cap at three cards per row in the ~1120px container; drops to two,
   * then one, as the viewport narrows. ``min(320px, 100%)`` keeps a
   * single card from overflowing on very narrow phones. */
  grid-template-columns: repeat(auto-fill, minmax(min(320px, 100%), 1fr));
  gap: 1rem;
  align-items: stretch;
}
</style>
