/**
 * The brand the page is wearing, as handed to the bundle by the server.
 *
 * ``backend/services/brand.py`` injects ``window.__OPKOMST_BRAND__``
 * into every HTML shell (the Vite dev server does the same), so the
 * bundle never contains a logo, a wordmark or an app name — only the
 * code that reads them. That is what lets a new organisation be a
 * folder in ``brands/`` plus a row, with no rebuild.
 */

/** What the house brand's advertising slot needs. Null on every brand
 *  an organisation owns, which is how a page knows it carries none.
 *  ``client_id`` is null until a deployment is given one, and then no
 *  network script, consent dialog or cookie is involved at all: the
 *  slot renders ``fallback_*_url`` instead. See ``docs/ads.md``. */
export interface BrandAds {
  client_id: string | null;
  rail_slot: string | null;
  banner_slot: string | null;
  /** Offered in the slot when no ad is served. Each service's own
   *  button artwork, committed to ``brands/`` and served from this app
   *  rather than from their CDNs, wrapped in an ordinary link: no embed
   *  widget, no third-party request, no CSP hole. The two URLs are
   *  optional and independent; the button images ship with the brand. */
  coffee_url: string | null;
  coffee_button_url: string | null;
  patreon_url: string | null;
  patreon_button_url: string | null;
}

export interface Brand {
  ads: BrandAds | null;
  slug: string;
  /** Where the app is mounted: the router's history base. ``/{tenant}/``
   * for an organisation, ``/`` for the house brand, which is the
   * personal app. */
  app_base: string;
  app_name: string;
  wordmark: string;
  org_name: string;
  org_url: string;
  logo_url: string;
  favicon_url: string;
}

declare global {
  interface Window {
    __OPKOMST_BRAND__?: Brand;
  }
}

/** The injected brand. Throws when the marker wasn't substituted —
 * a page without a brand is a broken deploy, not a case to default. */
export function brand(): Brand {
  const injected = window.__OPKOMST_BRAND__;
  if (!injected) {
    throw new Error("No brand injected — the page shell is missing its OPKOMST_BRAND_INJECTION marker");
  }
  return injected;
}

export const APP_NAME = brand().app_name;

/** Whether this page is the tenant-less app at the root.
 *
 * The house brand is mounted at ``/`` and no organisation is; the
 * server decides which of the two a URL gets (``routers/spa.py``), so
 * the base it injected is the answer and the app never parses the URL
 * to second-guess it. Drives the things a personal account doesn't
 * have: no chapters, no admin pages, no organisation to sign in to. */
export function isPersonalApp(): boolean {
  return brand().app_base === "/";
}
