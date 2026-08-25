/// <reference types="vitest" />
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath, URL } from "node:url";
import vue from "@vitejs/plugin-vue";
import { defineConfig, type Plugin } from "vite";

/**
 * Dev-only middleware: route ``/e/{slug}`` to ``public-event.html``.
 *
 * In production, ``backend/routers/spa.py`` handles ``/e/{slug}``
 * by reading ``public-event.html`` off ``frontend/dist`` and
 * injecting ``window.__OPKOMST_EVENT__`` before serving it. The
 * Vite dev server has no equivalent — visiting ``/e/foo`` would
 * fall through to ``index.html`` (the admin SPA) and the public
 * mini-app would never mount.
 *
 * This plugin closes the gap by URL-rewriting ``/e/<slug>`` to
 * ``/public-event.html`` before Vite resolves the file. No
 * inlining of event data: the mini-app's
 * ``window.__OPKOMST_EVENT__ === undefined`` branch detects the
 * dev case and falls back to fetching the event over the existing
 * ``/api`` proxy. So dev = inline-data-fallback path; prod =
 * inline-data-fast path. Both work, both look identical to the
 * mini-app code.
 */
function publicEventDevRoute(): Plugin {
  // The ``/e/`` namespace is shared: an 8-char event slug (nanoid
  // alphabet) serves the sign-up page; anything else is a chapter slug →
  // the agenda page. This mirrors the ``is_event_slug`` dispatch in
  // ``backend/routers/spa.py`` so both dev and prod route the same way.
  const eventSlug = /^\/e\/[23456789abcdefghijkmnpqrstuvwxyz]{8}(?:[/?#]|$)/;
  return {
    name: "opkomst-public-event-dev-route",
    apply: "serve",
    configureServer(server) {
      server.middlewares.use((req, _res, next) => {
        const path = (req.url ?? "").split("?")[0];
        if (/^\/e\/[^/?#]+/.test(path)) {
          req.url = eventSlug.test(req.url ?? "")
            ? "/public-event.html"
            : "/public-chapter.html";
        }
        next();
      });
    },
  };
}

/**
 * Dev-only middleware: route ``/f/{slug}`` to ``public-form.html``.
 *
 * Mirrors ``publicEventDevRoute`` one-to-one for the forms
 * mini-app. In production ``backend/routers/spa.py`` handles
 * ``/f/{slug}`` by reading the built ``public-form.html`` off
 * ``frontend/dist`` and injecting ``window.__OPKOMST_FORM__``
 * before serving. The dev server has no equivalent — without
 * this rewrite ``/f/foo`` would fall through to the admin SPA's
 * ``index.html`` and the form mini-app would never mount.
 */
function publicFormDevRoute(): Plugin {
  return {
    name: "opkomst-public-form-dev-route",
    apply: "serve",
    configureServer(server) {
      server.middlewares.use((req, _res, next) => {
        const url = req.url ?? "";
        if (/^\/f\/[^/?#]+/.test(url.split("?")[0])) {
          req.url = "/public-form.html";
        }
        next();
      });
    },
  };
}

/**
 * Dev-only middleware: route ``/d/{slug}`` to ``public-datepoll.html``.
 * Mirrors the event/form dev routes one-to-one for the datepoll
 * mini-app.
 */
function publicDatepollDevRoute(): Plugin {
  return {
    name: "opkomst-public-datepoll-dev-route",
    apply: "serve",
    configureServer(server) {
      server.middlewares.use((req, _res, next) => {
        const url = req.url ?? "";
        if (/^\/d\/[^/?#]+/.test(url.split("?")[0])) {
          req.url = "/public-datepoll.html";
        }
        next();
      });
    },
  };
}

/**
 * Dev-only middleware: route ``/c/{slug}`` to ``public-chore.html``.
 * Mirrors the event/form/datepoll dev routes for the chore-roster
 * mini-app.
 */
function publicChoreDevRoute(): Plugin {
  return {
    name: "opkomst-public-chore-dev-route",
    apply: "serve",
    configureServer(server) {
      server.middlewares.use((req, _res, next) => {
        const url = req.url ?? "";
        if (/^\/c\/[^/?#]+/.test(url.split("?")[0])) {
          req.url = "/public-chore.html";
        }
        next();
      });
    },
  };
}

/**
 * Dev-only middleware: serve the organiser SPA for ``/{tenant}/…``, and
 * 404 everything that isn't a page.
 *
 * In production ``backend/routers/spa.py`` looks the first segment up as
 * a live tenant and serves ``index.html``; the bare root and unknown
 * slugs are 404, because a shell that can't know whose data it would
 * show is worse than nothing. The dev server has no database, so it
 * treats the local tenants — the same ``rsp`` the brand plugin injects,
 * plus any other brand folder — as the organiser prefixes.
 *
 * A path no tenant owns still serves the shell — in the house brand,
 * whose router is based at ``/`` and therefore renders the app's own
 * not-found page. Without that rewrite Vite's SPA fallback serves the
 * page under whichever brand it last used, the router (based at
 * ``/rsp/``) bounces the visitor to ``/rsp/events``, and dev quietly
 * disagrees with prod about whether the root exists.
 */
function organiserAppDevRoute(): Plugin {
  // Paths the dev server owns: Vite internals, the source tree, and the
  // public mini-apps rewritten by the plugins below.
  const notAPage = /^\/(@|src\/|node_modules\/|api\/|brand\/|assets\/|e\/|f\/|d\/|c\/|__)/;
  return {
    name: "opkomst-organiser-app-dev-route",
    apply: "serve",
    configureServer(server) {
      server.middlewares.use((req, _res, next) => {
        const path = (req.url ?? "").split("?")[0];
        const wantsHtml = (req.headers.accept ?? "").includes("text/html");
        // Both branches serve the same shell; which brand it wears (and
        // so whether it renders the app or the 404) is decided by the
        // brand plugin from the same first path segment.
        if (wantsHtml && !notAPage.test(path)) req.url = "/index.html";
        next();
      });
    },
  };
}

/**
 * Substitute ``<!-- OPKOMST_BRAND_INJECTION -->`` in every HTML shell,
 * exactly as ``backend/services/brand.py::head`` does in production:
 * the first-paint colours, the palette stylesheet, the icons and
 * ``window.__OPKOMST_BRAND__``.
 *
 * Without this the dev server would serve a shell with no palette and
 * no brand, and every component reading ``brand()`` would throw — dev
 * and prod have to agree on what a page head contains.
 *
 * The files themselves come from the backend over the ``/brand`` proxy
 * below, so the URLs here are the same ones prod emits.
 */
function brandDevInjection(): Plugin {
  return {
    name: "opkomst-brand-dev-injection",
    apply: "serve",
    transformIndexHtml(html, ctx) {
      // Which organisation's brand this page wears. In prod the tenant
      // comes from the URL (organiser app) or the entity behind the
      // slug (public pages). Dev has no database, so: a first segment
      // that names a brand folder is that organisation; a public
      // mini-app path is the default local tenant, since the entity it
      // would resolve to can't be looked up here; anything else belongs
      // to no organisation and gets the house brand, which renders the
      // not-found page — the same thing prod serves with a 404.
      const path = (ctx.originalUrl ?? "").split("?")[0];
      const first = path.split("/")[1] ?? "";
      const brandsDir = fileURLToPath(new URL("../brands", import.meta.url));
      const isPublicPage = /^\/[efdc]\//.test(path);
      const slug = existsSync(`${brandsDir}/${first}/brand.json`)
        ? first
        : isPublicPage
          ? "rsp"
          : "opkomst";
      const dir = `${brandsDir}/${slug}`;
      const m = JSON.parse(readFileSync(`${dir}/brand.json`, "utf-8"));
      // Image fields are null for a brand without files (the house
      // brand): no icon links, and the mark renders as a wordmark.
      const url = (file: string | null) => (file ? `/brand/${slug}/${file}` : null);
      const p = m.palette;
      const brand = {
        slug,
        app_base: slug === "opkomst" ? "/" : `/${slug}/`,
        palette: p,
        app_name: m.app_name,
        wordmark: m.wordmark,
        org_name: m.org_name,
        org_url: m.org_url,
        logo_url: url(m.logo),
        favicon_url: url(m.favicon),
      };
      const tags = [
        `<style>:root{--boot-bg:${p.bg};--boot-surface:${p.surface};--boot-fg:${p.fg};`
        + `--boot-fg-muted:${p.fg_muted};--boot-accent:${p.accent};--boot-border:${p.border};}</style>`,
        `<link rel="stylesheet" href="${url("tokens.css")}">`,
      ];
      if (m.favicon) tags.push(`<link rel="icon" type="image/png" sizes="192x192" href="${url(m.favicon)}">`);
      if (m.apple_touch_icon) {
        tags.push(`<link rel="apple-touch-icon" sizes="180x180" href="${url(m.apple_touch_icon)}">`);
      }
      tags.push(`<script>window.__OPKOMST_BRAND__ = ${JSON.stringify(brand)};</script>`);
      return html.replace("<!-- OPKOMST_BRAND_INJECTION -->", tags.join("\n    "));
    },
  };
}

export default defineConfig({
  plugins: [
    vue(),
    brandDevInjection(),
    organiserAppDevRoute(),
    publicEventDevRoute(),
    publicFormDevRoute(),
    publicDatepollDevRoute(),
    publicChoreDevRoute(),
  ],
  test: {
    // happy-dom for component / Vue-Query composables (need a DOM
    // for ``app.mount(document.createElement(...))``); pure-utility
    // tests that don't touch the DOM are unaffected.
    environment: "happy-dom",
    include: ["src/__tests__/**/*.test.ts"],
    // The server injects ``window.__OPKOMST_BRAND__`` into every HTML
    // shell; under vitest there is no server, so the setup file plays
    // that role. Without it any component reading the brand throws.
    setupFiles: ["src/__tests__/setup-brand.ts"],
  },
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // Forward /api/* to the backend. Defaults to the dev port; the
      // E2E_API_PORT override lets ``playwright test`` boot the backend
      // on a non-default port when 8000 is already in use.
      "/api": `http://localhost:${process.env.E2E_API_PORT ?? "8000"}`,
      // The brand files (palette, logo, icons) are served by the
      // backend off ``brands/`` in dev and prod alike, so the page head
      // the dev server injects points at the same URLs prod emits.
      "/brand": `http://localhost:${process.env.E2E_API_PORT ?? "8000"}`,
    },
  },
  build: {
    rollupOptions: {
      // Three HTML entry points → three independent bundle graphs.
      // The two public mini-apps at ``/e/{slug}`` and ``/f/{slug}``
      // ship only what their form needs (Vue + the form component
      // + a tiny inline i18n dict + raw fetch). No PrimeVue, no
      // Pinia, no Vue Query, no router. Target wire weight:
      // ~30 KB gzip each vs the admin SPA's ~200 KB. Backend
      // routes serve the built ``public-event.html`` /
      // ``public-form.html`` (with payload inlined); every other
      // path falls through to the admin SPA's ``index.html``.
      input: {
        main: fileURLToPath(new URL("./index.html", import.meta.url)),
        publicEvent: fileURLToPath(
          new URL("./public-event.html", import.meta.url),
        ),
        // Same split as ``publicEvent``: dedicated bundle graph
        // for ``/f/{slug}`` so public visitors land on ~30 KB
        // gzip instead of the admin SPA's ~200 KB.
        publicForm: fileURLToPath(
          new URL("./public-form.html", import.meta.url),
        ),
        // Same split again: dedicated bundle graph for ``/d/{slug}``.
        publicDatepoll: fileURLToPath(
          new URL("./public-datepoll.html", import.meta.url),
        ),
        // Same split again: dedicated bundle graph for ``/c/{slug}``.
        publicChore: fileURLToPath(
          new URL("./public-chore.html", import.meta.url),
        ),
        publicChapter: fileURLToPath(
          new URL("./public-chapter.html", import.meta.url),
        ),
      },
      output: {
        // Split heavy vendor libs into their own chunks. The main
        // app chunk drops below the 500 kB warning threshold; the
        // vendor chunks cache separately and survive across deploys
        // that touch app code but not deps.
        // A function (not an object) so PrimeVue can be split by role:
        // the public chore page uses only ``DatePicker``, so it must pull
        // the shared PrimeVue base + theme tokens + DatePicker, but never
        // the admin-only widgets (Select, Dialog, AutoComplete, …). An
        // object map couldn't express "base vs widgets" because the base
        // modules aren't ones we import by name.
        manualChunks(id) {
          if (id.includes("/node_modules/vue-router/")) return "vue-router";
          if (id.includes("/node_modules/pinia/")) return "pinia";
          if (id.includes("/node_modules/vue-i18n/") || id.includes("/node_modules/@intlify/")) return "i18n";
          // ``vue-core`` is shared with the public mini-apps; router +
          // pinia stay admin-only so the public bundle doesn't pull them.
          if (id.includes("/node_modules/vue/") || id.includes("/node_modules/@vue/")) return "vue-core";

          // Theme tokens (Aura) — loaded by every app through the shared
          // preset, so its own chunk.
          if (id.includes("/node_modules/@primeuix/themes/")) return "primevue-themes";
          // The heaviest single widget; its own chunk so pages that don't
          // edit dates never pay for it.
          if (id.includes("/node_modules/primevue/datepicker/")) return "primevue-datepicker";
          // Shared PrimeVue runtime/base that DatePicker depends on
          // (base component, icons, utils, plus Button + InputText which
          // it composes). Kept apart from the admin widgets so the public
          // chore page loads only base + datepicker, not Select/Dialog/….
          if (
            id.includes("/node_modules/@primevue/") ||
            id.includes("/node_modules/@primeuix/") ||
            /\/node_modules\/primevue\/(button|inputtext|overlayeventbus|portal|ripple|config|baseicon|base)\//.test(id)
          ) {
            return "primevue-base";
          }
          // The remaining PrimeVue widgets (Select / Dialog / AutoComplete
          // / …) are admin-only. Left unforced so Rollup co-locates them
          // with the admin entry — forcing them into their own chunk
          // created a ``primevue ⇄ primevue-base`` circular chunk.
        },
      },
    },
  },
});
