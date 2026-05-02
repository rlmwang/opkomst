# Architecture principles

Distilled from the codebase as it stands at the end of R7. Each
principle has a one-line statement, a *why*, and a pointer to
where in the tree it's load-bearing.

## 1. Privacy by lifecycle, not by policy

The encrypted recipient address lives on the row that does the
work. The same ``UPDATE`` that finalises the row (sent / failed)
nulls the ciphertext; the reaper that ``DELETE``s a row takes the
ciphertext with it. There is no separate wipe pass, no scheduled
"scrub" job, no cross-table existence check.

*Why:* a lifecycle-coupled invariant can't drift out of sync with
itself. A policy ("we wipe addresses every Sunday") can.

*Where:* ``backend/models/email_dispatch.py``,
``backend/services/mail_lifecycle.py::_finalise``,
``backend/services/mail_lifecycle.py::reap_*``.

## 2. Decouple subsystems through the shared entity, not through cross-references

The signup record carries survey answers. The dispatch record
carries email work. Both hang off ``Event``. Neither references
the other. Two independent graphs share an event but the
question "which signup got which email" cannot be answered from
the schema.

*Why:* a structural decoupling enforces a privacy invariant the
typed code can't violate. Adding a column that bridges them is
the one PR that has to be reviewed; the rest of the codebase
can't re-introduce the link by accident.

*Where:* ``backend/models/email_dispatch.py`` (no ``signup_id``
column, by design), ``backend/models/feedback.py``
(``FeedbackResponse`` has ``submission_id``, never ``signup_id``).

## 3. Tables for parametric variation, not branches

When the same shape repeats with per-instance knobs, the knobs
go in a table. Adding a third instance is one row, not three
``elif`` branches scattered across half a dozen helpers.

*Why:* branching grows quadratically in the number of helpers
that have to know about every case. A table grows linearly.

*Where:* ``backend/services/mail_lifecycle.py::CHANNELS`` —
``REMINDER`` and ``FEEDBACK`` share one ``run_once(channel)``;
each channel pins a template, a toggle column on ``Event``,
a window predicate, and a context builder. The lone surviving
branch (mint a ``FeedbackToken`` for FEEDBACK) is the right
shape because exactly one channel needs it.

## 4. Constants in code for app-level fixed config

Things that are the same in every install and change at the same
cadence as the source code live in the source code. No DB table,
no seed step, no Alembic migration to backfill content.

*Why:* a DB table for fixed values is just source code that needs
a migration to edit. The seed step that keeps it in sync is a
foot-gun on first deploy, on test boot, and after every restore.

*Where:* ``backend/services/feedback_questions.py`` — the five
questions are a frozen ``QUESTIONS`` tuple. ``FeedbackResponse``
references questions by stable string key, not by FK. Adding a
question: append to the tuple + add i18n strings, ship.

## 5. Primitives across commit boundaries

Functions that span ``db.commit()`` calls take primitives, not
ORM rows. SQLAlchemy expires attribute access on every commit;
passing the live row across commits leaves a foot-gun where the
next attribute read either re-fetches a row that's been deleted
under us or silently observes stale state.

*Why:* the foot-gun is silent in tests (which usually run one
transaction) and intermittent in production (where parallel
workers race). Eliminate it structurally.

*Where:* ``backend/services/mail_lifecycle.py::_process_one``
takes ``dispatch_id: str + ciphertext: bytes``, not
``dispatch: EmailDispatch``.

## 6. Atomic claim via conditional UPDATE, not application locks

Multiple workers race-safely claim work with a single
``UPDATE ... SET message_id = ? WHERE id = ? AND status = 'pending'
AND message_id IS NULL`` followed by reading the affected-rows
count. One worker wins; losers see ``rowcount = 0`` and bail.

*Why:* zero infrastructure (no Redis lock, no advisory lock, no
``SELECT ... FOR UPDATE``). The DB already has the primitive.

*Where:* ``backend/services/mail_lifecycle.py::_process_one``
"Step 1 — atomic claim".

## 7. Soft-delete via partial-unique index, not via tombstone tables

A ``deleted_at`` column plus a partial-unique index on the
identity column over ``deleted_at IS NULL``. Re-registering a
soft-deleted email restores the original row with its original
``entity_id`` — JWTs, audit log references, and any FK that
pointed at the old id keep working without backfill.

*Why:* the alternative (move-to-archive-table) doubles the schema
and breaks every FK on the way out. Soft-delete with a partial
index is a one-row schema change.

*Where:* ``backend/models/users.py::User`` (``uq_users_email_live``),
``backend/models/chapters.py::Chapter``.

## 8. Routers thin, services pure-ish

Routers do auth, input validation, and a small combine.
Everything else — SQL queries, derived aggregates, side effects
— lives in a service module that takes ``db, ...`` and returns
DTOs. A handler that exceeds ~30 lines is a smell.

*Why:* services are unit-testable without a router fixture or
HTTP client. The router becomes a contract, not a workshop.

*Where:* ``backend/services/feedback_stats.py`` (extracted
April 2026); ``backend/services/access.py``;
``backend/routers/admin.py::_apply_user_change``.

## 9. Fresh autogenerate, no data-migration tricks

Pre-launch, the migration story is ``DROP SCHEMA public CASCADE
&& alembic upgrade head``. We never accumulate transitional
defaults, backfills, or "remove this in v2" markers in the
migration tree.

*Why:* every transitional default is a future hidden coupling.
Pre-launch we have the freedom to keep migrations clean; we
should use it.

*Where:* CLAUDE.md rule #1; ``backend/alembic/versions/`` holds
the initial autogenerate plus a couple of clean schema-only
follow-ups (drop a table, drop a model). Every other iteration
that touched the schema was folded back into the initial
autogenerate rather than chained as a data migration.

