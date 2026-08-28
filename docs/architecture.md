# Architecture

How the app is wired today. Keep it in step with the code.

## Stack

FastAPI on Python 3.13 with SQLAlchemy 2.0 and Alembic, Postgres
everywhere. Vue 3 with TypeScript, Vite and PrimeVue 4 on the front,
with types generated from the OpenAPI schema. Mail is Jinja templates
per locale over a pluggable backend. Address autocomplete comes from
PDOK.

Sign-in is a magic link. There are no passwords: an email carries a
single-use token, redeeming it mints a JWT.

## What it makes

Six things, all built the same way: an organiser owns one, it has a
short public link, and the people who use that link never make an
account.

| | |
|---|---|
| Event | sign-ups, optionally recurring (`docs/design-recurring-events.md`) |
| Questionnaire | questions and answers |
| Quiz | a questionnaire with an answer key (`docs/design-quizzes.md`) |
| Kompas | a questionnaire that places you on a map (`docs/design-kompas.md`) |
| Date poll | pick a date with a group (`docs/design-datepolls.md`) |
| Chore roster | recurring turns, fairly shared (`docs/design-chores.md`) |

The last three products live in the `forms` table, told apart by
`mode`. The others have their own tables.

## Tenants

Two kinds, one shape. An **organisation** is named in the `TENANTS`
environment variable with a brand folder committed for it; it has
chapters, members and an admin surface, and its app lives at
`/{slug}/…`. A **personal** account is one person who typed an address
at the root; it has no chapters, no admin pages, and ceilings on how
much it may hold.

Every table carries `tenant_id`, denormalised onto child rows on
purpose so a query cannot forget it. Writes never name it: the column
defaults to the tenant bound to the request, and a write with nothing
bound is an error rather than a guess. Public URLs carry no tenant at
all; the entity behind the slug decides which one the request is in.

## Privacy

The contract is the product, so it is enforced in several places at
once:

* An attendee's address is optional, encrypted at rest, used for the
  mail the organiser switched on, and then deleted. The invariant
  (`encrypted_email IS NULL` if and only if no pending dispatch points
  at the row) has a property test and a table test behind it.
* Only the mail worker may decrypt. A static check greps the tree for
  anyone else calling it.
* Feedback answers carry no link back to the person who gave them.
* Logs carry a route name and an outcome. The one place an address
  appears is the line that sends mail.
* No third-party scripts on an organisation's pages, ever.

## Mail

Everything goes through `services/mail.py`: render, send, retry,
metrics, and the backends. `services/mail_lifecycle.py` owns the
channels (reminder, feedback, chore reminder), each of which is a
window predicate, a template and a context builder.

Sending mail to participants is the paid plan
(`docs/design-paywall.md`). Sign-in links and "here is what you made"
are never gated.

## Cron

One-shot subcommands of the same image, invoked by the host's
scheduler: dispatch a channel, run the reapers, tick the rosters and
the event horizon, reap the auth tokens. No scheduler process.

## Layout

```
backend/
  routers/     one file per resource, thin
  services/    the logic worth testing
  models/      one file per domain
  schemas/     the DTOs that generate openapi.json
  alembic/     migrations
frontend/src/
  pages/       one page per route
  composables/ Vue Query, one per domain
  public*/     the mini-apps behind the public links, no bundle shared
brands/{slug}/ palette, logo, icons, per organisation
tests/         see docs/runbook.md for what each file proves
```

The public pages are their own small bundles rather than routes in the
app, because a visitor who opens one link should not download an
organiser's tool to read it.
