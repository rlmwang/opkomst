# Benchmarks

What the app costs to read, kept as a log. One section per run, newest
first, so a change that costs something shows against the run before it.

## Running one

```bash
make db-up
set -a && source .env && set +a
LOCAL_MODE=1 uv run uvicorn backend.main:app --port 8000        # one shell
uv run python scripts/bench.py --reset --fill --levels 1,8      # another
```

Two tables come out.

**Pages** is what somebody waits for. A screen is not one request: an
organiser opening an event fires six at once and waits for the slowest,
and under load those six compete with each other as much as with
anybody else's. Every page counts `/auth/me`, because the guard
resolves the session before anything paints.

**Endpoints** is what one read costs alone, which is where a regression
gets diagnosed once a page has shown one.

`p50` and `p95` are milliseconds, `rps` is requests (or page loads) per
second at that concurrency.

## The data

`--fill` tops every table up to the `BUSY` profile in
`scripts/bench.py`: two years of a chapter, 120 events on 240 dates,
500 answers per form, 60 people on a datepoll, 520 shifts on the
roster. `--scale N` multiplies how much there is, never how big each
one is: a meeting always has 20 people at it, because 200 is not a
bigger chapter, it is a different product. `--reset` deletes what a
fill wrote, which is how a smaller scale runs after a bigger one.

Filling matters more than it sounds. The seeded dev database is a
demo: eight events, nine signups, three datepoll answers. Every read
that joins to those looks free against it, and Postgres plans them for
tables that fit on one page. The fill ends with `ANALYZE` for the same
reason: without it the planner works from statistics gathered when the
tables were empty, every read looks slow, and the ranking that comes
out is an artefact of the load rather than of the code.

## What the numbers cannot tell you

The load generator is one Python process running async httpx, so it has
a ceiling of its own: `/health`, which does nothing, tops out at **300
rps** and costs **7 ms** at concurrency 1. Anything measured near
100-150 rps is within a factor of two of the harness, not necessarily
of the app. Read the p50 column for what something costs and the rps
column only as a shape. A real server-side ceiling needs a load
generator on another machine.

Runs are on a 12th Gen Intel i5-1235U, 12 cores, 15 GB, Postgres 16.13,
Python 3.14.5, one uvicorn worker, over local loopback with no proxy.
Production sits behind Traefik with `compress=true`, so the bytes there
are fewer and the CPU is the same. Repeats move 20-30% on a laptop:
read a smaller change as noise.

## 2026-08-30 - the lists answer with a page

The load is thousands of events and polls with twenty sign-ups each,
not one of either with thousands. So the lists were the hot path, and
they answered with everything: 1,202 events was 511 KB, and the browser
did the sorting and the searching over what it had been sent.

Where that time went, on 1,202 events:

| | |
|---|---|
| the statement | 11 ms |
| building 1,202 DTOs in Python | 60 ms |
| serialising to JSON | 2.5 ms |

Fifty microseconds of Python per row, for rows nobody drew. Now:

| endpoint | before | after |
|---|---|---|
| event list, p50 | 39 ms | 32 ms |
| event list at c=8 | 225 ms | 144 ms |
| event list, payload | 511 KB | 22 KB |
| event list, page 12 | n/a | 38 ms |
| event list, searched | n/a | 32 ms |

* **Page 12 costs what page 1 costs.** That is the point: the read no
  longer grows with the table.
* **The count is the extra query.** Numbered pages need a total, so
  every list is 4 queries where it was 3.
* The sort moved with it. The dashboard's order (what is coming,
  soonest first, then what has happened, newest back) is
  ``ORDER BY next_starts_at NULLS LAST, starts_on DESC``.

## 2026-08-30 - one read per page, events and datepolls

The details pages asked five and three times for one thing. Measured
back to back on the same database, 10x, one worker:

| page | requests | p50 c=1 | p50 c=8 |
|---|---|---|---|
| event details, before | 6 | 57 | 347 |
| event details, after | 2 | 38 | 201 |
| datepoll details, before | 4 | 58 | 465 |
| datepoll details, after | 2 | 50 | 322 |

* **The saving is the repeated access work, not the queries.** Each
  request re-bound the tenant and re-checked the chapter scope before
  answering. The event page is 22 queries where the five reads were 36,
  and the datepoll page 10 where three were 16.
* **What is left on the datepoll page is its payload**: 1,203
  submissions, 184 KB, because the grid draws one row per person.
* `event list` is 511 KB for 1,200 live events and the browser filters
  it. Real organisations archive, and the archive is its own endpoint,
  so at a realistic 120 it is 51 KB. Unbounded either way.

## 2026-08-30 - three volumes

