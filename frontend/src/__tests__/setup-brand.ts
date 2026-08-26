/**
 * Vitest stands in for the server's brand injection.
 *
 * Every HTML shell is served with ``window.__OPKOMST_BRAND__`` already
 * defined (``backend/services/brand.py`` in prod, the dev plugin in
 * ``vite.config.ts`` locally). Under vitest there is no shell, so this
 * setup file defines it before any test module imports the branding
 * helper — which throws by design when the brand is absent.
 *
 * The values are the RSP brand's; nothing asserts on them, they just
 * have to be present and well-formed.
 */

import brandManifest from "../../../brands/rsp/brand.json";

window.__OPKOMST_BRAND__ = {
  // An organisation's brand, so no advertising: the same null the
  // server sends for every brand but the house one.
  ads: null,
  slug: "rsp",
  app_base: "/rsp/",
  app_name: brandManifest.app_name,
  wordmark: brandManifest.wordmark,
  org_name: brandManifest.org_name,
  org_url: brandManifest.org_url,
  logo_url: `/brand/rsp/${brandManifest.logo}`,
  favicon_url: `/brand/rsp/${brandManifest.favicon}`,
};
