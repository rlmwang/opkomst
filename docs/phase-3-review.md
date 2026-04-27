# Independent review — Phase 3.1 + Phase 2 review fixes

## Verdict

The Phase 2 review's two named bugs (run_once filter, sent_at stamping) are
genuinely fixed and the dedup'd `new_message_id()` helper is correct. Phase
3.1's `reap_expired` is wired and works. **But** the commit ships with a
broken test (`test_decrypt_only_called_from_feedback_worker` has been red
since Phase 2 — reminder_worker is now a legitimate decrypt caller and the
test was never updated), the in-code env default the previous review
flagged still lives in `services/ics.py:86`, and APScheduler's interval
triggers default to first-fire-after-interval which leaves both new
recovery paths uncovered for an entire 1h / 24h after worker boot. Three
small follow-ups land this cleanly.

## Bugs found

- **`backend/services/ics.py:86` — in-code default for `MESSAGE_ID_DOMAIN`
  still present.** `os.environ.get("MESSAGE_ID_DOMAIN", "opkomst.nu")`.
  The Phase 2 review explicitly flagged this CLAUDE.md violation; the
  Phase 3 commit removed it from the worker helpers but left the ICS
  generator's copy. The dedup is incomplete: ICS calendar attachments
  still synthesise UIDs with the hardcoded fallback when the env var is
  missing.

- **`tests/test_privacy.py::test_decrypt_only_called_from_feedback_worker`
  is failing on `develop` and was not updated.** The Phase 2 commit added
  `encryption.decrypt` to `reminder_worker._process_one` (correctly — the
  reminder also needs to decrypt the recipient address) and even
  documented it as "A second legitimate caller of
  `services.encryption.decrypt`" in `reminder_worker.py:25-27`. The
  privacy test still asserts the single-caller invariant. `pytest tests/`
  on this commit: `1 failed, 83 passed`. Pre-existing but the Phase 2
  reviewer missed it and Phase 3 didn't catch it either — exactly the
  "previous reviews keep missing" category.

- **`backend/routers/events.py:31-67` `_retire_disabled_channels`
  toggle-off vs claimed-but-not-yet-sent race.** The retire UPDATE filters
  on `status == 'pending'` but **not** on `message_id IS NULL`. When the
  worker has already claimed a row (status pending, message_id set) and
  is mid-SMTP, an organiser flipping the toggle off flips status to
  `not_applicable`, the worker's `_finalise` no-ops on its
  `status == 'pending'` guard, and the SMTP send still fires (the SMTP
  call has already happened by the time `_finalise` runs). End state:
  email sent, status `not_applicable`, message_id wiped, no audit trail
  back to the message. The Phase 2 review noted "the race with a worker
  mid-send is closed" — it isn't, for the toggle-off path. Add
  `Signup.{channel}_message_id.is_(None)` to both retire filters, or
  accept the leak and document it.

## Concerns

- **APScheduler interval triggers don't run on boot.** `interval` jobs
  fire `interval` *after* `add_job()` was called. With `hours=24` on
  `reminder_reap_expired` and `hours=1` on `reap_partial_sends`, a
  worker that crashes and restarts daily will *never* run the expired
  reaper, and the hourly partial-send reaper is dark for the first hour
  after every deploy. `reap_partial_sends` is at least covered by the
  boot-time call in `worker.py:46-50`; `reap_expired` has no equivalent.
  Fix: add `next_run_time=datetime.now()` to both `add_job` calls, or
  call `reminder_worker.reap_expired()` once at boot alongside the
  partial-send reap.

- **`reap_expired` Python-list IN-clause is unbounded.**
  `reminder_worker.py:160-168` collects every `Event.entity_id` whose
  `starts_at <= now` into a Python list. Today's seed is small but a
  multi-year-old DB hits 10k+ historical events and the IN clause grows
  linearly. Postgres caps `IN` at 32k expressions before the planner
  starts thrashing; SQLite has its own (1000 by default,
  `SQLITE_LIMIT_VARIABLE_NUMBER`). At minimum add a `LIMIT` or
  rewrite as a correlated subquery / EXISTS. Not urgent but the
  comment ("we can't `join` an UPDATE...readable") is wrong — both
  dialects support `UPDATE ... WHERE EXISTS (SELECT 1 FROM events
  WHERE events.entity_id = signups.event_id AND ...)`.

