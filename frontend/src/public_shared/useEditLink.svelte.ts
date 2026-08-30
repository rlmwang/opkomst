/**
 * The magic-link edit contract shared by every public mini-app
 * (event / form / datepoll / chore).
 *
 * A submission mints a secret edit token. Recording that token MUST also
 * rewrite the URL onto ``?s={token}`` (no reload) so a panicked refresh
 * on the confirmation screen reopens the editable submission instead of
 * a blank new form. Bundling both into ``confirmSaved`` makes the
 * routing structural: there is no way to store the token without
 * updating the URL, so it cannot be forgotten per page. It once was, on
 * the chore page.
 *
 * @param prefix the public route segment (``e`` / ``f`` / ``d`` / ``c``).
 * @param getSlug a getter, so callers can hold the slug as a constant or
 *   derive it lazily from the path.
 */
export function useEditLink(prefix: string, getSlug: () => string) {
  // The token present when the page loads in edit mode (``?s=...``).
  const editToken = new URL(window.location.href).searchParams.get("s");

  // The token to surface on the confirmation screen (the edit link).
  // Null until a submission confirms, so edit mode hides the link until
  // the visitor saves.
  let savedToken = $state<string | null>(null);

  const editUrl = $derived(
    savedToken ? `${window.location.origin}/${prefix}/${getSlug()}?s=${savedToken}` : "",
  );

  /**
   * Record the edit token and route the URL onto it, one atomic step, so
   * the confirmation is always reachable again by refresh.
   */
  function confirmSaved(token: string): void {
    savedToken = token;
    if (editUrl) window.history.replaceState(null, "", editUrl);
  }

  // A getter, because a plain property would hand the caller the value
  // this ran with rather than the one it has.
  return {
    editToken,
    get editUrl() {
      return editUrl;
    },
    confirmSaved,
  };
}
