# 03: Overlay lists, and then PrimeVue itself

The last four components, and the one that collects the prize. Select,
MultiSelect and AutoComplete are one machine with three faces: a list in
an overlay, driven from a field, navigable by keyboard. Popover is that
overlay with arbitrary content in it.

| component | uses | PrimeVue source | the face it wears |
|---|---|---|---|
| `Select` | 8 | 60,910 B | pick one, with a filter box |
| `AutoComplete` | 3 | 60,512 B | pick one, list arrives asynchronously |
| `MultiSelect` | 2 | 69,276 B | pick several, chosen ones show as chips |
| `Popover` | 2 | 13,198 B | anchored panel, imperative `toggle()` |

This is the largest task in the series and the one that can regress
quietly, because keyboard and screen-reader behaviour is invisible until
somebody who needs it cannot use the app.

## What already exists

`src/components/DatePicker.vue` built and proved half of this. Take from
it directly rather than writing it again:

- `Teleport` to the body with a `position`/`top`/`insetInlineStart`
  computed from `getBoundingClientRect`, flipping above the field when
  there is no room below.
- Reposition on `resize` and on capture-phase `scroll`.
- Close on capture-phase `pointerdown` outside both the field and the
  panel, and on Escape with focus returning to the field.
- The panel's Aura geometry: `0.75rem` padding, `6px` radius,
  `var(--brand-surface-200)` border, the popover shadow.

Pull that into `src/composables/useOverlayPanel.ts` as the first step,
and change `DatePicker.vue` to use it. That refactor is guarded by the
existing 13 DatePicker tests passing unedited.

What is genuinely new is the list: roving focus with the arrow keys,
Home and End, Enter to choose, type-ahead, and the ARIA combobox
wiring (`role="combobox"`, `aria-expanded`, `aria-controls`,
`aria-activedescendant`, `role="listbox"` and `role="option"` with
`aria-selected`).

## Phase 1: replicate

Build `src/components/SelectField.vue` first, then the other two on top
of it. Read `@primeuix/themes/dist/aura/select/index.mjs` and
`@primeuix/styles/dist/select/index.mjs` for the values, and the same
pair for `multiselect`, `autocomplete` and `popover`.

Props already in use, which are the whole surface to support:

- **Select:** `:options`, `option-label`, `option-value`, `:placeholder`,
  `:disabled`, `filter`, `filterPlaceholder`, `show-clear`, `fluid`,
  `v-model` / `:model-value` + `@update:model-value`.
- **AutoComplete:** `:suggestions`, `option-label`, `:placeholder`,
  `:disabled`, `:delay`, `:min-length`, `@complete`, `@option-select`,
  `@blur`, `@keyup`, `fluid`, `v-model`.
- **MultiSelect:** `:options`, `option-label`, `:placeholder`, `filter`,
  `display`, `fluid`, `v-model`.
- **Popover:** template `ref` with an imperative `toggle(event)`,
  `@show`, `@hide`, default slot.

Keep the names. A call site should change its import and nothing else.

**Done when:** each behaves identically at every call site, including
with the keyboard and with a screen reader. Test both. This is the phase
where "identical" is worth the most, because it is the phase where
nobody would notice if it were not.

## Phase 2: swap, measure, and delete PrimeVue

Swap the 15 call sites. Then the part this whole series was for:

1. Delete `src/primevue-preset.ts`.
2. Remove `PrimeVue`, `primeVueConfig` and `app.use(PrimeVue, ...)` from
   `src/main.ts`, and the same from `src/__tests__/` setup where it
   appears.
3. Remove the four `primevue-*` rules from `manualChunks` in
   `vite.config.ts`, and the comment above them that explains the
   base-versus-widgets split, which stops being true.
4. Remove `primevue` and `@primeuix/themes` from `package.json`, then
   `npm install`.
5. `primeicons` is a separate question, and the answer is probably also
   remove. 23 distinct icons are used across 65 call sites, against a
   35,148 B woff2 and an 84,980 B ttf that both ship today. Inline those
   23 as SVG the way `DatePicker.vue` and `RichTextField.vue` already do
   and the font goes with the rest. If that is more than this task
   should carry, leave it and open a follow-up, but do not leave it
   unrecorded.
6. Confirm nothing in `dist` mentions primevue.

**Measure the critical path here.** This is the step that collects the
59,891 gz. Use the command in the series README, with the Sentry DSN
set, and put the before and after in the commit message.

Tests worth having, since this is where regressions hide: keyboard
navigation opens, moves, selects and closes; the filter narrows the list
and Enter takes the first match; MultiSelect adds and removes; clear
empties the model; the panel closes on outside click and on Escape.

## Phase 3: correct to the house style

Everything the series deferred lands here, because after phase 2 nothing
has a PrimeVue neighbour left to match.

- **Move the form-field roles to the app's own tokens.** Borders go from
  `--brand-surface-200` `#dcd2b9` to `--brand-border` `#e6dec9`; text
  from `--brand-surface-700` `#403d39` to `--brand-text` `#1a1a1a`;
  muted from `--brand-surface-500` `#7e7466` to `--brand-text-muted`
  `#5e5a52`. This is the change task 01 deferred, and it touches every
  control the series built, not only this task's.
- **Reconcile with `src/public_shared/forms.css`.** `.input` there uses
  `var(--brand-bg)` as its background and a red focus ring; the Aura
  replica uses `var(--brand-surface-0)` and a red border with no ring.
  Those are two different house inputs, and by the end of this series
  the app should have one. Pick, and change the loser.
- **Check the whole app once, on screen.** The series has been changing
  one control at a time against neighbours that were still PrimeVue.
  This is the first moment the organiser app is entirely ours, and the
  first moment it can be judged as a whole.

When this lands, update `docs/design-richtext-details.md`'s sibling
docs and `CLAUDE.md`'s Frontend section, which still says "PrimeVue 4"
and describes the `@layer primevue, app` ordering that `theme.css` will
no longer need.
