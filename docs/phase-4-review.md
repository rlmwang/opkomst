# Independent review — Phase 4 + Phase 5.6 fixes

## Verdict

Phase 4.1 and 4.2 land working code with reasonable test coverage, and the
Phase 5.6 follow-ups address the substantive findings of the previous review
(naive-UTC test now has teeth, outage test now seeds two events, boot-time
`reap_partial_sends` is wrapped). However: the batch-limit query has **no
`order_by`**, so per-tick FIFO is implicit (relies on insertion order plus
SQLite/Postgres planner whim) rather than guaranteed; the new retry test
**actually sleeps 1 s of wall-clock per run** because freezegun does not
patch `time.sleep` and the test does not use the `clock` fixture; and Phase
4.3 is checked off without meeting the plan's stated acceptance criterion.
Solid, but two real bugs and one unmet acceptance.

## Bugs found

- **`backend/services/reminder_worker.py:209` and `feedback_worker.py:178` —
  `.limit(batch_size)` without `.order_by()`.** SQLite returns rows in
  rowid order *most* of the time but the standard makes no such guarantee
  (Postgres explicitly does not). With multiple events sharing a worker
  tick, a tick that fills the batch with rows from event A can starve
  rows from event B indefinitely if the planner happens to scan A first
  on every sweep. Fix: add `.order_by(Signup.created_at.asc())` (or
  `Signup.id.asc()`). The `test_run_once_caps_at_email_batch_size` test
  doesn't catch this — it inserts 5 rows on one event and asserts only
  the *count* (2/2/1), never that the *same* rows that were skipped on
  tick 1 get processed on tick 2. Two later signups jumping the queue
  would still total 2/2/1 and pass.

- **`tests/test_reminder_worker.py:112` — `test_reminder_retry_succeeds_on_second_attempt`
  sleeps 1 second of real wall-clock per run.** `send_with_retry` calls
  `time.sleep(_RETRY_SLEEP_SECONDS)` between attempts; the default is 1 s
  read at module import. The test takes no `clock` fixture and does not
  monkeypatch the sleep, and freezegun does not patch `time.sleep` (it
  only patches `datetime.now`, `time.time`, etc.). Every CI run pays a
  literal second. Worse: the suite has **no test that verifies the sleep
  actually happens** — i.e., that retry #2 is delayed — so the
  exponential-backoff acceptance criterion in 4.2 is asserted by
  inspection, not by test. Fix: monkeypatch
  `backend.services.email._RETRY_SLEEP_SECONDS = 0` for the
  success-path test, and add a separate test that asserts the gap
  between attempt timestamps with a captured-time fake.

- **Phase 4.3 acceptance unmet.** The plan says "visible in `/health` or
  a debug endpoint that the executor's `_max_workers` is bounded." The
  commit message says "Already implemented … documented in commit
  history rather than adding a redundant guard." `backend/main.py:110`
  shows `/health` returns only `{"status": "ok"}`; nothing exposes
  `_max_workers`, and there is no test asserting the bound. Either
  expose it on `/health` (or a debug endpoint), or add a one-line unit
  test on `_get_executor()._max_workers == 4`, or formally amend the
  acceptance criterion in the plan. As shipped, 4.3 is checked off
  without meeting its own gate.

## Concerns

- **`send_with_retry` log key (`attempt=0/1`).** The old inline retry
  loops in both workers also logged `attempt=attempt` from a
  `range(2)`, so this is consistent within the codebase — but
  zero-indexed `attempt=0` for a human-readable failure log is a small
  papercut for ops. Consider `attempt=attempt+1, total=attempts`.

- **Module-level `_RETRY_SLEEP_SECONDS` capture.** Reading the env once
  at import time means tests can't override it via `monkeypatch.setenv`
  (which is the obvious move and would silently no-op). Same shape as
  `email_batch_size()` — make this a function call, not a module
  constant.

- **`tests/_worker_helpers.py:16` — module-level `_slug_counter`.**
  Shared across the test process, so two tests that compare slug
  ordering would couple. Harmless today (no test does); also harmless
  under `pytest-forked` (fresh process per test). Under `pytest-xdist`
  the counter is per-worker-process, so collisions across xdist
  workers depend on the unique-slug constraint hitting per-process
  random ordering. The project's own conftest already discourages
  xdist; restating that this counter is one more reason not to enable
  it without per-worker DB isolation.

- **`feedback_worker.run_for_event` filter migration.** Switching from
  `feedback_sent_at IS NULL` to `feedback_email_status == "pending"` is
  semantically tighter and the right call for an organiser-triggered
  "send now" — it deliberately skips rows already in `failed` /
  `bounced` / `sent`, avoiding both duplicates and re-sending to
  bounced addresses. The two filters are equivalent for reaped rows
  today (the reaper now stamps `*_sent_at`), so no behaviour change in
  the steady state. Worth a one-line comment in the docstring noting
  the deliberate exclusion of `failed` rows so a future contributor
  doesn't "fix" it by widening the gate.

- **Naive-UTC e2e tolerance of 5 s.** Defensible — `make_event` calls
  `datetime.now(UTC)` *outside* the freezegun block in some teardown
  paths and the seeded `starts_at` is computed against a non-frozen
  `datetime.now()` if the fixture order ever shifts. 5 s is generous
  but not papering over a real bug; sub-second drift in test envs is
  normal. Leave it.

- **Outage test's future-event seeding works** but reads awkwardly:
  the test re-fetches the event via a fresh session just to overwrite
  `starts_at` to `now+30d`. Cleaner: extend `make_event` to take an
  explicit `starts_at` so two events at different offsets can be
  seeded in one call, no second session needed.

## Honest grade

- **4.1 batch limit** — Implemented but no `order_by`; FIFO unproven
  by test. B-.
- **4.2 retry helper** — Helper is clean and dedupes both workers'
  inline loops. Tests waste 1 s of wall-clock and don't actually
  verify the sleep happens. B.
- **4.3 thread pool bound** — No code change, no debug endpoint, no
  test. Acceptance criterion not met. C.
- **5.6 fix: naive-UTC test** — Now has a real assertion; good. A-.
- **5.6 fix: outage test seeds two events** — Future event correctly
  protected; reaper-filter regression would now be caught. A.
- **5.6 fix: `reap_partial_sends` wrapped at boot** — Symmetrical
  with `reap_expired`; previous review's inconsistency closed. A.
- **`_unique_slug` helper** — Right fix for the frozen-clock uuid7
  collision. Module-state caveat noted but not blocking. A-.

## Test gaps

- A FIFO assertion in `test_run_once_caps_at_email_batch_size`:
  capture which `signup_id`s were sent on each tick and assert
  insertion-order. Without it, the missing `order_by` is invisible.
- A retry-timing test that monkeypatches `time.sleep` to record the
  delay and asserts attempt 2 is gated on it — the actual Phase 4.2
  acceptance criterion ("call timestamps are >= 1 s apart").
- Either a `/health` field or a unit test asserting
  `_get_executor()._max_workers == 4` — Phase 4.3 acceptance.
- A multi-event batch-limit test (two events, batch size 2): proves
  the cap doesn't starve rows on the second event when the first
  event has more rows than the batch.
- A `monkeypatch.setenv("EMAIL_RETRY_SLEEP_SECONDS", "0")` test that
  confirms the override works — currently it would silently no-op
  because the value is read at module import.
