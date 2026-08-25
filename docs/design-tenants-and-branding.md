# Design: tenants and centralized branding

Status: proposed. Turns the single-org install into a multi-tenant one:
every row belongs to a tenant, the organiser app moves from `/` to
`/{tenant}` (`opkomst.nu/rsp`), and everything that makes the app *look*
like a particular organisation moves out of the code into a per-tenant
brand folder. Adding an organisation becomes: drop a folder in
`brands/`, insert one row, done — no rebuild, no code change.

Today the RSP identity is scattered: `rsp-logo.png` sits in
`frontend/src/assets/` and `frontend/public/`, the palette is a `:root`
block in `frontend/src/assets/theme.css`, a second copy of the palette
is inlined in each public HTML shell's first-paint `<style>`, a third
copy is a hex ramp in `frontend/src/primevue-preset.ts`, the wordmark
and the `rsp.nu` link are hardcoded in two `BrandMark.vue` files, and
the email templates reference `{{ public_base_url }}/rsp-logo.png`. All
of it collapses into one folder per tenant.

## The two halves

**Tenancy** is a data-model change: a `tenants` table, a `tenant_id` on
every other table, tenant-scoped reads, and a tenant segment on the
organiser app's URLs.

**Branding** is a delivery change: the visual identity becomes runtime
data (files on disk + a small JSON manifest) rather than build-time
constants, so a tenant's look is chosen per request, not per bundle.

They meet in exactly one place: given a request, which tenant is this,
and therefore which brand folder do we serve?

## Part 1 — the brand folder

```
brands/
  opkomst/                  the house brand: fallback for unknown slugs
    brand.json
    tokens.css
    logo.png
    favicon.png
    apple-touch-icon.png
  rsp/
    brand.json
    tokens.css
    logo.png
    favicon.png
    apple-touch-icon.png
    fonts/…                 optional; @font-face lives in tokens.css
```

`tokens.css` is *only* custom properties — the `:root` block that today
opens `theme.css`, nothing else:

```css
:root {
  --brand-red: #9f000b;
  --brand-red-hover: #7f0009;
  --brand-bg: #f6f1e7;
  …
  /* The PrimeVue ramps, previously hex literals in primevue-preset.ts */
  --brand-primary-50: #fdf2f2;
  …
  --brand-surface-0: #fbf7ee;
  …
}
```

`brand.json` carries everything that isn't a colour:

```json
{
  "app_name": "opkomst.nu",
  "wordmark": "RSP",
  "org_name": "Revolutionair Socialistische Partij",
  "org_url": "https://rsp.nu",
  "logo": "logo.png",
  "favicon": "favicon.png",
  "apple_touch_icon": "apple-touch-icon.png",
  "mail_from_name": "RSP",
  "boot": { "bg": "#f6f1e7", "fg": "#1a1a1a", "accent": "#9f000b", "border": "#e6dec9" }
}
```

`boot` is the handful of colours the first-paint spinner needs before
any stylesheet has loaded; it is the only duplication left, and it is
duplication *within one file* rather than across four.

**Serving.** FastAPI mounts `brands/` read-only at `/brand/{tenant}/…`
with a short-cache header (not `immutable` — brand files keep their
names across edits). Nothing about a brand goes through Vite, which is
what makes "add a folder" enough: the bundle never learns tenant names.
The Vite dev server proxies `/brand` to the backend alongside `/api`.

**Structural CSS stays put.** `theme.css`, `forms.css` and the
component styles keep every rule that isn't a colour or a font. They
already consume `var(--brand-*)`; the transition is deleting the `:root`
block from `theme.css` and letting the tenant's `tokens.css` supply it.

**PrimeVue.** `primevue-preset.ts` keeps its structure and loses its
literals: `primary.500: "var(--brand-primary-500)"`, `surface.0:
"var(--brand-surface-0)"`, and so on. PrimeVue emits these into its own
`--p-*` variables, which resolve at runtime against whichever
`tokens.css` the page loaded. One preset, every tenant.

**Guard.** `scripts/check_brand_tokens.py`, wired into lefthook and CI:
no hex literal, `rgb(`/`hsl(` colour, or `*-logo.png` reference may
appear under `frontend/src/`, `backend/services/mail_templates/`, or the
HTML shells — only under `brands/`. This is the rule that keeps the
centralisation from rotting back out, and it is the reason the palette
can never fork into a fourth copy.

## Part 2 — the tenant

```python
class Tenant(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "tenants"
    slug: Mapped[str]            # 'rsp' — the URL segment and brand-folder name
    name: Mapped[str]            # display name in the organiser app
    deleted_at: Mapped[datetime | None]
```

The brand folder is addressed by `slug`; there is no `brand_dir`
column, because two names for one thing is one name too many.

