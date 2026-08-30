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
  // An organisation's brand, so no strapline of ours either.
  tagline_nl: null,
  tagline_en: null,
  slug: "rsp",
  app_base: "/rsp/",
  app_name: brandManifest.app_name,
  wordmark: brandManifest.wordmark,
  org_name: brandManifest.org_name,
  org_url: brandManifest.org_url,
  logo_url: `/brand/rsp/${brandManifest.logo}`,
  favicon_url: `/brand/rsp/${brandManifest.favicon}`,
};

// happy-dom has no Web Animations API, and Svelte's transitions call
// ``element.animate`` to hold an element's first frame. Nothing here
// asserts on an animation, so a stub that reports a finished one is
// enough; without it the toast's fly-in throws past every assertion and
// fails the run on an error rather than on a test.
//
// It has to finish, not merely say it has. An out-transition removes
// its element when the animation ends, so a stub that never ends is an
// element that never goes away, and a test asking whether the toast
// left waits forever.
if (typeof Element !== "undefined" && !Element.prototype.animate) {
  Element.prototype.animate = function animate(): Animation {
    const animation = {
      cancel() {},
      finish() {
        animation.onfinish?.(new Event("finish") as AnimationPlaybackEvent);
      },
      onfinish: null as ((event: AnimationPlaybackEvent) => void) | null,
      finished: Promise.resolve(),
      currentTime: 0,
      playState: "finished",
    };
    // On the next turn, so a caller that assigns ``onfinish`` after
    // calling this is still heard.
    queueMicrotask(() => animation.finish());
    return animation as unknown as Animation;
  };
}