- **Naive vs tz-aware datetime mismatch.** `Event.starts_at` is
  `DateTime` (no `timezone=True`, `backend/models/events.py:26`). The
  reaper compares it against `datetime.now(UTC)` (tz-aware,
  `reminder_worker.py:152`). SQLite silently coerces; Postgres on
  `TIMESTAMP WITHOUT TIME ZONE` raises `can't compare offset-naive and
  offset-aware datetimes` or silently casts to local time depending on
  driver. Phase 5.7 was supposed to ship a property test for exactly
  this and hasn't. Currently a production landmine, not a unit-test
  gap.

- **Reaper-vs-worker concurrent `pending` UPDATE.** `reap_expired`
  filters on `status == "pending"` and a worker mid-process also has
  `status == "pending"` (after the message_id claim). The reaper's
  bulk UPDATE could flip a row to `not_applicable` while the worker is
  in `send_email_sync`, and the worker's `_finalise` no-ops on the
  status guard. Same shape as the toggle-off race; same fix.

- **`reaped_partial_sends` log is one aggregate line.** Previous review
  asked for one warning per row so ops can grep the seven affected
  rows; still aggregate.

## Honest grade

- **Phase 3.1 (`reap_expired`)** — Correct happy path, two latent
  scaling/safety issues (unbounded IN, no boot-fire). Tests cover the
  semantic surface but not the operational gap.
- **Bug 1 fix (run_once status filter)** — Correctly applied
  (`feedback_worker.py:194`); symmetric with reminder_worker.
- **Bug 2 fix (sent_at stamping)** — Done in both
  `reap_partial_sends` (`email_lifecycle.py:78,92`) and `reap_expired`
  (`reminder_worker.py:184`). Invariant is honest now.
- **Concern: boot-only reaper** — Hourly schedule added
  (`worker.py:80-83`), wrapper closes a fresh session per tick — clean.
  Misses the "first hour after boot is dark" subtlety.
- **Concern: helper dedup** — `new_message_id()` extracted to
  `services/email/__init__.py:75-82`, env-default removed *there*. But
  `services/ics.py:86` still has the in-code default — fix incomplete.
- **Outstanding from previous review** — process-global `_TMP_DB`
  (still there, conftest.py:25); not addressed.

## Test gaps

- **`test_reaper_stamps_sent_at_so_row_isnt_re_fetched` doesn't deliver
  on its name.** It only asserts `feedback_sent_at is not None` after
  reaping. The promise in the name is "row isn't re-fetched on a
  subsequent run_once" — that needs a second `feedback_worker.run_once()`
  call and an assertion about the absence of further work (or the
  fake_email's empty `.sent` list). As written, it's a one-line
  not-None check.

- **`test_reap_with_clock_advanced_past_window` uses freezegun, which
  patches `datetime.now()` and `time.time()` — does it reach
  SQLAlchemy?** SQLAlchemy compares the Python-side `datetime.now(UTC)`
  in `reap_expired:152` against the `Event.starts_at` value stored in
  SQLite. Both ends are Python-side, so freezegun's patch *does* take.
  Verified by reading `_FrozenClock`. Test is honest.

- **No toggle-off-vs-reaper race test.** The toggle-off-vs-worker race
  test asked for in the previous review still hasn't shipped, and now
  there's an analogous reaper race (see Bugs).

- **No "claim commits before SMTP" direct test.** Previous review asked
  for it; still not present. The new tests still set
  `feedback_message_id` manually instead of running `_process_one` with
  a SMTP-raising fake.

- **No Postgres-dialect smoke for naive-vs-aware datetime.** Phase 5.7
  is the place; not landed.