## 10. Crash recovery via reapers, not transactions

Mid-send work isn't wrapped in a single transaction. The worker
pre-mints a ``message_id``, commits, then talks to SMTP. A crash
between the commit and the SMTP response leaves the row in
``status=pending, message_id=set`` — recoverable by a daily
reaper that flips long-stuck pending rows to ``failed``.

*Why:* SMTP doesn't roll back. A "send and commit" transaction
that the SMTP call sits inside is a fiction; the boundary is
real, and the recovery has to be an explicit reaper sweep.

*Where:* ``backend/services/mail_lifecycle.py::reap_partial_sends``,
``::reap_expired``.

## 11. 404 over 403 for cross-tenant scope

A user looking at a resource that belongs to a chapter they don't
have access to gets a 404, not a 403. The existence of the
resource isn't leaked through the difference between "not found"
and "not allowed".

*Why:* 403 is a side-channel. 404 is the same response shape the
user gets for a typo'd id, so the two cases are indistinguishable
to the client.

*Where:* ``backend/services/access.py::get_event_for_user``.

## 12. Process-boot side effects in one module

Sentry init, migration runs, anything else that has to happen
before the FastAPI app is constructed lives in
``backend/bootstrap.py``. ``backend/main.py`` is pure app
construction (FastAPI, middleware, router registration).

*Why:* ``main.py`` is the file every refactor is tempted to add
to. A clean separation gives the next contributor a bright line
between "process bring-up" and "request routing".

*Where:* ``backend/bootstrap.py``, ``backend/main.py``,
``backend/cli.py`` (cron entry-points share the bring-up).

## 13. Cron entry-points are one-shot subcommands of the same image

Coolify's scheduled tasks invoke ``python -m backend.cli <verb>``
on the same container image. Each invocation does one sweep and
exits; non-zero exit becomes a Coolify alert. No long-running
scheduler container, no separate cron image.

*Why:* one image, one deploy, one set of dependencies. The cron
inherits every fix that lands in the API.

*Where:* ``backend/cli.py``, ``docs/deploy.md``.

## 14. Logs carry events + ids, never PII

Every action logs a structured event with ``actor_id``,
``target_id``, and a small ``log_extras`` map. Email addresses,
names, and free-text content never enter the log line. The
mail-send hop is the only place a recipient address ever appears
in code, and it doesn't get logged there either.

*Why:* logs leak. Privacy invariants that depend on "remember not
to log this" don't survive a year of contributors.

*Where:* every router module's ``logger.info`` calls;
``tests/test_privacy.py::test_decrypt_only_called_from_mail_lifecycle``
(static greppable allowlist of decrypt callers).

## 15. No try/except as a bandaid

The only legitimate ``except`` is at a real boundary: SMTP
failure, network call, encryption decode, optional disk-free
probe. Internal code propagates. A bare ``except Exception``
that flips state to a "safe" default and continues is a bug
report waiting to happen.

*Why:* swallowed exceptions hide real bugs. The "best effort"
disk-free check in ``/health`` is the carefully-scoped
exception that proves the rule.

*Where:* CLAUDE.md guardrail; the few legitimate exceptions are
in ``backend/services/mail_lifecycle.py`` (decrypt, SMTP) and
``backend/routers/health.py`` (disk-free).

## 16. Pre-launch mindset: clean break over compatibility

When code shape is wrong, change the shape. Don't add a
parameter ``legacy_mode=False``, don't keep the old field with
``# TODO remove in v2``, don't write a fallback for "callers that
haven't been updated yet". There aren't any; we're pre-launch.

*Why:* every transitional shim is interest payable forever. The
code shape converges on the destination only when nobody is
defending intermediate versions.

*Where:* CLAUDE.md rule #1; the seven R1–R7 commit prefixes in
``git log`` are the chronicle of clean breaks.

## Reflection

The codebase as it stands honours every principle above without
visible exception in the audit-able surface. The places where the
list reads as aspirational are the places I'd flag a future
contributor:

- **Principle 5 (primitives across commits)** is the youngest
  rule and the one most likely to regress. Currently only
  ``_process_one`` enforces it. A new long-running worker that
  spans commits would need to be told. A pyright lint rule
  ("no ORM row across a ``db.commit()`` boundary") would close
  the gap structurally; today the rule lives in code review.

- **Principle 8 (routers thin)** holds at the
  feedback / admin / auth layer but ``backend/routers/events.py``
  is 449 lines and still hosts the bulk of event-side query
  logic inline. It's the next router due for the
  ``services/feedback_stats``-style split when it grows further.

- **Principle 12 (boot in one module)** is a fresh split — the
  ``cli.py`` cron init still has its own small Sentry call
  because it deliberately omits the FastAPI integrations. It's
  not duplicated logic, it's a different setup; calling that
  out here so a future "DRY this up" PR doesn't mistakenly
  collapse them.

- **Principle 14 (no PII in logs)** is statically checked.
  ``test_logger_pii_kwargs_allowlist`` greps the backend for
  ``logger.<level>(... to=|email=|recipient=)`` and pins the
  allowlist to ``services/mail.py`` (the email-send hop) and
  ``seed.py`` (local-mode demo bootstrap). A new caller
  passing a recipient address through a log kwarg fails CI;
  growing the allowlist is a deliberate code-review event.

What's notably absent — and the codebase is better for it — is
any layer of "frameworky" infrastructure: no service container,
no event bus, no repository pattern, no DTO mapper layer.
Routers call services, services call SQLAlchemy. The single
indirection that does exist (``CHANNELS`` table for the
worker) is justified by the alternative (``elif`` chains) being
strictly worse.
