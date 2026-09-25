# 01: Anchor registry, the action, anchors in the shared components

Design: `docs/design-tour.md` chapter 5, and the anchor list in
chapter 10. Nothing visible changes in this task. When it lands, every
control a tour will light has a name, and a test proves every name is
both declared and rendered somewhere.

## The registry

`frontend/src/tours/anchors.ts`:

- `export type AnchorName = "door.form" | "door.sent" | "home.events" |
  … ` as one union. The full list is chapter 4 and chapter 10 of the
  design: `door.form`, `door.sent`; `home.{events,datepolls,chores,forms,quizzes,compasses}`;
  `list.new`, `list.filter`, `list.archived`; `row.details`,
  `row.archive`; `share.link`, `share.qr`; `details.edit`,
  `details.recover`, `details.signups`, `details.feedback`;
  `form.card`, `form.title`, `form.submit`, `form.section.first`,
  `form.section.own`, `form.fold`, `form.fold.switch`; `header.menu`,
  `header.subtabs`; `admin.approve`, `admin.chapter.new`,
  `admin.chapter.address`, `admin.agenda`.
- A module-level `Map<AnchorName, HTMLElement[]>` and a `$state`
  change counter (`version`). `register(name, el)` pushes and bumps;
  `unregister` removes and bumps. `resolve(name)` returns the first
  element in document order, comparing with `compareDocumentPosition`
  rather than insertion order, so a row that mounts late still loses
  to the first row.
- `export function anchor(node: HTMLElement, name: AnchorName)` is the
  Svelte action: register on mount, unregister on destroy, re-register
  if the name changes.

No selectors, no callbacks, no data attributes. The registry is the
only way the engine finds an element.

## Where the action goes

| anchor | file | on |
|---|---|---|
| `door.form`, `door.sent` | `components/LoginForm.svelte` | the `<form>`, the sent `<p>` |
| `home.*` | `components/TileGrid.svelte` | each tile's link, by `tile.key` |
| `list.new`, `row.details`, `row.archive` | `components/EntityListPage.svelte` | the three `AppButton`s via the new prop |
| `list.filter` | the list view's chapter filter | the select's wrapper |
| `list.archived` | `components/AppHeader.svelte` | the archived subtab link |
| `share.link`, `share.qr` | `components/ShareStub.svelte` | the copy button's tooltip span, the QR button |
| `details.edit` | `components/DetailHeaderCard.svelte` | the edit button |
| `details.recover` | `components/RecoverLinksPill.svelte` | the pill |
| `details.signups`, `details.feedback` | `pages/EventDetailsPage.svelte` | the two cards |
| `form.card`, `form.title`, `form.submit` | `components/FormPageShell.svelte` | the card, the heading, the submit button |
| `header.menu`, `header.subtabs` | `components/AppHeader.svelte` | the menu trigger, the subtabs `<nav>` |
| `admin.approve` | `pages/UsersPage.svelte` | the first approve button |
| `admin.chapter.new`, `admin.chapter.address` | the chapters page | the new button, the first row's address |
| `admin.agenda` | `pages/SettingsPage.svelte` | the agenda window section |

`form.section.first`, `form.section.own`, `form.fold` and
`form.fold.switch` are declared in the union now and registered by
task 02's components; until then the declared-and-rendered test lists
them as owed and task 02 removes that list.

**`AppButton` gains `anchor?: AnchorName`** and applies the action to
its own `<button>`. It takes named props and no spread, so this is one
prop and one `use:` directive. `AppInput` gains nothing.

## Panel alignment

`useOverlayPanel` places a panel's left edge on the anchor's left edge.
Add `align?: "start" | "center"` to its `PlacementOptions`, default
`"start"`, one line in the arithmetic. Nothing changes for the popover.
The callout in task 03 passes `"center"`.

## The locale parity test

`frontend/src/__tests__/locale-parity.test.ts`: load `nl.json` and
`en.json`, flatten both, assert the key sets are equal. Fix whatever
that finds today before it lands; the test is not allowed to ship
with an exclusion list.

## Tests

- `frontend/src/__tests__/anchors.test.ts`: register two elements
  under one name in reverse document order and `resolve` returns the
  first in the document; unregister bumps the version; the action
  cleans up on destroy.
- A static test that every `AnchorName` in the union appears in some
  `.svelte` file as `use:anchor={"…"}`, `anchor="…"` or in `TileGrid`'s
  key template. Grep-shaped, like `test_privacy.py`'s static checks.
- Existing `app-controls.test.ts` and `site-footer.test.ts` pass
  unedited: the prop is optional and the action is inert without a
  tour.

**Done when:** the union, the registry and the action exist; every
listed component registers its anchors; `AppButton` has the prop;
`useOverlayPanel` takes an alignment; the parity test passes with no
exclusions; nothing on screen changed.
