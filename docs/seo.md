# Being findable

Five pages of forms is a thin site, and metadata does not fix that. What
follows is what the app does to be findable, and what it deliberately
keeps out of an index.

## Indexed, and not

Every public page an organiser hands out is a link somebody was given,
not a page a search engine should list: `robots.txt` keeps
`/e/`, `/f/`, `/d/`, `/c/`, `/k/` and `/q/` out, and the sitemap
contains only the written pages, the root and the organisation front
pages.

The reason is not SEO hygiene. A sign-up page names an address, a date
and often a chapter, and none of that is ours to publish.

## The written pages

`backend/content/` holds one markdown file per question somebody
actually types: how to run a sign-up without per-ticket fees, how to
plan a date without an account, and so on. One file
carries the front matter and the prose; the shared chrome, the heading
and the closing call to action come from the template around it. They
are server-rendered with no bundle, so the text is in the HTML that
arrives.

Each one is written to be read rather than to rank, carries its own
title, description and canonical, and ends by pointing at the thing in
the app that solves the problem it describes. `docs/style-copy.md` and
`docs/style-nederlands.md` are the rules they are written to.

## Per-page metadata

Every route has its own title and description, an OG image where there
is one, and a canonical URL on the canonical host. One host: requests to
the other name redirect rather than serving the same page twice.

The app's own pages (the root and the five that make something) have no
picture of their own, so their card carries the app's mark. A page for
somebody's event carries that event's image when there is one.

## The two files a search engine asks the site for

Not a page: the hostname itself. Both are served by
`backend/routers/root_files.py`, before the SPA fallback that would
otherwise answer them with the app's HTML shell.

`/favicon.ico` is the icon a result list shows next to the link. It is
fetched by fixed path rather than read out of the page head, and a 404
there leaves whatever icon was stored last time in place, which is how
opkomst.nu spent its first weeks in Google's index wearing the logo of
the one organisation the app was originally built for. The bytes are
the house brand's PNG: the path belongs to the hostname, and the
hostname is ours.

HEAD works on every route. Starlette's router adds HEAD to a GET route
and FastAPI's does not, so every page in the app answered 405 to the
request a crawler makes when it wants to know whether a page changed.
