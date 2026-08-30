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
//   Sporthal De Kaai · Tweewekelijks · 10 weken · eerstvolgende: 10-09-2026 19:00
//
// A one-off has no "next" session, only its date, so it drops the word.
const { event }: { event: EventListOut } = $props();

const oneOff = $derived(event.cycle_slots.length === 0);
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
    &middot; {#if !oneOff}{t("event.nextSession")} {/if}{formatDateTime(event.next_starts_at, locale())}
  {:else}
    &middot; {t("dashboard.noUpcoming")}
  {/if}
</p>
