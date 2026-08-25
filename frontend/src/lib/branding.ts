/**
 * The brand the page is wearing, as handed to the bundle by the server.
 *
 * ``backend/services/brand.py`` injects ``window.__OPKOMST_BRAND__``
 * into every HTML shell (the Vite dev server does the same), so the
 * bundle never contains a logo, a wordmark or an app name — only the
 * code that reads them. That is what lets a new organisation be a
 * folder in ``brands/`` plus a row, with no rebuild.
 */

export interface Brand {
  slug: string;
  /** Where the organiser app is mounted — the router's history base.
   * ``/{tenant}/`` for an organisation, ``/`` for the house brand,
   * which only ever renders the not-found page. */
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
