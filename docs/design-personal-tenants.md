# Design: personal accounts (tenant-less pages)

Status: built. Gives `opkomst.nu` itself a front door. Someone with
no organisation behind them fills in one form, gives an address, and has
a working event and a working app: their own events, forms, datepolls
and chore rosters, and nothing else. No admin pages, no WhatsApp, no
chapters, nobody to invite, and no sign-up step before the first useful
thing they make.

Before this, the root 404'd and every organiser URL was `/{tenant}/…`,
which answers "which organisation?" before anything else can happen. A
person who just wants to run one event has no answer to that question,
and shouldn't have to have one.

## What a personal account is

**A tenant with exactly one person in it.** Not a special case beside
tenants — a kind of tenant, so every rule already written (a row belongs
to one tenant, reads are scoped to it, writes bind it, the flush guard
refuses to cross it) applies without a second code path.

```python
class Tenant(...):
    kind: Mapped[Literal["organisation", "personal"]]
```

| | organisation | personal |
| --- | --- | --- |
| URL | `/{slug}/events` | `/events` |
| brand | `brands/{slug}/` | the house brand |
| people | many, admin-approved | exactly one, self-approved |
| chapters | yes | no |
| admin pages | yes | no |
| WhatsApp blast | admin-only | no |
| public pages | `/e/{slug}` etc. | identical |

The slug still exists and is still unique — it names the row, and the
CLI-created organisations keep using it in URLs — but a personal
tenant's slug never appears in a URL. It is an 8-char nanoid, same
generator as event slugs, so it can't collide with an organisation name
someone might want later.

## URLs

The root *is* the app for personal accounts:

| | |
| --- | --- |
| `/login`, `/auth/redeem` | the tenant-less door |
| `/events`, `/forms`, `/datepolls`, `/chores` | the four workspaces |
| `/events/new` etc. | the create forms, signed in or not |
| `/` | the landing page: 4 tiles, sign-in under them |
| `/rsp/…` | unchanged — an organisation's app |
| `/e/…`, `/f/…`, `/d/…`, `/c/…` | unchanged — public, no tenant in the URL |

`spa.py`'s fallback becomes: first segment is a live organisation slug →
that organisation's app; otherwise → the personal app in the house
brand. The 404 case disappears, and with it the awkward "the bare root
doesn't exist" answer.

That makes the app's own top-level paths and the organisation slugs one
namespace, so slugs must not shadow routes. `services/slug.py` already
holds the reserved set for chapter slugs (the agenda lives at
`/{tenant}/{chapter}`); it grows the rest of the root's vocabulary —
`api`, `health`, `brand`, `assets`, `e`, `f`, `d`, `c`, `me` — and the
`TENANTS` reconcile refuses a reserved slug, so a name in the env can't
shadow a page.

**The session key** follows the app, not the brand: `token:{slug}` for
an organisation, `token:personal` at the root. Signing in to your own
account and to RSP in two tabs stays possible, and neither leaks into
the other's URLs (the bug the per-tenant key already fixed once).

## The landing page

`/` is a door with four handles, not a sign-in wall. The signed-out root
shows the same four tiles the signed-in app shows, in a 2x2 grid. The
sign-in form sits below them, past a rule and a word that says it is the
other way in:

```
        ┌───────────┬───────────┐
        │  Events   │   Forms   │
        ├───────────┼───────────┤
        │ Datepolls │  Chores   │
        └───────────┴───────────┘


        ───────  or sign in  ───────

            email  [ send link ]
```

The gap is the design. The tiles are the offer; sign-in is for the
people who have already taken it, and a form pressed up against four
buttons reads as a step in them ("pick one, then identify yourself")
rather than as the alternative to them. So: roughly triple the tile
grid's own gap above the divider, the divider labelled, and the form
narrower than the grid, so nothing about it looks like a fifth tile.

A tile is not "learn more". It opens that thing's create form, the same
`EventFormPage` a signed-in organiser gets, with one extra field pinned
above the rest: **the organiser's email address**, required. Everything
below it is the form that already exists, minus the chapter picker (a
personal tenant has none).

