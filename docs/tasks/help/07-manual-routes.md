# 07: Manual routes, template, sitemap, ads flag, links

Design: `docs/design-manual.md` chapters 7 and 9. When this lands the
manual is on the web in both languages under both bases, with
openings only, and the app links to it from everywhere the design
lists.

## Router

`backend/routers/manual.py`, included in `main.py` before
`spa.mount(app)`, as the privacy router is:

| route | language | audience |
|---|---|---|
| `GET /handleiding`, `/handleiding/{slug}` | nl | all, house brand |
| `GET /manual`, `/manual/{slug}` | en | all, house brand |
| `GET /{tenant}/handleiding`, `/{tenant}/handleiding/{slug}` | nl | organisation, that brand |
| `GET /{tenant}/manual`, `/{tenant}/manual/{slug}` | en | organisation |

The tenant routes resolve the slug through the same lookup the SPA
fallback uses for `/{tenant}/…` and 404 on an unknown or personal
tenant. An unknown chapter slug is 404. The organisation pages emit
the `noindex, follow` meta the SPA head already emits for non-house
brands.

**Ads.** A root chapter page renders the ad slot on the written
pages' terms and sets `request.state.ads_allowed = True` when a
client id is configured, exactly as `_written_page` does. The root
index, every tenant page and the PDF set nothing. Read
`tests/test_ads.py` before writing the router so the new tests are
its shape.

**Sitemap.** `_SITEMAP_PATHS` in `routers/root_files.py` gains
`/handleiding`, `/manual` and each root chapter in both languages.
Nothing under a tenant.

## Template

`backend/templates/manual.html`, its own file. It wears the brand it
is served under (`brand.palette_css(slug)` in the head, the brand's
wordmark), which the content template does not. Layout: the chapter
list in a left column at and above 720px, above the text below it;
the language twin link at the top where the language switch sits on
other pages; previous and next at the foot of a chapter; the same
colophon as `content.html`. The index page is the list with the PDF
link ("Download als PDF" / "Download as PDF") and nothing else; the
PDF link 404s until task 09 and that is fine for a proposal that
ships in order, but it is not fine to leave: task 09 is the next
manual task.

Print rules under `@media print`: a page break before each chapter
heading, captions under pictures, links printed with their address
after the text. Task 09 reuses this sheet.

## Links into it

- `AppHeader.svelte`: the Handleiding item in the help group (task 04
  left it unrendered) opens the chapter for the route by the table in
  design chapter 9, in the current brand and locale: the root base or
  `/{slug}`, `handleiding` or `manual` by `locale`.
- `public_shared/Colophon.svelte`: a manual link beside Blog, without
  the house-brand check, to the base and language in effect.
- `content.html` footer and the blog index: the same link.
- `mail_templates/nl/started.html` and `en/started.html`: one sentence
  under the "you did not do this yourself" line, with the root manual
  link. `started.html` is sent on every start-door create, so one
  sentence and no more.

## Tests

`tests/test_manual.py` grows:

- the index and each chapter answer 200 in both languages under the
  root and under the seeded organisation; a personal tenant's slug
  under a prefix is 404; an unknown chapter is 404.
- the root rendering of chapter 1 contains no `organisation` element
  and the organisation rendering does (uses a marked paragraph task
  10 will keep; until then the test's fixture chapter).
- a root chapter carries the ad slot once a client id is configured
  and the index does not; no tenant page carries it; the security
  headers loosen only on the root chapter.
- tenant pages carry `noindex`; root pages do not.
- the sitemap test in `test_content.py` extends to the manual paths.
- `tests/test_mail_templates.py` (or the nearest): both `started`
  templates render the manual line with the root URL.

Frontend: `site-footer.test.ts` and the header test cover the two
links.

**Done when:** `/handleiding/inloggen` and `/rsp/manual/signing-in`
render with the right brand and audience, the sitemap lists the root
pages, the menu and the colophon reach them, and `test_ads.py` is
untouched and green.
