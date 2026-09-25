# 06: Front-matter module, manual service, chapter skeleton

Design: `docs/design-manual.md` chapters 4 and 5. Independent of the
tour. When this lands the chapters exist as data with their openings
written, and a service serves them by language and audience.

## The shared module

`backend/services/frontmatter.py`: the `key: value` parser lifted out
of `services/content.py::_parse` (the two `---` fences, the loop over
colon-separated lines, the required-keys check) as
`parse(path, required) -> tuple[dict[str, str], str]`. `content.py`
imports it and loses its own copy. No YAML. `tests/test_content.py`
passes unedited.

## The files

```
backend/manual/
  nl/01-inloggen.md … 14-mail.md
  en/01-signing-in.md … 14-mail.md
  nl/pictures/   en/pictures/      (task 08 fills these)
```

Front matter: `title`, `description`, `audience` (`all` or
`organisation`). Nothing else, and nothing optional. The number in
the file name is the order; the slug is the name after the dash.

For this task each file holds the front matter and the two-sentence
opening only. Task 10 writes the rest.

## The service

`backend/services/manual.py`:

- `Chapter`: frozen dataclass with `number`, `slug`, `title`,
  `description`, `audience`, `body`, `language`, and a cached `html`
  rendered with the same `markdown.Markdown(extensions=["tables",
  "attr_list"])` shape as `content.py`, on first read.
- `html_for(audience)`: the rendered HTML with every element carrying
  class `organisation` removed when `audience == "all"`. One pass with
  `html.parser`-level tooling already in the standard library, or a
  regex over `<p class="organisation">…</p>` if the note-box pattern
  proves that is the only shape; pick one and test it.
- `CHAPTERS: dict[str, tuple[Chapter, ...]]` per language, loaded at
  import; two files claiming one number raise, a missing front-matter
  line raises, a language missing a number the other has raises.
- `chapters_for(language, audience)`: the tuple with organisation
  chapters filtered out for `all`.
- `by_slug(language, slug)`.

## Reserved words

`services/slug.py::RESERVED_SLUGS` gains `handleiding` and `manual`.
While there, `q` and `i` are live top-level routes that are not
reserved today; add them in the same commit and say so in its body.

## Tests

`tests/test_manual.py`:

- every chapter parses; both languages have the same numbers; the
  audience flag is one of two values.
- the root tuple has no organisation chapter and the organisation
  tuple has three, at the end.
- `html_for("all")` contains no element with class `organisation`
  and `html_for("organisation")` keeps it, on a fixture chapter with
  one marked paragraph.
- `handleiding`, `manual`, `q` and `i` are reserved.
- `test_content.py` unedited.

**Done when:** `uv run pytest tests/test_manual.py tests/test_content.py`
is green, ruff is clean, and `content.py` no longer owns a parser.
