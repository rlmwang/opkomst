# Removing PrimeVue: task specs

**All three landed. This is the record, not a plan.** The app has no
component library and no icon font; `node_modules/primevue`,
`node_modules/@primeuix` and `src/primevue-preset.ts` are gone, so the
reference paths below no longer resolve. They are kept because they say
where each number came from.

Three tasks that took the organiser app off PrimeVue. Shipped in order;
each left the suite green and the app shippable.

The pattern for each is the one `src/components/DatePicker.vue` already
proved, and every task below repeats it in three phases:

1. **Replicate.** Build our component against PrimeVue's own reference
   files, so "identical" is measured rather than eyeballed.
2. **Swap and measure.** Change the call sites, delete the PrimeVue
   import, rebuild, and record what the bundle did.
3. **Correct to the house style.** Find where Aura's values disagree with
   the app's own tokens, and make the small corrections.

Phase 3 is separate from phase 1 on purpose. Replicating first means any
visual difference afterwards is a decision somebody made, not a mistake
somebody missed.

## What this is worth

Measured by building everything PrimeVue pulls in: **695,767 raw /
129,598 gzipped.** It splits in two, and the halves behave differently.

| | gzipped | when it loads |
|---|---|---|
| `primevue-base` + `primevue-themes` | 59,891 | every page, in the critical path |
| the widgets | ~70,000 | folded into route chunks, on navigation |

**The critical-path 60 kB is all-or-nothing.** `primevue-base` and
`primevue-themes` go away when the *last* PrimeVue component goes, not
gradually: removing Button alone saves nothing there. The widget half
shrinks per component removed, immediately, in whichever route chunk
held it.

So tasks 01 and 02 pay in route chunks and in having less to maintain.
Task 03 is what collects the 60 kB, and only its final step does.

For scale: the organiser app's production critical path is **170,966
gzipped** today, so this is about a third of it.

None of this touches a public page. PrimeVue left the public bundles
when the chore page's date fields became `DatePicker.vue`.

## Order

| # | Task | What goes | Depends on |
|---|---|---|---|
| 01 | Plain controls *(landed; spec deleted)* | Button, InputText, Textarea, ToggleSwitch, ProgressBar, IconField, InputIcon | none |
| 02 | The ones we already own *(landed; spec deleted)* | Toast, InputNumber, Dialog, ConfirmDialog, Tooltip | 01 |
| 03 | Overlay lists *(landed; spec deleted)* | Select, MultiSelect, AutoComplete, Popover, then PrimeVue and PrimeIcons themselves | 01, 02 |

01 and 02 are independent of each other in principle. 02 lists after 01
because both touch the same pages and doing them together means one pass
over each file.

**Counting call sites, not files.** Task 01's spec said 61 call sites and
the real number was 135, because the first count was of import
statements. Button alone is 78. Count tags before estimating.

**Shell components pay in the critical path, route components do not.**
Both specs said the critical path would not move until task 03. That
held for 01 and was wrong for 02, which took 19,917 gz off it. Toast,
ConfirmDialog and Tooltip are registered in `main.ts` and rendered in
`App.vue`, so they were in the entry chunk, not behind a route.

**What task 03 collected.** The organiser critical path went from
150,517 gz to 100,321 gz: 50,196 gz, which is a third of it. That is
the last of `primevue-base` and `primevue-themes`, the four overlay
widgets, and PrimeIcons' 35 kB woff2 and 85 kB ttf, replaced by 23 SVG
paths in `AppIcon.vue`. Nothing in `dist` mentions PrimeVue any more,
and the app ships no icon font.

## Where the reference lives

Every task reads the same four places. Nothing here is guesswork, and
none of it should be re-derived by eye.

- **Geometry and colour roles per component:**
  `node_modules/@primeuix/themes/dist/aura/<component>/index.mjs`. This
  is the token file: sizes, paddings, radii, and which semantic colour
  each part uses.
- **The CSS those tokens fill:**
  `node_modules/@primeuix/styles/dist/<component>/index.mjs`. Class
  names, layout, transitions, states.
- **What the semantic names resolve to:**
  `node_modules/@primeuix/themes/dist/aura/base/index.mjs`, under
  `semantic`. This is where `{content.background}` becomes
  `{surface.0}`.
- **Our overrides:** `src/primevue-preset.ts`. It maps `surface.N` to
  `var(--brand-surface-N)` and `primary.N` to `var(--brand-primary-N)`,
  and overrides some form-field roles. Read it before assuming Aura's
  default applies.

Resolved, that chain gives the map every task needs:

| Aura role | resolves to |
|---|---|
| `{content.background}`, `{form.field.background}` | `var(--brand-surface-0)` |
| `{content.hover.background}` | `var(--brand-surface-100)` |
| `{content.border.color}` | `var(--brand-surface-200)` |
| `{form.field.border.color}` | `var(--brand-surface-200)` (preset override) |
| `{form.field.color}` | `var(--brand-surface-900)` (preset override) |
| `{form.field.placeholder.color}` | `var(--brand-surface-500)` (preset override) |
| `{form.field.hover.border.color}` | `var(--brand-surface-400)` |
| `{content.color}`, `{text.color}` | `var(--brand-surface-700)` |
| `{primary.color}` | `var(--brand-primary-500)` |
| `{primary.contrast.color}` | `#fff` |
| `{border.radius.md}` | `6px` |
| `{form.field.padding.x}` / `.y` | `0.75rem` / `0.5rem` |
| `{transition.duration}` | `0.2s` |
| `{overlay.popover.padding}` | `0.75rem` |
| `{overlay.popover.shadow}` | `0 4px 6px -1px rgba(0,0,0,.1), 0 2px 4px -2px rgba(0,0,0,.1)` |
| `{focus.ring}` | `1px solid {primary.color}`, offset `2px` |
| `disabledOpacity` | `0.4` (preset override) |

