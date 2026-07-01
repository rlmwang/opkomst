# 05 — Public enrolment backend

**Layer:** backend · **Depends on:** 02, R4 (public slug/token resolver) · **Design refs:**
§6 (email contract), §8 (auth), §9 (public side), §12 (privacy tests).

## Goal

Public, account-free enrolment and self-management via the per-submission edit token. A
volunteer can enrol (pseudonym + optional email + chore picks), revisit their personal page
by token, edit picks, toggle reminders, and leave. This task owns the **encrypt side** of
the new email contract and the privacy-test updates that go with it. Shift actions
(done/handoff/claim) and reminder *sending* are deferred to 06/08.

## Deliverables

Mirror `backend/routers/signups.py` + `backend/routers/forms_public.py` (edit-token
GET/PUT) and `backend/services/edit_token.py`.

1. **Public schemas** (extend `backend/schemas/chores.py`):
   - `EnrollIn` — `display_name: DisplayName`, `email: LowercaseEmail | None`,
     `email_reminders: bool` (only meaningful with email), `chore_ids: list[str]`.
   - `EnrollAck` — `edit_token: str` (raw, shown once).
   - `PersonalPageOut` — `display_name?`, `enrolled_chore_ids: list[str]`,
     `email_reminders: bool`, `has_email: bool`, plus `my_shifts: []` and `open_shifts: []`
     (empty until task 06). **Never** returns the email or ciphertext.
   - `EnrollEditIn` — `display_name`, `chore_ids`, `email_reminders` (+ optional add/replace
     email).

2. **`backend/routers/chores_public.py`** — `/api/v1/chores`, no auth, mutators
   `@limiter.limit(Limits.PUBLIC_SIGNUP)`:
   - `GET /chores/by-slug/{slug}` → `PublicRosterOut` (live only; 404 archived/unknown).
     Resolve via **`public_access.resolve_by_slug`** (R4) — no per-router slug helper.
     *(This route is what puts `PublicRosterOut` into the OpenAPI schema; task 04 removed
     its `frontend/src/api/types.ts` alias because nothing emitted it yet — the public
     mini-app re-adds the alias in task 07.)*
   - `GET /chores/by-slug/{slug}/qr.svg` → QR resolving to `/c/{slug}`, via
     `services/qr.py::render_qr` (mirror `datepolls_public.get_datepoll_qr`). **Needed by
     the admin UI too** — see the deferred frontend wiring below.
   - `POST /chores/by-slug/{slug}/enroll` →
     1. `raw, hash = edit_token.new_edit_token()`; create `Volunteer(edit_token_hash=hash,
        display_name, email_reminders, encrypted_email=encrypt(email) if email else None)`.
     2. Create `Enrollment` rows for `chore_ids` (validated against the roster's chores).
     3. If email given: send the personal-page link via `mail.send_email` (fire-and-forget,
        **plaintext `to=` at request time — no decrypt**), template `chore_welcome.html`
        with `build_url("c/{slug}", s=raw)`.
     4. Return `EnrollAck{edit_token: raw}`.
   - `GET /chores/by-token/{token}` → `PersonalPageOut`. Resolve via
     **`public_access.resolve_by_token`** (R4) with `parent_model=Roster`,
     `parent_fk=Volunteer.roster_id` (410 if roster archived; no events-style `ends_at`
     guard).
   - `PUT /chores/by-token/{token}` → edit enrolment: reconcile `Enrollment` set, update
     `display_name`; **reminder/email transitions**:
     - turn reminders **off** → set `email_reminders=False` **and null `encrypted_email`**
       (the mute path wipes; §6);
     - turn reminders **on** while adding/replacing an email → `encrypt` and store.
   - `POST /chores/by-token/{token}/leave` → delete the Volunteer row (Enrollment CASCADE;
     `encrypted_email` gone; future shifts → `volunteer_id` NULL via SET NULL).

3. **Mail template** — `backend/services/mail_templates/{nl,en}/chore_welcome.html` +
   register if templates are enumerated. Contains the personal-page link + a one-line note
   that the link is the only way back in.

4. **Privacy machinery** (the careful part — update deliberately, don't loosen):
   - `tests/test_privacy.py`: **scope** the `EmailDispatch` wipe-rule assertion to events
     explicitly (chores don't use `EmailDispatch`). Add `backend/routers/chores_public.py`
     to the **`encryption.encrypt`** caller allowlist and to the `encrypted_email`
     **write-site** allowlist. **Do not** add anything to the `encryption.decrypt`
     allowlist — it stays `{mail_lifecycle.py}`.
   - Confirm `to=` only ever appears in the mail path (welcome send logs route + outcome;
     no email in logs).

5. **`make openapi`**.

6. **Deferred frontend wiring from task 04** (do once `qr.svg` exists):
   - Wire the inline QR into **`ChoresListPage.vue`** (side panel, mirroring
     `DatepollListPage`) and **`ChoresDetailsPage.vue`** using `choreQrUrl(slug)` +
     `useChoresClipboard().copyQr`. Task 04 shipped copy-link only to avoid a broken
     `<img>` before this endpoint existed.
   - Re-add `export type PublicRosterOut = S["PublicRosterOut"];` to
     `frontend/src/api/types.ts` (now that the by-slug route emits it) if task 07 hasn't
     already.

## Tests

- **`tests/test_chores_public.py`** — enroll (with + without email) → token GET prefill →
  PUT (change picks) → leave; archived roster → 410; unknown token → 404; enroll into a
  chore from another roster → rejected.
- **`tests/test_chore_email_state.py`** (parallel to `test_email_state_machine.py`):
  enroll-with-email ⇒ `encrypted_email` set; mute ⇒ ciphertext NULL + enrolment kept;
  leave ⇒ row gone. Assert the positive invariant *`email_reminders=False` ⇒
  `encrypted_email IS NULL`*.
- **Volunteer-list leak guard** (add to `test_privacy.py` or the router test): the
  organiser `GET /chores/{id}/volunteers` (stub returning `display_name` + enrolled chores
  + load=0 for now) never includes email/ciphertext/token. *(Wire the real load in task
  06; the leak guard can assert the shape now.)*
- `tests/test_rate_limits_audit.py` passes for the new mutators.

## Acceptance

- `uv run pytest --no-cov` green; `make openapi` no diff; `uv run ruff check backend tests`
  clean.

## Out of scope

Shift generation + `my_shifts`/`open_shifts` population + done/handoff/claim (06). Reminder
*sending* (08). Public UI (07).
