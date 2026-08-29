/// <reference types="vitest" />
import { request as httpRequest } from "node:http";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath, URL } from "node:url";
import { svelte } from "@sveltejs/vite-plugin-svelte";
import vue from "@vitejs/plugin-vue";
import { defineConfig, type Plugin } from "vite";

// Mirrors ``backend/services/brand.py``: where the brand folders live,
// and which of them belongs to no organisation. The dev server has no
// database, so a folder's existence is how it tells an organisation's
// slug from one of the app's own paths.
const BRANDS_DIR = fileURLToPath(new URL("../brands", import.meta.url));
const HOUSE_BRAND = "opkomst";

// A public mini-app URL is ``/{prefix}/{slug}`` and nothing deeper.
// Prod matches it with a single path parameter, so ``/e/{slug}/feedback``
// misses it and falls through to the app's own router. Dev has to draw
// the line in the same place, or the sign-up page swallows the feedback
// questionnaire.
const PUBLIC_MINI_APP = /^\/[efdcqk]\/[^/?#]+\/?$/;

// Mirrors ``backend/services/content.py`` plus the privacy policy: the
// top-level paths the backend renders itself. ``tests/test_content.py``
// fails if this list and the server's ever disagree.
const CONTENT_PATHS = [
  "/privacy",
  "/voorwaarden",
  "/aanmeldpagina-voor-je-evenement",
  "/datumplanner-zonder-account",
  "/aanmeldformulier-zonder-google",
  "/wat-gebeurt-er-met-je-mailadres",
  "/pubquiz-maken-zonder-account",
  "/kieskompas-maken-zonder-onderzoeksbureau",
  "/vrijwilligers-inroosteren",
  "/wat-mag-je-bewaren-van-deelnemers",
  "/ledenvergadering-voorbereiden",
  "/gratis-alternatief-voor-eventbrite",
];

/**
 * Dev-only middleware: hand the written pages to the backend.
 *
 * ``/privacy`` and the four pages in ``backend/services/content.py``
 * are server-rendered Jinja with no bundle behind them, so in dev they
 * have to come from the backend the way they come from it in prod.
 *
 * A ``server.proxy`` entry is the obvious tool and it does not work:
 * Vite answers document requests (``Accept: text/html``) from its own
 * HTML middleware before the proxy is consulted, so ``curl`` got the
 * page and a browser got ``index.html`` with the SPA's own 404 inside
 * it. Middleware registered here runs ahead of all of that.
 *
 * The failure this prevents only exists in dev, which is the worst
 * place for it: dev is where these links get clicked while the page is
 * being written.
 */
function contentPagesDevRoute(): Plugin {
  const port = process.env.E2E_API_PORT ?? "8000";
  return {
    name: "opkomst-content-pages-dev-route",
    apply: "serve",
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const path = (req.url ?? "").split("?")[0].replace(/\/$/, "") || "/";
        if (!CONTENT_PATHS.includes(path)) return next();
        const upstream = httpRequest(
          { host: "localhost", port, path: req.url, method: req.method, headers: req.headers },
          (backend) => {
            res.writeHead(backend.statusCode ?? 502, backend.headers);
            backend.pipe(res);
          },
        );
        upstream.on("error", () => {
          // The one thing worth saying out loud: the page is fine, the
          // backend is not running on the port Vite is looking at.
          res.writeHead(502, { "content-type": "text/plain; charset=utf-8" });
          res.end(`No backend on localhost:${port}. Start it with: uv run uvicorn backend.main:app --reload\n`);
        });
        req.pipe(upstream);
      });
    },
  };
}

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
  // ``/e/`` is the event sign-up page and nothing else — the chapter
  // agenda moved under its organisation (see
  // ``organiserAppDevRoute``), so this prefix no longer sniffs slug
  // shapes to decide which page it means.
  return {
    name: "opkomst-public-event-dev-route",
    apply: "serve",
    configureServer(server) {
      server.middlewares.use((req, _res, next) => {
        const path = (req.url ?? "").split("?")[0];
        if (path.startsWith("/e/") && PUBLIC_MINI_APP.test(path)) req.url = "/public-event.html";
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
function publicQuizDevRoute(): Plugin {
  return {
    name: "opkomst-public-quiz-dev-route",
    apply: "serve",
    configureServer(server) {
      server.middlewares.use((req, _res, next) => {
        const path = (req.url ?? "").split("?")[0];
        if (path.startsWith("/q/") && PUBLIC_MINI_APP.test(path)) req.url = "/public-quiz.html";
        next();
      });
    },
  };
}

function publicCompassDevRoute(): Plugin {
  return {
    name: "opkomst-public-compass-dev-route",
    apply: "serve",
    configureServer(server) {
      server.middlewares.use((req, _res, next) => {
        const path = (req.url ?? "").split("?")[0];
        if (path.startsWith("/k/") && PUBLIC_MINI_APP.test(path)) req.url = "/public-compass.html";
        next();
      });
    },
  };
}

function publicFormDevRoute(): Plugin {
  return {
    name: "opkomst-public-form-dev-route",
    apply: "serve",
    configureServer(server) {
      server.middlewares.use((req, _res, next) => {
        const path = (req.url ?? "").split("?")[0];
        if (path.startsWith("/f/") && PUBLIC_MINI_APP.test(path)) req.url = "/public-form.html";
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
        const path = (req.url ?? "").split("?")[0];
        if (path.startsWith("/d/") && PUBLIC_MINI_APP.test(path)) req.url = "/public-datepoll.html";
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
        const path = (req.url ?? "").split("?")[0];
        if (path.startsWith("/c/") && PUBLIC_MINI_APP.test(path)) req.url = "/public-chore.html";
        next();
      });
    },
  };
}

/**
 * Dev-only middleware: serve the app for ``/{tenant}/…`` and for the
 * root, and pass everything that isn't a page through to Vite.
 *
 * In production ``backend/routers/spa.py`` looks the first segment up
 * as a live organisation and serves ``index.html`` in its brand; a path
 * no organisation owns is the personal app, served in the house brand
 * and based at ``/``. The dev server has no database, so it treats the
 * brand folders as the organisation prefixes and everything else as the
 * root's own paths, which is the same split.
 *
 * The shell is read and transformed here rather than by rewriting
 * ``req.url``: without that, Vite's SPA fallback serves the page under
 * whichever brand it last used, and the router bounces the visitor into
 * an organisation they didn't ask for.
 */
function organiserAppDevRoute(): Plugin {
  // Paths the dev server owns: Vite internals and the source tree. The
  // public mini-app URLs are handled by the plugins below and skipped
  // via ``PUBLIC_MINI_APP``; the written pages come off the backend and
  // are skipped via ``CONTENT_PATHS``. This middleware answers every
  // other request that wants HTML, so anything it does not skip here
  // never reaches the plugin that owns it.
  const notAPage = /^\/(@|src\/|node_modules\/|api\/|brand\/|assets\/|health$|__)/;
  // The app's own first-level routes. Under an organisation's slug,
  // anything that is not one of these is a chapter agenda: the same
  // split prod makes by looking the second segment up as a chapter,
  // decided here by the only signal a database-less dev server has.
  // ``services/slug.RESERVED_SLUGS`` keeps a real chapter from ever
  // being called one of these.
  const appRoutes = new Set([
    "", "admin", "auth", "chapters", "chore", "compass", "datepoll",
    "event", "form", "login", "quiz", "register", "settings", "users",
  ]);
  const isOrganisation = (segment: string) =>
    segment !== "" && segment !== HOUSE_BRAND && existsSync(`${BRANDS_DIR}/${segment}/brand.json`);
  return {
    name: "opkomst-organiser-app-dev-route",
    apply: "serve",
    configureServer(server) {
      server.middlewares.use(async (req, res, next) => {
        const path = (req.url ?? "").split("?")[0];
        const wantsHtml = (req.headers.accept ?? "").includes("text/html");
        if (!wantsHtml || notAPage.test(path) || PUBLIC_MINI_APP.test(path)) return next();
        if (CONTENT_PATHS.includes(path.replace(/\/$/, "") || "/")) return next();

        // Prod resolves the first segment as an organisation and only
        // then asks whether the second names a chapter. Dev has to make
        // the same two decisions in the same order: a path that belongs
        // to no organisation is the root's own, whatever its second
        // segment is, so ``/events/new`` gets the app rather than being
        // mistaken for a chapter called "new".
        const [, first = "", second = ""] = path.split("/");
        const shell = isOrganisation(first) && !appRoutes.has(second) ? "public-chapter.html" : "index.html";
        // Read and transform the shell here rather than rewriting
        // ``req.url`` and letting Vite serve it: the brand plugin
        // decides the tenant from the request path, and a rewrite would
        // hand it ``/index.html`` — which fell back to the house brand,
        // so every organiser page came out unstyled and routed against
        // the wrong base. Passing the real path keeps that decision on
        // the URL the visitor actually asked for.
        try {
          const html = readFileSync(fileURLToPath(new URL(`./${shell}`, import.meta.url)), "utf-8");
          res.setHeader("content-type", "text/html; charset=utf-8");
          res.end(await server.transformIndexHtml(path, html, path));
        } catch (err) {
          next(err);
        }
      });
    },
  };
}

/**
 * Ask the backend which brand a public ``/{prefix}/{slug}`` page wears.
 *
 * Prod bakes this into the served HTML: the entity behind the slug
 * names the tenant, and the tenant names the brand folder. The dev
 * server serves the shells itself and has no database, so it asks the
 * one process that does. An unreachable backend or an unknown slug
 * falls back to the house brand, which is what prod serves for a slug
 * that resolves to nothing.
 */
async function publicBrandSlug(prefix: string, slug: string): Promise<string> {
  const port = process.env.E2E_API_PORT ?? "8000";
  try {
    const res = await fetch(`http://localhost:${port}/api/v1/dev-public-brand/${prefix}/${slug}`);
    if (!res.ok) return HOUSE_BRAND;
    return ((await res.json()) as { slug: string }).slug;
  } catch {
    return HOUSE_BRAND;
  }
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
    async transformIndexHtml(html, ctx) {
      // Which organisation's brand this page wears. In prod the tenant
      // comes from the URL (organiser app) or the entity behind the
      // slug (public pages). Dev makes the same two decisions: a first
      // segment that names a brand folder is that organisation, and a
      // public mini-app path is whoever owns the entity behind the
      // slug, which only the database knows, so the backend is asked.
      // Every other path belongs to no organisation and gets the house
      // brand, which is the personal app, exactly as prod serves it.
      // ``originalUrl`` is the path the visitor asked for; ``ctx.path``
      // is the fallback for the shells Vite serves directly.
      const path = (ctx.originalUrl ?? ctx.path ?? "").split("?")[0];
      const [, first = "", second = ""] = path.split("/");
      const slug = existsSync(`${BRANDS_DIR}/${first}/brand.json`)
        ? first
        : PUBLIC_MINI_APP.test(path)
          ? await publicBrandSlug(first, second)
          : HOUSE_BRAND;
      const dir = `${BRANDS_DIR}/${slug}`;
      const m = JSON.parse(readFileSync(`${dir}/brand.json`, "utf-8"));
      // Image fields are null for a brand without files (the house
      // brand): no icon links, and the mark renders as a wordmark.
      const url = (file: string | null) => (file ? `/brand/${slug}/${file}` : null);
      const p = m.palette;
      const brand = {
        // Mirrors ``brand.py::_ads``: null on an organisation's brand,
        // and on the house brand whatever the environment carries.
        // Normally nothing is set and the slot renders its unconfigured
        // state, which is what a developer sees by default; exporting
        // the same vars the backend reads exercises the live path.
        // The dev server does not serve the loosened CSP, so a real ad
        // will be blocked here even when the ids are set: this is for
        // the slot's markup, not for the ad itself.
        ads:
          slug === HOUSE_BRAND
            ? {
                client_id: process.env.ADSENSE_CLIENT_ID ?? null,
                rail_slot: process.env.ADSENSE_SLOT_RAIL ?? null,
                banner_slot: process.env.ADSENSE_SLOT_BANNER ?? null,
                coffee_url: process.env.SUPPORT_COFFEE_URL ?? null,
                coffee_button_url: url(m.support_coffee_button),
                patreon_url: process.env.SUPPORT_PATREON_URL ?? null,
                patreon_button_url: url(m.support_patreon_button),
              }
            : null,
        slug,
        app_base: slug === HOUSE_BRAND ? "/" : `/${slug}/`,
        palette: p,
        app_name: m.app_name,
        wordmark: m.wordmark,
        org_name: m.org_name,
        tagline_nl: m.tagline_nl ?? null,
        tagline_en: m.tagline_en ?? null,
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
      // The backend substitutes per-page title, description and
      // canonical here (``spa.py::_app_head_meta``). The dev server has
      // no such table, so it fills the marker with the bare title the
      // shell used to carry: enough to see a page, not a claim that the
      // metadata is being tested locally.
      return html
        .replace("<!-- OPKOMST_BRAND_INJECTION -->", tags.join("\n    "))
        .replace("<!-- OPKOMST_HEAD_INJECTION -->", `<title>${m.app_name}</title>`);
    },
  };
}

export default defineConfig({
  plugins: [
    vue(),
    // Both, while the front end moves across (``docs/tasks/svelte``).
    // A ``.vue`` and a ``.svelte`` of the same name can sit side by
    // side because the import names the extension.
    svelte(),
    brandDevInjection(),
    organiserAppDevRoute(),
    publicEventDevRoute(),
    publicFormDevRoute(),
    publicQuizDevRoute(),
    publicCompassDevRoute(),
    publicDatepollDevRoute(),
    publicChoreDevRoute(),
    contentPagesDevRoute(),
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
    // Under vitest, modules are resolved the way a server would resolve
    // them, and Svelte's server build has no ``mount``. Asking for the
    // browser condition is what gives a test the component that
    // renders. Only under test: the real build resolves normally.
    conditions: process.env.VITEST ? ["browser"] : undefined,
  },
  server: {
    port: 5173,
    proxy: {
      // Forward /api/* to the backend. Defaults to the dev port; the
      // E2E_API_PORT override lets ``playwright test`` boot the backend
      // on a non-default port when 8000 is already in use.
      "/api": `http://localhost:${process.env.E2E_API_PORT ?? "8000"}`,
      // The brand files (palette, logo, icons) come from the API in dev
      // exactly as they do in prod — one server owns them.
      "/brand": `http://localhost:${process.env.E2E_API_PORT ?? "8000"}`,
    },
  },
  build: {
    rollupOptions: {
      // One HTML entry point per app → independent bundle graphs.
      // The public mini-apps at ``/e/{slug}``, ``/f/{slug}`` and the
      // rest
      // ship only what their form needs (Vue + the form component
      // + a tiny inline i18n dict + raw fetch). No Pinia, no Vue
      // Query, no router. Target wire weight:
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
        // And the same again for ``/q/{slug}``: a quiz is answered one
        // question at a time, and shares every renderer with the form.
        publicQuiz: fileURLToPath(
          new URL("./public-quiz.html", import.meta.url),
        ),
        // And for ``/k/{slug}``: a kompas walks the same way and ends
        // on a map instead of a score.
        publicCompass: fileURLToPath(
          new URL("./public-compass.html", import.meta.url),
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
        manualChunks(id) {
          if (id.includes("/node_modules/vue-router/")) return "vue-router";
          if (id.includes("/node_modules/pinia/")) return "pinia";
          // ``vue-core`` is shared with the public mini-apps; router +
          // pinia stay admin-only so the public bundle doesn't pull them.
          if (id.includes("/node_modules/vue/") || id.includes("/node_modules/@vue/")) return "vue-core";
        },
      },
    },
  },
});
