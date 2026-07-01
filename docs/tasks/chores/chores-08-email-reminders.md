# 08 — Email reminders

**Layer:** backend · **Depends on:** 06 · **Design refs:** §6, §7 (reminders), §11, §12.

## Goal

Optional, disclosed shift reminders: `reminder_days_before` days before an assigned shift
(default 1), a volunteer who opted in gets a mail that deep-links to their personal page.
Shifts are **date-only**, so timing is days-before sent at a fixed civil local hour (a
module constant / `Settings` value, e.g. 18:00 Europe/Amsterdam), never an hours-before
offset and never midnight.
Decryption happens **only** in the lifecycle worker (invariant preserved). Plus the
archived-roster email purge. This is the final layer; everything below it already works
email-free.

## Deliverables

1. **`mail_lifecycle.run_chore_reminders()`** (new entry point in
   `backend/services/mail_lifecycle.py`, **not** a third `EmailChannel` — see §7 rationale).
   Select shifts where: `on_date - reminder_days_before` has arrived and the day's fixed
   send hour has passed; `status='scheduled'`; `reminder_sent_at IS NULL`; assignee exists
   with
   `encrypted_email` not null and `email_reminders` true; roster live with
   `reminder_enabled`. For each (bounded batch, ordered by id):
   - **`encryption.decrypt`** the address (this is the only decrypt site — allowlist
     unchanged);
   - `send_with_retry(to=plaintext, template="chore_reminder.html", context=..., ...)` with
     a deep link `build_url("c/{slug}", s=raw_token, shift=shift_id)`;
   - on success stamp `reminder_sent_at=now`; on failure leave it null (retries next sweep,
     naturally bounded by the lead window). Reuse `mail.py` render/backends/Message-ID as-is.
   - The reminder must carry one-click **manage / mute / leave** links to the personal page
     (§6).
   > Note: the personal-page link needs the **raw** edit token, but only the hash is stored.
   > Resolve this in design: the reminder links to `c/{slug}` and the volunteer re-opens via
   > their bookmarked `?s=` link, **or** mint a short-lived read token for the deep link.
   > Pick the simpler honest option and document it; do **not** store raw edit tokens.

2. **CLI** — `dispatch chore-reminder` in `backend/cli.py` calls `run_chore_reminders()`;
   log `event=cli_dispatch_done channel=chore-reminder processed=N` (route + outcome only,
   **no `to=` outside the mail path**).

3. **Templates** — `backend/services/mail_templates/{nl,en}/chore_reminder.html` (extends
   `base.html`). Subject + body via the render path; all copy localised.

4. **Archived-roster purge** — extend the daily reap (the `reap-expired` slot) so an
   archived roster past a grace window has its volunteers' `encrypted_email` nulled (and/or
   volunteers removed). Hard-delete already cascades. Document the grace window through
   `Settings` if configurable (no bare default in code).

5. **Config** — any new tunables (batch size, grace window) go through
   `backend/config.py::Settings`, required or explicitly defaulted there — never inline.

6. **Deploy/runbook** — add the `dispatch chore-reminder` **hourly** cron to the
   Scheduled-Tasks table + the Sentry-monitors table in `docs/deploy.md`, and its monitor
   to `docs/runbook.md` (mirror the existing rows). *(The `roster-tick` daily cron was
   already documented in both files in task 06 — do not re-add it.)* Note the archived-
   roster email purge behaviour in `docs/runbook.md`.

## Tests

- **`tests/test_chore_reminders.py`** — within-window assigned shift with opted-in email ⇒
  one send + `reminder_sent_at` stamped; second sweep ⇒ no resend (idempotent);
  `email_reminders=False` / no email / roster reminders off / archived ⇒ no send; send
  failure ⇒ `reminder_sent_at` stays null. Use the fake/console mail backend.
- **Decrypt-site invariant** — `tests/test_privacy.py` still asserts `encryption.decrypt`
  is called **only** from `mail_lifecycle.py` (this task adds a call there; allowlist
  unchanged). Re-confirm green.
- **Purge test** — archived roster past grace ⇒ volunteer ciphertext nulled.
- The property/state machine in `test_privacy_invariant_property.py` (events) stays green —
  chores don't touch `EmailDispatch`.

## Acceptance

- `uv run pytest --no-cov` green; `uv run ruff check backend tests` clean; migration (if the
  purge needs a column) idempotent under the CI downgrade/upgrade check.
- `EMAIL_BACKEND=console` local run: create roster → enrol with email + reminders →
  `roster-tick` → `dispatch chore-reminder` → see the `event=email_console urls=[…]` line
  with the personal-page deep link.

## Out of scope

None — this completes the design. Post-launch ideas (broadcast "up for grabs" mail, a
post-cycle feedback questionnaire) are not part of this series.
