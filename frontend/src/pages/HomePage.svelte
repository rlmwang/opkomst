<script lang="ts">
import AppCard from "@/components/AppCard.svelte";
import AppHeader from "@/components/AppHeader.svelte";
import ChapterGrid from "@/components/ChapterGrid.svelte";
import TileGrid, { type Tile } from "@/components/TileGrid.svelte";
import PersonalIndexPage from "@/pages/PersonalIndexPage.svelte";
import TenantIndexPage from "@/pages/TenantIndexPage.svelte";
import { chaptersQuery, sortedChapters } from "@/composables/useChapters.svelte";
import { t } from "@/i18n.svelte";
import { brand, isPersonalApp } from "@/lib/branding";
import { auth } from "@/stores/auth.svelte";

/**
 * The landing page has two faces, decided by whether the visitor has a
 * session here.
 *
 * Signed in it is the organiser's landing page: one tile per kind of
 * thing the tool makes, with the organisation's management pages on a
 * full-width tile below. "Which of the workspaces did I want?" is the
 * first question every session starts with, and answering it from a
 * dropdown on the events list made events the accidental home.
 *
 * Signed out it is whose front page this is: an organisation's chapters
 * under its slug, and the six create forms at the root, where there is
 * no organisation and the visitor came to make one thing.
 *
 * The split is client-side because the session lives in localStorage,
 * and the server has no way to know which face to render.
 *
 * The signed-in face ends where the signed-out one begins: the
 * organisation's chapters, each linking to the agenda it publishes.
 * Those are the pages an organiser hands to somebody else, and until
 * they were listed here the only way back to one was to remember its
 * URL.
 */
const personalApp = isPersonalApp();
const b = brand();

// A personal account has no chapters and no endpoint to ask; an
// unapproved one is shown the waiting card instead of this page.
const query = chaptersQuery({
  enabled: () => auth.isAuthenticated && auth.isApproved && !auth.isPersonal,
});
const chapters = $derived(sortedChapters(query.data));

// An account still waiting on an admin gets no tiles at all: every one
// of them is approval-gated, so each would open onto the same "not
// approved yet" answer. It is told once, here, instead.
//
// Same order as the signed-out face and the workspace menu: settle a
// date, put the event up, share out the work, ask people something,
// and last the one that is for the evening itself.
const tiles = $derived<Tile[]>([
  { key: "events", to: "/event", label: t("home.eventsTile"), hint: t("home.eventsHint") },
  { key: "datepolls", to: "/datepoll", label: t("home.datepollsTile"), hint: t("home.datepollsHint") },
  { key: "chores", to: "/chore", label: t("home.choresTile"), hint: t("home.choresHint") },
  { key: "forms", to: "/form", label: t("home.formsTile"), hint: t("home.formsHint") },
  { key: "quizzes", to: "/quiz", label: t("home.quizzesTile"), hint: t("home.quizzesHint") },
  { key: "compasses", to: "/compass", label: t("home.compassesTile"), hint: t("home.compassesHint") },
  // Nobody to manage and no chapters to sort them into: a personal
  // account is one person.
  ...(auth.isPersonal
    ? []
    : [{ key: "admin", to: "/users", label: t("header.admin"), hint: t("home.adminHint"), wide: true }]),
]);
</script>

{#if !auth.isAuthenticated && personalApp}
  <PersonalIndexPage />
{:else if !auth.isAuthenticated}
  <TenantIndexPage />
{:else if !auth.isApproved}
  <AppHeader />
  <main class="container-wide stack">
    <AppCard class="pending-card">
      <h2>{t("dashboard.pendingTitle")}</h2>
      <p>{t("dashboard.pendingBody")}</p>
    </AppCard>
  </main>
{:else}
  <AppHeader />
  <main class="container-wide stack">
    <!-- No title or lede: the header already says whose app this is,
         and the tiles say what it does. -->
    <TileGrid {tiles} gap="0.75rem" />

    <!-- The chapters, under a labelled rule. Same divider grammar as
         the signed-out face uses for its sign-in door: the tiles above
         are what this account makes, these are what it published. -->
    {#if chapters.length > 0}
      <section class="chapters">
        <p class="divider muted">{t("home.chapterAgendas")}</p>
        <ChapterGrid {chapters} tenantSlug={b.slug} />
      </section>
    {/if}
  </main>
{/if}

<style>
/* The waiting-for-approval card is two lines of text; it stays a card
 * rather than stretching the full width of the column. */
main :global(.pending-card) {
  max-width: 42rem;
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
</style>
