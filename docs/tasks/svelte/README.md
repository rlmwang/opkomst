# Moving the front end to Svelte

A proposal, then a plan. The decision is taken; what follows is how to
take it without a six-week stop.

**Phases 0 and 1 have landed.** All seven public entries are Svelte and
no public page ships Vue: **97,550 gz off them**, about a quarter of
each. The organiser app is phases 2 to 4 and has not started. See the
phase list below for the numbers and what they cost.

## Why

`vue-core` is **32,626 gz** and it is on all eight entries. After the
PrimeVue series and with `vue-i18n` on its way out, it is the largest
single thing the app ships, and on a public page it is most of the page:

| entry | total gz | vue-core's share |
|---|---|---|
| organiser (`index.html`) | 100,321 | 33% |
| public-chore | 64,300 | 51% |
| public-event | 61,923 | 53% |
| public-datepoll | 56,324 | 58% |
| public-compass | 55,667 | 59% |
| public-quiz | 52,983 | 62% |
| public-form | 52,753 | 62% |
| public-chapter | 46,871 | 70% |

Vue ships a runtime that interprets your components at runtime. Svelte
compiles each component into the code that updates its own DOM, so
there is almost no runtime left to send. The trade is that the compiled
components are larger than Vue's templates. On a page with a handful of
components the trade is very good; on a page with fifty it is closer.
Which is why phase 0 below measures rather than assumes.

The public pages are the ones a stranger opens on mobile data, from a
link, once. They are where the bytes matter and they are where the win
is largest. That is not a coincidence and it is the order to work in.

**This supersedes the idea of rewriting the public mini-apps in plain
JavaScript.** Svelte reaches the same size without anybody hand-writing
`createElement` calls, and leaves the public and organiser halves
speaking one language instead of two.

## What has to move

50,878 lines under `frontend/src`, but 12,303 of those are the
generated `api/schema.ts` and 2,158 are the JSON catalogues:

| | files | lines |
|---|---|---|
| `components/` | 53 | 8,277 |
| `pages/` | 27 | 9,326 |
| `composables/` | 30 | 2,531 |
| `public_shared/` | 24 | 2,325 |
| the seven public entries | 33 | 6,674 |
| `lib/`, `stores/`, `router/` | 26 | 1,876 |

Call it **31,000 lines of component and page code**, of which 9,000 is
public and 22,000 organiser.

## Every dependency has a counterpart

This is the part that makes it a translation rather than a redesign:

| today | on Svelte |
|---|---|
| `vue` | `svelte` |
| `vue-router` | a small SPA router on Vite, see below |
| `pinia` (one store, `auth.ts`) | a Svelte store, which is built in |
| `@tanstack/vue-query` | `@tanstack/svelte-query` |
| `vue-i18n` | already going, see `docs/tasks/i18n/` |
| `@sentry/vue` | `@sentry/svelte` |
| `@vue/test-utils` | `@testing-library/svelte` |
| `vue-tsc` | `svelte-check` |
| `@vitejs/plugin-vue` | `@sveltejs/vite-plugin-svelte` |

Vue's Composition API and Svelte 5's runes line up closely enough that
most of a `<script setup>` block translates a line at a time: `ref` is
`$state`, `computed` is `$derived`, `watch` is `$effect`, `defineProps`
is `$props`, and scoped `<style>` is scoped `<style>`.

## Svelte, not SvelteKit

SvelteKit wants to own routing, the server and the build. This app
already has all three: FastAPI serves eight built HTML entries, inlines
the payload into the public ones, and `vite.config.ts` decides which
shell a path gets. Adopting SvelteKit means arguing with that
architecture for no gain.

**Svelte plus Vite, keeping the eight entries exactly as they are.**
The only thing that needs replacing is `vue-router`, and only for the
organiser app, since the public entries have no router at all. The
route table in `src/router/index.ts` is 175 lines of paths, guards and
`meta`, and it maps onto any of the small Svelte SPA routers without a
change in shape.

## Phases

Each one leaves the suite green and the app shippable, the way the
PrimeVue series did.