The order matters. The visitor came to make an event, so the app asks
about the event; the address is the last thing standing between the
finished form and a working public link, not the first thing standing
between them and the form.

`/{tenant}/` is untouched: an organisation's signed-out root is still
its public `TenantIndexPage`. Organisations have members, and members
sign in.

## Starting without an account

Submitting that form creates the thing. No confirmation step in front of
it, no draft state behind it, and the response carries the public URL
(`/e/{slug}`) so the visitor can share it before they have read the mail.

`POST /api/v1/start/events` (and `/forms`, `/datepolls`, `/chores`)
takes `{email, ...the same *Create body the organiser endpoint takes}`
and does three things in one transaction:

1. **Resolve the account.** A live personal user with that address owns
   the write. Otherwise a personal tenant and its one user are created
   right there: `kind="personal"`, `role="organiser"`,
   `is_approved=True`, name = the address.
2. **Bind and write.** `tenancy.bind(tenant.id, ...)`, then the same
   service call the organiser route makes. One create path per entity,
   reached by two doors.
3. **Mail the link.** A single-use `LoginToken` for that user, in the
   house brand, saying what was created and linking to it.

So the entity's owner is decided by an address nobody has proved they
control yet, and that is deliberate: proving it is what the mail does,
and the only thing an unproven address buys you is a row in an inbox you
cannot read. What it costs is that a stranger who types someone else's
address can add an event to their account. The mail names the event and
the account it landed in, which makes that visible on arrival rather
than discoverable later, and `Limits.PUBLIC_WRITE` keeps it from being
done in bulk. Nothing else in the account is readable, writable, or
enumerable from the start form.

## Signing up, which is now just signing in

For a personal account, an address *is* the account, so there is no
registration step to complete. `POST /auth/login-link` with `tenant:
null` resolves the address the same way the start form does, creating
the personal tenant and user if it is new, and always sends a
`LoginToken`. Same 200 either way, so the endpoint still cannot be
probed, and now it also hides which addresses have personal accounts.

That deletes a flow rather than adding one: `RegistrationToken`,
`/register/complete` and the name prompt stay where they belong, in an
organisation's door, where a human reads your name in a user list and an
admin decides whether you are in. At the root there is nobody to tell
apart and nobody to approve you, because the tenant is you.

## What a personal account cannot do

Three layers, in the order a request meets them:

- **Not offered.** The nav drops the admin and WhatsApp entries; the
  landing page shows four tiles and no admin tile; the entity forms drop
  the chapter picker.
- **Refused by the matrix.** `permissions.can` gains one rule ahead of
  the role checks: every `Action` in the user/chapter families is denied
  outright when the actor's tenant is personal. `tests/test_permissions.py`
  is a table test, so this is one column, not a scatter of `if`s.
- **Refused by the route.** `/api/v1/admin/*`, `/api/v1/chapters*` and
  the WhatsApp proxy 404 for a personal actor — 404, not 403, so the
  surface doesn't advertise what other tenants have.

Entity writes reject a `chapter_id` from a personal tenant (422): a
chapter of another organisation is not assignable, and their own tenant
has none.

## Chapter scoping, which is now conditional

This is the one existing rule that breaks. `access.scope_filter` reads
"rows whose `chapter_id` is in the user's live chapter set", and a user
with no memberships matches nothing — correct for an organisation,
fatal for a personal tenant, where everything has `chapter_id IS NULL`.

The rule becomes: **the tenant is always the boundary; the chapter set
narrows it only for organisations.**

```python
def scope_filter(db, user, model):
    same_tenant = model.tenant_id == user.tenant_id
    if is_personal(db, user):
        return same_tenant     # the tenant predicate is the whole scope
    ids = chapter_ids_for_user(db, user)
    return and_(same_tenant, model.chapter_id.in_(ids)) if ids else false()
```

