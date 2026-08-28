# Being findable

Status: built, except the two items that are not code. Item 6 (the www
DNS record) and item 1 (Search Console) are yours; everything else in
the table at the bottom is shipped.

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
    "/datepolls/new": ("Datumplanner maken", "…"),
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
| "datumplanner" | datumplanner.nl, Doodle | no account, no cookies, no ads on the poll itself |
| "aanmeldformulier evenement" | Google Forms, Eventbrite, Aanmelder.nl | free, Dutch, no Google account, deletes the address |
| "vrijwilligersrooster maken" | spreadsheets, Sign-up genius | fair rotation built in |
| "gratis aanmeldpagina" | a long tail of builders | one link, thirty seconds, nothing to install |

We are not going to outrank Doodle for "datumplanner". We can rank for
the qualified long tail, where the qualifier is the thing we actually
do differently: without an account, without cookies, without Google,
privacy-first, in Dutch.

### 3.2 Pages worth writing

Each of these is one page, answering one question, linking to the
create page that solves it:

1. **Datumplanner zonder account of cookies.** The comparison page.
   What datumplanner.nl and Doodle store, what we do not.
2. **Aanmeldformulier maken zonder Google Forms.** The migration page,
   for people who know what they want and dislike where it lives.
3. **Wat gebeurt er met je e-mailadres.** The privacy story as a page
   rather than a policy: encrypted, used once, deleted. This is the
   differentiator and currently it is buried in a collapsed disclosure.
4. **Vrijwilligers inroosteren zonder spreadsheet.** For the chores
   feature, which nobody is searching for by name.

Four pages, each 400 to 800 words, each linking into the app. That is a
week of writing, not a week of engineering.

Deliberately not written: a "voor organisaties" page. An organisation
arrives because somebody in it already uses the tool, not through a
search result, so a page pitching at them would be aimed at an audience
that is not searching.

### 3.3 Internal linking

An earlier draft of this section said the pages barely link to each
other. That was wrong, and worth correcting rather than quietly
deleting, because the correction changes what needs building.

What already exists:

| Link | Where |
|---|---|
| Root to the four create pages | the tiles in `PersonalIndexPage` |
| Any organiser page back to the root | `AppHeader`, whose wordmark is a `router-link to="/"` |
| A public sign-up page to the landing page | `BrandMark public-link`, pointing at `org_url` |
| Any public page to the privacy policy and the source | `Disclosure` |

The graph is therefore already connected. A crawler that lands on
`/events/new` reaches the root in one hop and every sibling in two,
which is well inside what a crawler will follow. **There is no crawl
problem to fix.** The remaining work is about the pages in 3.2, which
do not exist yet, and about one small correctness fix.

#### The one fix worth making now

`BrandMark`'s public link opens in a new tab. On an organisation's
page that is right: it leads to `rsp.nu`, which is somewhere else. On a
house-brand page `org_url` is `https://opkomst.nu`, so it is a link
from our own page to our own site, opening a new tab for no reason and
written as an absolute URL rather than a route. Make it a same-tab
in-app link when the brand is the house brand. Ten minutes.

#### Where the content pages hang, when they exist

The four pages in 3.2 need somewhere to be linked from, and the answer
is not "the landing page", because `docs/focus.md` spent a day making
that page one clear choice between four tiles. Adding a reading list
above the fold would undo it.

**A footer, on house-brand app pages only.** The app has no footer
today, which is why this question has no obvious answer yet. One
belongs here:

- **Where it appears:** the root and the four create pages. Not on
  public sign-up, form, datepoll or roster pages, which are somebody's
  invitation to their own event and already carry the `Disclosure`
  card. Not on any organisation-branded page, for the same reason
  advertising never appears there: it is their page.
- **What it holds:** the four content pages, the privacy policy, and
  the source link. Nothing else, and no marketing copy.
- **What it looks like:** the muted treatment `Disclosure` already
  uses. Small type, no accent colour, separated by a rule. It is a
  colophon, not a nav bar, and it sits below the primary content so it
  competes with nothing.
- **Why a footer rather than a nav:** a nav bar is for places you go
  during a task. These are places you go instead of the task. The
  bottom of the page is where a reader who did not find what they
  wanted goes looking, and it is where a crawler looks for the site
  graph.

That is one shared component, mounted in two shells, and it is about
half a day. It is worth doing when there is something to put in it and
not before: a footer linking to four pages that do not exist yet is
four broken links.

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

| # | Item | State | Part |
|---|---|---|---|
| 1 | Search Console, baseline | **yours**: register and submit the sitemap | 4.1 |
| 2 | `noindex, follow` on public entity pages | done | 2.1 |
| 3 | Per-route title, description, canonical | done | 1.1 |
| 4 | Real 404s for the two cases the server knows | done | 1.2 |
| 5 | `/sitemap.xml` and the `Sitemap:` line | done | 1.4 |
| 6 | www DNS and redirect | **yours**: DNS record plus redirect | 1.3 |
| 7 | JSON-LD on the root | done | 1.5 |
| 8 | The four content pages | done, four pages written | 3.2 |
| 9 | Same-tab house-brand logo link | done | 3.3 |
| 10 | The footer, once the content pages exist | done | 3.3 |

The four written pages live in ``backend/templates/content/``, listed
once in ``services/content.py``, which the router, the sitemap and the
footer all read. ``tests/test_content.py`` holds the guards: that each
page serves and describes itself, that the five app pages no longer
share a title, that an organiser page says ``noindex``, that a path
nothing serves is a 404, and that the frontend's copy of the page list
still matches the server's.

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