**0. Spike, and get a real number.** *(Landed.)* Ported
`public-chapter` and nothing else. It is the smallest entry: 5 files,
543 lines, 46,871 gz before, of which 32,626 was Vue. It shares
`PublicShell`, `BrandMark`, `PublicIdentity`, `PublicNotice`, `AdSlot`,
`AdUnit`, `Colophon` and `AppToast` with the other six, so porting it
ported the shared floor as well: 9 components and the entry.

**46,871 gz to 29,968 gz. A saving of 16,903, which is 36% of the
page.**

Less than the 32.6 kB of runtime that left, and that difference is the
trade the proposal named: Svelte's compiled components are larger than
Vue's templates, so roughly half the runtime saving is spent buying the
components back. On this entry the app's own code went from about 14 kB
across seven chunks to 22.4 kB in one. On a bigger entry that ratio gets
worse, which is the thing to watch in phase 1 and the reason phases 2 to
4 are worth less than their line count suggests.

The verdict is go. 36% off the page a stranger actually loads is worth
having, and it comes with fewer moving parts rather than more.

Three things the spike found:

- **`@sveltejs/vite-plugin-svelte@7` wants Vite 8.** Pinned to `^6.2.4`,
  which peers on Vite 7. A Vite major does not belong in a measurement.
- **`lib/toast.ts` had to stop being Vue.** Both halves of the app show
  toasts from the one module-level queue, so it is now a plain array and
  a set of listeners, and each `AppToast` keeps its own reactive copy.
  That pattern is the general answer for anything in `lib/` that a
  Svelte component and a Vue component both use.
- **Svelte's compiler found an a11y bug the Vue version shipped.** The
  event card's poster credit was a `<figcaption>` that was not inside a
  `<figure>`. Fixed in the port.

**Checking, while both are in the tree.** `vue-tsc` cannot read a
`.svelte` and `svelte-check` cannot read a `.vue`, so they get a config
each: `tsconfig.svelte.json` lists the directories Svelte owns and grows
as phase 1 does. `npm run check` runs both.

**1. The public half.** *(Landed.)* The other six entries, smallest
first. Vue now ships only on `index.html`; no public entry pulls
`vue-core` at all.

| entry | before | after | saving |
|---|---|---|---|
| `public-chapter` | 46,871 | 32,095 | 14,776 (32%) |
| `public-form` | 52,753 | 38,468 | 14,285 (27%) |
| `public-quiz` | 52,983 | 39,364 | 13,619 (26%) |
| `public-datepoll` | 56,324 | 42,382 | 13,942 (25%) |
| `public-compass` | 55,667 | 42,539 | 13,128 (24%) |
| `public-event` | 61,923 | 48,477 | 13,446 (22%) |
| `public-chore` | 64,300 | 49,946 | 14,354 (22%) |

**97,550 gz off the seven pages a stranger actually loads**, and about
a quarter off each. The percentage falls as the page grows, which is
the trade phase 0 measured: the runtime saving is fixed at 32.6 kB and
the compiled components cost more than the templates did. `PublicShell`
is now one 21.1 kB chunk every public page shares and a returning
visitor downloads once.

**Five components are drawn by both frameworks** for the length of
phases 2 to 4, because the organiser app renders them too. Rather than
keeping two copies of each rule, their arithmetic was extracted and both
components run it:

| component | shared module |
|---|---|
| `CompassPlot` | `public_shared/compass-plot.ts` |
| `MonthGrid` | `components/month-grid.ts` |
| `DatePicker` | `components/date-picker.ts`, `components/date-picker.css` |
| `useOverlayPanel` | `composables/overlay-panel.ts` |

Each extraction is proved by the Vue component's own tests passing
unedited: the date picker's thirteen, the plot's, the roster view's.

**What the compiler found.** Svelte type-checks the template, and
`svelte-check` reports a11y and dead CSS. Across phase 1 that surfaced
nine real defects the Vue versions had shipped: a `<figcaption>` outside
any `<figure>`; a question prompt that was a `<label>` around nothing;
map dots that were focusable `listitem`s a keyboard could reach and not
read; a date input carrying `aria-expanded` with no combobox role; and
five blocks of CSS for markup that no longer existed.

