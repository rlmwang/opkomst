<script lang="ts" generics="T extends { id: string }">
import type { Snippet } from "svelte";

import SelectField from "@/components/SelectField.svelte";
import AppCard from "@/components/AppCard.svelte";
import AppHeader from "@/components/AppHeader.svelte";
import AppSkeleton from "@/components/AppSkeleton.svelte";
import SearchInput from "@/components/SearchInput.svelte";
import { t } from "@/i18n.svelte";

/**
 * Shared shell for "managed resource" list pages — the active and
 * archive variants for Events today; Forms once that feature
 * lands. Owns the page header, the title + intro, the
 * actions-row (chapter filter + search + slotted leading
 * controls), the loading skeleton, and the empty-state / no-match
 * branches.
 *
 * Per-page concerns stay outside the shell: the data source (a
 * Vue Query composable), sort order (applied to ``items`` before
 * it arrives), pre-shell guard banners (e.g. the "no chapters
 * yet" onboarding card), mutation handlers, error toasts.
 *
 * Search is name+free-text — the parent supplies a
 * ``searchKeys`` function that returns the haystack strings for
 * a row. The filter is case-insensitive substring across the
 * returned strings.
 */
interface ChapterOption {
  id: string;
  name: string;
}

let {
  title,
  intro,
  items,
  loaded,
  chapterFilter = $bindable(),
  chapterOptions,
  searchPlaceholder,
  searchKeys,
  emptyCopy,
  noMatchesCopy,
  skeletonRows,
  actionsLeading,
  row,
}: {
  title: string;
  intro?: string;
  items: T[];
  loaded: boolean;
  chapterFilter: string | null;
  chapterOptions: ChapterOption[];
  searchPlaceholder: string;
  /** Strings to search through for a given row. Several haystacks mean
   *  any-substring match. */
  searchKeys: (item: T) => string[];
  emptyCopy: string;
  noMatchesCopy: string;
  skeletonRows?: number;
  actionsLeading?: Snippet;
  row: Snippet<[{ item: T }]>;
} = $props();

let query = $state("");

const filtered = $derived.by(() => {
  const q = query.trim().toLowerCase();
  if (!q) return items;
  return items.filter((item) => searchKeys(item).some((s) => s.toLowerCase().includes(q)));
});
</script>

<AppHeader />
<div class="container-wide stack">
  <h1>{title}</h1>
  {#if intro}<p class="muted">{intro}</p>{/if}

  <div class="actions-row">
    <!-- Optional leading control ("+ New event" on active, nothing on
         archive). The chapter filter and the search always render. -->
    {#if actionsLeading}{@render actionsLeading()}{/if}
    <!-- No chapters to filter by, no filter. A personal account has
         none at all; an organisation's member always has one. -->
    {#if chapterOptions.length > 0}
      <SelectField
        bind:value={chapterFilter}
        options={[{ id: null, name: t("dashboard.chapterFilterAll") }, ...chapterOptions]}
        optionLabel="name"
        optionValue="id"
        placeholder={t("dashboard.chapterFilterAll")}
        class="chapter-filter"
      />
    {/if}
    <SearchInput bind:value={query} placeholder={searchPlaceholder} class="search" />
  </div>

  {#if !loaded}
    <AppSkeleton rows={skeletonRows ?? 3} cards />
  {:else if items.length === 0}
    <AppCard stack={false}>
      <p class="muted">{emptyCopy}</p>
    </AppCard>
  {:else if filtered.length === 0}
    <p class="muted">{noMatchesCopy}</p>
  {:else}
    {#each filtered as item (item.id)}
      {@render row({ item })}
    {/each}
  {/if}
</div>

<style>
.actions-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem;
}
.actions-row :global(.search) {
  flex: 1;
  min-width: 0;
  max-width: 24rem;
  margin-left: auto;
}
:global(.chapter-filter) {
  min-width: 12rem;
}

/* Below the container width there isn't room to sit the 12rem
 * chapter filter beside the search box: the filter kept its
 * fixed width and the search collapsed to whatever was left,
 * which on a phone was roughly a third of the row. Rather than
 * split the row into two cramped halves, every control takes the
 * full width and stacks — the search field is the one that
 * actually needs the space, and full-width rows give all three
 * a comfortable tap target. */
@media (max-width: 720px) {
  .actions-row > :global(*) {
    flex: 1 1 100%;
    min-width: 0;
  }
  .actions-row :global(.search) {
    max-width: none;
    margin-left: 0;
  }
  /* The slotted "+ New …" link wraps its button, so the width
   * has to be pushed through to the button itself. */
  .actions-row :global(.app-btn) {
    width: 100%;
    justify-content: center;
  }
}
</style>
