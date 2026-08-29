<script lang="ts">
import type { Snippet } from "svelte";

import AppHeader from "@/components/AppHeader.svelte";
import AppSkeleton from "@/components/AppSkeleton.svelte";

/**
 * Shared shell for "managed resource" details pages — EventDetailsPage
 * today; FormDetailsPage when the Forms feature lands. Owns the page
 * header, the ``.container .stack`` wrapper, and the
 * waiting-for-the-resource skeleton.
 *
 * Per-page concerns stay outside: the resource fetch (a Vue Query
 * composable), the body cards (overview / stats / per-resource
 * sections), error toasts. The shell only renders the skeleton
 * vs. the slot body based on ``loaded``.
 *
 * Why not a richer shell with a "title + actions" header band? The
 * existing EventDetailsPage carries the resource title inside an
 * overview card alongside chapter chip + public URL + QR; promoting
 * the title out of that card would be a DOM/UX change to events,
 * not a refactor. Forms can adopt the same card-first pattern.
 */
const {
  loaded,
  skeletonRows,
  children,
}: {
  /** True once the primary resource (the event, the form) has arrived.
   *  The body is what mounts when this flips true. */
  loaded: boolean;
  /** Skeleton row count while ``loaded`` is false. */
  skeletonRows?: number;
  children: Snippet;
} = $props();
</script>

<AppHeader />
<div class="container-wide stack">
  {#if !loaded}
    <AppSkeleton rows={skeletonRows ?? 4} cards />
  {:else}
    {@render children()}
  {/if}
</div>
