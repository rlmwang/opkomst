<script lang="ts" generics="T extends { id: string; name_nl: string | null; name_en: string | null; chapter_name?: string | null }">
import type { Snippet } from "svelte";

import AppButton from "@/components/AppButton.svelte";
import AppCard from "@/components/AppCard.svelte";
import AppHeader from "@/components/AppHeader.svelte";
import EntityCard from "@/components/EntityCard.svelte";
import ListPageView from "@/components/ListPageView.svelte";
import type { EntityList } from "@/composables/useEntityList.svelte";
import { hoverPrefetch } from "@/composables/useHoverPrefetch.svelte";
import { lt } from "@/composables/useLocalizedText.svelte";
import { t } from "@/i18n.svelte";
import { useToasts } from "@/lib/toasts";
import { auth } from "@/stores/auth.svelte";
import { go } from "@/router/navigation.svelte";

/**
 * The list screen, for all four public-facing resources.
 *
 * A page supplies its copy, its rows, where a row's details and public
 * page live, and what a row says in the middle. The chapter filter, the
 * search, the skeleton, the empty states, the hover prefetch, the share
 * stub and the archive button are the same everywhere and live here.
 *
 * The no-chapters state renders its own header and title rather than the
 * list shell's, because an organiser with no chapter has nothing to
 * filter, search or archive. The dashboard puts a picker inside that
 * card; every other page only explains.
 */
let {
  copy,
  items,
  loaded,
  isError,
  list,
  newPath,
  newLabel,
  detailsPath,
  publicUrl,
  qrSrc,
  sharePrefix,
  copyLink,
  copyQr,
  prefetch,
  searchKeys = (item: T) => [lt(item.name_nl, item.name_en) ?? ""],
  meta,
  count,
  onboarding,
}: {
  copy: (key: string, params?: Record<string, unknown>) => string;
  items: T[];
  loaded: boolean;
  isError: boolean;
  list: EntityList<T>;
  /** Where the "new" button goes. The chapter filter rides along, so a
   *  filtered list creates into the chapter being looked at. */
  newPath: string;
  newLabel: string;
  detailsPath: (item: T) => string;
  /** The row's public page, absent where it has none yet. */
  publicUrl: (item: T) => string | undefined;
  qrSrc: (item: T) => string | undefined;
  /** i18n prefix for the share stub's two labels, e.g. ``"event.share"``. */
  sharePrefix: string;
  copyLink: (item: T) => void;
  copyQr: (item: T) => void;
  /** Warm the details page's queries for a row the pointer rests on. */
  prefetch: (id: string) => void;
  searchKeys?: (item: T) => string[];
  meta?: Snippet<[T]>;
  count?: Snippet<[T]>;
  onboarding?: Snippet;
} = $props();

const toasts = useToasts();
const hover = hoverPrefetch((id) => prefetch(id));

$effect(() => {
  if (isError) toasts.error(copy("loadFailed"));
});

function openNew(): void {
  const chapter = list.chapter.value;
  void go(chapter ? `${newPath}?chapter=${encodeURIComponent(chapter)}` : newPath);
}
</script>

{#if auth.needsChapters}
  <AppHeader />
  <div class="container-wide stack">
    <h1>{copy("title")}</h1>
    <p class="muted">{copy("intro")}</p>
    <AppCard>
      <h2>{t("dashboard.noChaptersTitle")}</h2>
      <p class="muted">{t("dashboard.noChaptersBody")}</p>
      {#if onboarding}{@render onboarding()}{/if}
    </AppCard>
  </div>
{:else}
  <ListPageView
    title={copy("title")}
    intro={copy("intro")}
    {items}
    {loaded}
    bind:chapterFilter={list.chapter.value}
    chapterOptions={list.chapter.options}
    searchPlaceholder={copy("searchPlaceholder")}
    {searchKeys}
    emptyCopy={copy("empty")}
    noMatchesCopy={copy("noMatches")}
    skeletonRows={2}
  >
    {#snippet actionsLeading()}
      <AppButton label={newLabel} icon="plus" onclick={openNew} />
    {/snippet}

    {#snippet row({ item })}
      {#snippet cardTitle()}
        <h3>
          {lt(item.name_nl, item.name_en)}
          {#if item.chapter_name}<span class="chapter-chip">{item.chapter_name}</span>{/if}
        </h3>
      {/snippet}
      {#snippet cardMeta()}{#if meta}{@render meta(item)}{/if}{/snippet}
      {#snippet cardCount()}{#if count}{@render count(item)}{/if}{/snippet}
      {#snippet cardActions()}
        <AppButton
          label={copy("details")}
          icon="info-circle"
          size="small"
          severity="secondary"
          onclick={() => void go(detailsPath(item))}
        />
        <AppButton
          label={copy("archive")}
          icon="archive"
          size="small"
          severity="secondary"
          text
          onclick={() => list.askArchive(item)}
        />
      {/snippet}

      <EntityCard
        publicUrl={publicUrl(item)}
        qrSrc={qrSrc(item)}
        copyLinkLabel={t(`${sharePrefix}.copyLink`)}
        qrLabel={t(`${sharePrefix}.copyQr`)}
        oncopyLink={() => copyLink(item)}
        oncopyQr={() => copyQr(item)}
        onmouseenter={() => hover.enter(item.id)}
        onmouseleave={() => hover.leave()}
        onfocusin={() => hover.enter(item.id)}
        title={cardTitle}
        meta={meta ? cardMeta : undefined}
        count={count ? cardCount : undefined}
        actions={cardActions}
      />
    {/snippet}
  </ListPageView>
{/if}
