# Independent review — Phase 5.6 + auth fixture rescue

## Verdict

The auth-fixture rescue is correct and overdue: the `setdefault`-vs-empty-string trap on `BOOTSTRAP_ADMIN_EMAIL` and the dev-DB-leak via inherited `DATABASE_URL` were real, latent footguns and worth the prose comments. The session-scoped `_bootstrap_schema` fixture solves the "table users already exists" cascade the previous review flagged. Phase 5.6 lands four-of-four required scenarios plus three extras, and 5.5/5.7/Phase-3 review followups are largely closed. **However**, two of the seven new e2e tests don't actually verify what their docstrings claim, the toggle-off-mid-send race test is a near miss, and the boot-time `reap_partial_sends` call is left unwrapped while the `reap_expired` call right next to it is now wrapped — exactly the inconsistency the previous review's fix should have addressed in one shot. Net: solid work, but two assertions need teeth.

## Bugs found

- **`tests/test_email_lifecycle_e2e.py:284` — `test_e2e_event_starts_at_in_signup_response_uses_naive_utc` doesn't test what its name claims.** The body asserts only `r.status_code == 201`. The name and docstring promise a check that the response uses naive UTC for `starts_at`; no assertion ever inspects the response body, the DB column, or anything time-zone related. It's a smoke test mis-named as an invariant test. Either rename to `test_e2e_signup_with_naive_starts_at_succeeds` (honest), or assert `r.json()["event"]["starts_at"]` parses as naive (or aware) and matches the seeded value.

- **`tests/test_email_lifecycle_e2e.py:214` — the outage/reaper test cannot detect a "future events also reaped" regression.** `clock.advance(days=4, hours=3)` puts the event in the past before `reap_expired()` runs, so a buggy reaper that dropped the `Event.starts_at <= now` filter would still pass. To actually exercise the filter the test needs a *second* event whose `starts_at` is still in the future at reap time, plus a pending signup on it, and assert that signup stayed `pending`. Without it, the reaper-correctness assertion is just "reaper runs and counts 1".

- **`backend/worker.py:46-51` — `reap_partial_sends` at boot is still unwrapped.** The previous review flagged the boot-time call as a crash risk; this commit wraps `reap_expired` (lines 62-67) but not `reap_partial_sends` (lines 45-51), which sits seven lines above and runs against the same DB with the same risk profile (transient connection error, half-applied migration). Either wrap both with the same `try/except + logger.exception` shape, or wrap neither and document why one is more critical. Inconsistent treatment is the worst of both worlds.

## Concerns

- **Toggle-off-mid-send test (`test_disabling_skips_rows_currently_mid_send`) is correct but fragile to a future Phase-2.1 tightening.** The real worker claim writes only `*_message_id`; the test mirrors that. Good. However if a future change makes the `_retire_disabled_channels` filter also check `*_sent_at IS NULL` (a plausible follow-up), the test would still pass without exercising the new condition. Consider adding a parallel test where the row has `feedback_sent_at` set (post-send) to nail that branch — small, cheap, and prevents silent regressions.

- **`test_e2e_smtp_failure_wipes_via_failed_path` is robust to fixture leakage** because `fake_email` is function-scoped and re-installed per test, so the `raise_on = None` mid-test mutation cannot leak. The reset is fine; just calling that out so it isn't flagged in a future review. However, `fake_email.fail_n_times(addr, 999)` followed by `raise_on = None` leaves `_raises_remaining[addr] = 998` dangling — harmless under per-test reset, but if anyone ever moves `fake_email` to session scope this becomes a time bomb. Add a `reset()` call instead of poking `raise_on` directly.

- **Toggle-off e2e test calls `_retire_disabled_channels` directly instead of `PUT /events/{id}`.** The comment justifies this with "admin auth fixture chain", but the suite *already has* that chain (`organiser_headers`, `chapter_id`, `admin_token`). Using PUT would also exercise (a) the `was_questionnaire/was_reminder` branch, (b) the SCD2 archive-on-write that `update_event` does *before* calling the helper, and (c) the `ends_at <= starts_at` validator. Today the test asserts the helper's logic but not its wiring — a router refactor that forgot to call `_retire_disabled_channels` would not be caught.

- **xdist footgun, restated.** `_TMP_DB` is computed at module-import time. Pyproject keeps `addopts = ""` to stay in-band, but a developer running `pytest -n auto` would silently share one tempfile across worker processes and get nondeterministic interleavings on schema setup. Worth a `pytest_configure` hook that refuses xdist outright until per-worker DBs are wired up — or at least a `tmp_path_factory`-based path keyed on `worker_id`.

- **`os.environ["LOCAL_MODE"] = "0"`** is fine *if and only if* every consumer reads it as `== "1"`. I spot-checked the seed module and found that pattern; if a future caller does `bool(os.environ.get("LOCAL_MODE"))`, `"0"` is truthy and demo seeding would re-enable. Worth a one-line conftest-side comment, or set `LOCAL_MODE=""` (falsy in either reading).

- **`test_signup_list_only_exposes_name_and_size` already protects the privacy invariant** (the equality assertion on the dict shape implicitly excludes `email`/`feedback_email_status` — it's not a "subset" check). The drift fix is correct.

## Honest grade

- **5.6 e2e (4 required + 3 extras)** — Required four scenarios all green and meaningfully end-to-end. The naive/aware bonus test is a no-op assertion; the outage test under-specifies the reaper filter. B+.
- **Auth-fixture rescue (force overrides + `_bootstrap_schema`)** — Correct, well-commented, fixes the headline 23-error mass failure from the previous review. A.
- **`worker.py` boot-time `reap_expired` wrap** — Correct shape but applied inconsistently with `reap_partial_sends` two blocks up. B-.
- **Toggle-off mid-send race test** — Correct mirror of the worker's claim mechanism (message_id only, no `*_sent_at`). Closes the previous review's "no test for the headline race fix" gap. A-.
- **Privacy test help_choices update** — Correct; assertion still enforces full equality so the privacy invariant remains tight. A.
- **`fake_email.raise_on = None` mid-test** — Acceptable under function scope, but poking the field directly instead of using `reset()` is unidiomatic and will rot if the fixture's scope ever changes. B.

## Test gaps

- A `PUT /events/{id}`-driven toggle-off test that exercises the router's own SCD2 update + the helper call together (today only the helper is covered).
- A reaper test with both a started and an unstarted event in the same DB, asserting only the started one's signup is reaped (catches `starts_at <= now` regressions).
- A boot-time worker test: spin up `backend.worker.main` in a thread with a forced exception in `reap_expired`, assert the scheduler still starts (verifies the new `try/except` actually saves the worker process).
- A `reap_partial_sends`-fails-at-boot variant of the same test (would force the inconsistency above into the open).
- A real assertion in `test_e2e_event_starts_at_in_signup_response_uses_naive_utc` — either drop the test or have it actually check the response/DB time-zone shape.
- A signup-time naive-vs-aware property test that runs against Postgres in CI (the previous review's open gap; still open — Phase 5.7's hypothesis test only exercises SQLite).