## The house style, for phase 3

Where the app has its own name for a colour, that is the one to end on.
The values are not always the same, and the difference is the point:

| role | Aura ramp | the app's own | same? |
|---|---|---|---|
| panel / input background | `--brand-surface-0` | `--brand-surface` | identical |
| accent | `--brand-primary-500` | `--brand-red` | identical |
| border | `--brand-surface-200` `#dcd2b9` | `--brand-border` `#e6dec9` | **different** |
| body text | `--brand-surface-700` `#403d39` | `--brand-text` `#1a1a1a` | **different** |
| muted text | `--brand-surface-500` `#7e7466` | `--brand-text-muted` `#5e5a52` | **different** |

`DatePicker.vue` shows how this lands: the popup panel moved to the
app's own tokens, and the input kept the form-field values because it
sits in a row of PrimeVue inputs and has to match its neighbours. That
second consideration disappears as this series progresses, and by the
end of task 03 nothing has a PrimeVue neighbour left to match.

Two house facts that are already true and should be reused rather than
rebuilt: `src/public_shared/forms.css` defines `.input`, `.btn` and
`.btn-primary`, and `src/components/MonthGrid.vue` is the app's own
calendar language.

## Conventions every task must honour

From `CLAUDE.md`, and these have teeth:

- **Cleanest design, no backwards compatibility.** Pre-launch. When a
  PrimeVue component goes, its import, its theme entry and its
  `manualChunks` rule go with it in the same commit. No shim that
  forwards to the new component, no prop kept "for the old call sites".
- **Colours live in `brands/`.** `scripts/check_brand_tokens.py` fails on
  a hex or a tinted `rgba()` anywhere under `frontend/src`, including
  inside comments. Black and white shadows are allowed. Reading a
  `var(--brand-…)` no brand defines fails too.
- **Few font sizes.** Reuse what the file already has: `0.6875`,
  `0.8125`, `0.875`, `1`, `1.125rem`. Aura's day-view `font-size: 1rem`
  is in that set; if a component's token asks for something outside it,
  round to the nearest one the app already uses and note it in phase 3.
- **Row action buttons stay visible.** No `opacity: 0` hover-reveal.
- **All visible strings through `t()`**, `nl` and `en` in lock-step. A
  component that is also used by a public mini-app takes its labels as
  props instead, the way `MonthGrid` does, because those apps have no
  vue-i18n.
- **Never an emdash or en-dash**, anywhere.
- Before calling a task done: `npx vue-tsc --noEmit`, `npx vitest run`,
  `npm run build`, and `uv run python scripts/check_brand_tokens.py`.

## Measuring, so the numbers in these specs stay comparable

Every figure in this series is gzipped bytes of the entry's critical
path, from a build **with a Sentry DSN set**. A local build has none, so
Vite drops the `init` block and the number comes out about 34 kB low.

```bash
cd frontend
VITE_SENTRY_DSN="https://abc@o1.ingest.sentry.io/1" npx vite build
cd dist && tot=0
for a in $(grep -o 'assets/[A-Za-z0-9_.-]*\.\(js\|css\)' index.html | sort -u); do
  tot=$((tot + $(gzip -c "$a" | wc -c)))
done; echo "$tot gz"
```

Record the before and after in each task's commit message, as the
DatePicker and Sentry commits do.

## Deferred, so it is not lost

**The app has three buttons, and should have one.** Task 01 built
`AppButton` to Aura's geometry: `0.5rem 0.75rem` padding, `500` label
weight. `theme.css` has `.btn-secondary` at `0.4rem 0.875rem`, and
`public_shared/forms.css` has `.btn-primary` at `0.625rem 1.5rem` with
`600` weight and an `8rem` minimum, plus a plain `.btn`. They disagree on
padding, weight and gap.

That is not task 01's to settle, because the other two are what the
public mini-apps render and changing them changes public pages. It is a
question about the whole app's button, worth asking on its own. The
organiser side has now stopped moving, so it is askable.

Task 03 settled the same question for the input: the organiser field
won, and `public_shared/forms.css`'s `.input` took its padding, its
ground, its shadow and its ring-less focus. The button is the last
control where the two halves of the app still disagree.

**The form-field colours now read the app's own names.** Task 03's
phase 3 moved `AppInput`, `AppTextarea`, `AppToggle`, `DatePicker`,
`SelectField`, `MultiSelectField` and `AutoCompleteField` from
`--brand-surface-200` / `--brand-surface-900` / `--brand-surface-500`
to `--brand-border` / `--brand-text` / `--brand-text-muted`. The one
role with no house name is the hover border, which is now
`color-mix(in srgb, var(--brand-text-muted) 45%, transparent)`.
