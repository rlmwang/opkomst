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

`backend/templates/content/` holds one page per question somebody
actually types: how to run a sign-up without per-ticket fees, how to
plan a date without an account, and so on. They are server-rendered
with no bundle, so the text is in the HTML that arrives.

Each one is written to be read rather than to rank, carries its own
title, description and canonical, and ends by pointing at the thing in
the app that solves the problem it describes. `docs/style-copy.md` and
`docs/style-nederlands.md` are the rules they are written to.

## Per-page metadata

Every route has its own title and description, an OG image where there
is one, and a canonical URL on the canonical host. One host: requests to
the other name redirect rather than serving the same page twice.
