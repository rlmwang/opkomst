# 07 — Public mini-app

**Layer:** frontend · **Depends on:** 05, 06 (both public payloads complete) ·
**Design refs:** §8, §10 (public mini-app).

## Goal

The volunteer-facing page at `/c/{slug}` (and `/c/{slug}?s={token}`): enrol, then return to
a personal hub to manage picks, see upcoming turns, mark done / hand off, claim open shifts,
manage reminders, and leave. Built entirely from the existing public-mini-app parts. Works
fully without email.

## Deliverables

Mirror the public-event / public-form mini-app (separate Vite entry, backend-served with
inlined payload).

1. **Entry point** — `frontend/public-chore.html` + `frontend/src/public_chore/`
   (`main.ts`, i18n, API client) added as a `vite.config.ts` `rollupOptions.input` entry
   `publicChore` (the existing inputs are `main`, `publicEvent`, `publicForm`,
   `publicDatepoll`). Backend SPA handler serves it on `/c/:slug` with
   `window.__OPKOMST_CHORE__` inlined (mirror how `public-event.html` /
   `public-datepoll.html` are wired — each has its own `src/public_datepoll/` etc.).

2. **`PublicChore.vue`** — wraps `PublicShell` (+ `PublicHero`, `PublicNotice`), renders in
   the **roster's locale** (UX principle: locale per entity, not per user). Two modes keyed
   on `?s={token}`:
   - **Enrol** (no token): `display_name` (optional), the chore checkbox list, and — behind
     a `Disclosure` with the **chore-specific email copy** (§6: "kept encrypted for the life
     of your enrolment, deleted on leave/mute") — an optional email + reminders toggle.
     Submit → show the personal-page URL via `EditLink`.
   - **Personal** (`?s={token}`): enrolled chores (editable), **"My turns"** (upcoming
     `scheduled` shifts with **Mark done** / **Can't make it → find someone else**),
     **"Up for grabs"** (open shifts to claim), reminder toggle, **Leave** (guarded
     confirm). On `handoff`/`done`/`claim`, refetch the personal payload.

3. **`usePublicChore.ts`** (in the mini-app) — Vue Query reads/mutations against the
   public endpoints: by-slug, enroll, by-token GET/PUT, shifts done/handoff/claim, leave.

4. **i18n** — mini-app `nl` + `en` strings (the mini-apps carry their own locale bundles).
   Public surfaces show one generic localised failure string, never backend error text.

## UX rules to honour (principles-ux.md)

- Privacy disclosure **in front of** the email field.
- Disabled-with-reason over hidden (e.g. "Mark done" only on your own current shift).
- Optimistic for routine toggles; pessimistic confirm for **Leave** (irreversible — deletes
  your email).
- No visible string under 13px; every icon button has tooltip + aria-label.

## Tests

- Component tests: enrol payload shape (with/without email); personal mode renders my-shifts
  + open-shifts; done/handoff/claim call the right endpoints and refetch; leave confirms.
- `npx vue-tsc --noEmit` clean (no biome/eslint step in this repo).

## Acceptance

- `npm run test` green.
- Manual end-to-end against tasks 05/06 backend: enrol → copy link → open personal page →
  (after a `roster-tick`) see an assigned shift → hand it off → mark another done → leave.

## Out of scope

Reminder emails (08) — the page only needs to exist for reminders to deep-link into it.
