# R1 — Backend refactor: org-entity model spine mixin

**Layer:** backend (refactor) · **Run before:** 01 · **Consumed by:** 01 (Roster model).

## Goal

The `Event`, `Form`, and `Datepoll` models each re-declare the same ~8-column spine
(~65 duplicated lines). Extract it into one mixin so the 4th entity (Roster) declares the
spine in one line, and migrate the existing three onto it. **Pure refactor — no schema
change, no migration.**

## Deliverables

1. **`backend/mixins.py`** — add `OrgEntityMixin` (alongside `UUIDMixin`/`TimestampMixin`)
   carrying the columns that are byte-identical across all three:
   `slug` (Text, unique, indexed), `name` (Text, not null),
   `image_url` (Text?), `image_artist_instagram` (Text?),
   `locale` (`Literal["nl","en"]`, default `"nl"`),
   `created_by` (FK `users.id` SET NULL), `chapter_id` (FK `chapters.id` SET NULL, indexed),
   `archived_at` (DateTime?, indexed).
   - FK columns (`mapped_column(ForeignKey(...))`) work directly in a mixin.
   - **Do NOT** put `description`/`topic` in the mixin — Event uses `topic`, Form/Datepoll
     use `description`; those stay per-model.
   - The composite `ix_{table}_archived_chapter` Index embeds the table name, so leave it
     per-model in each `__table_args__` (one line each) rather than fighting
     `@declared_attr.directive`. Keep it simple.
2. **Migrate** `Event`, `Form`, `Datepoll` to `class X(UUIDMixin, TimestampMixin,
   OrgEntityMixin, Base)`, deleting the now-inherited column declarations. Leave each
   model's entity-specific columns and its `__table_args__` Index untouched.

## The hard guard (this is the whole point)

The generated DDL must be **identical**. Prove it:

- `uv run alembic -c backend/alembic.ini revision --autogenerate -m "verify no drift"`
  produces an **empty** migration (no column/index/constraint ops). Delete that throwaway
  revision after confirming. If it's non-empty, the mixin diverged from the originals — fix
  the mixin, don't accept a migration.
- Column order in a table may shift (mixin columns vs inline); that's cosmetic and fine as
  long as autogenerate sees no operations.

## Tests

- Full backend suite green **with no test edits** (`uv run pytest --no-cov`).
- The existing CI idempotency check (`downgrade base; upgrade head; upgrade head`) still
  passes against the unchanged head revision.

## Acceptance

- Empty autogenerate diff (proof of no schema change).
- `uv run pytest --no-cov` green; `uv run ruff check backend tests` clean.

## Out of scope

The Roster model itself (task 01 — it will simply add `OrgEntityMixin` to its bases).
Schema/Pydantic-side `Locale` relocation is handled in task 02.
