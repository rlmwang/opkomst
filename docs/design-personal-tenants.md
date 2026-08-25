# Design: personal accounts (tenant-less pages)

Status: proposed. Gives `opkomst.nu` itself a front door. Someone with
no organisation behind them signs up with an email address, confirms a
link, and lands in a working app: their own events, forms, datepolls and
chore rosters, and nothing else. No admin pages, no WhatsApp, no
chapters, nobody to invite.

Today the root 404s and every organiser URL is `/{tenant}/…`, which
answers "which organisation?" before anything else can happen. A person
who just wants to run one event has no answer to that question, and
shouldn't have to have one.

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
| `/login`, `/register/complete`, `/auth/redeem` | the tenant-less door |
| `/events`, `/forms`, `/datepolls`, `/chores` | the four workspaces |
| `/` | the landing page (4 tiles, no admin tile) |
| `/rsp/…` | unchanged — an organisation's app |
| `/e/…`, `/f/…`, `/d/…`, `/c/…` | unchanged — public, no tenant in the URL |

`spa.py`'s fallback becomes: first segment is a live organisation slug →
that organisation's app; otherwise → the personal app in the house
brand. The 404 case disappears, and with it the awkward "the bare root
doesn't exist" answer.

That makes the app's own top-level paths and the organisation slugs one
namespace, so slugs must not shadow routes. `services/slug.py` grows a
reserved set — `events`, `forms`, `datepolls`, `chores`, `users`,
`chapters`, `login`, `register`, `auth`, `admin`, `api`, `health`,
`brand`, `assets`, `e`, `f`, `d`, `c`, `me` — refused by
`tenant-create` and asserted by a test that walks the router table, so
adding a route later can't silently break an existing organisation.

**The session key** follows the app, not the brand: `token:{slug}` for
an organisation, `token:personal` at the root. Signing in to your own
account and to RSP in two tabs stays possible, and neither leaks into
the other's URLs (the bug the per-tenant key already fixed once).

## Signing up

The existing magic-link door, minus the parts that only make sense with
an organisation behind them. `POST /auth/login-link` takes `tenant:
null` for the root app:

1. the address matches a live personal account → sign-in link;
2. it doesn't → registration link;
3. either way, the same 200 — the privacy contract is unchanged, and now
   also hides which addresses have personal accounts.

Redeeming a personal registration link creates the tenant and the user
in one transaction: `kind="personal"`, `role="organiser"`,
`is_approved=True`. Self-approval is not a carve-out in the approval
rule — there is nobody to approve you, because the tenant is you.

**No name step.** The account's name is the email address. The current
completion page exists only to ask for a name; for a personal account it
asks nothing and redeems on load. An organisation's flow keeps the name
prompt: there, other people read your name in a user list.

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
def scope_filter(db, user, column):
    if user.tenant.kind == "personal":
        return true()          # the tenant predicate is the whole scope
    ids = chapter_ids_for_user(db, user)
    return column.in_(ids) if ids else false()
```

`get_scoped` keeps its `tenant_id == user.tenant_id` predicate in both
branches, so a personal user's `true()` is scoped by the layer under it,
not by trust.

## Emails

Personal accounts wear the house brand: `mail_from_name` and the logo
block come from `brands/opkomst/`, which has no image, so the mail
renders its wordmark. Everything else — the reminder and feedback
channels, the wipe rule, the disclosure copy — is unchanged, because
none of it ever knew about organisations.

## What changes, by file

- `backend/models/tenants.py` — `kind`.
- `backend/alembic/versions/…` — add `kind`, existing tenant is
  `organisation`.
- `backend/services/tenants.py` — `create_personal(email)`; `create`
  refuses a reserved slug.
- `backend/services/slug.py` — the reserved set + `personal_slug()`.
- `backend/routers/auth.py` — `tenant: str | None`; the personal branch
  of complete-registration; no-name redemption.
- `backend/schemas/auth.py` — `tenant` optional; `UserOut.tenant_kind`
  so the frontend can hide what doesn't exist.
- `backend/permissions.py` — the personal-tenant denial rule.
- `backend/routers/admin.py`, `chapters.py`, `whatsapp.py` — 404 for
  personal actors.
- `backend/services/access.py` — the conditional chapter scope.
- `backend/routers/spa.py` — root serves the personal app, no 404.
- `frontend/src/lib/branding.ts` — `app_base` already carries `/`.
- `frontend/src/api/client.ts` — `token:personal` at the root.
- `frontend/src/components/AppHeader.vue`, `pages/HomePage.vue` — hide
  what a personal account doesn't have.
- `frontend/src/pages/*FormPage.vue` — no chapter picker.
- `frontend/vite.config.ts` — the dev server's root serves the app.
- `tests/test_personal_tenants.py` — the capability table, end to end.

## Steps

1. `kind` + migration + `create_personal` + reserved slugs.
2. The tenant-less door: root serving, sign-up, session key.
3. Conditional chapter scope + the permission denials + route 404s.
4. The frontend's missing pieces (nav, landing, forms).

## Open questions

1. **Upgrading.** A personal account that grows into an organisation —
   same rows, new kind and slug, first user becomes admin. Worth doing
   now, or when someone asks?
2. **Two accounts, one address.** Signing in at `/rsp/login` and at the
   root with the same address gives two separate accounts, by design.
   Should the root's sign-in email mention it ("this is your personal
   account, not RSP's"), or is that noise?
3. **Limits.** A personal tenant is free to create unlimited events and
   send unlimited reminder mail. Does that need a cap before the root
   page is public?
