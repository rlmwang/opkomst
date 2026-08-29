<script lang="ts">
import AppConfirmDialog from "@/components/AppConfirmDialog.svelte";
import AppToast from "@/components/AppToast.svelte";
import SiteFooter from "@/components/SiteFooter.svelte";
import AdSlot from "@/public_shared/AdSlot.svelte";
import { locale } from "@/i18n.svelte";
import { route } from "@/router/navigation.svelte";

/**
 * The organiser app's shell: the page the router chose, with the toast
 * stack, the confirm dialog, the advertising slot and the colophon
 * around it.
 *
 * Signing in is not bootstrapped here. The guard is the one place that
 * knows which routes need auth state, and the shell asking as well
 * produced two ``/auth/me`` requests on every load, plus one on public
 * routes that need none.
 */

// The first paint shows the page background alone while the first
// navigation settles: the guard may be waiting on ``/auth/me``, slow on
// a cold backend, and then the page's own chunk has to arrive. A
// spinner over that gap beats a blank screen, and the delay before it
// keeps a fast load from flashing one.
let showLoader = $state(false);
const timer = window.setTimeout(() => {
  if (!route.ready) showLoader = true;
}, 150);

$effect(() => {
  if (route.ready) window.clearTimeout(timer);
});

const Page = $derived(route.component);
</script>

<AppToast />
<AppConfirmDialog />

<!-- The shell is a column as tall as the viewport and this is the part
     of it that grows, so the colophon lands on the bottom edge of the
     screen on a page with too little content to push it there, instead
     of floating halfway up under the last card. -->
<div class="app-main">
  {#if Page}
    <Page {...route.params} />
  {/if}
</div>

<!-- Advertising, on the pages that carry any. ``AdSlot`` decides: an
     organisation's app gets none at all. -->
<AdSlot locale={locale() as "nl" | "en"} />

<!-- The colophon: the written pages, the policy and the source. House
     brand only; an organisation's pages are theirs. Last on the page and
     below the banner, because it is the bottom edge of the site and an
     ad underneath it read as a second footer. -->
<SiteFooter />

{#if !route.ready && showLoader}
  <div class="app-loading" role="status" aria-label="Laden…">
    <span class="app-loading-spinner"></span>
  </div>
{/if}

<style>
/* Global on purpose: the element that has to be the column is the mount
 * point, which is outside every component, and the box-sizing reset is
 * the whole document's. Only this bundle mounts ``App``, so the public
 * mini-apps are left as they are. Inside ``@layer app`` like every other
 * global rule. */
@layer app {
  /* Padding and border count inside a declared width. PrimeVue's reset
   * used to set this for the whole page; it left with PrimeVue, and
   * without it every fluid input overflows its column by its own
   * padding. */
  :global(*),
  :global(*::before),
  :global(*::after) {
    box-sizing: border-box;
  }

  :global(#app) {
    display: flex;
    flex-direction: column;
    min-height: 100dvh;
  }
}

.app-main {
  flex: 1 0 auto;
}
.app-loading {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--brand-bg);
  z-index: 9999;
}
.app-loading-spinner {
  width: 2.25rem;
  height: 2.25rem;
  border-radius: 50%;
  border: 3px solid color-mix(in srgb, var(--brand-red) 25%, transparent);
  border-top-color: var(--brand-red);
  animation: app-loading-spin 0.8s linear infinite;
}
@keyframes app-loading-spin {
  to {
    transform: rotate(360deg);
  }
}
@media (prefers-reduced-motion: reduce) {
  .app-loading-spinner {
    animation: none;
  }
}
</style>
