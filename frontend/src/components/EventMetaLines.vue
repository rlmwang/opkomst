<script setup lang="ts">
import { useI18n } from "@/i18n";
import type { EventListOut } from "@/composables/useEvents";
import { formatDateTime } from "@/lib/format";
import { mapLink } from "@/lib/map-link";
import { recurrenceHint } from "@/lib/recurrence";

// The meta line an event shows wherever it is summarised: the list card
// and its details header. They used to be written out separately and
// drifted — two lines versus one, the location linked in one place and
// plain in the other — so the same event read as two different things on
// two screens. One component, one line:
//
//   Sporthal De Kaai · Tweewekelijks · 10 weken · eerstvolgende: 10-09-2026 19:00
//
// A one-off has no "next" session, only its date, so it drops the word.
const props = defineProps<{ event: EventListOut }>();
const { t, locale } = useI18n();

const oneOff = () => props.event.cycle_slots.length === 0;
</script>

<template>
  <p class="muted overview-meta">
    <template v-if="event.location">
      <a
        :href="mapLink({
          location: event.location,
          latitude: event.latitude,
          longitude: event.longitude,
        })"
        target="_blank"
        rel="noopener"
        class="meta-link"
      >{{ event.location }}</a>
      ·
    </template>
    {{ recurrenceHint(t, event) }}
    <template v-if="event.next_starts_at">
      · <template v-if="!oneOff()">{{ t("event.nextSession") }} </template>
      {{ formatDateTime(event.next_starts_at, locale) }}
    </template>
    <template v-else>· {{ t("dashboard.noUpcoming") }}</template>
  </p>
</template>