`--reset --fill --scale N`, so the three runs are independent rather
than cumulative. 10x is 1,200 events on 2,400 dates, 48k signups, 20k
form submissions on 90k answers, 1,200 datepoll answers, 5,500 shifts.

p50 alone, and at eight organisers at once:

| page | 1x | 3x | 10x | 10x, c=8 |
|---|---|---|---|---|
| compass details | 134 | 172 | **437** | 1036 |
| roster details | 150 | 228 | **330** | **2932** |
| event details | 115 | 140 | 136 | 944 |
| datepoll details | 89 | 63 | 132 | 963 |
| form details | 55 | 63 | 125 | 442 |
| dashboard | 46 | 57 | 102 | 580 |
| users | 36 | 55 | 54 | 423 |
| form list | 32 | 29 | 30 | 181 |
| compass list | 26 | 30 | 34 | 201 |

* **Two pages grow with the data; the rest do not.** Every list is flat
  from 120 events to 1,200. Those reads are indexed for the shape they
  ask, so a chapter ten times older opens just as fast.
* **`compass details` is the steepest**, 134 ms to 437. It re-derives
  every dot on the map on every load, so it is linear in answers and in
  nothing else.
* **`roster details` is the worst under load**, 2.9 s at eight
  organisers. Its schedule replays the roster from its first day, so it
  is linear in the roster's age: 15 ms at six months old, 41 ms at ten
  years, showing the same 78 rows either way. Four of that endpoint's
  eight queries feed the replay rather than the page.
* **`event details` is flat at 136 ms** and still third slowest,
  because its cost is six requests rather than any one of them: the
  session, the event, its occurrences, one occurrence's signups, that
  occurrence's stats, the feedback summary. Five are about the same
  event. The fix is fewer requests, not faster ones.
* **No single endpoint is slow.** The worst read on the busy database
  is 68 ms (`compass summary`); the worst page is five times that.

## Endpoints, 2026-08-30, at 1x

| endpoint | p50 c=1 | p50 c=8 | p50 c=32 | rps c=32 |
|---|---|---|---|---|
| auth/me | 15 | 87 | 253 | 126 |
| form public | 15 | 87 | 275 | 117 |
| chapters | 16 | 81 | 306 | 108 |
| compass public | 18 | 91 | 310 | 107 |
| form list | 19 | 93 | 311 | 107 |
| form details | 22 | 120 | 346 | 89 |
| compass details | 24 | 134 | 404 | 86 |
| event occurrences | 24 | 153 | 427 | 78 |
| datepoll summary | 24 | 134 | 386 | 82 |
| datepoll csv | 24 | 142 | 394 | 81 |
| roster details | 24 | 123 | 481 | 74 |
| event feedback csv | 24 | 123 | 376 | 89 |
| form submissions | 25 | 147 | 397 | 75 |
| compass submissions | 25 | 139 | 444 | 71 |
| chapter agenda | 25 | 125 | 426 | 82 |
| event details | 26 | 146 | 424 | 75 |
| roster accountability | 28 | 156 | 450 | 75 |
| event list | 29 | 158 | 483 | 72 |
| form summary | 30 | 130 | 406 | 76 |
| event feedback-summary | 31 | 158 | 458 | 66 |
| roster schedule | 37 | 226 | 605 | 54 |
| form csv | 47 | 199 | 554 | 63 |
| compass csv | 62 | 225 | 704 | 47 |
| compass summary | 68 | 231 | 768 | 42 |

The roster rows understate it: this ran while the seeded roster was
still forming, and a forming roster skips the projection that is most
of its work. `--fill` starts it now.

## Earlier, on a demo database

These predate the fill, so only the form, quiz and kompas rows mean
anything: those tables were the only ones with data in them. Kept for
the deltas they record, not for their absolute numbers.

**2026-08-29, the `/submissions` reads stopped pivoting.** They built a
map of every answer per submission to serve a popover that wants four
fields. Form 65 ms to 32, kompas 93 to 30, and 20 rps to 60 at c=32.
The endpoint is now one `SELECT` of four columns.
`services/form_answers` had no callers left and is gone.

**2026-08-29, the CSV went out in chunks.** The first cut yielded one
row per `yield`, which is one ASGI message and one write each. A
500-row export took 171 ms against the 24 the statement takes.
Gathering 64 KB first: 53 ms, and the download then cost less than the
JSON read it replaced.

**2026-08-29, the arithmetic moved into SQL.** Quiz marking and the
kompas' coordinates and axis statistics stopped being Python folds over
every stored answer. Query counts fell across the forms endpoints (7 to
5, 9 to 7) and `tests/test_query_budget.py` was ratcheted to match.
