<script setup lang="ts">
import { computed, ref } from "vue";
import { brand } from "@/lib/branding";
import PublicIdentity from "@/public_shared/PublicIdentity.vue";
import PublicNotice from "@/public_shared/PublicNotice.vue";
import PublicShell from "@/public_shared/PublicShell.vue";
import { chromeStrings, type Locale } from "@/public_shared/strings";
import { resolveText } from "@/public_shared/bilingual";
import { ApiError, type ChapterAgenda, type EventCard as EventCardData, fetchChapterAgenda } from "./api";
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

// Title search over both lists. Accent- and case-insensitive substring
// on the title as the visitor reads it (``resolveText``, so the language
// toggle moves the search with the page). Client-side: the agenda is
// already here in full, and a chapter's list is a page, not a corpus.
const query = ref("");
const fold = (v: string) =>
  v
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();
function matching(cards: EventCardData[]): EventCardData[] {
  const needle = fold(query.value.trim());
  if (!needle) return cards;
  return cards.filter((e) => fold(resolveText(e.name_nl, e.name_en, locale.value) ?? "").includes(needle));
}
const upcoming = computed(() => matching(agenda.value?.upcoming ?? []));
const past = computed(() => matching(agenda.value?.past ?? []));

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
      />
      <PublicIdentity v-else :title="b.wordmark" />
    </template>

    <PublicNotice v-if="loadFailed" :message="c.loadFailed" />
    <PublicNotice v-else-if="notFound" :message="t.notFound" />

    <template v-else-if="agenda">
      <input
        v-model="query"
        type="search"
        class="input agenda-search"
        :placeholder="t.searchTitles"
        :aria-label="t.searchTitles"
      />

      <p v-if="query && !upcoming.length && !past.length" class="muted agenda-section">
        {{ t.searchNoMatches }}
      </p>

      <template v-else>
        <section class="agenda-section">
          <p v-if="!query && !upcoming.length" class="muted">{{ t.emptyUpcoming }}</p>
          <div v-else-if="upcoming.length" class="agenda-grid">
            <EventCard
              v-for="e in upcoming"
              :key="e.slug"
              :event="e"
              :locale="locale"
            />
          </div>
        </section>

        <section v-if="past.length" class="agenda-section">
          <h2 class="section-heading">{{ t.pastHeading }}</h2>
          <div class="agenda-grid past-grid">
            <EventCard
              v-for="e in past"
              :key="e.slug"
              :event="e"
              :locale="locale"
              past
            />
          </div>
        </section>
      </template>
    </template>
  </PublicShell>
</template>

<style scoped>
.agenda-section {
  margin-top: 1.5rem;
}
/* Sits above the grid at the width of a single card, so it reads as one
 * control over the list rather than a full-bleed banner. */
.agenda-search {
  margin-top: 0.5rem;
  max-width: min(320px, 100%);
}
/* An ``h2`` at the app's own size (theme.css); only the spacing under
   it is this page's business. */
.section-heading {
  margin: 0 0 0.75rem;
}
.agenda-grid {
  display: grid;
  /* Two of the poster-beside-text cards per row in the ~1090px container,
   * one as the viewport narrows. ``min(440px, 100%)`` keeps a single card
   * from overflowing on very narrow phones. */
  grid-template-columns: repeat(auto-fill, minmax(min(440px, 100%), 1fr));
  gap: 1rem;
  align-items: stretch;
}
</style>
