<script setup lang="ts">
/**
 * What actually sits in the slot, in priority order:
 *
 * 1. **An ad**, when the deployment has an ``ADSENSE_CLIENT_ID`` and an
 *    ad-unit id for this format.
 * 2. **An ask**, when ``SUPPORT_COFFEE_URL`` or ``SUPPORT_PATREON_URL``
 *    is set: one line of copy and each service's own button. The
 *    buttons are images this app serves, wrapped in ordinary links, so
 *    this path still loads nothing from outside and needs no CSP hole.
 * 3. **A statement of fact**, "no ads", when there is neither. The slot
 *    is never a blank rectangle.
 *
 * Both rails and the phone banner render through here, so the formats
 * cannot drift apart. ``variant`` only decides how things stack: down
 * the rail, across the banner.
 *
 * A live unit asks for its ad when it comes near the viewport, not when
 * it mounts. The phone banner is at the foot of the page and on most
 * visits is never reached, so asking on mount bills an advertiser for an
 * impression nobody had and costs the visitor a request they did not
 * need. A desktop rail is beside the content and asks immediately,
 * because it is already on screen.
 */
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import type { BrandAds } from "@/lib/branding";
import { type Locale, chromeStrings } from "./strings";
import { supportLinks } from "./support";

const props = defineProps<{
  ads: BrandAds;
  /** The AdSense ad-unit id for this format, null when unconfigured. */
  slotId: string | null;
  variant: "rail" | "banner";
  locale: Locale;
}>();

const c = computed(() => chromeStrings(props.locale));
const live = Boolean(props.ads.client_id && props.slotId);
const support = computed(() => supportLinks());

/** The ``<ins>`` itself, so the observer has something to watch. */
const unit = ref<HTMLElement | null>(null);
let observer: IntersectionObserver | null = null;
let requested = false;

/** Ask for an ad, once and once only.
 *
 * Pushing an empty object is how the tag is told a slot is ready. The
 * queue exists before the script does, which is the documented way to
 * declare a slot the page rendered client-side.
 *
 * Exactly once is the part that matters: a second push against the same
 * ``<ins>`` is an ad request that can never render, and requests that
 * do not render are what Google warns lazy loading tends to produce. */
function request() {
  if (!live || requested) return;
  requested = true;
  observer?.disconnect();
  observer = null;
  const w = window as unknown as { adsbygoogle?: unknown[] };
  (w.adsbygoogle = w.adsbygoogle ?? []).push({});
}

onMounted(() => {
  if (!live) return;
  // The phone banner sits at the foot of the page, so on most visits it
  // is never seen. Asking for it on mount bills an advertiser for an
  // impression nobody had, and costs the visitor the request. It is
  // asked for when it comes near the viewport instead.
  //
  // ``rootMargin`` is the lead time: 300px is roughly a flick of the
  // thumb, enough for the ad to arrive before the slot is on screen and
  // not so much that scrolling past the fold requests everything below
  // it. A rail, which is beside the content at desktop width, is already
  // intersecting when the observer starts and fires immediately.
  if (!("IntersectionObserver" in window) || !unit.value) {
    request();
    return;
  }
  observer = new IntersectionObserver(
    (entries) => {
      if (entries.some((entry) => entry.isIntersecting)) request();
    },
    { rootMargin: "300px" },
  );
  observer.observe(unit.value);
});

onBeforeUnmount(() => {
  observer?.disconnect();
  observer = null;
});
</script>

<template>
  <!-- The unit is never scaled or clipped: its size comes from
       requesting that ad format, which AdSense allows, rather than from
       transforming what it delivers, which it forbids. -->
  <ins
    v-if="live"
    ref="unit"
    class="adsbygoogle"
    :data-ad-client="props.ads.client_id"
    :data-ad-slot="props.slotId"
  />
  <div v-else class="filler" :class="variant">
    <span class="filler-text">{{ support.length > 0 ? c.supportHeading : c.adNone }}</span>
    <a
      v-for="s in support"
      :key="s.url"
      :href="s.url"
      target="_blank"
      rel="noopener"
      class="support-link"
    >
      <img :src="s.button" :alt="s.label" />
    </a>
  </div>
</template>

<style scoped>
.adsbygoogle {
  display: block;
  width: 100%;
  height: 100%;
}

/* The dashed frame belongs to the slot, not to this: it wraps a live
 * ad the same way (see ``AdSlot``). */
.filler {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  box-sizing: border-box;
}
/* Down the rail, which has room for the line and both buttons under
 * it; across the banner, which is one line high. */
.filler.rail {
  flex-direction: column;
  gap: 0.75rem;
  padding: 1rem 0.5rem;
}
.filler.banner {
  flex-direction: row;
  gap: 0.625rem;
  padding: 0 0.5rem;
}

.filler-text {
  font-size: 0.8125rem;
  color: var(--brand-text-muted);
  text-align: center;
  text-wrap: balance;
}
.filler.banner .filler-text {
  text-align: left;
}

/* Each service's own button, at its own aspect ratio, scaled to fit and
 * never cropped or recoloured, which is what both brand guidelines ask
 * for. */
.support-link {
  display: block;
  line-height: 0;
  flex-shrink: 0;
}
.support-link img {
  display: block;
  width: 100%;
  height: auto;
}
.filler.rail .support-link {
  width: 100%;
}
.filler.banner .support-link {
  width: 84px;
}
.support-link:hover img {
  opacity: 0.85;
}
</style>
