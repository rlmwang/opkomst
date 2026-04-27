# Independent review — Phase 5.5 + 5.7 + Phase 3 review fixes

## Verdict

The five Phase-3-review fixes all landed correctly: `ics.py:86` reads
`os.environ["MESSAGE_ID_DOMAIN"]`, the privacy invariant test now
expects the two-worker set, both `_retire_disabled_channels` UPDATEs
filter on `message_id IS NULL`, `reap_expired` is a correlated
`EXISTS` subquery, `worker.py` calls it at boot, and the sent-at
test now actually re-runs `feedback_worker.run_once`. **But the
Phase 5.5 webhook suite is broken**: all 12 cases error at fixture
setup with `table users already exists`, including in isolation —
shipping a 12-case suite where 0 actually run is the headline
finding. Phase 5.7 is honest but ships at `max_examples=80`, not
the plan's mandated 1000. Two race-fix tests promised by the
previous review still aren't there.

## Bugs found

- **`tests/test_webhook_scaleway.py` — every test errors at setup,
  in isolation.** Reproduce with
  `CORS_ORIGINS="*" uv run pytest tests/test_webhook_scaleway.py`:
  12 errors, 0 passed.
  Cause: this is the first test file to import `backend.models` at
  module top (via `from _worker_helpers import ...`), so by the time
  the `db` fixture runs `Base.metadata.create_all(engine)` the
  ORM-side metadata already knows every table — `create_all` actually
  emits DDL. Then the `client` fixture imports `backend.main`, which
  runs `alembic upgrade head` against the same tempfile DB; alembic
  finds tables but no version row and tries to apply
  `cf80197e2fe9_initial_schema` from scratch → `table users already
  exists`. The pattern is "passes on the prior commit because no
  prior file imported models at module top before requesting
  `client`". The commit message claims "97 tests pass" — under
  `CORS_ORIGINS="*"` the actual count is **85 passed, 23 errored**.
  The 12 webhook errors are part of that 23.
  Fix: import `backend.models` lazily inside the helpers, or make
  the `db` fixture skip its `create_all` when `_TMP_DB` already has
  the alembic_version row, or move the alembic call to a
  session-scoped autouse fixture that runs before `db`.

- **`Event.starts_at` is `DateTime` (naive) on the model but the
  property test seeds it from `astimezone(UTC).replace(tzinfo=None)`
  and the worker compares against `datetime.now(UTC)` (aware).** On
  SQLite the comparison silently coerces both sides to ISO strings
  and the test passes. On Postgres `TIMESTAMP WITHOUT TIME ZONE` vs
  `timestamptz` will either raise or silently shift to local time,
  depending on the driver. The property test does *not* exercise
  the production dialect, so the very landmine 5.7 was meant to
  surface is still hidden — the test is a SQLite-only regression
  test. Plan §5.7 said "confirm both code paths agree" — they
  agree on SQLite only.

## Concerns

- **Plan says 1000 examples, code says 80.** `max_examples=80` is a
  silent deviation from the stated acceptance criterion, with a
  comment in the test claiming "~80 examples" as if that were the
  spec. CI runtime (23s) is acceptable; bump to 1000 or amend the
  plan to match.

- **Boot-time `reap_expired()` is unguarded.** `worker.py:55-58`
  calls it before the scheduler starts. If it raises (DB
  unreachable, lock timeout, schema-mismatch on a half-applied
  migration in another container), the worker crashes on boot
  rather than starting the scheduler in a degraded state and
  retrying on the daily tick. Wrap in `try/except` + `logger.error`
  + continue — same pattern as production-grade boot code.

- **No test for `_retire_disabled_channels` toggle-off-vs-claimed
  race.** This was the headline race fix in this commit, but
  `tests/test_toggle_off_cleanup.py` doesn't reference `message_id`
  at all, and no new test was added. The fix is unverified — a
  future change that drops the `message_id IS NULL` filter would
  pass all tests.

- **No test for the boot-time `reap_expired()` call.** `worker.py`'s
  added boot block has zero coverage. APScheduler boot semantics
  remain a runtime-discovery problem.

- **No test for reaper-vs-worker race.** Previous review flagged
  that `reap_expired` and `_process_one` both filter on
  `status == "pending"` and can stomp each other mid-SMTP. Same
  shape as the toggle-off race; same lack of test.

- **`test_decrypt_only_called_from_email_workers` doesn't ignore
  `backend/alembic/`.** Today no migration references
  `encryption.decrypt` so the test passes, but a future data
  migration that needs to re-encrypt rows would legitimately call
  it and trip this static check. Add a directory exclude.

- **Hypothesis test seeds `Event(id="evt-1", entity_id="evt-1")`
  per example.** Fine in series; under pytest-xdist (currently off)
  multiple workers would collide on the same tempfile DB. Not a
  bug today, a footgun the moment xdist is enabled.

- **`reap_expired` log line is still aggregate.** Phase-3 review
  asked for one log per row; still
  `logger.info("reminder_reap_expired", count=reaped)`. Marked
  not-fixed in this round.

## Honest grade

- **Phase 5.5 (webhook tests)** — Code is structured well, cases
  cover the plan's required matrix plus three reasonable extras
  (delivery-ignored, batch, missing-message-id). **But the suite
  doesn't actually run** — fixture-import-order bug means 0/12
  green. Cannot be considered shipped.
- **Phase 5.7 (timezone property)** — Honest property test, but
  exercises only the SQLite dialect (the very dialect where the
  bug it's hunting can't manifest), and runs at 8% of the planned
  example budget. C+.
- **`ics.py` env-default fix** — Correct.
- **Privacy test fix** — Correct; assertion now matches reality.
- **`_retire_disabled_channels` mid-send race fix** — Correct in
  code, but unverified by tests.
- **`reap_expired` EXISTS rewrite** — Correct, dialect-portable.
- **APScheduler boot-fire fix** — Correct, but unguarded against
  boot-time DB errors.
- **`sent_at` stamping test** — Correct; now genuinely tests the
  invariant the name claims.

## Test gaps

- A toggle-off-on-claimed-row test (the explicit purpose of the
  new `message_id IS NULL` filter).
- A reaper-vs-worker concurrent-pending test (same shape as
  toggle-off; flagged by previous review, still missing).
- A boot-time `reap_expired` test (verifies `worker.py` actually
  calls it, and that exceptions don't kill the worker).
- A Postgres-dialect smoke for the property test (the *whole point*
  of 5.7 was to catch naive-vs-aware on the prod dialect).
- A signature-tampering case on a real signed body (currently only
  "wrong signature for body"; no "valid signature for *original*
  body, but body mutated post-signing" — same outcome but a more
  honest framing).
- A test that fails when someone accidentally drops the
  `message_id IS NULL` filter from one of the two retire UPDATEs.
- A migration-aware variant of `test_decrypt_only_called_...` that
  ignores `backend/alembic/versions/`.
