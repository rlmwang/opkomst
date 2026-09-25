# 02: Form section and fold components

Design: `docs/design-tour.md` chapter 10. A refactor the pages are
owed regardless of the tour: the four edit pages render the same
section block 29 times, 15 of them with a switch in the heading, and
the extra-settings fold four times, each with its own open state. The
guard is *no behaviour change, existing tests pass unedited*. The
counts today:

| page | lines | sections | toggle rows |
|---|---|---|---|
| `EventFormPage.svelte` | 899 | 10 | 8 |
| `DatepollEditPage.svelte` | 812 | 5 | 2 |
| `ChoresEditPage.svelte` | 600 | 7 | 2 |
| `FormEditPage.svelte` | 666 | 7 | 3 |

## `FormSection.svelte`

Props, all named, no spread:

- `heading: string`
- `enabled?: boolean` (bindable). When bound, the heading becomes a
  toggle row with the switch in front of it and the label id wired to
  the switch, exactly as the pages do by hand today. When absent, a
  plain heading.
- `explainer?: string`
- `anchor?: AnchorName`, applied to the `<section>`.
- `children: Snippet`

Read the eight toggle rows in `EventFormPage` first: they are the
widest use, and the component has to carry every variation they have
(switch first, label id, the explainer under the heading, the fields
hidden or shown by the switch). If a variation exists in only one
page, that page keeps it inline and the component does not grow a
prop for it.

## `AdvancedFold.svelte`

The `details.advanced` block: one `<details>` with a `<summary>`
carrying the two summary strings the pages already have, `open`
bindable, the fold's anchor `form.fold` on the summary. Each page
drops its own `advancedOpen` state and toggle handler and binds the
component's instead. `docs/design-public-pages-ux.md` says every edit
page ends this way; after this task there is one place that can.

Inside the fold, the first switch registers `form.fold.switch`
through `FormSection`'s anchor prop. Which switch is first is the
page's business; the tour lights whichever it is.

`form.section.first` goes on each page's first section and
`form.section.own` on the product's own section: when, dates, chores
or questions. The page passes the name; the component registers it.

## Migration

Migrate the four pages one at a time, `EventFormPage` first. After
each page: `npm run test`, `npm run typecheck`, and open the page
once at 1024px and at 375px to compare with the previous commit. The
create and update payloads must be byte-identical, which
`entity-crud.test.ts` and the e2e critical paths check for the parts
they cover.

Remove the owed-anchors list from task 01's static test; every name
in the union is now rendered.

## Tests

- `frontend/src/__tests__/form-section.test.ts`: a bound `enabled`
  renders the switch, wires `aria-labelledby` to the heading, and
  toggles; an unbound one renders a heading and no switch; the
  explainer renders only when given; the anchor registers.
- `advanced-fold.test.ts`: `open` round-trips through the bind
  accessor (`__tests__/bind.svelte.ts`); the summary carries the
  `form.fold` anchor.
- Everything that exists passes unedited.

**Done when:** the four pages use the two components, the pages are
about 200 lines shorter between them, every form anchor is registered,
and no payload, string or pixel changed.
