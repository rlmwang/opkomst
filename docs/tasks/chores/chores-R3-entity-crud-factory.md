# R3 — Frontend refactor: entity CRUD composable factory

**Layer:** frontend (refactor) · **Run before:** 04 · **Consumed by:** 04 (`useChores`).

## Goal

`useEvents.ts`, `useForms.ts`, `useDatepolls.ts` are ~80% identical — the same
list/archived/single/create/update/archive/restore/delete query+mutation set, differing
only in the resource string and query-key prefix (~250 mechanical lines each). Extract a
factory, migrate the three, then `useChores` is ~30 lines plus its few extras. No behaviour
change.

## Deliverables

1. **`frontend/src/composables/createEntityCrud.ts`** (new) — `createEntityCrud<TOut,
   TCreate>({ resource })` returns the common hooks with the proven patterns baked in:
   - `useList({enabled, chapterId})` → key `[resource,"active",{chapter}]`, URL
     `/api/v1/{resource}` (+ `?chapter_id=`).
   - `useArchived({chapterId})` → key `[resource,"archived",{chapter}]`.
   - `useSingle(id)` → key `[resource,"single",id]`.
   - `useCreate` / `useUpdate` (with the optimistic `onMutate` snapshot + `onError`
     rollback + `onSettled` invalidate) / `useArchive` / `useRestore` / `useDelete`.
   - `invalidateLists(qc)` helper keyed on `[resource]`.
   Match the EXACT current query-key shapes and optimistic semantics from `useEvents.ts`.
2. **Migrate** `useEvents`/`useForms`/`useDatepolls` to build their common hooks from the
   factory and keep ONLY their entity-specific extras alongside:
   - events: `useEventStats`, `useSendEmailsNow`, `useEventSignups`, `useDeleteSignup`;
   - forms: `useFormSummary`, `fetchFormSubmissions`;
   - datepolls: `useDatepollSummary`, `fetchDatepollSubmissions`.
   Note `useEvents` currently lacks a `useEvent` single-fetch while forms/datepolls have
   one — the factory gives all three `useSingle` uniformly (a strict improvement, not a
   behaviour change to existing call sites).

## The guard

Query keys, endpoints, and optimistic snapshot/rollback behaviour stay identical — the
TanStack cache must behave exactly as before. Existing composable/page tests pass
**unedited** (update only test wiring that reaches into a renamed internal, never an
assertion).

## Tests

- `npm run test` green with no assertion changes.
- Add a focused unit test for `createEntityCrud` (key shapes; optimistic update then
  rollback on error).

## Acceptance

- `npm run test` green; `npx vue-tsc --noEmit` clean.
- Manual: events/forms/datepolls list, create, edit (optimistic), archive — unchanged.

## Out of scope

`useChores` itself (task 04 builds it from the factory). The ordered-list editor (task 03,
a separate concern).
