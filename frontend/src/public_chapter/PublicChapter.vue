<script setup lang="ts">
import { computed, ref } from "vue";
import PublicNotice from "@/public_shared/PublicNotice.vue";
import PublicShell from "@/public_shared/PublicShell.vue";
import { chromeStrings, type Locale } from "@/public_shared/strings";
import { ApiError, type ChapterAgenda, fetchChapterAgenda } from "./api";
import EventCard from "./EventCard.vue";
import { pickLocale, strings } from "./i18n";

// Tri-state payload convention (same as the other mini-apps): an object
// renders, ``null`` is "chapter not found", ``undefined`` is the dev
// server (no server injection) → fetch over the API proxy.
const slug = window.location.pathname.replace(/^\/e\/+/, "").split(/[/?#]/)[0];
const locale = ref<Locale>(pickLocale());
const t = computed(() => strings(locale.value));
const c = computed(() => chromeStrings(locale.value));

const initial = window.__OPKOMST_CHAPTER__;
const agenda = ref<ChapterAgenda | null>(initial ?? null);
const notFound = ref(initial === null);
const loadFailed = ref(false);

if (initial === undefined) {
  fetchChapterAgenda(slug)
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
    <PublicNotice v-if="loadFailed" :message="c.loadFailed" />
    <PublicNotice v-else-if="notFound" :message="t.notFound" />

    <template v-else-if="agenda">
      <header class="agenda-head">
        <h1>{{ agenda.chapter.name }}</h1>
        <p v-if="agenda.chapter.city" class="muted">{{ agenda.chapter.city }}</p>
      </header>

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
.agenda-head h1 {
  margin: 0;
  font-size: 1.75rem;
  line-height: 1.2;
}
.agenda-head .muted {
  margin: 0.25rem 0 0;
}
.agenda-section {
  margin-top: 1.5rem;
}
.section-heading {
  margin: 0 0 0.75rem;
  font-size: 1.1rem;
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
