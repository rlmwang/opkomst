# 03 — Refactor: extract the ordered-list editor pattern

**Layer:** frontend · **Depends on:** none (do before 04) · **Design refs:** §10
(refactors).

## Goal

`FormEditPage` + `QuestionEditor` and `DatepollEditPage` each hand-roll the same
"ordered array of sub-editors with add / move-up / move-down / delete" logic. Chores will
be the third use. Extract it **now**, with zero behaviour change, so task 04 builds
`ChoreEditor` on a shared base instead of copy #3.

This is a pure refactor: no new features, no visual change, existing tests stay green.

## Deliverables

1. **`frontend/src/composables/useOrderedList.ts`** — a generic composable owning an
   ordered `T[]`: `add(item)`, `removeAt(i)` / `remove(predicate)`, `moveUp(i)`,
   `moveDown(i)`, `canMoveUp(i)`, `canMoveDown(i)`, and ordinal renumbering on change.
   Model the API on what `FormEditPage` currently does to its question array.
2. **Migrate `FormEditPage.vue`** onto `useOrderedList` (questions). `QuestionEditor.vue`
   keeps its per-item props/emits (`update:modelValue`, `delete`, `moveUp`, `moveDown`,
   `canMoveUp`, `canMoveDown`) — only the parent's array bookkeeping moves into the
   composable.
3. **Migrate `DatepollEditPage.vue`** onto `useOrderedList` (slots), insofar as it uses the
   same add/move/remove shape. If a datepoll slot list is materially different (e.g. no
   reordering), only adopt the parts that genuinely match — don't force it.

## Constraints

- **No behaviour change.** Drafts (`useFormDraft`), validation, and submit payloads stay
  byte-identical. This is the test: existing form/datepoll editor tests pass untouched.
- Don't broaden scope into unrelated cleanup.

## Tests

- Existing `npm run test` suite green with no test edits (proves no behaviour change). If a
  component test reaches into the old internal array methods directly, update only that
  test's wiring, not its assertions.
- Add a focused unit test for `useOrderedList` (add/move/remove/renumber).

## Acceptance

- `npm run test` green.
- `npx vue-tsc --noEmit` clean (the build's typecheck gate; the project has no
  biome/eslint step).
- Manual: open `/forms/new` and `/datepolls/new`, add/reorder/remove rows — identical
  behaviour to before.

## Out of scope

The `ChoreEditor`, `CycleGridPicker`, and any chores pages (task 04).