The tenant predicate is inside the filter rather than left to each
caller, so a personal account's missing chapter set never widens into
everybody's rows. The same goes for the one read that reaches through a
chapter id instead of a scope filter: the public agenda joins on the
chapter *and* its tenant, because `chapter_id` is a bare FK and a row
in another tenant carrying that id would otherwise be published on an
organisation's page.

## Emails

Personal accounts wear the house brand: `mail_from_name` and the logo
block come from `brands/opkomst/`, which has no image, so the mail
renders its wordmark. Everything else — the reminder and feedback
channels, the wipe rule, the disclosure copy — is unchanged, because
none of it ever knew about organisations.

## What changes, by file

- `backend/models/tenants.py` — `kind`, plus the two properties every
  caller asks instead of reading it: `is_personal` and `brand_slug`.
- `backend/alembic/versions/…` — add `kind`, existing tenant is
  `organisation`.
- `backend/services/tenants.py` — `resolve_personal(email)`, the one
  resolve-or-create both doors use; `sync_from_env` refuses a reserved
  slug and the house brand.
- `backend/services/tenancy.py` — the binding carries the brand.
- `backend/services/limits.py` — the ceilings, each one question about
  `tenant.is_personal`.
- `backend/services/entities.py` — one create path per kind, reached by
  the organiser route and the start endpoint both.
- `backend/services/mail.py` — the worker thread inherits the caller's
  context, so a mail wears its own account's brand; the From name comes
  from that brand too.
- `backend/services/admin_digest.py` — per organisation, so no admin
  reads another's pending list.
- `backend/services/agenda.py`, `backend/routers/chapters.py` — the
  tenant predicate alongside `chapter_id`.
- `backend/services/slug.py` — the reserved set + `personal_slug()`.
- `backend/routers/auth.py` — `tenant: str | None`; the root branch of
  login-link resolves-or-creates and always mints a `LoginToken`.
- `backend/routers/start.py` — the four `POST /api/v1/start/{kind}`
  routes: resolve the account, bind, refuse a `chapter_id`, create,
  mail the link in the language the form was filled in.
- `backend/schemas/auth.py` — `tenant` optional; `UserOut.tenant_kind`
  so the frontend can hide what doesn't exist.
- `backend/schemas/start.py` — the four `Start*` bodies: the existing
  `*Create` plus a `LowercaseEmail`.
- `backend/services/mail_templates/{nl,en}/started.html` — what was
  created, where it lives, and the sign-in link.
- `backend/permissions.py` — the personal-tenant denial rule.
- `backend/routers/admin.py`, `chapters.py`, `whatsapp.py` — 404 for
  personal actors.
- `backend/services/access.py` — the conditional chapter scope.
- `backend/routers/spa.py` — root serves the personal app, no 404.
- `frontend/src/lib/branding.ts` — `app_base` already carries `/`;
  `isPersonalApp()` reads it.
- `frontend/src/api/client.ts` — `token:personal` at the root.
- `frontend/src/composables/useStartMode.ts` — what the four create
  pages share: the flags, the address, the POST, the refusals in words
  the visitor can act on, the chapter rule and where cancel goes.
- `frontend/src/composables/useFormDraft.ts` — drafts scoped per app
  and dropped on sign-out.
- `frontend/src/components/{StartAccountField,StartedPanel}.vue` — the
  one extra field, and the link that already works.
- `frontend/src/components/AppHeader.vue` — hide what a personal
  account doesn't have.
- `frontend/src/pages/HomePage.vue` — the root's signed-out face: the
  same four tiles, sign-in below, no admin tile.
- `frontend/src/pages/*FormPage.vue` — no chapter picker and no agenda
  toggle; signed out at the root, an email field on top and the start
  endpoint as the target.
- `frontend/src/public*/` — a full instance says so, rather than
  reporting a failure to submit.
- `frontend/vite.config.ts` — the dev server resolves the first segment
  as an organisation first, exactly as prod does, so the root's own
  deep paths get the app.