`Chapter` becomes a child of `Tenant`; `User` belongs to exactly one
tenant; the four `OrgEntity` types (Event, Form, Datepoll, Roster) and
every row hanging off them carry the tenant of their root.

### `tenant_id` on all 27 tables

Every table gets `tenant_id TEXT NOT NULL REFERENCES tenants(id)`,
indexed, via a `TenantMixin` in `backend/mixins.py`. For child rows
(`occurrences`, `signups`, `form_responses`, `shifts`, …) this is
denormalized — the value is derivable through the parent FK — and that
is deliberate: every read filter, every uniqueness index, and every
"could this row leak across tenants" question becomes a single-column
predicate on the row itself, with no join to get it wrong.

Denormalization needs a guard, so it gets two, in the style the repo
already uses for its privacy invariants:

- `tests/test_tenancy.py::test_every_table_has_tenant_id` walks
  `Base.metadata.tables` and asserts the column exists, is `NOT NULL`,
  and is indexed. A new model without it fails CI.
- `tests/test_tenancy.py::test_child_tenant_matches_parent` walks every
  FK in the metadata and asserts, per relationship, that child and
  parent tenant agree — a Hypothesis-free structural sweep over seeded
  data plus an explicit check in the write paths that create children.

Composite FKs (`(id, tenant_id)`) would let the database enforce the
second one, at the cost of a wider key on 27 tables. The structural test
is the chosen guard; the keys stay simple.

### Uniqueness after tenancy

- `users.email` — unique per `(tenant_id, email)` among live users. The
  same human can organise for two tenants with the same address; those
  are two `User` rows, and the login door is per tenant (below).
- `chapters.name` — unique per `(tenant_id, name)` among live rows.
- `chapters.slug` — **globally** unique among live rows, not per tenant.
  The chapter agenda lives at `/e/amsterdam` and that URL carries no
  tenant, so two tenants cannot both own `amsterdam`; the existing
  collision suffixer (`amsterdam-2`) handles it.
- entity slugs — already globally unique 8-char nanoids. Unchanged.

### Reads and writes

`services/access.py` keeps its shape and grows one predicate.
`chapter_ids_for_user` already scopes organisers; the change is that
`role=admin` stops meaning *global* and starts meaning *every live
chapter in the user's tenant*. Every organiser query gains
`tenant_id == user.tenant_id`; `get_scoped` applies it centrally, so
the guarantee stays in one place, as it is today.

Creating a tenant is not a UI operation. `python -m backend.cli
tenant-create --slug rsp --name "RSP"` is the whole story, matching the
existing one-shot CLI convention. That removes the need for a
platform-superadmin role: nobody signs into "the platform", only into a
tenant.

### Auth

The JWT gains a `tenant` claim, and `get_current_user` resolves the user
within that tenant. The magic-link door needs the tenant *before* a
token exists, and the SPA knows it from its own URL, so
`POST /api/v1/auth/login-link` takes `tenant` in its body. The emitted
link points at `/{tenant}/auth/redeem`. The privacy contract is
unchanged: still always 200, still never reveals whether the address
exists — now scoped to one tenant's user set.

## Part 3 — URLs

**Organiser app** moves under the tenant segment:

| today | after |
| --- | --- |
| `/events` | `/rsp/events` |
| `/chapters` | `/rsp/chapters` |
| `/auth/redeem` | `/rsp/auth/redeem` |
| `/admin/whatsapp` | `/rsp/admin/whatsapp` |

`spa.py` serves `index.html` for `/{tenant}/*` when `{tenant}` is a live
tenant slug, injecting the tenant's `<link>` tags (tokens, favicon,
apple-touch-icon), the boot colours, and
`window.__OPKOMST_TENANT__ = {slug, brand}` into the shell. `main.ts`
reads it and builds `createWebHistory("/" + slug + "/")`. Vite's `base`
stays `/`, so the content-hashed `/assets/*` URLs are shared by every
tenant and cached once.

Unknown first segment falls through to the existing SPA 404, and so does
`/` itself: there is no root page and no redirect shim to the old root
paths. The public marketing site that will eventually live there is a
separate build, once the tenants exist.

**Public pages keep their URLs exactly.** `/e/{slug}`, `/e/{chapter}`,
`/f/{slug}`, `/d/{slug}`, `/c/{slug}` are unchanged and carry no tenant
segment. `spa.py` already resolves the entity server-side to inline its
payload; that same lookup now yields `entity.tenant`, and the handler
injects that tenant's brand into the `<head>` — stylesheet link, icons,
boot colours — and its `brand.json` into the payload as
`window.__OPKOMST_BRAND__`. `BrandMark.vue` (both copies, which merge
into one shared component under `public_shared/`) reads the wordmark,
logo URL and org link from there instead of importing an asset.

An unknown or archived slug has no tenant, so it renders the house
brand — the same tri-state the mini-apps already have for payloads.

