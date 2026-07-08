<script setup lang="ts">
import { computed } from "vue";
import { formatDate, formatTimeRange } from "@/lib/format";
import { mapLink } from "@/lib/map-link";
import PublicHero from "@/public_shared/PublicHero.vue";
import { chromeStrings, type Locale } from "@/public_shared/strings";
import type { EventCard } from "./api";
import { strings } from "./i18n";

// One event in the agenda grid. Its poster (or the muted-RSP-logo
// default), the date/time, location, title, topic, and the sign-up CTA.
// The whole card isn't a single anchor because ``PublicHero`` renders its
// own credit link; the title and CTA are the links instead.
const props = defineProps<{ event: EventCard; locale: Locale; past?: boolean }>();

const t = computed(() => strings(props.locale));
const c = computed(() => chromeStrings(props.locale));
const href = computed(() => `/e/${props.event.slug}`);
</script>

<template>
  <article class="event-card card" :class="{ past }">
    <PublicHero
      v-if="event.image_url"
      :image-url="event.image_url"
      :artist="event.image_artist_instagram"
      :credit-label="c.imageCredit"
    />
    <div v-else class="card-logo" aria-hidden="true">
      <img src="/rsp-logo.png" alt="" />
    </div>

    <div class="card-body">
      <p class="card-when">
        {{ formatDate(event.starts_at, locale) }} ·
        {{ formatTimeRange(event.starts_at, event.ends_at, locale) }}
      </p>
      <p class="card-where">
        <a
          :href="mapLink({ location: event.location, latitude: null, longitude: null })"
          target="_blank"
          rel="noopener"
          class="meta-link"
        >{{ event.location }}</a>
      </p>
      <h2 class="card-title">
        <a :href="href">{{ event.name }}</a>
      </h2>
      <div v-if="event.topic" class="richtext card-topic" v-html="event.topic"></div>

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
.event-card {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  height: 100%;
}
.event-card.past {
  opacity: 0.72;
}
/* Muted RSP-logo default in the same 4:5 frame as PublicHero, so the
 * grid stays even for events without a poster. */
.card-logo {
  width: 100%;
  max-width: 320px;
  aspect-ratio: 4 / 5;
  margin: 0 auto;
  border-radius: 12px;
  border: 1px solid var(--brand-border);
  background: var(--brand-bg);
  display: flex;
  align-items: center;
  justify-content: center;
}
.card-logo img {
  width: 55%;
  max-width: 160px;
  opacity: 0.22;
  filter: grayscale(1);
}
.card-body {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  flex: 1;
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
.card-title {
  margin: 0.125rem 0 0;
  font-size: 1.125rem;
  line-height: 1.25;
}
.card-title a {
  color: inherit;
  text-decoration: none;
}
.card-title a:hover {
  text-decoration: underline;
  text-decoration-color: var(--brand-red);
}
/* Clamp the topic so cards keep even heights in the grid. */
.card-topic {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.card-foot {
  margin-top: auto;
  padding-top: 0.25rem;
}
.card-cta {
  display: inline-block;
  width: auto;
  text-decoration: none;
}
.card-came {
  display: inline-block;
}
</style>
