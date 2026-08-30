<script lang="ts">
import { locale, t } from "@/i18n.svelte";
import type { EventListOut } from "@/composables/useEvents.svelte";
import { formatDateTime } from "@/lib/format";
import { mapLink } from "@/lib/map-link";
import { recurrenceHint } from "@/lib/recurrence";

// The meta line an event shows wherever it is summarised: the list card
// and its details header. They used to be written out separately and
// drifted — two lines versus one, the location linked in one place and
// plain in the other — so the same event read as two different things on
// two screens. One component, one line:
//
//   Sporthal De Kaai · Tweewekelijks · 10 weken · 10-09-2026 19:00
//
// The date stands on its own. It was labelled "eerstvolgende:", which
// is most of the line's width for a word the position already says,
// and Dutch has no shorter one worth the space.
const { event }: { event: EventListOut } = $props();
</script>

<p class="muted overview-meta">
  {#if event.location}
    <a
      href={mapLink({
        location: event.location,
        latitude: event.latitude,
        longitude: event.longitude,
      })}
      target="_blank"
      rel="noopener"
      class="meta-link"
    >{event.location}</a>
    &middot;
  {/if}
  {recurrenceHint(t, event)}
  {#if event.next_starts_at}
    &middot; {formatDateTime(event.next_starts_at, locale())}
  {:else}
    &middot; {t("dashboard.noUpcoming")}
  {/if}
</p>
