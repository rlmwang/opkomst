<script lang="ts">
/** A single centered card for the standalone screens every public
 *  mini-app shows: loading, "no longer available", load-failed, and
 *  the post-submit thank-you. One component so these screens look and
 *  read the same across all three. */
const { title, message }: { title?: string; message: string } = $props();
</script>

<div class="card notice">
  {#if title}<h2>{title}</h2>{/if}
  <p class="muted">{message}</p>
</div>

<style>
.notice { text-align: center; }
.notice h2 { margin: 0 0 0.5rem; }
.muted { color: var(--brand-text-muted); margin: 0; }
</style>
