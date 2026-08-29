# 02: The ones we already own

Five PrimeVue components whose replacement is mostly already written,
sitting unused by the organiser app, or done natively by the browser.
The work is adoption and deletion, not construction.

| component | uses | PrimeVue source | what replaces it |
|---|---|---|---|
| `Toast` + `ToastService` + `useToast` | 3 | 22,170 B | `src/public_shared/PublicToast.vue` |
| `InputNumber` | 1 | 50,300 B | `src/components/NumberStepper.vue` |
| `Dialog` | 2 | 24,071 B | `src/components/AppDialog.vue` over `<dialog>` |
| `ConfirmDialog` + `ConfirmationService` + `useConfirm` | 3 | 10,175 B | the same dialog, with two buttons |
| `Tooltip` (directive) | 1 registration | 22,717 B | a small directive of our own |

Note the ratio: 129 kB of PrimeVue source against components that mostly
exist. `InputNumber` alone is 50 kB for one call site.

## Phase 1: replicate

Each of the five has its own reference, and for three of them the
reference is our own code, not Aura's.

**Toast.** `src/primevue-preset.ts:24` says `PublicToast.vue` "mirrors
these exact values", so the two are already meant to be the same thing.
Verify that claim rather than trusting it: compare the preset's `toast`
block against `PublicToast.vue`'s styles, and if they have drifted,
`PublicToast.vue` is the one that is right, because it is the one with
no theme underneath it. Move it out of `public_shared/` into
`components/` if the organiser app is going to share it, and check
`publicToast.ts`'s `showToast` API against every `useToast()` call in
the organiser app.

**InputNumber.** One call site, `AdminWhatsAppPage.vue`, using `:min`,
`:max`, `:step="1"`, `showButtons`, `buttonLayout="horizontal"`, `suffix="
s"` and a `4rem` right-aligned input. `NumberStepper.vue` already does
the first five. Add the suffix if it does not have one; do not add
anything else, and do not generalise `NumberStepper` for a case that
does not exist.

**Dialog and ConfirmDialog.** `AppDialog.vue` exists. The two `Dialog`
call sites need `modal`, `:closable`, `:header`, `v-model:visible` and a
`:style` width, all of which `<dialog>` and its `showModal()` do
natively, including the backdrop, the top layer and Escape to close.
`ConfirmDialog` is that dialog with a message and two buttons; replace
`useConfirm()` with a small composable of the same shape over it, and
check `src/lib/confirms.ts`, which already holds the confirm copy.

**Tooltip.** One `app.directive("tooltip", Tooltip)` registration, used
as `v-tooltip.top` in `LanguageSwitcher.vue` and elsewhere. Aura's
tooltip is a dark rounded box with a caret. Write the directive against
`@primeuix/themes/dist/aura/tooltip/index.mjs` for the values. If the
only modifier in use is `.top`, support `.top` and nothing else.

**Done when:** each of the five behaves and looks as it does now, at
every call site, in the running app.

## Phase 2: swap and measure

Delete the five imports, plus `ToastService` and `ConfirmationService`
from `main.ts` and their `app.use(...)` calls, plus the `tooltip`
directive registration.

`AdminWhatsAppPage.vue` is the biggest single win in this task: its
route chunk was 49,050 raw / 14,376 gz at last measure, most of which is
`InputNumber`. Record what it becomes.

The critical path still should not move. `primevue-base` and
`primevue-themes` remain until task 03.

Tests: the confirm composable resolves on accept and rejects on cancel;
the dialog closes on Escape. The toast already has whatever tests
`PublicToast` came with, and they should keep passing unedited, which is
the sign the adoption did not change it.

## Phase 3: correct to the house style

The interesting one here is that three of these five replacements are
*already* house-styled, because they were written for the public
mini-apps where PrimeVue never reached. So phase 3 mostly runs backwards:
instead of moving our component toward the house style, check whether
adopting it changes how these surfaces look in the organiser app, and
decide whether that change is welcome.

It generally will be. A toast that already matches the public pages is a
toast that now matches everywhere. Say so in the commit, with what
visibly changed.

The one thing to look at properly: `AppDialog` over native `<dialog>`
gets the browser's backdrop, which is not Aura's. Set it explicitly
rather than inheriting whatever the browser picked, and keep it neutral
so the brand-token check passes.
