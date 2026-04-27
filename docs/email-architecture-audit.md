# Email infrastructure — structural audit

A step back from the recent robustness work to look at the
*shape* of the email system. The 17 plan items shipped (all of
1–6) make it work; this document is about whether it's the right
*design*, and what would change if we were starting fresh today.

I'm targeting the things that will compound over the next year of
maintenance — the kind of structural debt that's invisible until
the third channel needs to be added.

---

## TL;DR

The single biggest opportunity is **collapsing the two workers
and the two parallel column-sets into a generic "email channels"
abstraction**. Today's code is "feedback worker" + "reminder
worker" with ~90% of `_process_one`, `_finalise`, `run_once`,
boot-time hooks and tests duplicated. That duplication is what
caused half the bugs the reviews caught (one channel got a fix,
the other was missed). Adding a third channel today (a "thank
you for coming" the morning after, a "tomorrow!" T-1d, a "your
sign-up was edited" notification) means another ~250-line copy.

A small-but-painful second issue is the **status field encoded
as a free-text string** with values scattered across many call
sites. SQLAlchemy enums + a state-machine helper would make
illegal transitions impossible at the type level.

The webhook handler's correlation-by-message-id is **fragile and
asymmetric** — it tries one column, then the other, with no index
covering both. A `MessageDispatch` table would normalise this.

The rest is smaller fish — naming, folder layout, observability —
but adds up.

---

## 1. The duplicated-worker problem (biggest)

### What it looks like today

```
backend/services/feedback_worker.py    236 lines
backend/services/reminder_worker.py    232 lines
```

`diff -u feedback_worker.py reminder_worker.py | wc -l` is **368**.
The diff is dominated by:

- `feedback_email_status` vs `reminder_email_status` (find/replace).
- `feedback_message_id` vs `reminder_message_id` (find/replace).
- `feedback_sent_at` vs `reminder_sent_at` (find/replace).
- The selection query (different time-window predicates).
- The template name + URL builder.
- Feedback-only: `_mint_token` + `FeedbackToken` cleanup.

That's it. `_process_one`, `_finalise`, the conditional-claim
UPDATE, the wipe-when-done UPDATE, the metric emission, the
imports, the docstring, the boilerplate — all duplicated in full.

Every Phase-2 review and Phase-5 review found at least one bug
because a change to one worker wasn't mirrored in the other:

- `feedback_worker.run_once` was missing the `status == "pending"`
  filter for ages while reminder_worker had it (Phase 2 review #1).
- `reminder_worker` didn't have batch-limit `.limit(...)` in the
  same shape as feedback_worker (Phase 4).
- `reap_partial_sends` was wrapped at boot but `reap_expired`
  wasn't, even though they sit two lines apart (Phase 3 review).

The reviews keep catching this because the duplication is
*work-causing*, not just code-aesthetic.

### Proposal: a single `EmailChannel` abstraction

Stand up a small declarative description of what an email channel
is, then collapse the two workers into one parametric
implementation.

```python
# backend/services/email_channels.py
@dataclass(frozen=True)
class ChannelSpec:
    """Declarative description of an email channel. Both
    'reminder' and 'feedback' fit this shape; a third channel
    (e.g. T-1d, day-of nudge) is one ChannelSpec instance away."""
    name: str  # "reminder", "feedback"
    template_name: str
    status_col: ColumnElement
    sent_at_col: ColumnElement
    message_id_col: ColumnElement
    event_toggle_col: ColumnElement  # Event.reminder_enabled, etc.
    window: WindowFn  # given event → does this channel fire now?
    build_context: ContextFn  # given event → template context dict
    on_success: PostSendHook | None = None  # feedback wants token mint
    on_failure: PostSendHook | None = None  # feedback wants token cleanup

REMINDER = ChannelSpec(
    name="reminder",
    template_name="reminder.html",
    status_col=Signup.reminder_email_status,
    sent_at_col=Signup.reminder_sent_at,
    message_id_col=Signup.reminder_message_id,
    event_toggle_col=Event.reminder_enabled,
    window=lambda ev, now: now < ev.starts_at <= now + REMINDER_WINDOW,
    build_context=lambda ev: {
        "event_name": ev.name,
        "event_url": build_url(f"e/{ev.slug}"),
        "starts_at": ev.starts_at,
    },
)

FEEDBACK = ChannelSpec(
    name="feedback",
    ...
    on_success=mint_feedback_token,
    on_failure=drop_feedback_token,
)

CHANNELS = (REMINDER, FEEDBACK)
```

Then **one** `_process_one` that takes a `ChannelSpec`. **One**
`_finalise`. **One** `run_once` per channel that calls into the
shared core. **One** reaper. **One** lifecycle helper.

Adding a "T-1d nudge" channel is now: write a third `ChannelSpec`
constant. No new worker file, no new schema columns, no new
APScheduler job (or one trivial one).

### The schema implication

The hard part is that today's schema has parallel columns:
`feedback_email_status` / `feedback_sent_at` / `feedback_message_id`
and the reminder triplet. An `EmailChannel` abstraction over a
fixed pair of triplets is fine, but the *real* generalisation is:

```sql
CREATE TABLE signup_email_dispatches (
    id          TEXT PRIMARY KEY,
    signup_id   TEXT NOT NULL REFERENCES signups(id),
    channel     TEXT NOT NULL,             -- "reminder" | "feedback" | …
    status      TEXT NOT NULL,             -- pending | sent | failed | bounced | complaint | not_applicable
    message_id  TEXT,
    sent_at     TIMESTAMP,
    UNIQUE (signup_id, channel)
);
CREATE INDEX ON signup_email_dispatches(message_id) WHERE message_id IS NOT NULL;
CREATE INDEX ON signup_email_dispatches(channel, status);
```

Now:

- The worker query is `WHERE channel = ? AND status = 'pending' …`
  — same shape regardless of which channel you're sweeping.
- The webhook lookup is a single indexed query on `message_id`,
  no "try column A, fall back to column B" logic. Adding a third
  channel doesn't add another OR clause to the webhook.
- `reap_partial_sends` is one SQL statement, not two.
- `_retire_disabled_channels` is one SQL statement per disabled
  channel, not bespoke per-column code.
- The privacy-wipe rule becomes a single condition: "encrypted
  email is wiped iff no row in `signup_email_dispatches` for this
  signup has `status = 'pending'`".
- Adding bounce / complaint counts becomes a `GROUP BY channel,
  status` query.

This is a bigger lift (Alembic migration that splits columns into
rows + backfill + ORM model rewrite) but it eliminates **every
class of bug the reviews kept finding**, because there's no second
column-set to forget about.

**Effort:** ~1 day. **Risk:** medium — alembic migration touching
production data. **Reward:** maintenance load drops by ~30% and
adding a new channel is a config change.

---

## 2. The status field is a stringly-typed state machine

`feedback_email_status` and `reminder_email_status` are `TEXT`
columns whose legal values are
`{not_applicable, pending, sent, failed, bounced, complaint}`.
Today this is enforced **only** by convention — every code path
that writes to one of these columns has to remember the
allowed-set, and the transition rules are scattered across:

- `routers/signups.py` (sets pending or not_applicable at signup)
- `services/{feedback,reminder}_worker.py` (pending → sent/failed)
- `services/email_lifecycle.py` (pending → failed via reaper;
  pending → not_applicable via expired-window reaper)
- `routers/events.py:_retire_disabled_channels` (pending →
  not_applicable)
- `routers/webhooks.py` (sent → bounced/complaint)

If a future change introduces a typo (`"complaint "` with a
trailing space, `"complained"` instead of `"complaint"`), nothing
catches it — neither at write-time nor at read-time. The
worker's `WHERE status == "pending"` filter would silently
exclude the typo'd row.

### Proposal

```python
# backend/services/email_channels.py
class EmailStatus(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    BOUNCED = "bounced"
    COMPLAINT = "complaint"

# In the model:
status: Mapped[EmailStatus] = mapped_column(
    sa.Enum(EmailStatus, name="email_status"),
    ...
)
```

SQLAlchemy + Postgres turns this into a proper `ENUM` type at
the DB layer — illegal values are rejected by the database. The
Python side gets autocomplete and a single source of truth.

A small step further: a `Transition` table (or just a docstring
on the enum) listing legal `from → to` transitions, and a helper
that validates them at the call site. For our state space (~6
states, ~10 legal transitions) this is cheap and catches every
"oops, we flipped sent back to pending" bug at code-review time.

**Effort:** ~2h. **Reward:** every typo and every accidental
state-machine violation becomes a static error.

---

## 3. The webhook's "try-column-A-then-column-B" is asymmetric

```python
# backend/routers/webhooks.py:81-93
signup = (
    db.query(Signup)
    .filter(Signup.feedback_message_id == message_id)
    .first()
)
channel = "feedback"
if signup is None:
    signup = (
        db.query(Signup)
        .filter(Signup.reminder_message_id == message_id)
        .first()
    )
    channel = "reminder"
```

Two queries instead of one (waste). Hard-codes the channel order
(if a third channel ever ties on message_id, which shouldn't
happen but isn't enforced, the order matters). Won't extend to
a third channel without another `if signup is None: …` clause.

The model from §1 fixes this in passing: one indexed lookup on
`signup_email_dispatches.message_id` returns `(signup, channel)`
in a single round-trip. Webhook handler shrinks to ~30 lines.

A separate concern: the webhook is **the only writer** that
moves status from `sent` to `bounced` / `complaint`, and there's
no `WHERE status = 'sent'` guard. If a webhook fires for a row
that was retired to `not_applicable` after the email already
went out (the case the Phase 3 review flagged), we'd still flip
to bounced. Not a security issue but a correctness one — the
status semantically becomes `bounced-but-also-was-retired`.

Should be:

```python
.update({status_col: "bounced"}, ...)
.where(channel_status == "sent")  # only flip from a known-sent state
```

**Effort:** 1h alongside §1. **Reward:** webhook complexity drops,
no asymmetry, third channel is free.

---

## 4. Reapers are inconsistently organised

Today:

- `reap_partial_sends` lives in `services/email_lifecycle.py`
  (operates on both channels).
- `reap_expired` lives in `services/reminder_worker.py`
  (operates on the reminder channel only).
- Toggle-off cleanup (`_retire_disabled_channels`) lives in
  `routers/events.py` because it reuses the events session.

All three are conceptually the same operation: "scan rows, flip
status conditionally, maybe wipe ciphertext". They're spread
across three files because they were added at different phases.

### Proposal

Pull all three into `services/email_lifecycle.py` as a
**three-method `Reaper` interface**:

```python
class EmailReaper:
    def reap_partial_sends(self, db) -> int: ...
    def reap_expired_windows(self, db) -> int: ...
    def retire_event_channels(
        self, db, *, event_id: str, channels: set[ChannelSpec]
    ) -> int: ...
```

The first two are scheduled jobs; the third is called from the
events router. They share the helper that does the conditional
status flip + ciphertext wipe — currently this logic is inline
in three different places (with subtle differences: only
`reap_partial_sends` stamps `*_sent_at`).

**Effort:** ~3h. **Reward:** "where do I look for cleanup logic?"
has one answer.

---

## 5. Boot-time + scheduled-tick reapers are wrapped inconsistently

`backend/worker.py` calls `reap_partial_sends` and `reap_expired`
at boot, both wrapped in `try/except`. The same functions are
also scheduled as APScheduler jobs (hourly + daily). The
scheduled invocations are NOT wrapped — APScheduler itself
catches and logs uncaught job exceptions, but with a different
log shape (`apscheduler.executors.default` event) than the
boot-time version (`worker_boot_*_failed` event).

That means the same failure produces two different log signatures
depending on when it fires. Anyone setting up a Sentry alert
rule has to handle both.

### Proposal

The wrapper logic should live in the reaper module itself:

```python
def reap_partial_sends_safe() -> int:
    try:
        return reap_partial_sends_raw()
    except Exception:
        logger.exception("email_reap_partial_sends_failed")
        sentry_sdk.capture_exception()
        return 0
```

Then both boot-time and scheduled invocations get the same
behaviour with one log shape.

**Effort:** 30min. **Reward:** consistent observability.

---

## 6. Templates: the locale split is half-baked

`templates/{nl,en}/{template}.html` works for two languages and
two templates, but:

- Adding a third locale means duplicating every template.
- Adding a third template means writing it in every locale or
  hoping no one notices the missing-locale crash.
- Subjects are pulled out of the template via
  `{% set subject = "..." %}` — convenient, but means the
  subject can't reuse the template's other context vars without
  jinja juggling.
- The reminder template subject contains an em-dash; the feedback
  template doesn't. Stylistic drift across templates is invisible.

### Proposal

A small `TemplateRegistry` with one declaration per
(template, locale) pair, plus a CI check that every template has
every locale, plus typed context (so a template that expects
`event_name` fails at render-time if someone passes
`evt_name`).

**Effort:** ~3h. **Reward:** confident multi-locale rollouts.
Lower priority — only matters if we add a third locale or
template.

---

## 7. Test infrastructure has duplication that mirrors source duplication

The two worker test files (`test_feedback_worker.py`,
`test_reminder_worker.py`) are 90% the same shape. Many tests
exist in both. Same with the toggle-off tests across channels.

If §1's `EmailChannel` abstraction lands, the test suite
collapses too: parametrise over `CHANNELS`, run the same
test body for each. Dropping ~200 lines of test duplication.

The `_worker_helpers.make_event` / `make_signup` are decent but
have grown organically. Worth a once-over to align field
defaults with what the API would produce — there are subtle
gaps (e.g. `make_event` defaults to `questionnaire_enabled=True`
+ `reminder_enabled=True`, the API defaults are different).

**Effort:** ~2h after §1. **Reward:** the test suite shrinks
in lockstep with the source.

---

## 8. The deploy story has a load-bearing convention

`Dockerfile` bakes `DISABLE_SCHEDULER=1`. The worker overrides
it. **Anyone copying the API service config in Coolify and
forgetting to clear the env var gets a worker that does
nothing** (the defence-in-depth in `worker.py` catches it, but
only because we check explicitly). The whole "API container
must not run the scheduler" property is enforced by env-var
convention, not by code.

### Proposal

Two thin entrypoints, no env coupling:

```python
# backend/api.py
from .main import app  # FastAPI app, no scheduler ever
```
```python
# backend/worker.py
def main(): ...  # scheduler, no FastAPI ever
```

`Dockerfile` CMD points at the API; the worker container's CMD
points at `python -m backend.worker`. **`DISABLE_SCHEDULER`
disappears entirely** because the scheduler code only exists in
`worker.py`.

Today, `backend/main.py` *both* defines the FastAPI app *and*
imports / wires the scheduler (gated on `DISABLE_SCHEDULER`).
That's a structural smell — the API binary shouldn't even know
APScheduler exists.

**Effort:** ~2h. **Reward:** one fewer footgun, one fewer env
var to document, the API container's import graph shrinks.

---

## 9. `services/email/__init__.py` is doing too much

It's the email-package public API + the singleton backend
factory + the executor singleton + the message-id minter + the
batch-size config + the retry helper + the metric emitter. ~220
lines covering five distinct concerns.

Split into:

- `services/email/sender.py` — `send_email`, `send_email_sync`,
  `send_with_retry`.
- `services/email/backends.py` — `EmailBackend` protocol,
  `get_backend`, `_executor` plumbing.
- `services/email/identifiers.py` — `new_message_id`,
  `_message_id_domain`.
- `services/email/config.py` — `email_batch_size`,
  `_retry_sleep_seconds`, `get_from_address`.
- `services/email/observability.py` — `emit_metric`.

Single responsibility per file; the public API stays the same
because `__init__.py` re-exports.

**Effort:** ~1h. **Reward:** cosmetic but the file's import
graph stops being mysterious.

---

## 10. `_retire_disabled_channels` lives in the wrong place

It's defined in `backend/routers/events.py` because that's where
the toggle-off path runs. But it's a domain-logic function, not
HTTP-routing logic — `routers/` should be thin adapters over
service code. It's testable today (the suite mounts it directly),
but the router file gets imported every time you touch any event
endpoint, dragging the email lifecycle along for the ride.

Move to `services/email_lifecycle.py` (or §4's `EmailReaper`).
The router calls into it; tests call into it. `routers/events.py`
shrinks by 30 lines.

**Effort:** 15min. **Reward:** layering.

---

## Suggested priority

| Item | Effort | Maintenance reward | Priority |
|------|--------|-------------------|----------|
| 1. EmailChannel abstraction + dispatches table | 1d | **Very high** — biggest win | **Do first** |
| 2. Status as enum + state machine | 2h | High — type-safety | Do with #1 |
| 3. Webhook lookup over dispatches table | 1h | High — falls out of #1 | Do with #1 |
| 4. Unified reaper interface | 3h | High — single place for cleanup | Do with #1 |
| 8. Decouple worker.py from main.py | 2h | High — structural | Standalone |
| 5. Consistent reaper wrapper | 30m | Medium — observability | Anytime |
| 9. Split email/__init__.py | 1h | Low — cosmetic | Anytime |
| 10. Move retire helper to services | 15m | Low — layering | Anytime |
| 6. Locale + template registry | 3h | Low today, high if multi-locale | Defer |
| 7. Test parametrisation | 2h | Falls out of #1 | After #1 |

The "do first" cluster (1 + 2 + 3 + 4) is one ~1.5-day refactor.
After it, every reviewer-flagged class of bug from the last week
becomes structurally impossible. The other items are
quality-of-life that won't change behaviour but will make the
code easier to live with.

## What I'd skip

- **Async workers (FastAPI background tasks, Celery, etc.)** —
  current scale doesn't justify it. APScheduler with one worker
  process is correct for a one-VPS deploy. Revisit if we ever
  push >100 events/day.
- **Per-event quotas / rate limiting on outbound** — Phase 4.1's
  batch limit is enough until we hit Scaleway's per-minute caps.
- **Postgres-side transactional locking (`SELECT … FOR UPDATE
  SKIP LOCKED`)** — the conditional-claim pattern is correct on
  SQLite and Postgres, no need for an additional lock primitive
  unless we genuinely need horizontal worker scaling.

These are tempting but premature. The structural items above
buy more.
