# Personal accounts

The root of the site is an app in its own right. Somebody with no
organisation behind them fills in one form, gives an address, and has a
working public link plus an account to manage it from.

## What one is

A tenant with exactly one person in it. Not a special case beside
tenants: a kind of tenant, so every rule already written (a row belongs
to one tenant, reads are scoped to it, writes bind it) applies with no
second code path.

| | organisation | personal |
|---|---|---|
| URL | `/{slug}/event` | `/event` |
| brand | `brands/{slug}/` | the house brand |
| people | many, admin-approved | exactly one |
| chapters | yes | no |
| admin pages | yes | no |
| plan | paid | free until lifted |
| public pages | identical | identical |

A personal account's slug is a generated id that never appears in a
URL. `Tenant.brand_slug` is what any page or mail asks for the folder it
wears, so nothing assumes a slug names a brand folder.

## Starting without an account

The landing page is four tiles and a sign-in form, not a wall. A tile
opens the create form itself, with one extra field pinned above it: the
organiser's address. Submitting it creates the account, creates the
thing, and returns the public link, all in one request.

The address is unproven, deliberately. Proving it is what the mail
does, and the only thing an unproven address buys is a row in an inbox
you cannot read. The mail that follows names what was made and carries
the sign-in link.

## Ceilings

The root hands an account to anyone who types an address, so a personal
account is bounded: how many live things it may hold, how many people
may sign up to one of them, and how much mail it may cause in a day.
Every refusal names the limit and how to make room. The rules are in
`services/limits.py`; an organisation has none of them, because an
operator put it in `TENANTS` on purpose.
