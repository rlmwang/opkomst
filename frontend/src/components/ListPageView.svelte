<script lang="ts" generics="T extends { id: string }">
import type { Snippet } from "svelte";

import AppButton from "@/components/AppButton.svelte";
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
 * Per-page concerns stay outside the shell: the data source, pre-shell
 * guard banners (e.g. the "no chapters yet" onboarding card), mutation
 * handlers, error toasts.
 *
 * The search box and the page numbers are the request. An organisation
 * runs thousands of events, so the list arrives one page at a time
 * ordered and filtered by the database; this used to hold every row and
 * hide the ones that did not match what you typed.
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
  search = $bindable(),
  page = $bindable(),
  total,
  perPage,
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
  /** What is typed in the search box. The server does the matching. */
  search: string;
  /** Which page is on screen, one-based, and what it is one of. */
  page: number;
  total: number;
  perPage: number;
  emptyCopy: string;
  noMatchesCopy: string;
  skeletonRows?: number;
  actionsLeading?: Snippet;
  row: Snippet<[{ item: T }]>;
} = $props();

const pages = $derived(Math.max(1, Math.ceil(total / perPage)));

/** The numbers to draw. Every page when there are few, and a window
 *  around the current one when there are many, so the row of buttons
 *  stays the same width at page 3 and at page 300. */
const numbers = $derived.by(() => {
  if (pages <= 7) return Array.from({ length: pages }, (_, i) => i + 1);
  const around = [page - 1, page, page + 1].filter((n) => n > 1 && n < pages);
  const shown = [1, ...around, pages];
  const out: (number | "gap")[] = [];
  for (const [i, n] of shown.entries()) {
    if (i > 0 && n - (shown[i - 1] as number) > 1) out.push("gap");
    out.push(n);
  }
  return out;
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
    <SearchInput bind:value={search} placeholder={searchPlaceholder} class="search" />
  </div>

  {#if !loaded}
    <AppSkeleton rows={skeletonRows ?? 3} cards />
  {:else if total === 0 && !search}
    <AppCard stack={false}>
      <p class="muted">{emptyCopy}</p>
    </AppCard>
  {:else if total === 0}
    <p class="muted">{noMatchesCopy}</p>
  {:else}
    {#each items as item (item.id)}
      {@render row({ item })}
    {/each}

    {#if pages > 1}
      <nav class="pages" aria-label={t("common.pages")}>
        <AppButton
          label={t("common.previousPage")}
          size="small"
          severity="secondary"
          text
          disabled={page <= 1}
          onclick={() => (page = page - 1)}
        />
        {#each numbers as n, i (`${n}-${i}`)}
          {#if n === "gap"}
            <span class="gap" aria-hidden="true">…</span>
          {:else}
            <AppButton
              label={String(n)}
              size="small"
              severity="secondary"
              text={n !== page}
              onclick={() => (page = n)}
            />
          {/if}
        {/each}
        <AppButton
          label={t("common.nextPage")}
          size="small"
          severity="secondary"
          text
          disabled={page >= pages}
          onclick={() => (page = page + 1)}
        />
      </nav>
    {/if}
  {/if}
</div>

<style>
/* The page numbers, centred under the rows: previous, the window of
 * numbers, next. Wraps on a phone rather than scrolling sideways. */
.pages {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 0.25rem;
  padding-top: 0.5rem;
}
.gap {
  padding: 0 0.25rem;
  color: var(--brand-text-muted);
}

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
