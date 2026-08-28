# Tenants and branding

Which organisations exist is deployment configuration. `TENANTS` is the
source of truth (`rsp:RSP,rood:ROOD`), reconciled into the table on
every boot: new slugs are created, renamed ones renamed, and a slug
that disappears is soft-deleted, which stops its URLs serving and
leaves every row where it is.

There is no UI for this and no platform-admin role. Nobody signs in to
"the platform", only to a tenant.

## One slug, three jobs

A slug is the organisation's URL prefix (`/rsp/events`), the name of its
brand folder (`brands/rsp/`) and the key its session is stored under.
One name for one thing, so a tenant whose brand folder is missing stops
the boot rather than serving pages with no palette.

## The brand folder

Everything visual an organisation owns lives in `brands/{slug}/`: a
`brand.json`, a `tokens.css` with the palette, a logo, a wordmark and
the icons. It is served, not bundled, so adding an organisation is a
folder and an env var rather than a build.

No colour and no logo lives anywhere else. A script fails the commit if
a hex value or an image path appears outside `brands/`, and it also
fails on a `var(--brand-…)` that no brand defines, which is how a rule
silently dropped by the browser gets caught.

## Every row knows its tenant

`tenant_id` is on every table, NOT NULL and indexed, denormalised onto
child rows so a query cannot forget it. Writes never name it: the
column defaults to the tenant bound to the request, bound from the JWT
for an organiser and from the resolved entity for a public visitor.
Nothing bound is an error.

A flush guard checks it one last time at the session boundary, so a
read that forgot its filter still cannot become a cross-tenant write.
