# Benchmarks

What the read endpoints cost, and where the time goes. Kept as a log:
one section per run, newest first, so a change that costs something
shows up against the run before it.

## Running one

```bash
make db-up
set -a && source .env && set +a
LOCAL_MODE=1 uv run uvicorn backend.main:app --port 8000        # one shell
uv run python scripts/bench.py --fill --levels 1,8              # another
```

Two tables come out.

**Pages** is what somebody waits for. A screen is not one request: an
organiser opening an event fires six at once and waits for the slowest,
and under load those six compete with each other as much as with
anybody else's. Every page counts `/auth/me`, because the route guard
resolves the session before the page paints.

**Endpoints** is what one read costs on its own. That is where a
regression gets diagnosed once a page has shown one.

`p50` and `p95` are milliseconds. `rps` is requests (or page loads) per
second at that concurrency.

## The data it runs against

`--fill` tops every table up to the `BUSY` profile in `scripts/bench.py`:
two years of a chapter, 120 events on 240 dates, 20 signups on each,
feedback from 7 of them, 500 answers per form, 60 people on a datepoll,
520 shifts on the roster.

Filling matters more than it sounds. The seeded dev database is a demo:
eight events, nine signups, three datepoll answers. Every read that
joins to those tables looks free against it, and Postgres picks plans
for tables that fit on one page. Until 2026-08-30 everything here
except the forms was measured against that demo, so the event, roster,
datepoll and feedback rows in the older runs below say nothing.

`--fill` also runs `ANALYZE` afterwards, which is worth an afternoon of
wrong answers on its own: without it the planner works from statistics
gathered when the tables were empty, every read looks slow, and the
ranking that comes out is an artefact of the load rather than of the
code.

## What the numbers cannot tell you

The load generator is one Python process running async httpx, so it has
a ceiling of its own. On the machine below, `/health` (no database, no
work) tops out at **300 rps** and costs **7 ms** at concurrency 1. Any
endpoint measured near 100-150 rps is therefore within a factor of two
or three of the harness, not necessarily of the app, and the flattening
of `rps` between c=8 and c=32 is partly the client running out of core.

Read the p50 column for what an endpoint costs, and the rps column only
as a rough shape. Proving a real server-side ceiling needs a load
generator on another machine.

## 2026-08-30 - first run against a busy database

Machine: 12th Gen Intel i5-1235U, 12 cores, 15 GB, Postgres 16.13,
Python 3.14.5. One uvicorn worker. The `BUSY` profile above. Same-run
repeats move by 20-30% on a laptop, so read a change of less than that
as noise.

Pages, which is the number that matters:

| page | requests | p50 c=1 | p50 c=8 | loads/s c=8 |
|---|---|---|---|---|
| compass list | 2 | 27 | 179 | 45 |
| form list | 2 | 29 | 191 | 43 |
| users | 3 | 39 | 221 | 33 |
| dashboard | 3 | 51 | 436 | 18 |
| form details | 3 | 57 | 377 | 21 |
| datepoll details | 4 | 79 | 523 | 15 |
| compass details | 3 | 97 | 532 | 15 |
| roster details | 5 | 136 | 1169 | 7 |
| event details | 6 | 153 | 862 | 9 |

Endpoints, same database:

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

### What this run said

* **No single endpoint is slow. Pages are, by adding up.** The worst
  read on the busy database is 68 ms; the worst page is 153, because it
  is six reads deep. Nothing on the endpoint table would have found
  that.
* **`event details` fires six requests**: the session, the event, its
  occurrences, one occurrence's signups, that occurrence's stats, and
  the feedback summary. Five of them are the same event. That is the
  page to fix, and the fix is fewer requests rather than faster ones.
* **`roster details` fires five** and is the slowest under load: 1.2 s
  at eight organisers. Both roster rows understate it: the seeded
  roster was still forming when this ran, and a forming roster skips
  the projection that is most of the work. `--fill` starts it now.
* **`roster schedule` recomputes rather than reads.** Its outlook is a
  replay of the roster from its first day: every date the pattern ever
  produced, every ledger event, then the rotation rule applied to what
  is not pinned yet. Four of its eight queries feed that replay rather
  than the page. It costs 15 ms on a roster six months old and 41 ms on
  one ten years old, showing the same 78 rows either way.
* **Filling the events changed almost nothing on the endpoint table.**
  `event list` went from 39 ms to 29 with fifteen times the events,
  which is noise: those reads were already indexed for the shape they
  ask. The demo database was hiding nothing there. It was hiding the
  page cost, which only shows when the requests are timed together.

## 2026-08-29 - after the `/submissions` reads stopped pivoting

Same machine and same 500 submissions per form as the run below. One
uvicorn worker.

