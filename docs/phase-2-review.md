# Independent review — Phase 2

## Verdict

Ship with two small fixes. The atomic-claim mechanism is correct and the
race-window analysis holds up: the conditional UPDATE filtered on
`status == 'pending' AND message_id IS NULL` is genuinely atomic at the
DB level on both SQLite and Postgres, and the workers correctly bail
when their claim returns 0. Phase 2.2's decrypt-fail final state is
clean (status=failed, message_id=NULL). The previous review's two flagged
items were addressed: `_retire_disabled_channels` is now three conditional
UPDATEs and the renamed decrypt test now agrees with its assertion. The
two issues worth fixing before more work lands on top are (a) the
feedback worker's `run_once` SELECT lacks a `status == 'pending'` filter,
so reaped/failed rows are re-fetched every tick forever, and (b) the
boot-only reaper plus a never-restarted worker means a stuck row is
stuck for the lifetime of the deployment.

## Bugs found

- **`backend/services/feedback_worker.py:189-200` — `run_once` SELECT
  doesn't filter on `feedback_email_status == "pending"`.** The reminder
  worker (`reminder_worker.py:170`) correctly does. The feedback query
  gates only on `feedback_sent_at.is_(None)`. After a partial-send reap
  the row has `status=failed` but `feedback_sent_at IS NULL` (the reaper
  in `email_lifecycle.py:67-71` sets only `feedback_email_status`,
  doesn't stamp `feedback_sent_at`), so every subsequent sweep keeps
  fetching, hand-rolling a message-id, hitting the claim filter, and
  bailing. Functionally safe (the claim filter saves us) but hot-loops
  dead rows forever and is the exact "claim relies on the status filter
  *and* the SELECT does too" defence-in-depth pattern that should match
  on both channels. Add `Signup.feedback_email_status == "pending"` to
  the WHERE clause and stamp `feedback_sent_at` / `reminder_sent_at` in
  `reap_partial_sends`.

- **`backend/services/email_lifecycle.py:50-90` — reaper doesn't stamp
  `*_sent_at`.** Same root cause as above. A reaped row reads as
  "channel finalised at status=failed but never sent" which is
  inconsistent with the regular failed-after-retry path
  (`_finalise` stamps `sent_at` regardless of `sent`). Stamp it in the
  reaper too so downstream queries / dashboards can rely on
  "sent_at IS NOT NULL ⇔ channel settled".

## Concerns (not bugs, but worth thinking about)

- **No in-process recovery path.** `reap_partial_sends` only runs in
  `worker.py:main()` at boot. The plan called the worker a singleton;
  in practice "singleton" + "deployed once" means a row stuck mid-send
  stays stuck until the next deploy. The hourly tick won't unstick it
  (the SELECT picks it up, the claim no-ops, it stays pending). Cheapest
  fix: register `reap_partial_sends` as an APScheduler job that runs,
  say, every 6 hours. The reaper is idempotent and cheap (two indexed
  UPDATEs).

- **SMTP-acked-then-reaped → silent duplicate-or-loss.** The plan
  acknowledges this trade-off ("treat as `failed` ... humans can
  investigate"). It's the right call, but the choice isn't documented
  in code — `reap_partial_sends`'s docstring says "we have no way to
  find out", which is true, but a future reader trying to make this
  loud needs context. A `logger.warning` per reaped row (currently it's
  a single aggregate warning) would let ops grep for "which seven rows".
  Minor.

- **`_message_id_domain()` and `_new_message_id()` duplicated** across
  `feedback_worker.py:43-48` and `reminder_worker.py:48-53`. Pre-launch,
  Rule #1: extract to `services/email_lifecycle.py` (or a new
  `services/message_id.py`) and import. Two copies will inevitably drift.

- **`MESSAGE_ID_DOMAIN` still has `"opkomst.nu"` default in code.**
  CLAUDE.md "Never assign default values to environment variables in
  code." Flagged in the previous review, not fixed in this commit.
  Pre-existing.

- **`tests/conftest.py:24` `_TMP_DB` is still process-global.** Same
  pytest-xdist hazard as before. Not a Phase 2 issue, but the parallel-
  worker test in this commit makes it tempting to think the suite is
  parallel-safe; it isn't, only the worker production code is.

## Honest grade per phase

- **2.1 (atomic claim + boot-time reaper)** — Correct claim mechanism;
  the SELECT-then-conditional-UPDATE is genuinely atomic on both
  dialects and the test verifies it. Implementation cuts a corner by
  reaping only at boot — fine in isolation, weak when combined with a
  long-lived worker process.
- **2.2 (decrypt failure terminal)** — Clean. Claim → decrypt-fail →
  `_finalise` sets `message_id=NULL` via a conditional UPDATE on
  `status=pending`; final row is `failed`/`NULL` and the next tick's
  query (reminder) excludes it on status. Feedback path same end state
  but, per the bug above, the next tick's SELECT still re-fetches.
- **Review fix #1 (`_retire_disabled_channels`)** — Done correctly. Three
  conditional UPDATEs, all status-filtered; the wipe filters on both
  channels settled. The race with a worker mid-send is closed: if the
  worker has claimed (status still pending, message_id set), the retire
  UPDATE matches, flips to `not_applicable`, and the worker's
  `_finalise` no-ops on status filter.
- **Review fix #2 (decrypt-test rename)** — Done. Name + assertion +
  docstring all agree, second-tick assertion added.
- **Review fix #3 (`reminder_worker.py` docstring)** — Done. Describes
  the post-1.2 flow.

## Test gaps

- **The plan's 2.1 acceptance literally says "boots the worker, mints a
  message_id, asserts the row is committed, then crashes the SMTP send".**
  `tests/test_partial_send_reaper.py:27,47,90,108` shortcuts this by
  manually setting `reminder_message_id = "<stuck@opkomst.nu>"` instead
  of running the worker, monkey-patching `send_email_sync` to raise
  *after* the claim commit, and asserting the post-crash DB state. The
  shortcut covers the reaper logic but doesn't validate that the claim
  commit actually happens before SMTP — i.e. that
  `feedback_worker._process_one` is in fact crash-safe at the line the
  spec depends on. Worth one extra test that uses a fake backend whose
  `send` raises, runs `_process_one`, and asserts the DB shows
  `pending` + `message_id IS NOT NULL` immediately afterward (i.e.
  before the reaper runs).

- **No test for the in-process stuck-row scenario** described under
  Concerns. If the hourly tick is the only recovery in production
  (because the worker doesn't restart between ticks), a test that runs
  one sweep with a crashing SMTP, then runs a *second* sweep without
  rebooting, and asserts the row is *still* `pending` would document the
  current limitation. (And then if a periodic reaper job is added per
  Concerns, that test flips its assertion.)

- **No toggle-off-vs-worker race test.** The previous review's gap list
  asked for one; the fix shipped without it.
  `_retire_disabled_channels`'s conditional UPDATEs would pass either
  way, but a regression that re-introduced ORM attribute writes wouldn't
  be caught by the suite as it stands.

- **`tests/test_parallel_workers.py` is honest.** SQLite serialises
  writes but the SELECT phase runs concurrently in both threads, both
  return the same 5 rows, then the per-row claim races and exactly one
  thread's UPDATE matches per row. The test would have failed before
  Phase 2.1 (no claim filter → both threads SMTP-ack) and passes now.
  Verified by reading the engine config (`backend/database.py:8-12`,
  default isolation, no `StaticPool`) and the worker code path.
