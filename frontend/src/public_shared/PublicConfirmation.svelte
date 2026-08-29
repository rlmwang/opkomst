<script lang="ts">
/** The post-submit confirmation shown on every public mini-app
 *  (event / form / datepoll / chore). One single card, IDENTICAL on all
 *  four: heading, one confirming line, then the secret edit link. The
 *  copy is fixed here (from ``chromeStrings``) so no entity can drift its
 *  own wording. It's deliberately the *only* card on the screen — the
 *  entity's top card is dropped on confirmation so nothing competes with
 *  the one thing that matters here: copying and saving that link.
 *
 *  Typography is a flat two-level scale — one bold heading, everything
 *  else the same regular muted body size — and every line shares the one
 *  column ``gap`` (``EditLink`` renders as a fragment so its lines are
 *  direct children here), so the rhythm is even top to bottom. There is
 *  no filler body line: the heading plus the link block say all there is
 *  to say. */
import EditLink from "./EditLink.svelte";
import { type Locale, chromeStrings } from "./strings";

const {
  url,
  locale,
  canEdit = true,
}: {
  url: string;
  locale: Locale;
  /** Passed through to ``EditLink``: whether the link leads back to
   *  something the visitor may still change. */
  canEdit?: boolean;
} = $props();

const c = $derived(chromeStrings(locale));
</script>

<div class="card confirmation">
  <h2 class="title">{c.thanks}</h2>
  <EditLink {url} {locale} {canEdit} />
</div>

<style>
.confirmation {
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
}
.title {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 600;
  line-height: 1.3;
}
</style>
