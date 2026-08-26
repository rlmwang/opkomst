# Being findable

Status: proposal, nothing built.

The goal: someone searching for a way to organise a sign-up should find
`opkomst.nu`, and the four pages that make something should be findable
in their own right:

```
/                /events/new   /forms/new   /datepolls/new   /chores/new
```

## Where we start

Better than it looks in one respect and worse in another.

Already true:

- `/robots.txt` is a real file and allows those five paths.
- `/privacy` exists, is linked from every public page, and is the kind
  of page a reviewer and a crawler both look for.
- Every public entity page (`/e/{slug}` and friends) already gets a
  server-rendered `<title>`, description and Open Graph tags from
  `routers/spa.py::_build_head_meta`. That work is done and good.

Not true yet, and this is the whole problem:

- **Every app route shares one title.** `/events/new` serves
  `<title>Opkomst</title>`, and so does `/`, and so does `/forms/new`.
  A search engine has five URLs it cannot tell apart.
- **No meta description anywhere on those five.** The snippet in a
  result page is then whatever Google scrapes, which for a form is
  usually the field labels.
- **No canonical URL**, so any path that renders the app is a candidate
  duplicate of every other.
- **No sitemap.**
- **The content is client-rendered.** Google executes JavaScript, but
  rendering is queued separately from crawling and can lag by days.
  Anything that matters should be in the HTML that arrives first.

## The shape of the fix

All five pages are served by one function,
`routers/spa.py::_serve_admin_shell`, which already injects the brand
into `<head>`. It is the same seam the public entity pages use for
their metadata, so this is extending a mechanism rather than inventing
one.

### 1. Per-route metadata, server-rendered

A table of the five paths, each with a title, a description and a
canonical URL, in both languages. The shell already carries a marker
where the head is injected; the same substitution takes the metadata.

Sketch, next to the existing `_build_head_meta`:

```python
# Path -> what a search result for it should say. Only the pages a
# stranger can reach: everything behind a sign-in is Disallow'd in
# robots.txt and has no business in an index.
_APP_PAGES = {
    "/":               ("opkomst.nu", "Aanmeldingen zonder gedoe. …"),
    "/events/new":     ("Evenement aanmaken", "…"),
    "/forms/new":      ("Vragenlijst maken", "…"),
    "/datepolls/new":  ("Datumprikker maken", "…"),
    "/chores/new":     ("Takenrooster maken", "…"),
}
```

Anything not in the table keeps today's bare title, which is correct:
an organiser's dashboard should not be described to a search engine at
all.

The copy belongs in `brands/opkomst/`, not in the table, if it is going
to differ per brand. It does not: only the house brand is indexed, so
the table is fine and simpler.

### 2. A sitemap

`/sitemap.xml`, listing exactly those five URLs, served from the same
module as `robots.txt` and `ads.txt` for the same reason: it is a file
a crawler asks for, and without its own route the SPA fallback answers
it with HTML. Then `robots.txt` gains the `Sitemap:` line that was
deliberately left out when there was nothing to point at.

### 3. Language

The pages are Dutch and the audience is Dutch. `<html lang>` is already
set. Two options, and the second is more work than it looks:

- **Dutch only for indexing.** One canonical URL per page, Dutch
  metadata, and the in-app language switch stays a runtime preference
  that search engines never see. Simple and correct for the audience.
- **Both languages properly**, which means separate URLs per language
  (`/en/events/new`), `hreflang` pairs, and a routing change. Only
  worth it if English-speaking organisers become a real audience.

Recommend the first, and revisit if Search Console shows English
queries arriving.

### 4. Structured data

One `WebApplication` JSON-LD block on `/`, naming the app, what it
does, and that it is free. This is what fills the richer result cards.
Small, static, and it goes in the same head injection.

### 5. The thing that is not markup

Five pages of forms is a thin site, and thin sites rank badly whatever
their metadata says. The pages that could earn traffic are the ones
that answer the question someone actually types:

- "hoe organiseer ik een aanmeldformulier zonder Google Forms"
- "datumprikker zonder cookies"
- "gratis aanmeldpagina voor een evenement"

That is a content decision rather than a code one, and it is worth more
than everything above combined. The technical work makes the site
indexable; it cannot make it interesting.

## What to do, in order

1. Per-route title, description and canonical for the five pages.
2. `/sitemap.xml`, and the `Sitemap:` line in `robots.txt`.
3. Register the site in Google Search Console and submit the sitemap.
   This is also the only honest way to know whether any of it worked,
   see `docs/analytics.md`.
4. JSON-LD on the root.
5. Decide about English.
6. Write something worth finding.

Items 1, 2 and 4 are about a day together. Item 3 is a console task.

## What this deliberately does not do

- No server-side rendering of the app itself. Google renders
  JavaScript, the five pages are small, and an SSR pipeline is a large
  permanent cost for a marginal gain.
- No keyword stuffing in the interface. The copy people read is the
  copy, and it is written for them.
- Nothing about the entity pages (`/e/{slug}`). Those are somebody's
  invitation to their own event, they already carry proper metadata for
  sharing, and they are not ours to optimise for search.
