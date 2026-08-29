# 01: Plain controls

Replace the seven PrimeVue components that are a styled element and
nothing else. No overlays, no keyboard behaviour, no focus management:
volume is the work here, not difficulty.

| component | uses | PrimeVue source | what it is |
|---|---|---|---|
| `Button` | 32 | 8,258 B | a `<button>` with a label, an icon slot and severity variants |
| `InputText` | 16 | 2,639 B | an `<input type="text">` |
| `ToggleSwitch` | 6 | 4,441 B | a checkbox drawn as a sliding track |
| `Textarea` | 2 | 4,028 B | a `<textarea>` |
| `IconField` | 2 | 801 B | a wrapper that reserves room for an icon |
| `InputIcon` | 2 | 997 B | the icon inside that wrapper |
| `ProgressBar` | 1 | 2,702 B | a div whose child has a width |

## What lands

New in `src/components/`: `AppButton.vue`, `AppInput.vue`,
`AppTextarea.vue`, `AppToggle.vue`. Those four have between 2 and 32 call
sites and real behaviour to share.

The other three do not become components. `IconField` and `InputIcon`
are a wrapper and its icon, two CSS rules on the one call site each pair
serves. `ProgressBar` has a single call site, `AdminWhatsAppPage.vue`,
and is two divs and a width percentage next to the `.progress-line` rule
already in that file. Fold all three into their call sites and delete the
concept: a shared component with one consumer is a worse shape than the
markup it hides.

`primevue-base` and `primevue-themes` **do not shrink**. They go in task
03. What shrinks here is the route chunks these components sit in, and
the number of things the app depends on.

## Phase 1: replicate

Read the reference before writing anything. For each component, the
token file at `@primeuix/themes/dist/aura/<name>/index.mjs` and the CSS
at `@primeuix/styles/dist/<name>/index.mjs`. Resolve through the map in
the series README.

The values that matter, already resolved:

**Button.** `padding: 0.5rem 0.75rem`, `border-radius: 6px`, `gap:
0.5rem`, label `font-weight: 500`, icon-only width `2.5rem`, transition
`0.2s`. Primary is `{primary.color}` background with `#fff` text and a
`{primary.color}` border. Text-secondary, which is what the icon buttons
use, is transparent with `var(--brand-surface-500)` text, hover
`var(--brand-surface-50)`, active `var(--brand-surface-100)`. Focus ring
`1px solid var(--brand-primary-500)` at `2px` offset.

Aura also has `rounded` and `outlined` variants. No call site uses
either, so do not build them.

**InputText and Textarea.** `font-size: 1rem`, `padding: 0.5rem
0.75rem`, `border: 1px solid var(--brand-surface-200)`, `border-radius:
6px`, colour `var(--brand-surface-900)`, placeholder
`var(--brand-surface-500)`, hover border `var(--brand-surface-400)`,
focus border `var(--brand-primary-500)` with no ring, disabled
`var(--brand-surface-50)` background and `var(--brand-surface-500)`
text. The box-shadow is Aura's `form.field.shadow`; flatten its tint to
a neutral one, as `DatePicker.vue` does, and say why in a comment
without writing the literal (the brand-token check reads comments).

**ToggleSwitch.** The preset overrides this one, so read
`src/primevue-preset.ts` and not Aura: track `{surface.200}` going to
`{primary.color}` when checked, handle `{surface.0}` throughout, handle
colour `{text.muted.color}` going to `{primary.color}`.

Every call site's props are already known, and this is the whole surface
to support. Keep the names, so a call site changes its import and
nothing else.

- **Button:** `:label`, `icon`, `severity`, `text`, `size`, `:disabled`,
  `:loading`, `type`, `as`, `@click`, plus `:aria-label` and
  `:aria-expanded` passed through.
- **InputText:** `v-model` / `:model-value`, `:placeholder`, `fluid`,
  `type`, `name`, `inputmode`, `autocomplete`, `spellcheck`,
  `autofocus`, `:aria-label`, `@input`, `@blur`.
- **Textarea:** `v-model`, `:placeholder`, `rows`, `:maxlength`,
  `:disabled`, `fluid`, `auto-resize`, and a template `ref`.
- **ToggleSwitch:** `v-model` / `:model-value`, `:disabled`, `inputId`.
- **ProgressBar:** `:value`.

`auto-resize` on Textarea is the only one carrying behaviour: it grows
the field to fit its content.

**Done when:** each component renders indistinguishably from the
PrimeVue one at every call site, checked side by side in the running
app. Not "close enough". This phase exists so that phase 3's differences
are deliberate.

## Phase 2: swap and measure

Change the import at all 61 call sites. Delete every `from
"primevue/<name>"` for the seven. Remove `Tooltip`'s siblings only if
they are among these seven; the rest stay until their own task.

Rebuild and record the route-chunk sizes before and after. The critical
path should be unchanged, and if it moved, find out why before
continuing.

Component tests for the two with real behaviour: `AppToggle` emits on
click and reflects `v-model`, `AppButton` does not fire while
`:disabled` or `:loading`. The rest are markup and need no test.

## Phase 3: correct to the house style

Now the deliberate part. Three things to look at, and the answer to each
is a judgement, not a rule:

- **Borders and text.** These controls sit next to PrimeVue `Select` and
  `AutoComplete` until task 03, so moving `--brand-surface-200` to
  `--brand-border` now would make our inputs visibly lighter than their
  neighbours. Defer it, and note in the commit that task 03 finishes it.
- **`.btn` and `.btn-primary` already exist** in
  `src/public_shared/forms.css`, written for the public mini-apps. Read
  them. If `AppButton` and those two disagree, one of them is wrong, and
  the app should end with a single button.
- **Any font size Aura asks for that is not in the app's set** goes to
  the nearest one that is.

Anything you change here, say what and why in the commit. Anything you
looked at and deliberately left, say that too.
