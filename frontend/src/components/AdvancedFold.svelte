<script lang="ts">
import type { Snippet } from "svelte";

import { t } from "@/i18n.svelte";
import { anchor } from "@/tours/anchors.svelte";

/**
 * The fold every edit page ends with: the thing itself above it, the
 * switches inside it, the page language below
 * (``docs/design-public-pages-ux.md``). Closed on arrival.
 *
 * A ``<details>`` and not a button plus a branch: it is a disclosure,
 * the browser already knows how to open and close one, and it tells a
 * screen reader so without any aria of ours. The summary carries the
 * tour's ``form.fold`` anchor, and a click step on it opens the fold.
 */
let { open = $bindable(false), children }: { open?: boolean; children: Snippet } = $props();
</script>

<details
  class="advanced"
  {open}
  ontoggle={(e) => (open = (e.currentTarget as HTMLDetailsElement).open)}
>
  <summary use:anchor={"form.fold"}>{open ? t("common.advancedHide") : t("common.advancedShow")}</summary>
  {@render children()}
</details>