| endpoint | p50 c=1 | p50 c=8 | p50 c=32 | rps c=32 |
|---|---|---|---|---|
| chapters | 16 | 84 | 276 | 113 |
| auth/me | 17 | 84 | 306 | 113 |
| form public | 19 | 101 | 280 | 116 |
| form list | 21 | 99 | 306 | 109 |
| chapter agenda | 23 | 131 | 397 | 86 |
| event feedback csv | 24 | 137 | 356 | 89 |
| form details | 26 | 105 | 407 | 77 |
| roster details | 26 | 133 | 425 | 75 |
| event occurrences | 27 | 167 | 493 | 63 |
| compass details | 28 | 127 | 467 | 69 |
| datepoll csv | 28 | 142 | 429 | 74 |
| event details | 29 | 155 | 640 | 53 |
| datepoll summary | 30 | 157 | 431 | 72 |
| **form submissions** | 32 | 204 | 799 | 39 |
| **compass submissions** | 30 | 181 | 535 | 60 |
| roster accountability | 32 | 179 | 493 | 65 |
| form summary | 33 | 127 | 434 | 73 |
| event feedback-summary | 36 | 211 | 547 | 60 |
| event list | 39 | 164 | 433 | 78 |
| roster schedule | 44 | 256 | 625 | 49 |
| form csv | 62 | 231 | 658 | 48 |
| compass summary | 80 | 261 | 763 | 45 |
| compass csv | 82 | 224 | 568 | 59 |

### What this run said

* **The two `/submissions` reads halved.** They pivoted every answer in
  Python to serve a popover that wants four fields. Form: 65 ms to 32.
  Kompas: 93 ms to 30, and 20 rps to 60 at c=32. The endpoint is now
  one `SELECT` of four columns, 4 queries against 5 and 6.
* `services/form_answers` had no callers left afterwards and is gone.
* **The slowest reads are now `compass summary` and `compass csv`**, at
  80 ms each. Both walk the same statement: every answer poled, meaned
  per axis, once for the map and once per exported row.
* `roster schedule` at 44 ms is unchanged.

## 2026-08-29 - after the SQL rewrites and the streamed CSV

Machine: 12th Gen Intel i5-1235U, 12 cores, 15 GB, Postgres 16.13,
Python 3.14.5. 500 submissions per form. Local loopback, no
compression, no proxy: production sits behind Traefik with
`compress=true`, so the wire numbers there are smaller and the CPU
numbers are the same.

One uvicorn worker:

| endpoint | p50 c=1 | p50 c=8 | p50 c=32 | rps c=32 |
|---|---|---|---|---|
| auth/me | 17 | 86 | 229 | 147 |
| chapters | 17 | 83 | 259 | 122 |
| form public | 15 | 84 | 257 | 126 |
| form list | 21 | 113 | 319 | 98 |
| event list | 23 | 126 | 345 | 91 |
| form details | 22 | 127 | 351 | 95 |
| chapter agenda | 24 | 123 | 396 | 80 |
| roster details | 26 | 155 | 406 | 77 |
| event occurrences | 29 | 157 | 474 | 70 |
| datepoll summary | 32 | 155 | 539 | 65 |
| form summary | 32 | 138 | 426 | 75 |
| event details | 38 | 210 | 576 | 56 |
| event feedback-summary | 39 | 237 | 673 | 48 |
| roster accountability | 35 | 196 | 704 | 50 |
| roster schedule | 43 | 328 | 796 | 40 |
| compass summary | 82 | 273 | 768 | 46 |
| **form csv** | 53 | 215 | 537 | 58 |
| **compass csv** | 99 | 267 | 609 | 55 |
| **datepoll csv** | 25 | 146 | 409 | 77 |
| **event feedback csv** | 24 | 139 | 510 | 67 |
| form submissions (JSON) | 65 | 449 | 1046 | 31 |
| compass submissions (JSON) | 93 | 691 | 1713 | 20 |

Three workers, the production shape, same machine: within noise of the
one-worker run on every endpoint, because the harness saturates first.
Worth re-running against a real load generator before drawing anything
from it.

### What this run said

* **Batching the CSV was worth 3x.** The first cut yielded one row per
  `yield`, which is one ASGI message and one write each. A 500-row form
  export took 171 ms while the statement behind it takes 24. Gathering
  64 KB before handing it over: 53 ms. `services/csv_export`.
* **The download now beats the JSON read it replaced**, 53 ms against
  65 for the same 500 rows, and holds up better under load (58 rps
  against 31 at c=32). The JSON `/submissions` endpoints still pivot in
  Python and are the slowest reads in the app.
* **`compass csv` is the expensive one** at 99 ms: it nests the
  positions statement as a CTE, so every row carries the map's
  arithmetic beside its answers.
* **`roster schedule` is the slowest of the reads.** Untouched so far.
