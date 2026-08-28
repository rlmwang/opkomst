# Architecture principles

The rules the backend converges on. Each one exists because the
alternative was tried or was obviously worse.

**Privacy by lifecycle, not by policy.** An address is deleted because
the code that needed it has run, not because a retention job decided it
was old enough. The wipe rule is an invariant with a state machine and a
property test behind it.

**Subsystems meet at the entity, never at each other.** A dispatch row
knows its occurrence; it does not know which sign-up produced it. That
missing foreign key is what makes "which person got which mail"
unanswerable from the schema.

**Tables for parametric variation, branches for real differences.**
Three products share the `forms` table because they differ by what an
answer means, not by what a form is. Two axes are two rows, not four
columns.

**Constants in code, secrets in the environment.** Anything an operator
must set has no default and fails at boot. Anything the app decides for
itself is a constant with a comment, not a config knob nobody will ever
turn.

**No ORM row survives a commit.** Cross a commit boundary with the
primitives you need, then re-read. A detached instance that lazy-loads
after its session closed is a bug that only shows up under load.

**Atomic claim by conditional UPDATE.** The workers take work with
`UPDATE ... WHERE status = 'pending'` and act on the row count. No
application-level locks, so two workers racing is a no-op rather than a
double send.

**Soft-delete through a partial unique index.** `deleted_at IS NULL`
scopes the uniqueness, so deleting an account frees its email for a
fresh registration and restoring it brings everything back.

**Routers thin, services testable.** A router resolves, authorises and
returns. Anything worth asserting on lives in a service that takes a
session and plain values.

**One fresh migration, no data-migration tricks.** Pre-launch there is
no production data to preserve, so the schema is what the models say and
nothing carries a shim for a shape we abandoned.

**Crash recovery through reapers, not long transactions.** Every
multi-step process has a finalising sweep that can be run again safely.

**404, not 403, across a tenant boundary.** Telling somebody that a
resource exists but is not theirs is still telling them it exists.

**Boot side effects in one module.** Migrations, tenant reconcile and
Sentry init happen in one place, so a second entry point cannot half-do
them.

**Cron is one-shot subcommands of the same image.** No scheduler
container, no second deployment artefact. The schedule lives with the
host.

**Logs carry events and ids, never PII.** Statically checked: a grep
over the backend pins which modules may log a recipient address.

**No try/except as a bandaid.** If a call can fail in a way worth
handling, handle that failure. Swallowing an exception to make a test
pass hides the thing the test was for.
