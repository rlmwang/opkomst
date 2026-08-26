# Being findable

Status: proposal, nothing built.

The goal: someone looking for a way to run a sign-up or a date poll
finds `opkomst.nu`, and the five pages a stranger can actually use are
findable in their own right:

```
/                /events/new   /forms/new   /datepolls/new   /chores/new
```

This document is in four parts: what is broken, what to index and what
to keep out, what to write, and how to know whether any of it worked.

---

## Part 1: what is broken

### 1.1 Five pages, one title

Every app route serves `<title>Opkomst</title>`. Not a variation, the
same eight characters. A search engine has five URLs it cannot tell
apart, no description to quote in a result, and no canonical to pick a
winner. This is the single biggest item here and everything else is
smaller.

The fix is not new machinery. `routers/spa.py::_build_head_meta`
already gives every public entity page a server-rendered title,
description and Open Graph block. The app shell goes through the same
module and simply does not use it. A table of five paths to their copy,
injected at the marker the brand already uses:

```python
_APP_PAGES = {
    "/":              ("opkomst.nu", "Aanmeldingen zonder gedoe. …"),
    "/events/new":    ("Evenement aanmaken", "…"),
    "/forms/new":     ("Vragenlijst maken", "…"),
    "/datepolls/new": ("Datumprikker maken", "…"),
    "/chores/new":    ("Takenrooster maken", "…"),
}
```

Anything not in the table keeps the bare title, which is right: an
organiser's dashboard has no business being described to a crawler.

### 1.2 Every unknown URL returns 200

`/does-not-exist` returns **200** with the app shell, and so does
`/e/zzzzzzzz`. The SPA then renders its own not-found page, which is
fine for a person and wrong for a crawler. Google calls this a soft
404, flags it in Search Console, and it wastes crawl budget on infinite
nonexistent URLs.

The current behaviour is deliberate and the comment in `_spa_fallback`
says why: the server does not know which client-side routes exist.
That reasoning holds for `/some/app/route`, but not for the cases the
server *does* know about:

- A slug that resolves to nothing (`/e/{unknown}`) is a 404 and the
  server knows it: `_resolve_public` already returned `None`.
- A path under no live organisation and not one of the app's own
  first-level routes is a 404 too, and `services/slug.RESERVED_SLUGS`
  already enumerates those routes.

Both should send 404 with the same rendered page. A 404 with a body is
still a usable page for a human.

### 1.3 www.opkomst.nu does not resolve at all

Not a redirect, no DNS. Anyone who types or links `www.` gets a
connection failure. Add the record and a permanent redirect to the
apex, so links from elsewhere land and so link equity is not split
across two hostnames.

### 1.4 No sitemap, and robots does not point at one

`/sitemap.xml` listing the five indexable URLs, served from the same
module as `robots.txt` and `ads.txt`, then the `Sitemap:` line in
`robots.txt` that was left out when there was nothing to point at.

### 1.5 No structured data

One `WebApplication` JSON-LD block on the root: name, what it does,
that it is free, in Dutch. Small and static.

### 1.6 What is already fine

Worth writing down so nobody spends time on it: the root is 4KB of HTML
served in under 100ms, the site is HTTPS-only, `<html lang>` is set,
the mini-apps are deliberately tiny, and `/privacy` exists and is
linked from every public page. Core Web Vitals are not the problem
here.

---

## Part 2: what to index, and what to keep out

This is the decision the first draft of this document missed, and it
matters more than the metadata.

### 2.1 Event pages are currently indexable, and should not be

Nothing emits `noindex`, so every `/e/{slug}`, `/f/{slug}`,
`/d/{slug}` and `/c/{slug}` is a candidate for the index. Consider what
that is:

- Thin. A title, a date, a place, a form.
- Structurally identical to every other one, which is the definition of
  a duplicate-content cluster.
- Expiring. Last month's barbecue is a page about nothing.
- Not ours. It is somebody's invitation to their own event.

A domain whose index is 95% expired thin pages ranks worse for the five
pages that matter. **Recommend `noindex, follow` on every public entity
page.** They stay perfectly shareable: `noindex` affects search
listings, not links, not Open Graph cards, not WhatsApp previews.

If an organiser wants their event found in search, that is a feature
request with an obvious shape (a per-event toggle, defaulting off), not
a default.

### 2.2 Chapter agendas are the organisation's call

`/{tenant}/{chapter}` is an organisation's public agenda: a real,
recurring, non-expiring page that they may well want found. It belongs
to them, so the default should be indexable and the decision theirs.
Worth an explicit line in `brand.json` if any of them ask for the
opposite.

### 2.3 Everything behind a sign-in