There is no flash of the wrong brand: the palette arrives in the same
HTML response as the payload, before any JS.

**Emails** take the brand from the sending entity's tenant.
`services/mail.py::render` injects a `brand` dict (the tenant's
`brand.json` plus absolute URLs) exactly where it injects `app_name`
today; templates use `{{ brand.logo_url }}` and `{{ brand.app_name }}`.
`services/branding.py`'s `APP_NAME` constant is deleted. One SMTP
account and one envelope domain stay shared; only the From *display
name* is per tenant.

**Link previews.** `og:site_name` and the `— opkomst.nu` title suffix in
`_og_head` become the entity tenant's `app_name`; the fallback OG image
becomes that tenant's favicon.

## Migration

One Alembic revision, and it does have data to preserve — this install
is deployed:

1. `create_table("tenants")`.
2. Insert `rsp` (name "RSP", slug `rsp`).
3. For each of the 27 tables: add `tenant_id` nullable, `UPDATE … SET
   tenant_id = (SELECT id FROM tenants WHERE slug='rsp')`, then
   `ALTER … SET NOT NULL`, add the FK and the index.
4. Drop and recreate the live-scoped unique indexes on `users.email`,
   `chapters.name` with the tenant in the key.

Downgrade drops the columns and the table; CI's
`downgrade base; upgrade head` idempotency run covers it. `seed.py`
creates the `rsp` tenant first and hangs everything off it.

## What changes, by file

- `backend/mixins.py` — `TenantMixin`.
- `backend/models/tenants.py` — new; every other model gains the mixin.
- `backend/services/access.py` — tenant predicate in `get_scoped` /
  `scope_filter` / `list_filter`; admin becomes tenant-global.
- `backend/services/brand.py` — new; loads and caches `brand.json` per
  tenant, resolves absolute asset URLs.
- `backend/services/branding.py` — deleted.
- `backend/services/mail.py` — `brand` in the render context.
- `backend/services/mail_templates/{nl,en}/_event_base.html` — logo from
  `brand`.
- `backend/routers/spa.py` — brand injection on all six shells, the
  `/{tenant}/*` organiser route, the tenant index at `/`.
- `backend/main.py` — mount `/brand`.
- `backend/cli.py` — `tenant-create`.
- `backend/auth.py`, `backend/routers/auth.py` — tenant claim + door.
- `frontend/src/assets/theme.css` — `:root` block deleted.
- `frontend/src/primevue-preset.ts` — literals → `var(--brand-*)`.
- `frontend/src/lib/branding.ts` — reads `window.__OPKOMST_BRAND__`.
- `frontend/src/components/BrandMark.vue` + `frontend/src/public/BrandMark.vue`
  — merged into `public_shared/BrandMark.vue`, brand-driven.
- `frontend/{index,public-*}.html` — palette `<style>` → injection marker.
- `frontend/src/router/index.ts`, `main.ts` — tenant-based history base.
- `frontend/vite.config.ts` — proxy `/brand`.
- `frontend/public/rsp-logo.png`, `frontend/src/assets/rsp-logo.png` —
  deleted; the file lives at `brands/rsp/logo.png`.
- `e2e/` + `tests/` — tenant fixture, `/rsp` prefixes.
- `scripts/check_brand_tokens.py` — new guard.
- `docs/architecture.md`, `docs/deploy.md` — tenancy + brand folder.
- `Dockerfile` — copy `brands/`.

## Implementation order

Each step ends green, so the work can stop between any two:

1. **Brand folder + guard.** Create `brands/opkomst` and `brands/rsp`,
   move the palette and logo, delete the duplicates, point everything at
   a single hardcoded `rsp` brand. No tenancy yet — the app looks
   identical and every colour has one home.
2. **Tenants table + migration.** Model, CLI, migration, backfill,
   seed. Reads still ignore it.
3. **Scoping.** Tenant predicate in `access.py`, JWT claim, per-tenant
   login door, uniqueness indexes, the two guard tests.
4. **Organiser URLs.** `/{tenant}/*` serving, router base, magic-link
   paths, E2E updates.
5. **Public brand resolution.** Entity → tenant → injected brand on the
   five public shells and in email; house-brand fallback; `/` index.

## Decisions

1. **Cross-tenant integrity** is enforced by the structural test, not by
   composite `(id, tenant_id)` foreign keys.
2. **The root path 404s.** No tenant index, no redirect to a default
   tenant. A public marketing site lands there later, built separately
   once the tenants exist.
3. **Email keeps one sending domain** and one SMTP account; only the
   From display name and the logo come from the tenant's brand.
4. **Locale strings stay shared.** Only the interpolated `appName`
   differs per tenant. A brand-folder locale overlay is the natural home
   if a tenant ever wants its own wording — out of scope here.
5. **The five steps ship one at a time**, each green and deployable, and
   are reviewed before the next starts.