- `tests/test_personal_tenants.py` — the capability table, end to end.
- `tests/test_start_flow.py` — new address creates tenant + user +
  entity + link; known address writes into the existing account;
  neither response says which of the two happened.

## The brand a tenant wears

An organisation's slug names its folder under `brands/`, because an
operator committed it there. A personal tenant's slug is a generated id
with no folder behind it, so it wears the house brand. That is one
rule, `Tenant.brand_slug`, and everything that renders asks a tenant for
it rather than assuming a slug names a folder: the public shells, the
mail, and the tenancy binding, which carries the brand rather than the
slug because the brand is the only thing it was ever read for. The JWT
carries it too, so a request binds both data and brand from the token
with no query.

Getting this wrong is not cosmetic: reading `brands/{nanoid}/` raises,
which would 500 the public page the start flow exists to produce and
permanently fail the mail, since a failed dispatch nulls the address it
needed.

## Decisions

1. **The unproven address stands.** A start submission writes
   immediately, into an existing account if the address has one, and the
   mail is the disclosure. Holding rows behind a click would cost a
   pending state on four entity types, a reaper, and a public link that
   doesn't work yet.
2. **Nobody makes an organisation from inside the app.** A personal
   account never grows into one and there is no upgrade path in the
   product: organisations exist because `TENANTS` names them and a brand
   folder is committed, which is an operator decision. A personal
   account that needs to become one is handled by hand, outside the app.
3. **Every email says which account it belongs to** — see below. No
   mail ever mentions an organisation the reader's account isn't in.
4. **Four limits, and every one of them is a property of a personal
   tenant.** An organisation is here because an operator put it in
   `TENANTS` and committed its brand; it is trusted, and none of these
   ceilings apply to it. They exist because the root page hands an
   account to anyone who types an address.
   - the start endpoints carry the existing `@limiter` treatment, so one
     caller can't mint accounts or entities in bulk;
   - a personal tenant has a ceiling on **active** entities per kind
     (archived ones don't count — archiving is how you make room);
   - a personal tenant has a daily ceiling on the mail its entities
     generate, since every event with an address on it costs sends. It
     counts sends, not queued rows, from both places mail leaves: the
     dispatch rows behind reminders and feedback, and the stamps behind
     chore reminders and volunteer welcomes. Over it, the worker leaves
     a dispatch pending and sends it once the rolling day has moved on,
     because there is no caller there to refuse. Transactional mail (a
     sign-in link, a "here is what you made") is outside it: one send
     per request, bounded by the rate limiter on the endpoint;
   - **an instance of a personal tenant takes at most 50 participants** —
     sign-ups on an event, fills on a form, submissions on a datepoll,
     volunteers on a roster. The 51st is refused on the public page with
     a plain "this is full", the same answer for every kind, and the
     organiser sees the count against the cap on the detail page. An
     organisation's event has no such ceiling.

   Every ceiling refuses with a message that names the limit and how to
   free room, never with a silent failure. Each one is a single check
   against `tenant.kind`, so an organisation never pays for the code
   that exists to bound a stranger.

## Emails say whose they are

The mail templates predate tenants and read as if one organisation
existed. That gets redone rather than patched:

- **Every mail wears its own tenant's brand** — logo, palette, wordmark
  and From name from `brands/{tenant}/`. A personal account's mail wears
  the house brand, which has no logo, so it renders its wordmark.
- **Every mail names the account it is about**, in the reader's own
  terms: the organisation's name for an organisation's mail, the address
  itself for a personal one. A reader who holds two accounts can tell
  which one a link opens before clicking it.
- **No mail references another tenant.** "This is your personal account,
  not RSP's" is exactly the shape to avoid: an organisation the reader's
  account has nothing to do with has no business in the message.
- **Plain, unambiguous copy.** What happened, what this link does, what
  to ignore. One subject line per purpose, no clever phrasing that reads
  differently depending on which account you thought you were using.

This applies to all of them — sign-in, registration, approval, the
pending digest, reminders, feedback, chore reminders, and the new
"here's what you just made" mail from the start form.
