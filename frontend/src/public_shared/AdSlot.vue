<script setup lang="ts">
/**
 * The one advertising surface, shared by the organiser app and all four
 * public mini-apps. Design and reasoning: ``docs/ads.md``.
 *
 * Three questions decide what renders, in this order:
 *
 * 1. **Whose page is this?** ``brand().ads`` is null on every brand an
 *    organisation owns, so their pages never carry advertising. The
 *    server decides that and the client only reads it.
 * 2. **How wide is the viewport?** At 1120px and up the slot is two
 *    120x600 rails pinned just outside the 720px content column. Below
 *    that there is no room beside the content, so it is a single 320x50
 *    banner at the foot of the page. Never both.
 * 3. **Is a network configured?** That question lives in ``AdUnit``.
 *
 * The breakpoint decides whether the unit is *created*, not merely
 * whether it is visible: an ad script measures its container, and a
 * hidden one is a zero-width box it will refuse to fill.
 */
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import AdUnit from "./AdUnit.vue";
import { brand } from "@/lib/branding";
import { type Locale, chromeStrings } from "./strings";

const props = defineProps<{
  locale: Locale;
  /** Suppress the slot on a page that has to stand alone, such as the
   *  post-signup confirmation. */
  hide?: boolean;
}>();

/** Wide enough for 16 + 160 + 64 + 720 + 64 + 160 + 16: the content
 *  column, a rail either side at the standard wide-skyscraper size, the
 *  64px gutter that keeps them off the content, and a margin. */
const RAILS_FROM = "(min-width: 1200px)";

const ads = brand().ads;
const c = computed(() => chromeStrings(props.locale));
const show = computed(() => Boolean(ads) && !props.hide);


const wide = ref(false);
let media: MediaQueryList | null = null;
const onChange = (e: MediaQueryListEvent) => {
  wide.value = e.matches;
};

onMounted(() => {
  if (!show.value) return;
  media = window.matchMedia(RAILS_FROM);
  wide.value = media.matches;
  media.addEventListener("change", onChange);
  if (ads?.client_id) loadAdSense(ads.client_id);
});

onBeforeUnmount(() => media?.removeEventListener("change", onChange));

/** The AdSense tag, added once per document however many units mount.
 *  It brings Google's consent dialog with it, so this function is the
 *  only thing in the app that can put a cookie banner on the screen.
 *  Without a client id it is never called. */
function loadAdSense(clientId: string) {
  const id = "adsense-tag";
  if (document.getElementById(id)) return;
  const tag = document.createElement("script");
  tag.id = id;
  tag.async = true;
  tag.crossOrigin = "anonymous";
  tag.src = `https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=${encodeURIComponent(clientId)}`;
  document.head.appendChild(tag);
}
</script>

<template>
  <template v-if="show && ads">
    <!-- Wide: two rails fixed to the viewport just outside the content
         column, so no page has to change its own layout to make room. -->
    <template v-if="wide">
      <aside class="ad-rail ad-rail-left" :aria-label="c.adLabel">
        <AdUnit :ads="ads" :slot-id="ads.rail_slot" variant="rail" :locale="locale" />
      </aside>
      <aside class="ad-rail ad-rail-right" :aria-label="c.adLabel">
        <AdUnit :ads="ads" :slot-id="ads.rail_slot" variant="rail" :locale="locale" />
      </aside>
    </template>
    <!-- Narrow: one banner at the foot of the page, in the flow. Never
         pinned to the screen, which on a sign-up page would land on top
         of the submit button. -->
    <aside v-else class="ad-banner" :aria-label="c.adLabel">
      <AdUnit :ads="ads" :slot-id="ads.banner_slot" variant="banner" :locale="locale" />
    </aside>
  </template>
</template>

<style scoped>
/* Rails are fixed rather than part of any page's grid, so no page has
 * to change its layout to make room, and they are pinned to the edges
 * of the viewport rather than to the content column. At the 1120px
 * breakpoint that puts exactly 64px between a rail and the content;
 * every pixel of screen beyond that widens the gap instead of the
 * margins, so on a large display the ads sit far out in the periphery
 * and the content is left alone. */
/* The box is always the ad's exact size, whether or not an ad is in it:
 * the script reports a container it cannot fill otherwise, and an empty
 * slot should show where the ad goes rather than quietly collapse. */
.ad-rail {
  position: fixed;
  top: 50%;
  transform: translateY(-50%);
  width: 160px;
  height: 600px;
  overflow: hidden;
}
.ad-rail-left {
  left: 16px;
}
.ad-rail-right {
  right: 16px;
}

.ad-banner {
  display: block;
  width: 320px;
  height: 50px;
  margin: 1.5rem auto 0;
  overflow: hidden;
}
</style>
