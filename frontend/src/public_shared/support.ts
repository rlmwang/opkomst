/**
 * Where to send someone who wants to pay for this, and the artwork to
 * ask with. One list, read by the two places that offer it: the
 * advertising slot's empty state (``AdUnit``) and the footer beside
 * every form (``SupportButtons``).
 *
 * A link only appears when the deployment has been given its URL *and*
 * the brand carries the button image, so a half-configured environment
 * shows nothing rather than a broken image.
 */
import { brand } from "@/lib/branding";

export interface SupportLink {
  url: string;
  button: string;
  label: string;
}

export function supportLinks(): SupportLink[] {
  const ads = brand().ads;
  if (!ads) return [];
  return [
    { url: ads.coffee_url, button: ads.coffee_button_url, label: "Buy me a coffee" },
    { url: ads.patreon_url, button: ads.patreon_button_url, label: "Patreon" },
  ].filter((s): s is SupportLink => Boolean(s.url && s.button));
}