**Two idioms have no Svelte spelling** and were translated rather than
kept. A `computed` with a setter becomes a `$derived` for reading plus
the state behind it for writing, bound through a getter and setter pair.
And a `watch` that must not fire on mount becomes either a handler on
the thing that changed or an effect with an explicit guard, because an
effect always runs once first: the sign-up page's draft would have been
wiped by the select-all watcher otherwise.

**2. The organiser shell.** `main.ts`, `App.vue`, the router, the auth
store, the Vue Query client, the toast and confirm singletons, and
`AppHeader`. This is the phase with the design decisions in it, because
it is where the framework-shaped code lives: the optimistic mutations'
`onMutate` snapshot and `onError` rollback, and the route guards.

**3. The organiser components.** 53 of them, 8,277 lines. Leaf-first,
because a page can render a Svelte component but not the other way
round without a bridge, and a bridge is a thing to maintain. The order
is roughly the order the PrimeVue series built them in.

**4. The organiser pages.** 27 files, 9,326 lines, one at a time. The
composables move with the pages that use them.

**5. Delete Vue.** `vue`, `vue-router`, `pinia`, `@tanstack/vue-query`,
`@sentry/vue`, `@vue/test-utils`, `vue-tsc`, `@vitejs/plugin-vue`.
Measure the critical path and record it. Confirm nothing in `dist`
mentions vue.

## What this costs, said plainly

- **Phases 2 to 4 are 22,000 lines with no user-visible result.** The
  organiser app looks identical when it is done. The saving there is
  real but it lands on a handful of organisers on laptops, not on the
  strangers the public pages serve. If the project has to stop
  somewhere, stopping after phase 1 is a coherent place: the bytes that
  matter are saved, and the organiser app keeps working on Vue
  indefinitely.
- **Two frameworks are in the tree between phase 0 and phase 5.** Both
  build, both test, and `package.json` carries both. That is the cost
  of not doing it in one commit, and it is the right cost to pay.
- **The e2e suite is the safety net.** It drives the app through a real
  browser and does not know what rendered the DOM, so it is the one
  thing that keeps working unchanged across every phase. Do not let it
  rot while this is happening.

## On native apps, since it came up

Svelte is not a reason to expect a native app, and not an obstacle to
one either.

If "native" means the web app in a shipped shell (Capacitor, or Tauri
v2), the framework is irrelevant: it runs a WebView and any of Svelte,
Vue or hand-written JS works identically. If it means real native
widgets, React Native and Expo are the mature answer and they need
React. Svelte's `svelte-native` is a small community project on
NativeScript and is not comparable; Vue is in the same position, so
this is not a reason to have stayed.

Worth asking whether the app wants one at all. Attendees arrive on a
link and install nothing, so an app can only serve organisers, and what
organisers do is edit forms on a laptop. A PWA gets the home-screen
icon and an offline shell for none of the store overhead.

## Conventions this inherits

From `CLAUDE.md`, unchanged by the framework:

- **Cleanest design, no backwards compatibility.** When a component
  moves, its Vue original and its entry in any build config go with it
  in the same commit. No bridge component that renders one from the
  other beyond what a phase needs while it is in flight.
- **Colours live in `brands/`.** `scripts/check_brand_tokens.py` reads
  `frontend/src` and does not care about file extensions, so it keeps
  working. Check it does before phase 1.
- **All visible strings through `t()`** in the organiser app, and as
  props in anything a public mini-app renders, the way `MonthGrid`
  already does.
- **Never an emdash or en-dash**, anywhere.
- Before calling a phase done: `svelte-check`, `npx vitest run`,
  `npm run build`, `uv run python scripts/check_brand_tokens.py`, and
  the e2e suite.

## Measuring, so the numbers stay comparable

The same command the PrimeVue series used, with the Sentry DSN set,
because a build without one drops the `init` block and comes out about
34 kB low:

```bash
cd frontend
VITE_SENTRY_DSN="https://abc@o1.ingest.sentry.io/1" npx vite build
cd dist && for html in index.html public-*.html; do
  tot=0
  for a in $(grep -o 'assets/[A-Za-z0-9_.-]*\.\(js\|css\)' "$html" | sort -u); do
    tot=$((tot + $(gzip -c "$a" | wc -c)))
  done
  echo "$html: $tot gz"
done
```

Record the before and after of every phase in its commit message.
