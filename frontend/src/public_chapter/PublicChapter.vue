<script setup lang="ts">
import { computed, ref } from "vue";
import logoUrl from "@/assets/rsp-logo.png";
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
    <template #brand>
      <div class="chapter-brand">
        <a
          class="chapter-brand__logo"
          href="https://rsp.nu"
          target="_blank"
          rel="noopener"
          aria-label="Revolutionair Socialistische Partij — rsp.nu"
        ><img :src="logoUrl" alt="" /></a>
        <div class="chapter-identity">
          <span class="chapter-identity__eyebrow">RSP</span>
          <template v-if="agenda">
            <h1>{{ agenda.chapter.name }}</h1>
            <p v-if="agenda.chapter.city" class="muted chapter-identity__city">
              {{ agenda.chapter.city }}
            </p>
          </template>
        </div>
      </div>
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
/* Chapter identity, hoisted into the shared header beside the party
 * logo: a small "RSP" eyebrow over the chapter name (the page's real
 * H1) and its city. Replaces the old orphaned second-row title, which
 * read as a stray heading on mobile. */
.chapter-brand {
  display: flex;
  align-items: center;
  gap: 0.875rem;
  min-width: 0;
}
.chapter-brand__logo {
  display: block;
  flex: none;
}
.chapter-brand__logo img {
  height: 60px;
  width: 60px;
  object-fit: contain;
  display: block;
}
.chapter-identity {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.chapter-identity__eyebrow {
  font-weight: 700;
  font-size: 0.8125rem;
  letter-spacing: 0.5px;
  line-height: 1.2;
  color: var(--brand-red);
}
.chapter-identity h1 {
  margin: 0.0625rem 0 0;
  font-size: 1.5rem;
  line-height: 1.15;
}
.chapter-identity__city {
  margin: 0.125rem 0 0;
  font-size: 0.9375rem;
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
