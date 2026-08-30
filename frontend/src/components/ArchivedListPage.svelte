<script lang="ts" generics="T extends { id: string; name_nl: string | null; name_en: string | null; chapter_name?: string | null }">
import type { Snippet } from "svelte";

import AppButton from "@/components/AppButton.svelte";
import AppCard from "@/components/AppCard.svelte";
import ListPageView from "@/components/ListPageView.svelte";
import type { ArchivedList } from "@/composables/useArchivedList.svelte";
import { lt } from "@/composables/useLocalizedText.svelte";
import { tip } from "@/lib/tooltip";

/**
 * The archive view, for all four resources.
 *
 * Events, questionnaires, rosters and date polls each had their own
 * archived page, and the four were the same seventy lines with a
 * different word in the i18n keys. What actually differs is two things:
 * where the copy comes from, and whether a row says anything under its
 * name. Both are parameters here, so there is one archive screen.
 *
 * ``copy`` takes the key after ``archived.`` and is the page's own
 * lookup, because the forms table's three products resolve a key
 * against their own resource before falling back (``formText``).
 *
 * The page keeps its own ``archivedList``: it owns the query, the
 * mutations and the i18n prefix its toasts read, and this owns the
 * markup those produce.
 */
let {
  copy,
  items,
  total,
  perPage,
  loaded,
  list,
  meta,
}: {
  copy: (key: string) => string;
  items: T[];
  /** How many rows the filter and the search leave, and how many fit on
   *  a page. */
  total: number;
  perPage: number;
  loaded: boolean;
  list: ArchivedList<T>;
  /** A line under the name, where the resource has one to show. */
  meta?: Snippet<[T]>;
} = $props();
</script>

<ListPageView
  title={copy("title")}
  intro={copy("intro")}
  {items}
  {loaded}
  bind:chapterFilter={list.chapter.value}
  chapterOptions={list.chapter.options}
  searchPlaceholder={copy("searchPlaceholder")}
  bind:search={list.chapter.search}
  bind:page={list.chapter.page}
  {total}
  {perPage}
  emptyCopy={copy("empty")}
  noMatchesCopy={copy("noMatches")}
  skeletonRows={2}
>
  {#snippet row({ item })}
    <AppCard stack={false} class="archive-row">
      <div>
        <h3>
          {lt(item.name_nl, item.name_en)}
          {#if item.chapter_name}<span class="chapter-chip">{item.chapter_name}</span>{/if}
        </h3>
        {#if meta}{@render meta(item)}{/if}
      </div>
      <div class="archive-row-actions">
        <AppButton
          label={copy("restore")}
          icon="replay"
          size="small"
          severity="secondary"
          onclick={() => list.restoreItem(item)}
        />
        <span use:tip={copy("delete")}>
          <AppButton
            icon="trash"
            size="small"
            severity="secondary"
            text
            ariaLabel={copy("delete")}
            onclick={() => list.askDelete(item)}
          />
        </span>
      </div>
    </AppCard>
  {/snippet}
</ListPageView>
