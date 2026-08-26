# Knowing what the traffic is

Status: proposal, nothing built.

The goal: know how many people reach the site, which pages they land
on, and whether the SEO work in `docs/seo.md` changed anything.

## The constraint this has to live inside

`CLAUDE.md` says: no analytics or tracking pixels anywhere, on any
page, in any brand. That rules out Plausible, Matomo, Umami and every
other script-in-the-page product, self-hosted ones included. It is not
a preference to be traded off against convenience: the disclosure on
every public page tells visitors there is no tracking, and that
sentence has to stay true.

What it does not rule out is counting. A server knows how many requests
it answered without learning anything about who sent them. The whole
design below is that distinction.

## Three sources, two of which exist already

### 1. Google Search Console, free, nothing to build

Impressions, clicks, average position, and the queries people actually
typed. For the question "did the SEO work" this is not one source among
several, it is the only source: nothing on our own server can see a
search result that was never clicked.

Setup is a verification step. We already serve `/ads.txt`, so the same
DNS or file method applies, and the sitemap from `docs/seo.md` gets
submitted here.

This should happen first, before any of the work below, because it is
free and because the SEO changes need a baseline to be measured
against.

### 2. AdSense reporting, free, already connected

Page views, impressions and revenue per page, for house-brand pages.
Not a general analytics tool and it sees nothing on an organisation's
pages, but for "how much traffic does the root get" it is a number we
already have.

Worth knowing before building anything: between Search Console and
AdSense, the main questions may already be answered.

### 3. First-party counters, which is what this document proposes

What the two above cannot give: traffic on organisation pages, which
carry no advertising and are usually not search destinations, and any
notion of a funnel, such as how many people who opened a sign-up page
actually signed up.

## The design

### What is counted

One row per day per surface, incremented server-side. Nothing else.

```
page_views(day, surface, count)
```

`surface` is a route class, not a URL: `root`, `create_event`,
`public_event`, `public_form`, and so on. Not the slug, because the
slug identifies somebody's event and a table of "which events got
looked at when" is exactly the kind of data this app exists to not
accumulate.

A second table for the one funnel worth knowing:

```
conversions(day, surface, action, count)
```

with `action` in `viewed`, `submitted`. Two counters, and the ratio
between them is the number anyone actually wants.

### What is deliberately not counted

- **No visitor identity of any kind.** No cookie, no
  `localStorage`, no fingerprint, no hashed IP. "Unique visitors" is
  therefore not a number this system can produce, and that is the
  trade: unique counting requires identifying, and identifying is the
  thing we do not do.
- **No IP address, stored or derived.** Which also means no country
  breakdown, no city, no ISP.
- **No user agent.** Which means no browser or device split. If the
  desktop-versus-phone ratio turns out to matter for the ad layout, the
  honest source is AdSense's own reporting, which already has it.
- **No referrer URL.** A referrer can carry a secret edit-link token in
  its path. Storing the host alone would be safe, but it is not worth
  the code that would have to keep proving it.
- **No per-entity counts.** See above.

### Where the counting happens

`TimingMiddleware` in `services/observability.py` already sees every
request with its route. This is one more thing it does, incrementing an
in-process counter, with a flush to the database every N seconds or on
shutdown. Per-request writes to Postgres for a page view would be a lot
of writes for a number nobody reads in real time.

The public entity pages are served by `routers/spa.py`, which knows
exactly which surface each one is, so the classification is a lookup
rather than a regex over paths.

### The dashboard

`CLAUDE.md` is explicit that there is no platform-admin role and no UI
for platform-level things: organisations are an env var, brands are a
folder. A traffic dashboard is a platform-level thing, so it follows
that pattern rather than breaking it:

```
python -m backend.cli traffic-report --days 30
```

printing a table per surface with a sparkline, in the same shape as the
existing one-shot CLI commands. No page, no route, no auth surface, and
nothing new exposed to the internet.

If a page is genuinely wanted later, the honest version is a static
HTML file the CLI writes, not a live route.

### Retention

Daily rows, kept for 24 months, then dropped by the existing reaper
pattern. Aggregates rather than events, so there is nothing to
anonymise: they were never personal.

## Work

| Piece | Size |
|---|---|
| Two tables plus the migration | 1 hour |
| Counter in the middleware, with the flush | half a day |
| Surface classification and its tests | half a day |
| `traffic-report` CLI | half a day |
| A test that no request attribute is stored | 1 hour |

Under two days. The last row is the one that matters most: a test
asserting the counter tables have no column that could hold anything
about a person is what keeps this design from drifting into the thing
it was written to avoid.

## Recommendation

Do the free things first and see whether they answer the question.
Register Search Console today, read AdSense's page reports for a
fortnight, and only build the counters if a question survives that both
of them cannot answer. The most likely survivor is the funnel: how many
people who see a sign-up page finish signing up. That one is worth
building for, and it is also the one nobody else can tell us.
