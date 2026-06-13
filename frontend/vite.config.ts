/// <reference types="vitest" />
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
  return {
    name: "opkomst-public-event-dev-route",
    apply: "serve",
    configureServer(server) {
      server.middlewares.use((req, _res, next) => {
        const url = req.url ?? "";
        if (/^\/e\/[^/?#]+/.test(url.split("?")[0])) {
          req.url = "/public-event.html";
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

export default defineConfig({
  plugins: [vue(), publicEventDevRoute(), publicFormDevRoute(), publicDatepollDevRoute()],
  test: {
    // happy-dom for component / Vue-Query composables (need a DOM
    // for ``app.mount(document.createElement(...))``); pure-utility
    // tests that don't touch the DOM are unaffected.
    environment: "happy-dom",
    include: ["src/__tests__/**/*.test.ts"],
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
      },
      output: {
        // Split heavy vendor libs into their own chunks. The main
        // app chunk drops below the 500 kB warning threshold; the
        // vendor chunks cache separately and survive across deploys
        // that touch app code but not deps.
        manualChunks: {
          // Vue split into three: ``vue-core`` is shared with the
          // public mini-app, ``vue-router`` and ``pinia`` are
          // admin-only. Keeping them as a single ``vue`` chunk
          // (the previous shape) made the public bundle pull
          // ~10 KB gzip of router + pinia code it doesn't import.
          "vue-core": ["vue"],
          "vue-router": ["vue-router"],
          pinia: ["pinia"],
          i18n: ["vue-i18n"],
          primevue: [
            "primevue/autocomplete",
            "primevue/button",
            "primevue/confirmdialog",
            "primevue/dialog",
            "primevue/iconfield",
            "primevue/inputicon",
            "primevue/inputnumber",
            "primevue/inputtext",
            "primevue/password",
            "primevue/select",
            "primevue/tag",
            "primevue/textarea",
            "primevue/toast",
            "primevue/toggleswitch",
            "primevue/tooltip",
            "primevue/useconfirm",
            "primevue/usetoast",
          ],
          // Datepicker is the heaviest single PrimeVue widget and is
          // only used on the event create/edit form. Splitting it
          // out keeps the public sign-up page and dashboard from
          // paying for it on first paint.
          "primevue-datepicker": ["primevue/datepicker"],
        },
      },
    },
  },
});
