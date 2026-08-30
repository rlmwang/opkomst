<script lang="ts">
import { brand } from "@/lib/branding";
import PublicIdentity from "@/public_shared/PublicIdentity.svelte";
import PublicNotice from "@/public_shared/PublicNotice.svelte";
import PublicShell from "@/public_shared/PublicShell.svelte";
import { chromeStrings, type Locale } from "@/public_shared/strings";
import { resolveText } from "@/public_shared/bilingual";
import { ApiError, type ChapterAgenda, type EventCard as EventCardData, fetchChapterAgenda } from "./api";
import EventCard from "./EventCard.svelte";
import { pickLocale, strings } from "./i18n";

// Tri-state payload convention (same as the other mini-apps): an object
// renders, ``null`` is "chapter not found", ``undefined`` is the dev
// server (no server injection), so fetch over the API proxy.
// ``/{tenant}/{chapter}``: the organisation owns the URL, so the chapter
// is the second segment. The tenant is the brand the server already
// injected, not a re-parse of the first one.
const slug = window.location.pathname.split("/").filter(Boolean)[1] ?? "";
let locale = $state<Locale>(pickLocale());
const t = $derived(strings(locale));
const c = $derived(chromeStrings(locale));

const b = brand();

const initial = window.__OPKOMST_CHAPTER__;
let agenda = $state<ChapterAgenda | null>(initial ?? null);
let notFound = $state(initial === null);
let loadFailed = $state(false);

// Title search over both lists. Accent- and case-insensitive substring
// on the title as the visitor reads it (``resolveText``, so the language
// toggle moves the search with the page). Client-side: the agenda is
// already here in full, and a chapter's list is a page, not a corpus.
let query = $state("");
const fold = (v: string) =>
  v
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();
function matching(cards: EventCardData[]): EventCardData[] {
  const needle = fold(query.trim());
  if (!needle) return cards;
  return cards.filter((e) => fold(resolveText(e.name_nl, e.name_en, locale) ?? "").includes(needle));
}
const upcoming = $derived(matching(agenda?.upcoming ?? []));
const past = $derived(matching(agenda?.past ?? []));

if (initial === undefined) {
  fetchChapterAgenda(b.slug, slug)
    .then((a) => {
      agenda = a;
    })
    .catch((err) => {
      if (err instanceof ApiError && err.status === 404) notFound = true;
      else loadFailed = true;
    });
}
</script>

<PublicShell bind:locale wide>
  {#snippet brand()}
    <!-- Until the agenda loads there is no chapter to name, so the
         header shows the organisation alone, exactly what its front page
         shows. -->
    {#if agenda}
      <PublicIdentity eyebrow={b.wordmark} title={agenda.chapter.name} />
    {:else}
      <PublicIdentity title={b.wordmark} />
    {/if}
  {/snippet}

  {#if loadFailed}
    <PublicNotice message={c.loadFailed} />
  {:else if notFound}
    <PublicNotice message={t.notFound} />
  {:else if agenda}
    <input
      bind:value={query}
      type="search"
      class="input agenda-search"
      placeholder={t.searchTitles}
      aria-label={t.searchTitles}
    />

    {#if query && !upcoming.length && !past.length}
      <p class="muted agenda-section">{t.searchNoMatches}</p>
    {:else}
      <section class="agenda-section">
        {#if !query && !upcoming.length}
          <p class="muted">{t.emptyUpcoming}</p>
        {:else if upcoming.length}
          <div class="agenda-grid">
            {#each upcoming as e (e.slug)}
              <EventCard event={e} {locale} />
            {/each}
          </div>
        {/if}
      </section>

      {#if past.length}
        <section class="agenda-section">
          <h2 class="section-heading">{t.pastHeading}</h2>
          <div class="agenda-grid past-grid">
            {#each past as e (e.slug)}
              <EventCard event={e} {locale} past />
            {/each}
          </div>
        </section>
      {/if}
    {/if}
  {/if}
</PublicShell>

<style>
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
