# Independent review — Phases 1 & 5

## Verdict

Ship with caveats. Phase 1.1 and the testing scaffolding (5.1–5.3) are
solid. Phase 1.2 is correct as written, but the same conditional-UPDATE
discipline isn't applied to `_retire_disabled_channels`, which can still
stomp a worker write — that's the same class of bug 1.2 was meant to
close. Phase 5.4 ships a misnamed test and is missing the parallel-no-
duplicate-sends test that the plan listed as the Phase 1.2 acceptance
criterion. None of this is launch-blocking but several items deserve
fixing before Phase 2 lands on top.

## Bugs found

- **`backend/routers/events.py:32–58` — `_retire_disabled_channels` still
  uses ORM attribute assignment.** Phase 1.2's whole point is "status
  writes go through a conditional UPDATE so concurrent writers don't
  stomp each other." This helper writes `s.feedback_email_status =
  "not_applicable"` unconditionally. If a worker's `_process_one` (which
  reads `pending`, sends mail, then conditional-UPDATEs to `sent`) races
  with this helper between the SMTP ack and the UPDATE, the helper's
  in-memory write — flushed in a separate session — will overwrite the
  worker's `sent` with `not_applicable` (or vice-versa, depending on
  commit order). The fix is the same WHERE-clause pattern the workers
  use. The plan doesn't mention this, so it quietly slipped.

- **`tests/test_reminder_worker.py:174–202` — test name/doc disagree with
  reality.** Name: `test_reminder_decrypt_failure_keeps_status_pending_
  today`. Docstring: "Pre-Phase-2.2 behaviour: a corrupt ciphertext
  leaves the row at `pending` ... once decrypt failure flips to `failed`,
  this test will need updating." Assertion: `assert
  row.reminder_email_status == "failed"`. The assertion is what the code
  actually does today (`reminder_worker.py:84` flips to `failed`
  unconditionally when `sent` is False, including the decrypt-failed
  branch). So the test passes for a reason that contradicts both its
  name and its docstring. Either the name+doc are stale, or someone read
  the spec and decided "actually we already do Phase 2.2" without
  documenting it. The cleanest fix is rename + rewrite the docstring;
  the messy thing is that this means Phase 2.2's acceptance criterion
  ("Run again, assert no second log entry / no second processing") is
  partly in scope already and the plan should reflect that.

- **`backend/services/reminder_worker.py:14` — stale docstring.** Says
  "Wipe the ciphertext via `email_lifecycle.wipe_if_done`". Phase 1.2
  replaced that with an inline SQL UPDATE (`reminder_worker.py:109–113`).
  The module no longer imports `email_lifecycle`. Update the comment or
  someone will grep for the helper, fail to find it, and get confused.

## Concerns (not bugs, but worth thinking about)

- **`backend/worker.py` — uncaught exceptions inside `run_once` only log
  to APScheduler's internal logger**, not to Sentry (Sentry's
  FastAPI/Starlette integrations only catch HTTP-served exceptions).
  Phase 6.2 plans to address this; until then a DB-down event
  manifests as a silent failed sweep. Not introduced by this commit, but
  worth noting that `worker.py` shipping with no Sentry hook makes the
  blast radius bigger than the API container's was.

- **`backend/worker.py` SIGTERM drain.** `scheduler.shutdown(wait=True)`
  blocks for the running tick. But each `run_once()` processes the
  *entire batch* in one transaction with a final `db.commit()` at the
  end — so a `kill -9` between an SMTP ack and the end-of-batch commit
  loses all status flips for the batch and re-sends them next tick. A
  graceful `docker stop` waits up to 10s by default. If the batch is
  large enough to exceed that, `docker stop` SIGKILLs and we silently
  re-send. Phase 4.1 (batch limit) + Phase 2.1 (premint message-id)
  together close this; until then, large batches are exposed.

- **Phase 1.2 plan called this "pessimistic-lock"** but the implementation
  is optimistic compare-and-set. Naming aside the implementation is
  the right one — just note the plan text and code disagree.

- **`backend/services/{reminder,feedback}_worker.py` — `MESSAGE_ID_DOMAIN`
  has a default value (`"opkomst.nu"`).** CLAUDE.md: "Never assign
  default values to environment variables in code." Pre-existing
  (`44b40fb`), not introduced by these phases, but worth fixing while
  you're in the area.

- **`tests/conftest.py:23` — `_TMP_DB` is a process-global temp file**
  shared by every test. Combined with `Base.metadata.drop_all(engine)
  / create_all(engine)` per test (line 48–49), tests are sequential-
  safe but not parallel-safe (`pytest-xdist` would corrupt). Not a bug
  today, but if you add `pytest -n auto` to CI you'll spend an
  afternoon debugging.

- **`tests/test_feedback_worker.py:200–254` test does reproduce the race
  it claims** — session_b's commit lands before session_a's
  `_process_one` runs its conditional UPDATE, and SQLite's deferred-
  begin semantics let session_a's UPDATE re-read the latest committed
  state. The test passes for the right reason. (I checked because race
  tests are easy to write so they pass for the wrong reason.) One nit:
  the assertion `feedback_message_id is None` only proves the UPDATE
  no-op'd; it doesn't prove that an email was sent during the race.
  That's intentional per the comment, but worth a note in the docstring
  that this test does NOT exercise the double-send window.

## Honest grade per phase

- **1.1** — Good. Worker entrypoint is small, the DISABLE_SCHEDULER
  guards (Dockerfile sets it; `worker.py` refuses if it's still set)
  form a defence-in-depth. SIGTERM via `BackgroundScheduler +
  threading.Event` is the right pattern.
- **1.2** — Correct for the worker code path, but incomplete: the toggle-
  off cleanup helper still does ORM-attribute writes and can race
  workers in exactly the failure mode 1.2 was meant to prevent.
- **5.1** — Solid; FakeBackend covers the API the workers actually use.
- **5.2** — Frozen-clock fixture works; the `set + advance` pattern
  composes cleanly. Unused by current tests though (no Phase 5.4 case
  uses it) — the workers are time-driven via `make_event(starts_in=...)`
  which encodes the relative timing into the data, not the clock. Fine
  for now; will become essential for Phase 3.1's reaper test.
- **5.3** — Lifecycle matrix tests are exhaustive and pure. Good
  unit-test hygiene.
- **5.4** — Behavioural tests cover most named cases but the parallel-no-
  duplicate-sends test (Phase 1.2's stated acceptance criterion) is
  missing, the decrypt-failure test name lies about its assertion, and
  there's no scaffolding yet to make the still-pending-phase tests
  drop in cleanly (no batch helper, no reaper helper).

## Test gaps

Items the plan calls out but the suite doesn't cover:

- **Phase 1.2 acceptance: parallel `run_once()` calls produce zero
  duplicate sends.** The plan explicitly requires this test in 5.4. It's
  not there. The closest test (`test_feedback_conditional_update_does_
  not_stomp_existing_status`) exercises a single-row race between two
  sessions, not concurrent workers. Add a `ThreadPoolExecutor`-based
  test that spins up two `run_once()` invocations against the same
  fixture DB and asserts `len(fake_email.sent) == 1`.

- **Reaper test for Phase 3.1.** Plan: "freezegun: signup pending,
  advance past event start, run reaper, assert flipped + wiped." Phase
  3.1 isn't shipped yet so this isn't a gap *now*, but the `clock`
  fixture exists explicitly to support it — make sure when 3.1 lands,
  the test uses `clock.set/advance` rather than re-deriving timestamps.

- **Batch-limit test for Phase 4.1.** Plan: "insert 500 rows, run, assert
  200 processed." Same comment — fixture is in place; new helper for
  bulk-inserting N signups would make this trivial.

- **Reminder + feedback both fire on the same signup; ciphertext wiped
  after the *second* send, not the first.** Listed in Phase 5.4. Half-
  covered: `test_reminder_keeps_ciphertext_when_feedback_pending` and
  `test_feedback_done_wipes_after_reminder_already_sent` cover the two
  halves separately, but no single test runs reminder THEN feedback on
  one signup with the time-flow simulated. Cheap to add now and would
  exercise the `clock` fixture for the first time.

- **Toggle-off race with worker.** Given the bug noted above
  (`_retire_disabled_channels` ORM writes), a test that runs the worker
  and `_retire_disabled_channels` interleaved would catch the regression
  fix. Should land alongside that fix.
