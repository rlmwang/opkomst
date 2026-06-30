# 04 — Admin frontend (rosters)

**Layer:** frontend · **Depends on:** 02 (API + schema.ts), 03 (useOrderedList),
R3 (createEntityCrud) · **Design refs:** §10.

## Goal

Organisers can fully manage rosters in the UI: list, search, create, edit (including the
multi-week recurrence picker), archive/restore/delete, and view a details page. The
"Corvee/Chores" item joins the workspace dropdown. Schedule/volunteer panels on the
details page show "nothing yet" until tasks 05/06 supply data.

## Deliverables

Mirror the Datepoll page set + composable.

1. **`frontend/src/composables/useChores.ts`** — build the common hooks from
   **`createEntityCrud({resource:"chores"})`** (R3): gives `useList`/`useArchived`/
   `useSingle`/`useCreate`/`useUpdate`/`useArchive`/`useRestore`/`useDelete` with the
   query keys `["chores",...]` and optimistic semantics already baked in. Add only the
   chore-specific extras here: `useChoreSchedule(id)` → `["chores",id,"schedule"]` and
   `useChoreVolunteers(id)`. Plus `useChoresClipboard` wrapping `useShareClipboard`
   (`publicUrlFor: /c/{slug}`). ~30 lines total.

2. **`CycleGridPicker.vue`** (new, reusable) — props `periodWeeks: number`, v-model
   `cycleSlots: number[]`. Renders `periodWeeks` rows × 7 day-toggles (Mon..Sun), each row
   labelled "Week 1 … Week k" (single row when k=1). Each toggle ↔ flat offset
   `week*7 + day`. Built on PrimeVue `ToggleButton`/`SelectButton`. All labels via `t()`.

3. **`ChoreEditor.vue`** (new) — one chore row built on `useOrderedList` semantics: name,
   `CycleGridPicker`, `people_per_shift` stepper, optional `EmojiPicker`. Props/emits match
   `QuestionEditor` (`update:modelValue`, `delete`, `moveUp`, `moveDown`, `canMoveUp`,
   `canMoveDown`).

4. **Pages** (lazy routes in `frontend/src/router/index.ts`,
   `meta:{requiresAuth,requiresApproved}`):
   - `/chores` → **`ChoresListPage.vue`** via `ListPageView`.
   - `/chores/archived` → **`ArchivedChoresPage.vue`** via `useArchivedList`.
   - `/chores/new` & `/chores/:id/edit` → **`ChoresEditPage.vue`** via `FormPageShell` +
     `useFormDraft` + `ChapterPicker` + `ImageField` + optional `LocationPicker` + the
     **recurrence controls** + the `ChoreEditor` list (via `useOrderedList`).
     - **Recurrence controls** (roster-level, above the chore list): `period_weeks`
       stepper/select; an **anchor-Monday** date picker shown only when k>1, constrained to
       Mondays (disabled-with-reason if not Monday). Changing k reshapes every
       `CycleGridPicker`; **shrinking k clears now-out-of-range slots with a warn-toast
       naming the affected chores** (the server clamps too — task 02).
   - `/chores/:id/details` → **`ChoresDetailsPage.vue`** via `DetailsPageShell`: overview
     card (name, recurrence summary, share link + QR), chore list. Add placeholder cards
     for "Volunteers" and "Schedule" that render an empty state for now (filled in 05/06).

5. **`ImageField.vue`** — its `resource` prop is a plain `string` (no literal union to
   edit), so just pass `resource="chores"`. The matching backend image endpoint
   (`folder="chores"`) is added in the chores router in **task 02** — there is no shared
   upload route to extend; confirm task 02 shipped it before wiring this.

6. **Nav** — add the fourth item to the workspace dropdown in `AppHeader.vue`
   (`sectionTabs`): key `chores`, `to: "/chores"`, `label: t("header.chores")`,
   `isActive` on `/chores`. Subtab pair for `/chores` + `/chores/archived` (Actief/Archief)
   like the others.

7. **i18n** — `chores.*` + `header.chores` keys in `nl` + `en` (locked-step).

## Tests

- Component test for `CycleGridPicker` (toggle ↔ offset mapping; k=2 two rows).
- Page test for `ChoresEditPage`: build a k=2 roster with two chores, assert the payload
  shape; shrink-k clears out-of-range slots + fires warn-toast.
- List/archived smoke tests mirroring the form/datepoll page tests.

## Acceptance

- `npm run test` green; `npx vue-tsc --noEmit` clean (no biome/eslint step in this repo).
- Manual: create a biweekly roster end-to-end against the task-02 API; verify it appears in
  the list and the dropdown, edit and archive it.

## Out of scope

Public mini-app (07). Real volunteer/schedule data (05/06).