Already handled: `robots.txt` disallows `/api/`, `/auth/`, `/admin/`
and `/register/`. Add `noindex` on those responses as belt and braces,
since `robots.txt` prevents crawling but not indexing of a URL somebody
linked.

---

## Part 3: what to write

Five pages of forms is a thin site, and no amount of markup fixes
that. This part is worth more than Parts 1 and 2 combined, and it is
the part that is not a code change.

### 3.1 Who we are competing with

| Query shape | Who ranks now | Our angle |
|---|---|---|
| "datumprikker" | datumprikker.nl, Doodle | no account, no cookies, no ads on the poll itself |
| "aanmeldformulier evenement" | Google Forms, Eventbrite, Aanmelder.nl | free, Dutch, no Google account, deletes the address |
| "vrijwilligersrooster maken" | spreadsheets, Sign-up genius | fair rotation built in |
| "gratis aanmeldpagina" | a long tail of builders | one link, thirty seconds, nothing to install |

We are not going to outrank Doodle for "datumprikker". We can rank for
the qualified long tail, where the qualifier is the thing we actually
do differently: without an account, without cookies, without Google,
privacy-first, in Dutch.

### 3.2 Pages worth writing

Each of these is one page, answering one question, linking to the
create page that solves it:

1. **Datumprikker zonder account of cookies.** The comparison page.
   What datumprikker.nl and Doodle store, what we do not.
2. **Aanmeldformulier maken zonder Google Forms.** The migration page,
   for people who know what they want and dislike where it lives.
3. **Wat gebeurt er met je e-mailadres.** The privacy story as a page
   rather than a policy: encrypted, used once, deleted. This is the
   differentiator and currently it is buried in a collapsed disclosure.
4. **Vrijwilligers inroosteren zonder spreadsheet.** For the chores
   feature, which nobody is searching for by name.
5. **Voor organisaties.** What a tenant gets, aimed at the RSPs of the
   world rather than at individuals.

Five pages, each 400 to 800 words, each linking into the app. That is a
week of writing, not a week of engineering.

### 3.3 Internal linking

The five app pages barely link to each other. The root's tiles link
into the create forms, and that is the whole graph. Each content page
above should link to its create page and to one sibling, and the root
should link to the content pages. A crawler that arrives at one page
should be able to reach all of them.

---

## Part 4: knowing whether it worked

### 4.1 Search Console first, before any of the work

Register and submit the sitemap before shipping the changes, so there
is a baseline. It is the only source that can see a search result that
was never clicked, and it reports the queries people actually typed,
which is what turns Part 3 from guesswork into a list. See
`docs/analytics.md`.

Two reports to watch: **Coverage**, which is where the soft 404s from
1.2 will show up as a number, and **Performance**, filtered to the five
URLs.

### 4.2 Realistic timeline

- Weeks 1 to 2: crawling and indexing of the changed pages.
- Weeks 4 to 8: the long-tail queries in 3.1 start appearing at all,
  usually at positions nobody clicks.
- Months 3 to 6: movement on those, if the content in Part 3 exists.
  Without it, the technical work plateaus at "findable when someone
  searches the brand name".

Nothing here produces a result next week, which is worth saying out
loud before anyone measures it next week.

---

## Order of work

| # | Item | Size | Part |
|---|---|---|---|
| 1 | Search Console, baseline | console task | 4.1 |
| 2 | `noindex, follow` on public entity pages | 1 hour | 2.1 |
| 3 | Per-route title, description, canonical | half a day | 1.1 |
| 4 | Real 404s for the two cases the server knows | 2 hours | 1.2 |
| 5 | `/sitemap.xml` and the `Sitemap:` line | 1 hour | 1.4 |
| 6 | www DNS and redirect | DNS task | 1.3 |
| 7 | JSON-LD on the root | 1 hour | 1.5 |
| 8 | The five content pages | a week of writing | 3.2 |
| 9 | Internal linking | 2 hours | 3.3 |

Items 2 to 7 and 9 are about two days of engineering together. Item 8
is the one that decides whether any of it matters.

## What this deliberately does not do

- **No server-side rendering of the app.** Google renders JavaScript,
  the pages are 4KB, and an SSR pipeline is a large permanent cost for
  a marginal gain.
- **No English URLs yet.** Doing two languages properly means
  `/en/…` paths and `hreflang` pairs, which is a routing change.
  Revisit if Search Console shows English queries arriving.
- **No link building of the paid kind.** The honest sources for this
  project are its GitHub repository, open-source and privacy-tool
  directories, Fediverse posts, and the organisations that use it
  linking from their own sites. That last one is worth asking for.
- **No keyword stuffing in the interface.** The copy people read is the
  copy.
