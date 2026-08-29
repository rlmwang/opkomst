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

/** Wide enough for 16 + 178 + 64 + 720 + 64 + 178 + 16: the content
 *  column, a framed rail either side (160 of ad plus its frame), the
 *  64px gutter that keeps them off the content, and a margin. */
const RAILS_FROM = "(min-width: 1236px)";

const ads = brand().ads;
const c = computed(() => chromeStrings(props.locale));
const show = computed(() => Boolean(ads) && !props.hide);

/** Whether a real ad is being served in each format. The label is for
 *  advertising: it is inaccurate over our own support buttons, and it
 *  would also be the thing that gets them ignored, since readers filter
 *  anything sitting inside a labelled ad frame. */
const railLive = Boolean(ads?.client_id && ads?.rail_slot);
const bannerLive = Boolean(ads?.client_id && ads?.banner_slot);


/* Resolved during setup, not on mount: deciding it a tick later
 * rendered the phone banner first and swapped it for the rails a frame
 * afterwards, which is a visible jump on every desktop load. */
const wide = ref(window.matchMedia(RAILS_FROM).matches);
let media: MediaQueryList | null = null;
const onChange = (e: MediaQueryListEvent) => {
  wide.value = e.matches;
};

onMounted(() => {
  if (!show.value) return;
  media = window.matchMedia(RAILS_FROM);
  media.addEventListener("change", onChange);
  if (ads?.client_id) loadAdSense(ads.client_id);
});

onBeforeUnmount(() => media?.removeEventListener("change", onChange));

/** The AdSense tag, added once per document however many units mount.
 *  It brings Google's consent dialog with it, so this function is the
 *  only thing in the app that can put a cookie banner on the screen.
 *  Without a client id it is never called.
 *
 *  **Injected when the browser is idle**, not the moment this mounts.
 *  ``async`` already keeps the tag from blocking parsing — it is what
 *  Google publishes and what they mean by "fully asynchronous" — but an
 *  async script still competes for bandwidth and the main thread while
 *  the app is hydrating, which is the part of a page load a visitor
 *  feels. Waiting for idle moves that competition to after the page has
 *  settled, and changes nothing about the ad code itself: what Google
 *  forbids modifying is how ads are placed and targeted, not when their
 *  tag is added to the page.
 *
 *  The 3-second timeout is the promise that idle eventually arrives. A
 *  page that never goes idle would otherwise never load an ad, and an
 *  ad slot that stays empty for ever is worse for a reader than one
 *  that fills a moment late. */
function loadAdSense(clientId: string) {
  const id = "adsense-tag";
  if (document.getElementById(id)) return;
  const inject = () => {
    if (document.getElementById(id)) return;
    const tag = document.createElement("script");
    tag.id = id;
    tag.async = true;
    tag.crossOrigin = "anonymous";
    tag.src = `https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=${encodeURIComponent(clientId)}`;
    document.head.appendChild(tag);
  };
  const idle = (window as unknown as { requestIdleCallback?: (cb: () => void, o?: object) => number })
    .requestIdleCallback;
  if (idle) idle(inject, { timeout: 3000 });
  else window.setTimeout(inject, 200);
}
</script>

<template>
  <template v-if="show && ads">
    <!-- Wide: two rails fixed to the viewport just outside the content
         column, so no page has to change its own layout to make room. -->
    <template v-if="wide">
      <aside class="ad-rail ad-rail-left">
        <span v-if="railLive" class="ad-label">{{ c.adLabel }}</span>
        <div class="ad-box rail-box">
          <AdUnit :ads="ads" :slot-id="ads.rail_slot" variant="rail" :locale="locale" />
        </div>
      </aside>
      <aside class="ad-rail ad-rail-right">
        <span v-if="railLive" class="ad-label">{{ c.adLabel }}</span>
        <div class="ad-box rail-box">
          <AdUnit :ads="ads" :slot-id="ads.rail_slot" variant="rail" :locale="locale" />
        </div>
      </aside>
    </template>
    <!-- Narrow: one banner at the foot of the page, in the flow. Never
         pinned to the screen, which on a sign-up page would land on top
         of the submit button. -->
    <aside v-else class="ad-banner">
      <span v-if="bannerLive" class="ad-label">{{ c.adLabel }}</span>
      <div class="ad-box banner-box">
        <AdUnit :ads="ads" :slot-id="ads.banner_slot" variant="banner" :locale="locale" />
      </div>
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
.ad-rail {
  position: fixed;
  top: 50%;
  transform: translateY(-50%);
  /* 160 of ad plus the frame's padding and rule on each side. */
  width: 178px;
}
.ad-rail-left {
  left: 16px;
}
.ad-rail-right {
  right: 16px;
}

.ad-banner {
  width: 338px;
  max-width: 100%;
  margin: 1.5rem auto 0;
}

/* A frame and a word, both deliberately quiet.
 *
 * An edge is a salience feature, so a strong border would pull the eye
 * out to the periphery. A faint one does the opposite job: a framed,
 * labelled rectangle is the clearest possible "this is an ad", and
 * banner blindness is triggered by exactly that, so the region is
 * classified and skipped sooner. Low contrast is what gets both.
 *
 * "Advertentie" / "Advertisement" is also the labelling AdSense
 * permits: those two words, or "Sponsored Links", and nothing else. */
.ad-label {
  display: block;
  margin-bottom: 0.25rem;
  color: var(--brand-text-muted);
  font-size: 0.6875rem;
  letter-spacing: 0.04em;
  text-transform: lowercase;
  opacity: 0.7;
}
/* ``content-box`` plus padding: the inner area stays the ad's exact
 * pixel size, and the frame stands off it instead of running along the
 * creative's own edge, where a dashed line against a busy image reads
 * as noise rather than as a boundary. */
.ad-box {
  border: 1px dashed var(--brand-border);
  border-radius: 6px;
  padding: 8px;
  overflow: hidden;
  box-sizing: content-box;
}
/* The ad itself is always given its exact size, whether or not one is
 * being served: the script reports a container it cannot fill
 * otherwise, and an empty slot should show where the ad goes rather
 * than quietly collapse. */
.rail-box {
  width: 160px;
  height: 600px;
}
.banner-box {
  width: 320px;
  height: 50px;
}
</style>
