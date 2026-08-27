<script setup lang="ts">
import { computed } from "vue";
import { brand } from "@/lib/branding";
import { formatDateShortWeekday, formatTimeRange } from "@/lib/format";
import { mapLink } from "@/lib/map-link";
import { resolveText } from "@/public_shared/bilingual";
import { chromeStrings, type Locale } from "@/public_shared/strings";
import type { EventCard } from "./api";
import { strings } from "./i18n";

// One event in the agenda grid: a full-bleed poster (or the muted
// organisation logo as the default) topping the card, then the date/time,
// location, title, topic,
// and the sign-up CTA. The whole card isn't a single anchor because the
// poster carries its own credit link; the title and CTA are the links.
const props = defineProps<{ event: EventCard; locale: Locale; past?: boolean }>();

const b = brand();
const t = computed(() => strings(props.locale));
const c = computed(() => chromeStrings(props.locale));
const href = computed(() => `/e/${props.event.slug}`);
const title = computed(() =>
  resolveText(props.event.name_nl, props.event.name_en, props.locale),
);
const topic = computed(() =>
  resolveText(props.event.topic_nl, props.event.topic_en, props.locale),
);
// A one-off event is "sessie 1 van 1" — pure noise, so no badge. Only a
// real series (finite ``> 1``, or open-ended ``null``) earns one.
const sessionBadge = computed(() => {
  if (props.event.total_sessions === 1) return null;
  return props.event.total_sessions === null
    ? t.value.sessionOpen(props.event.index + 1)
    : t.value.sessionOf(props.event.index + 1, props.event.total_sessions);
});

</script>

<template>
  <article class="event-card card" :class="{ past }">
    <div class="card-media">
      <img v-if="event.image_url" :src="event.image_url" alt="" class="card-media__img" />
      <div v-else class="card-media__placeholder" aria-hidden="true">
        <img :src="b.logo_url" alt="" />
      </div>
      <span v-if="sessionBadge" class="session-badge">{{ sessionBadge }}</span>
      <figcaption v-if="event.image_url && event.image_artist_instagram" class="card-credit">
        {{ c.imageCredit }}
        <a
          :href="`https://instagram.com/${event.image_artist_instagram}`"
          target="_blank"
          rel="noopener"
        >@{{ event.image_artist_instagram }}</a>
      </figcaption>
    </div>

    <div class="card-meta">
      <p class="card-when">
        {{ formatDateShortWeekday(event.starts_at, locale) }} ·
        {{ formatTimeRange(event.starts_at, event.ends_at, locale) }}
      </p>
      <p v-if="event.location" class="card-where">
        <a
          :href="mapLink({ location: event.location, latitude: null, longitude: null })"
          target="_blank"
          rel="noopener"
          class="meta-link"
        >{{ event.location }}</a>
      </p>
    </div>

    <div class="card-body">
      <h2 class="card-title">
        <a :href="href">{{ title }}</a>
      </h2>
      <div v-if="topic" class="richtext card-topic" v-html="topic"></div>

      <div class="card-foot">
        <span v-if="past" class="muted card-came">
          {{ event.attendee_count ? t.attendees(event.attendee_count) : "" }}
        </span>
        <a v-else :href="href" class="btn-primary card-cta">{{ t.signUp }}</a>
      </div>
    </div>
  </article>
</template>

<style scoped>
/* No card padding: the poster is flush to the card's edges, so we pad the
 * body instead and clip everything to the card's radius. Poster left,
 * words right — a 4:5 poster running the full width of the card outweighs
 * the handful of lines under it, and this gives the two equal say. */
.event-card {
  display: grid;
  grid-template-columns: 38% 1fr;
  grid-template-rows: auto 1fr;
  padding: 0;
  overflow: hidden;
  height: 100%;
}
.event-card.past {
  opacity: 0.72;
}
/* The poster column: a bit over a third of the card, its own 4:5, pinned
 * to the top so a long topic grows the card without stretching the
 * artwork. Also the positioning context for the session pill and the
 * artist credit. */
.card-media {
  position: relative;
  grid-column: 1;
  grid-row: 1 / span 2;
  align-self: start;
  aspect-ratio: 4 / 5;
}
.card-media__img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
/* Muted RSP-logo default, filling the same frame so the grid stays even
 * for events without a poster. */
.card-media__placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--brand-bg);
}
.card-media__placeholder img {
  width: 45%;
  max-width: 160px;
  opacity: 0.22;
  filter: grayscale(1);
}
/* Session pill, top-left over the poster — a red tag that never wraps or
 * spills the way the old inline "sessie i van n" chip did. */
.session-badge {
  position: absolute;
  top: 0.5rem;
  left: 0.5rem;
  font-size: 0.75rem;
  font-weight: 600;
  padding: 0.15rem 0.55rem;
  border-radius: 999px;
  background: var(--brand-red);
  color: #fff;
  white-space: nowrap;
}
/* Artist credit, bottom-right over the poster on a dark scrim chip. */
.card-credit {
  position: absolute;
  right: 0.5rem;
  bottom: 0.5rem;
  font-size: 0.75rem;
  padding: 0.1rem 0.5rem;
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
}
.card-credit a {
  color: #fff;
}
/* Date and location sit beside the poster; the title and topic get their
 * own row underneath, which on a phone is the full width of the card. */
.card-meta {
  grid-column: 2;
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  min-width: 0;
  padding: 1rem 1.25rem 0;
}
.card-body {
  grid-column: 2;
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  min-width: 0;
  padding: 0.5rem 1.25rem 1.25rem;
}
.card-when {
  margin: 0;
  font-size: 0.9375rem;
  color: var(--brand-text-muted);
}
.card-where {
  margin: 0;
  font-size: 0.9375rem;
}
/* Two lines each for the title and the topic, ellipsis past that: the
 * card is a glance, and an even ceiling keeps a long title from pushing
 * its neighbour's CTA out of line. */
.card-title {
  margin: 0.125rem 0 0;
  font-size: 1.125rem;
  line-height: 1.25;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.card-title a {
  color: inherit;
  text-decoration: none;
}
.card-title a:hover {
  text-decoration: underline;
  text-decoration-color: var(--brand-red);
}
.card-topic {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
/* Bottom-right: the CTA is the card's last word, and against the poster
 * column the far corner is where the eye lands after the topic. */
.card-foot {
  margin-top: auto;
  padding-top: 0.5rem;
  display: flex;
  justify-content: flex-end;
}
.card-cta {
  display: inline-block;
  width: auto;
  text-decoration: none;
}
/* Poster beside the text at every width, phones included — stacking it
 * back on top is the imbalance this layout exists to fix. A phone row is
 * ~390px, and 38% of that leaves the title barely 220px, so here the
 * poster takes a fixed 110px instead of a share and the words get the
 * rest. */
@media (max-width: 32rem) {
  .event-card {
    grid-template-columns: 96px 1fr;
  }
  .card-media {
    grid-row: 1;
    /* The poster's bottom-right corner floats inside the card here (the
     * title row sits under it), so it gets the card's own radius rather
     * than a raw edge. The other three touch a card edge or the grid. */
    border-bottom-right-radius: 10px;
    overflow: hidden;
  }
  .card-meta {
    padding: 0.75rem 0.875rem 0;
  }
  /* Full width under the poster: a title beside a 4:5 thumbnail on a
   * phone row has nowhere to go. */
  .card-body {
    grid-column: 1 / -1;
    padding: 0.625rem 0.875rem 0.875rem;
  }
}
.card-came {
  display: inline-block;
}
</style>
