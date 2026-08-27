<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import AppCard from "@/components/AppCard.vue";
import AppHeader from "@/components/AppHeader.vue";
import ChapterGrid from "@/components/ChapterGrid.vue";
import PersonalIndexPage from "@/pages/PersonalIndexPage.vue";
import TenantIndexPage from "@/pages/TenantIndexPage.vue";
import { chapterList, useChapters } from "@/composables/useChapters";
import { brand, isPersonalApp } from "@/lib/branding";
import { useAuthStore } from "@/stores/auth";

/**
 * The app's landing page has two faces, decided by whether the visitor
 * has a session here:
 *
 * * signed in — the organiser's landing page: one tile per kind of
 *   thing the tool makes, with the organisation-management pages on a
 *   full-width tile below. "Which of the four workspaces did I want?"
 *   is the first question every session starts with, and answering it
 *   from a dropdown on the events list made events the accidental home.
 * * signed out — whose front page this is: an organisation's chapters
 *   (``TenantIndexPage``) under its slug, and the four create forms
 *   (``PersonalIndexPage``) at the root, where there is no
 *   organisation and the visitor came to make one thing.
 *
 * The split is client-side because the session lives in localStorage;
 * the server has no way to know which face to render.
 *
 * The signed-in face ends where the signed-out one begins: the
 * organisation's chapters, each linking to the agenda it publishes.
 * They are the pages an organiser hands to somebody else, and until
 * they were listed here the only way back to one was to remember its
 * URL.
 */

const { t } = useI18n();
const auth = useAuthStore();
const personalApp = isPersonalApp();
const b = brand();

// A personal account has no chapters and no endpoint to ask; an
// unapproved one is shown the waiting card instead of this page.
const chaptersQuery = useChapters({
  enabled: computed(() => auth.isAuthenticated && auth.isApproved && !auth.isPersonal),
});
const chapters = chapterList(chaptersQuery);

interface Tile {
  key: string;
  to: string;
  label: string;
  hint: string;
}

// Events is the one workspace an unapproved organiser can open; the
// An account still waiting on an admin gets no tiles at all: every one
// of them is approval-gated, so each would open onto the same "not
// approved yet" answer. It is told once, here, instead.
// Same order as the landing page and the workspace menu: settle a
// date, put the event up, share out the work, ask people something,
// and the one that is for the evening itself.
const tiles: Tile[] = [
  { key: "events", to: "/events", label: t("header.events"), hint: t("home.eventsHint") },
  { key: "datepolls", to: "/datepolls", label: t("header.datepolls"), hint: t("home.datepollsHint") },
  { key: "chores", to: "/chores", label: t("header.chores"), hint: t("home.choresHint") },
  { key: "forms", to: "/forms", label: t("header.forms"), hint: t("home.formsHint") },
  { key: "quizzes", to: "/quizzes", label: t("header.quizzes"), hint: t("home.quizzesHint") },
  { key: "compasses", to: "/compasses", label: t("header.compasses"), hint: t("home.compassesHint") },
];
</script>

<template>
  <PersonalIndexPage v-if="!auth.isAuthenticated && personalApp" />
  <TenantIndexPage v-else-if="!auth.isAuthenticated" />
  <template v-else-if="!auth.isApproved">
    <AppHeader />
    <main class="container-wide stack">
      <AppCard class="pending-card">
        <h2>{{ t("dashboard.pendingTitle") }}</h2>
        <p>{{ t("dashboard.pendingBody") }}</p>
      </AppCard>
    </main>
  </template>

  <template v-else>
    <AppHeader />
    <main class="container-wide stack">
      <!-- No title or lede: the header already says whose app this is,
           and the tiles say what it does. -->
      <div class="tile-grid">
        <router-link v-for="tile in tiles" :key="tile.key" :to="tile.to" class="tile">
          <span class="tile-label">{{ tile.label }}</span>
          <span class="tile-hint muted">{{ tile.hint }}</span>
        </router-link>

        <!-- Nobody to manage and no chapters to sort them into: a
             personal account is one person. -->
        <router-link v-if="!auth.isPersonal" to="/users" class="tile tile-wide">
          <span class="tile-label">{{ t("header.admin") }}</span>
          <span class="tile-hint muted">{{ t("home.adminHint") }}</span>
        </router-link>
      </div>

      <!-- The chapters, under a labelled rule. Same divider grammar as
           the signed-out face uses for its sign-in door: the tiles above
           are what this account makes, these are what it published. -->
      <section v-if="chapters.length > 0" class="chapters">
        <p class="divider muted">{{ t("home.chapterAgendas") }}</p>
        <ChapterGrid :chapters="chapters" :tenant-slug="b.slug" />
      </section>
    </main>
  </template>
</template>

<style scoped>
/* The waiting-for-approval card is two lines of text; it stays a card
 * rather than stretching the full width of the column. */
.pending-card {
  max-width: 42rem;
}

/* Two columns at every width. The tiles are the whole page, so on a
 * phone they should still be side by side — a single column would push
 * the admin tile below the fold for no gain. */
.tile-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 0.75rem;
  margin-top: 0.5rem;
}
.tile-wide {
  grid-column: 1 / -1;
}

.tile {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  min-height: 6.5rem;
  padding: 1rem;
  border: 1px solid var(--brand-border);
  border-radius: 10px;
  background: var(--brand-surface);
  color: var(--brand-text);
  text-decoration: none;
  transition: border-color 120ms, background 120ms, transform 120ms;
}
.tile:hover {
  border-color: var(--brand-red);
  background: var(--brand-red-soft);
}
.tile:active {
  transform: translateY(1px);
}
.tile-label {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--brand-red);
}
.tile-hint {
  font-size: 0.875rem;
  line-height: 1.35;
}

/* The chapters are a different kind of destination from the tiles: a
 * tile opens this app, a chapter opens the page the public sees. The
 * rule is what says so, with equal air on both sides so it divides
 * rather than lids. */
.chapters {
  margin-top: 2rem;
}
.divider {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin: 0 0 1.5rem;
  font-size: 0.875rem;
}
.divider::before,
.divider::after {
  content: "";
  flex: 1 1 auto;
  height: 1px;
  background: var(--brand-border);
}

/* The full-width admin tile sits apart from the four workspaces: it
 * acts on the organisation rather than on its programme. */
.tile-wide {
  flex-direction: row;
  align-items: baseline;
  gap: 0.625rem;
  min-height: 0;
  flex-wrap: wrap;
}

/* On the narrowest phones the hint is the first thing to go — two
 * words per line reads worse than no line at all — and the tiles
 * shrink to fit the label they're left with. */
@media (max-width: 380px) {
  .tile {
    min-height: 3.5rem;
    padding: 0.75rem;
    justify-content: center;
  }
  .tile-wide {
    min-height: 0;
  }
  .tile-label {
    font-size: 1rem;
  }
  .tile-hint {
    display: none;
  }
}
</style>
