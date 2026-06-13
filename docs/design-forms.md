# Design: Forms backend (events-parity revision)

Status: proposed → implementing. Supersedes the earlier "forms are
zero-identity" stance. **Forms follow the same design principles as
Events** (and Datepolls): an organiser-authored, chapter-scoped,
public-by-slug object with a name, an optional description, and a
public surface where a respondent leaves an optional pseudonym. The
only thing that makes Forms different from Events is *what* it
collects (free-form questions vs fixed sign-up attributes) — not the
identity model.

## What changes

1. **A form gets a description.** Optional free text shown on the
   public page under the name, exactly like the event topic / the
   datepoll description.
2. **A respondent leaves an optional pseudonym.** Same contract as the
   event sign-up name and the datepoll respondent: `display_name`,
   optional, "real or not", `NULL` = anonymous, via the shared
   `DisplayName` primitive (`schemas/common.py`). The frontend renders
   `NULL` as a localised "Anonymous".

## Data model

The pseudonym is per *submission*, not per *answer*, so a submission
needs a row to hang it on — the same parent-submission shape Events
(`Signup`) and Datepolls (`DatepollSubmission`) already use. Today
`FormResponse.submission_id` is a bare random token with no parent
row; that becomes a real FK.

```
forms
  ... (unchanged) ...
  description   text null                       -- NEW: optional blurb, shown on the public page

form_submissions                                -- NEW table
  id            uuid pk                          -- the submission identifier
  form_id       text not null fk forms(id) on delete cascade   -- indexed
  display_name  text null                        -- pseudonym, real-or-not, NULL = anonymous
  created_at / updated_at

form_responses
  ... (unchanged columns) ...
  submission_id text not null fk form_submissions(id) on delete cascade   -- WAS a free token; now a FK
```

- `form_submissions` cascades from `forms`; `form_responses` cascades
  from `form_submissions`, so deleting a form still takes everything
  with it in one `DELETE`.
- One submission row per fill-out; N answer rows FK'd to it. This is
  the *same* shape as Datepolls — the submission-shape rule in
  `docs/principles-architecture.md` §17 is unchanged; what changes is
  that forms now *have* per-submission data (the pseudonym), so by
  that very rule they get a parent table.

## Schemas (`schemas/forms.py`)

- `FormCreate` / `FormUpdate`: add `description: str | None =
  Field(default=None, max_length=2000)`.
- `FormOut` and `PublicFormOut`: add `description: str | None`.
  (`FormListOut` stays lean — the list view doesn't render it.)
- `FormSubmitIn`: add `display_name: DisplayName` (shared primitive).
- `FormSubmissionOut` (CSV row): add `display_name: str | None`.

## Service (`services/forms.py`)

- `to_out` / `to_public_out`: include `description`.
- `submissions(db, form_id)`: build per-submission CSV rows by joining
  `FormSubmission` (for `display_name` + canonical `created_at`) to its
  `FormResponse` rows, keyed by question id — same mechanic as
  `datepolls_svc.submissions`.

## Public submit (`routers/forms_public.py`)

Create one `FormSubmission(form_id, display_name)`, flush for its id,
then the per-question `FormResponse` rows FK'd to it, in one commit.
The ack returns the submission id (now the row PK). Per-kind answer
validation is unchanged.

## Migration

One Alembic migration: `forms.description` column, the
`form_submissions` table, and the `form_responses.submission_id` FK.
Pre-launch, fresh DB — no data-migration tricks; CI's
`downgrade base; upgrade head; upgrade head` pins idempotency.

## Privacy posture (unchanged invariants, now uniform)

- The pseudonym is self-chosen and optional — the only respondent
  identifier, identical to Events. No email, no encryption, no IP.
- The submission id is opaque with no read-back endpoint.
- Open-source disclosure on the public page (now actually present —
  see `design-public-pages-ux.md`).
