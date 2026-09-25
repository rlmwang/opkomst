# 09: The PDF: brand service split, dependency group, image stage

Design: `docs/design-manual.md` chapter 8. Four pieces, in this
order, each committable alone.

## 1. The brand service reads settings at call time

`services/brand.py` builds `_PUBLIC_BASE` from `settings` at import
and reads the ad ids and support links in `_ads` and `payload`. Move
the base into `asset_url` and `payload` as local reads, so `manifest`
and `palette_css` import nothing from `config`. Add a static check to
`tests/test_privacy.py`'s neighbourhood (a new `tests/test_imports.py`
if it does not fit): the module has no top-level `settings.` reference.
Existing brand tests pass unedited.

## 2. The dependency group

`pyproject.toml`: `[dependency-groups] manual = ["weasyprint>=63"]`.
`uv lock`. The runtime's `uv sync --frozen --no-dev` does not install
groups; the build stage below syncs `--group manual`. Nothing in
`backend/` outside the entry point imports WeasyPrint.

## 3. The entry point

`backend/manual_pdf.py`, run as `python -m backend.manual_pdf <out-dir>`:

- imports `services.manual`, `services.brand` (the folder half),
  `jinja2` and `weasyprint`. Never `config`, never `database`, never
  `cli`.
- for each folder in `brands/` and each language: render
  `templates/manual-print.html` (the chapter HTML for that brand's
  audience, house brand meaning `all`, any other meaning
  `organisation`) with the print rules from task 07's sheet plus the
  page rules: A4, 20mm margins, 11pt body on a 65-character measure,
  ragged right, `break-before: page` on each chapter, a running footer
  with chapter title left and `counter(page)` right, and a table of
  contents whose numbers are `target-counter(attr(href), page)`.
- cover: the brand's logo and wordmark from the manifest, the word
  Handleiding or Manual, the app's name, and the month from
  `datetime.now()` at build time.
- writes `<out-dir>/{brand}/handleiding.pdf` and `manual.pdf`. The
  house brand's files go to `<out-dir>/handleiding.pdf` and
  `manual.pdf` as well, since the root serves them without a prefix.
- fonts: the print sheet names one family from the apt package the
  stage installs (`fonts-dejavu-core` is the smallest that covers
  Dutch and English; pick it unless the brand manifest names another).

## 4. The Docker stage and serving

`Dockerfile`: a third stage between the two that exist:

```
FROM python:3.13-slim AS manual-builder
COPY --from=ghcr.io/astral-sh/uv:0.5.4 /uv /usr/local/bin/
RUN apt-get update && apt-get install -y --no-install-recommends \
      libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-install-project --no-dev --group manual
COPY backend/ ./backend/
COPY brands/ ./brands/
RUN uv run --no-dev --group manual python -m backend.manual_pdf /app/pdf
```

The runtime stage adds `COPY --from=manual-builder /app/pdf ./frontend/dist/manual/`
beside the bundle copy. The runtime apt line does not change.

`routers/manual.py` serves `/handleiding.pdf`, `/manual.pdf` and
`/{tenant}/handleiding.pdf`, `/{tenant}/manual.pdf` from that folder
with the built assets' cache headers, and the index page's link from
task 07 now resolves. In local mode with no built PDF the route is
404 and the dev server proxy list in `vite.config.ts` gains the paths.

## CI

`.github/workflows/ci.yml`: the backend job installs the three Pango
packages and the font before `uv run pytest`, and syncs `--group
manual`, so the one test that imports WeasyPrint runs. The Docker
build job already builds the image and therefore the stage.

## Tests

- `tests/test_manual_pdf.py`: `manual_pdf` writes a file per brand
  and language into a temp dir; each starts with `%PDF`; the house
  brand's Dutch file has more pages than chapters (read the page
  count with `pypdf` if already present, otherwise count `/Type /Page`
  objects); the organisation file has three chapters more. Marked
  with the same marker the slow suites use.
- `tests/test_imports.py`: `backend/manual_pdf.py` and
  `services/brand.py`'s folder half import nothing from `config`.
- A route test that the four PDF paths answer 200 with
  `application/pdf` when the folder holds a file and 404 when it does
  not.

**Done when:** `docker build` produces an image whose `/app/frontend/dist/manual/`
holds six PDFs (three brands, two languages) and whose runtime layer
has no Pango; `uv run pytest` passes in CI with the apt line; the
index page's download link works on a deployed build.
