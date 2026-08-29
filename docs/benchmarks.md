# Benchmarks

What the read endpoints cost, and where the time goes. Kept as a log:
one section per run, newest first, so a change that costs something
shows up against the run before it.

## Running one

```bash
make db-up
set -a && source .env && set +a
LOCAL_MODE=1 uv run uvicorn backend.main:app --port 8000        # one shell
uv run python scripts/bench.py --fill 500 --levels 1,8,32       # another
```

`--fill N` tops the seeded form, quiz and kompas up to N submissions
and runs `ANALYZE` afterwards. Skipping the analyze is worth an
afternoon of wrong answers: the planner picks a plan for the empty
table it last saw, every read looks slow, and the ranking that comes
out is an artefact of the load rather than of the code.

`p50` and `p95` are milliseconds. `rps` is requests per second at that
concurrency.

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
* **`roster schedule` is 11 queries** and shows it. Untouched so far.
