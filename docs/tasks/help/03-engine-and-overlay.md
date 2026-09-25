# 03: Tour store, engine, overlay

Design: `docs/design-tour.md` chapters 6, 7 and 8. This task builds
the machine with one throwaway tour in a test; the real tours are
task 04. Nothing is reachable from the app's UI when this lands
except through the store.

## Step and tour types

`frontend/src/tours/types.ts`:

```ts
type Advance = { kind: "next" } | { kind: "click" } | { kind: "until"; name: AnchorName };
interface Step { page?: string; anchor: AnchorName; advance: Advance }
interface Tour { id: TourId; steps: Step[] }
```

`page` is a path pattern in the router's grammar (`:name`, `*`,
optional trailing slash) and is matched with the exported
`matchRoute`. A step without `page` runs on the page the tour was
started from. Nothing else on a step.

## The store

`frontend/src/stores/tour.svelte.ts`, a module with getters the way
`stores/auth.svelte.ts` is:

- State: `tour: TourId | null`, `product: string | null`, `index`,
  `startedOn: string` (the path at start), `resolved: Step[]`.
- Verbs: `start(id, product)`, `next()`, `back()`, `stop()`.
- `start` on a per-page tour resolves its list at once: every step
  whose anchor is not registered is dropped, and `resolved` is what
  remains. The welcome and sign-in tours keep their declared list.
- Every change is written to `sessionStorage` under
  `${APP}:tour` where `APP` is the same prefix `useFormDraft` uses
  (`personal` at the root, the organisation's slug otherwise). Read at
  boot.
- `stores/auth.svelte.ts::logout()` calls `tour.stop()` and removes
  the key, in the same function that calls `clearAllDrafts()`.

## The engine

`frontend/src/tours/engine.svelte.ts`, one `$effect` over the current
path, `anchors.version`, TanStack's `useIsFetching()` count and the
store's index, with the five outcomes of design chapter 8:

1. path matches and the anchor resolves: show.
2. path matches and something is fetching: wait.
3. path matches, nothing fetching, no anchor: drop the step and move on.
4. path does not match, and the previous step was `click` or `until`
   whose page is still the current one: wait.
5. otherwise: stop.

Click steps attach a one-shot capture-phase `click` listener to the
resolved element that advances without stopping the event. Until steps
watch `anchors.version` and advance when `resolve(name)` returns an
element. Measuring: `scrollIntoView` centred (upper half on a phone),
measure on the next frame, and on `resize`, capture-phase `scroll` and
a `ResizeObserver` on the element.

## The overlay

`frontend/src/components/TourOverlay.svelte`, mounted in `App.svelte`
beside `AppToast` and `AppConfirmDialog`, loaded with a dynamic import
when a tour starts and at boot when the storage key is present.

- **Mask:** one fixed `<svg>` the size of the viewport, `aria-hidden`,
  z-index 990, one `<path>` filled `rgba(0,0,0,.55)` with
  `fill-rule="evenodd"`: the viewport rectangle and, inside it, a
  rounded rectangle at the anchor's box plus 8px, with the anchor's
  computed `border-radius`. `pointer-events: fill` on the path; a
  click on it is swallowed by a handler that does nothing. A second
  rounded rectangle, 2px outside the hole, stroked 2px
  `var(--brand-red)`, no fill, `pointer-events: none`.
- **Callout:** `role="dialog"`, `aria-labelledby` the title, z-index
  1100, at most 20rem wide, 1rem padding, the popover's surface,
  border, radius and shadow, with an arrow toward the hole. Placed by
  `useOverlayPanel` with `align: "center"`, below the hole, flipped
  above when there is no room. Inside: counter at `0.8125rem` muted,
  title at `1rem` weight 600, body at `0.875rem`, a button row with
  Stoppen (text button, left) and Vorige and Volgende or Klaar (right).
  A click or until step renders no Volgende. Counter and body sit in
  an `aria-live="polite"` region.
- **Sheet:** at `max-width: 480px`, and at any width when the hole is
  taller than 60% of the viewport, the callout is a full-width sheet
  fixed to the bottom, no arrow, and the hole is scrolled into the
  upper half.
- **Focus:** focus moves to the callout when a step opens and returns
  to the element that started the tour when it ends (the store keeps
  a reference). Escape is a `keydown` listener on the callout element,
  not on the document. Enter and ArrowRight advance a next step,
  ArrowLeft goes back. Tab cycles the callout's buttons; on a click or
  until step, Tab from the last button focuses the resolved element and
  Shift+Tab from it returns to the first button. Inside a lit form,
  Tab behaves as it always does.
- **No transitions.** None on the mask, the callout or the sheet.

The strings the overlay itself uses (Stoppen, Vorige, Volgende, Klaar,
the counter's "van") go under `tour.` in both locales.

## Tests

- `tour-store.test.ts`: session storage round-trips; `logout` clears
  it; a per-page tour drops unregistered steps at start and the
  counter counts what is left.
- `tour-engine.test.ts`, hosted in `$effect.root` like the other
  composables: each of the five outcomes with a fake router path and
  fake fetching count; an until step advances when its anchor
  registers; a click step advances on a capture-phase click and the
  element's own handler still runs.
- `tour-overlay.test.ts`: the path's hole equals the anchor's box plus
  8px at the anchor's radius, for an element at each corner and one
  taller than the viewport; a click on the fill is swallowed and a
  click in the hole reaches the element; the sheet replaces the
  popover under 480px and for a tall hole; Escape with focus outside
  the callout does nothing; Tab from the last button on a click step
  lands on the anchor; the mask's z-index is below the toast's.

**Done when:** a tour defined in a test runs through the store from
start to Klaar in a mounted harness, survives a simulated navigation
via session storage, and nothing in the app's UI mentions it yet.
