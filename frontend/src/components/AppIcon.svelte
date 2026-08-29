<script lang="ts" module>
export type { IconName } from "./app-icons";
</script>

<script lang="ts">
/**
 * The app's icons, drawn rather than typed. Replaces PrimeIcons, whose
 * 23 glyphs in use cost a 35 kB woff2 and an 85 kB ttf that both
 * shipped.
 *
 * The paths are ``./app-icons``, shared with the Vue component that
 * draws the same set while the app crosses to Svelte
 * (``docs/tasks/svelte``). Every icon is decorative: the button or the
 * label beside it carries the meaning, so they are all ``aria-hidden``.
 */
import { PATHS, type IconName } from "./app-icons";

const {
  name,
  size = 16,
  class: className,
}: { name: IconName; size?: number; class?: string } = $props();

const paths = $derived(PATHS[name] ?? []);
</script>

<svg
  class="app-icon {className ?? ''}"
  width={size}
  height={size}
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="2"
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
>
  {#each paths as d, i (i)}
    <path {d} />
  {/each}
</svg>

<style>
.app-icon {
  flex: 0 0 auto;
  display: block;
}
</style>
