# Design: rich-text details field

Status: proposed. Lets organisers format the "details" body of an entity
(the event `topic`, the form / datepoll / roster `description`) with
**bold, italic, underline, strikethrough, and links**, stored as
sanitized HTML. The whole design turns on one security property: every
write funnels through a single server-side sanitizer, so nothing a
malicious or compromised organiser types can become executable script on
a public page. It also **centralises the public top card** (hero, title,
meta, details) into one shared component, since the details now render
through it (see Shared public top card).

## Scope

- **Marks**: bold, italic, underline, strikethrough, hyperlink. Nothing
  else (no headings, images, tables, colours, lists) unless asked for
  later. A small, closed set keeps the sanitizer allowlist tight and the
  toolbar obvious.
- **Fields**: the four entity-level bodies, all currently the shared
  `Description` type:
  - events `topic` (`schemas/events.py`)
  - forms `description` (`schemas/forms.py:72`)
  - datepolls `description` (`schemas/datepolls.py:62`)
  - rosters `description` (`schemas/chores.py:60`)
- **Not** the per-chore `ChoreIn.description` (`schemas/chores.py:36`),
  a short per-task label that stays plain text. So `Description` (plain,
  capped) survives for that one field; the four bodies move to a new
  `RichText` type (below).

## Storage format: sanitized HTML, not Markdown

We store **sanitized HTML**. Reasoning, in order of weight:

1. **Underline has no Markdown.** The requested mark set includes
   underline, which CommonMark cannot express; we would end up with
   HTML-in-Markdown anyway, which is the worst of both to sanitize.
2. **The editor is WYSIWYG**, not a Markdown textarea. Organisers click
   a bold button; the natural output of a rich-text editor is HTML.
   Round-tripping through Markdown adds a lossy conversion for no gain.
3. **One render path.** The public pages already render an HTML page;
   dropping a sanitized fragment in is a `v-html`, with no Markdown
   parser shipped to four deliberately-lean mini-apps (see Rendering).

HTML is safe at rest here **because it is sanitized on write** (next
section), so "store Markdown because it's inert" buys nothing: our stored
HTML is equally inert, and skips a parse step on every render.

## Sanitization: the security core

**Single chokepoint.** All formatting is sanitized **server-side, on
write, at the schema boundary**, and never anywhere else. Client output
is never trusted; the editor is a convenience, the sanitizer is the
authority.

New `RichText` type in `backend/schemas/common.py`, mirroring how
`Description` / `DisplayName` centralise a contract so the four fields
cannot drift:

```python
RichText = Annotated[
    str | None,
    Field(default=None, max_length=8000),      # raw-HTML ceiling (markup inflates)
    AfterValidator(sanitize_richtext),          # strip to the allowlist
]
```

The four body fields switch from `Description` to `RichText`. Because
every write path (`create_*` / `update_*` in the events / forms /
datepolls / chores routers, plus `services/chores.py` for the roster)
takes these Pydantic models, the sanitizer runs on **every** create and
update with no per-router code. A static test asserts the four fields are
typed `RichText` so a new field can't silently skip it.

**`backend/services/sanitize.py`** wraps **`nh3`** (Rust `ammonia`
bindings; a new backend dependency, added to `pyproject.toml`):

```python
import nh3

_ALLOWED_TAGS = {"p", "br", "strong", "em", "u", "s", "a"}
_ALLOWED_ATTRS = {"a": {"href"}}

def sanitize_richtext(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = nh3.clean(
        value,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRS,
        url_schemes={"http", "https", "mailto"},   # kills javascript:/data:
        link_rel="nofollow noopener noreferrer",    # forced on every <a>
        clean_content_tags={"script", "style"},     # drop content, not just the tag
    )
    cleaned = cleaned.strip()
    return cleaned or None
```

What this guarantees:

- **Tag allowlist**: only the five marks plus `p`/`br` survive. Any other
  tag is removed; `script` / `style` have their *contents* dropped too
  (not merely unwrapped), closing the classic `<script>alert()</script>`
  and `<style>` exfiltration holes.
- **Attribute allowlist**: only `href` on `<a>`. No `style`, `class`,
  `id`, `onclick`, `onerror`, or any `on*` handler can land in storage.
- **URL scheme allowlist**: `href` is restricted to `http` / `https` /
  `mailto`, so `javascript:`, `data:`, and `vbscript:` URLs are stripped.
- **Forced `rel`**: every link gets `nofollow noopener noreferrer`, so an
  organiser link can't `window.opener`-hijack or pass referrer/pagerank.
- **Idempotent + total**: sanitizing already-clean output is a no-op, and
  there is no code path that stores an unsanitized body.

**Visible-length cap.** The `max_length=8000` bounds raw markup; the
user-facing limit stays the ~2000 *visible* characters people already
reason about. `sanitize_richtext` (or a sibling validator) measures
`len(html_to_text(cleaned))` and rejects over 2000, so heavy formatting
can't sneak past a raw-length check. (This supersedes the plain
`Description` 2000 cap on these four fields.)

**Defense in depth (recommended, not required):** serve the app with a
`Content-Security-Policy` of at least `script-src 'self'` on the public
HTML responses. Even a hypothetical sanitizer bypass then cannot execute
an inline `<script>` or `on*` handler. Worth adding regardless of this
feature; called out here because rich text is the first user content that
reaches `v-html`.

## Rendering

**Public mini-apps.** Replace the escaped interpolation with a
`v-html` of the already-sanitized body, wrapped for styling:

```html
<!-- was: <p v-if="event?.topic" class="event-topic">{{ event.topic }}</p> -->
<div v-if="event?.topic" class="richtext" v-html="event.topic"></div>
```

This is safe **because the value was sanitized on write** and the public
render path is the only consumer. We deliberately do **not** ship a
client-side sanitizer (DOMPurify) or Markdown parser to the four public
bundles: that would cut against the documented lean-bundle convention
(`public/i18n.ts:1-11`, `public/main.ts:1-4`, "no router, no Pinia, no
PrimeVue, no vue-i18n"). The server sanitizer is the single source of
truth; the mini-apps trust it, and tests enforce it. Same `v-html`
swap in `public_form`, `public_datepoll`, `public_chore`.

- New shared `.richtext` CSS in `theme.css` (inside `@layer app`): normal
  weight, `line-height: 1.5`, styled `a` (underlined, brand colour),
  `p` spacing, and `u` / `s` rendering. Drop the current blanket
  `font-style: italic` on `.event-topic` (`PublicEvent.vue:720`): with
  real italics available, force-italicising the whole body is wrong. The
  `white-space: pre-line` newline hack goes away for these fields, since
  `<p>` / `<br>` now carry the line breaks. The resolved body treatment
  (which of the two current styles wins) is settled under Shared public
  top card below.

**Admin previews** (`EventDetailsPage.vue`, the form / datepoll / chore
details pages) render the same body: swap their `{{ description }}` /
`{{ topic }}` for the same `v-html="…"` + `.richtext` treatment. These
run inside the admin SPA, still rendering server-sanitized HTML.

## Shared public top card

The four public pages each hand-roll the header that sits above the fold
(hero, title, meta, details), and they have drifted apart. The details
rendering above only lands cleanly if that header is one component, so
this feature also **centralises the top card**. This is the biggest
visible payoff: today the same information looks different on every page.

### Where they diverge today

| | Event | Form | Datepoll | Chore |
|---|---|---|---|---|
| wrapper | `.card.event-header` (hero inside, `position:relative`) | `.card.title-card` | `.card.title-card` | hero **outside**, then `.card.stack` |
| title | `.event-title h1` 1.5rem | bare `h1` | bare `h1` | global `h1` |
| details | `.event-topic` italic, 1.0625rem | `.muted` 0.875rem | `.muted` 0.875rem | `.muted` 0.875rem |
| meta | `dl.event-meta`: date, time-range, location (icon rows) | none | ad-hoc brand-red `.location` link | none |
| hero margin | cancelled | intact | intact | intact (floats above card) |

Two things the request calls out: the event **details** are force-italic
and cramped, while the datepoll details (`.muted`, upright, readable) are
the ones to keep; but the event **info layout** (the icon `dl` meta, the
1.5rem title) is the one to keep. So we merge: datepoll's text treatment
for the body, the event's structure for everything around it.

### `public_shared/PublicTopCard.vue`

One shared component wraps the hero, title, details, and a meta slot:

```html
<PublicTopCard
  :image-url="…" :artist="…" :credit-label="…"
  :title="event.name"
  :description-html="event.topic"   <!-- pre-sanitized; rendered via .richtext v-html -->
>
  <template #meta> …entity-specific meta rows… </template>
  <template #actions> …event-only "add to calendar" popup… </template>
</PublicTopCard>
```

- **Wrapper**: a single `.top-card` (the global `.card` + `flex column`,
  `gap: 1rem`, `position: relative` for the actions popup). The hero
  renders **inside** it for all four, with its `margin-bottom` cancelled
  (today only the event does this). That alone fixes the chore's hero
  floating outside its card.
- **Title**: the event treatment for everyone, `h1` at `1.5rem`,
  `line-height: 1.25`, `overflow-wrap: anywhere`.
- **Details**: the shared `.richtext` body (see Rendering). Its resolved
  style is the **datepoll treatment de-italicised**: upright,
  `line-height: 1.5`, muted colour, at a readable body size (~1rem). The
  event's `font-style: italic` and the `.muted` 0.875rem shrink are both
  dropped; one rule now governs the details text on all four pages, the
  admin previews, and the agenda cards.
- **Meta**: an optional `#meta` slot rendered as the event's
  `dl`-of-icon-rows pattern, extracted to a tiny
  `public_shared/PublicMetaRow.vue` (icon slot + content) plus one shared
  `.meta-link` style (the event's inherit-colour + external-icon
  treatment). Each page fills only the rows it has:
  - **Event**: date, time-range, location.
  - **Datepoll**: location only, now an event-style meta row instead of
    the bespoke brand-red `.location` anchor.
  - **Form / Chore**: no meta, slot empty.
- **Actions**: an `#actions` slot for the event-only calendar popup;
  the other three pass nothing.

### CSS home

- `.richtext` and `.meta-link` become **global** rules in `theme.css`
  (`@layer app`), because `v-html` content can't be reached by scoped
  styles and because the admin previews and the agenda cards render the
  same markup.
- `.top-card` / `.meta-row` structure lives in the `PublicTopCard` /
  `PublicMetaRow` scoped CSS.
- The per-file `.event-header`, `.event-title`, `.event-topic`,
  `.event-meta`, `.title-card`, `.location`, and the scoped `.meta-link`
  overrides are **deleted** from the four pages; nothing renders a header
  by hand anymore.

### Reach: sign-up, secret-edit-link, admin details

The four public mini-apps each serve **two** modes from one component:
the sign-up / fill page and the secret-edit-link page (the token rides
as `?s=` on the same URL, so there is no separate file). The header
block renders in both modes, so moving it to `PublicTopCard` standardises
all eight public surfaces at once.

The same `PublicTopCard` is reused on the **four admin details pages**
(`EventDetailsPage`, `FormDetailsPage`, `DatepollDetailsPage`,
`ChoresDetailsPage`): it is a pure props + slots component (no i18n, no
PrimeVue), so it drops straight into the admin SPA. Content differences
(share buttons, archived badge, back link, stats) live in the `#actions`
/ `#meta` / `#title-extra` slots; placement and styling are shared. The
admin details description switches from escaped `{{ }}` to the same
`.richtext` `v-html`, so it renders formatting instead of raw tags.

### Agenda reuse

The chapter-agenda `EventCard` (see `docs/design-chapter-agenda.md`)
reuses the same primitives: `PublicHero`, the global `.richtext` for a
card's topic, and `PublicMetaRow` for its date/location line. So the
grid cards and the full top card read as one system, and the "one
consistent 4:5 hero" work (commit `524c81f`) extends to one consistent
header.

## Plaintext projections

Three server surfaces and one client surface consume the body as **plain
text** today. Each gets an HTML-to-text pass so tags don't leak as
literal `<strong>` noise:

- **`backend/services/sanitize.py::html_to_text(html) -> str`**: a small
  `html.parser`-based stripper (no new dep) that unwraps tags and turns
  `</p>` / `<br>` into newlines, then unescapes entities. Used by:
  - **OG / head meta** (`spa.py` `_build_head_meta` and the datepoll /
    roster siblings): `description = html_to_text(event.topic)` before it
    reaches `_og_head` (which still HTML-escapes for the attribute), so
    link previews show clean text, still truncated at 200.
  - **Event ICS** (`services/ics.py:93-97`): wrap `event.topic` in
    `html_to_text` before the RFC-5545 `_escape`, so calendar entries
    read as prose.
  - **Reminder email** (`mail_templates/{nl,en}/reminder.html:13`): pass
    `html_to_text(event.topic)` into the template context
    (`mail_lifecycle.py:177`). Email stays plain-text topic (autoescaped),
    the safe and portable choice across mail clients; the template markup
    is unchanged.
- **Client Web Share** (`PublicEvent.vue:224`, builds the native-share
  string from the raw topic): strip tags with the browser's own
  `DOMParser` (`new DOMParser().parseFromString(html, "text/html").body.textContent`),
  a zero-dependency `stripHtml` helper in `public_shared`. No sanitizer
  needed: this produces a string, never HTML.

## Editor

A **shared `frontend/src/components/RichTextField.vue`** replaces the
`<Textarea>` for the details field on all four admin edit pages
(`EventFormPage.vue` and the form / datepoll / chore editors), `v-model`
bound like the current textarea. It renders a small toolbar (bold,
italic, underline, strikethrough, link) over an editable region, loads
the stored HTML for re-editing, and emits HTML on change. It lives in the
admin SPA only; **no editor code reaches the public bundles**.

Link UX: a toolbar link button over a text selection opens a tiny inline
input for the URL (default `https://`), sets the mark, and offers unlink.
Malformed or non-http(s)/mailto URLs are dropped server-side regardless.

**Editor library (open decision):**

- **Tiptap** (ProseMirror), `StarterKit` trimmed to bold/italic plus the
  `Underline`, `Strike`, and `Link` extensions. Emits exactly
  `<strong> <em> <u> <s> <a>`, so its output already matches the
  allowlist and the server sanitize is a formality/backstop, not a
  reshaper. Full control, headless styling. Cost: several
  `@tiptap/*` + `prosemirror-*` packages in the admin bundle
  (lazy-loaded per route). **Recommended** for output cleanliness.
- **PrimeVue `Editor`** (Quill). Reuses the PrimeVue we already ship but
  pulls in `quill` + its CSS, and its toolbar/output need trimming to the
  five marks. Lighter integration story, heavier runtime, less precise
  output.

Either way the server sanitizer is unchanged and authoritative; the
choice only affects the admin bundle and toolbar ergonomics.

## Data & migration

- **No model change.** `topic` / `description` are already unbounded
  `Text`; storing HTML needs no column change.
- **One data migration, no schema change**: convert existing plain-text
  bodies to valid sanitized HTML so every stored value is uniformly
  renderable via `v-html`. `plaintext_to_html(s)` = HTML-escape, then map
  blank-line-separated paragraphs to `<p>` and single newlines to `<br>`,
  then run `sanitize_richtext`. Pre-launch, so this is a clean one-shot
  over whatever seed rows exist; `downgrade` is a no-op (the HTML renders
  fine as text too). Idempotency pinned by the usual
  `downgrade base; upgrade head; upgrade head`.

## Tests

- **XSS matrix** (`tests/`, against `sanitize_richtext`): each of
  `<script>alert(1)</script>`, `<img src=x onerror=alert(1)>`,
  `<a href="javascript:alert(1)">`, `<a href="data:text/html,...">`,
  `<b onclick=...>`, `<style>...</style>`, an unclosed / mutated-XSS
  payload, and an SVG/`foreignObject` payload produces output containing
  **only** allowlisted tags, no `on*` attribute, no non-http(s)/mailto
  `href`, and `rel="nofollow noopener noreferrer"` on every surviving
  link. Sanitizing the output again is a no-op.
- **Chokepoint / static**: the four body fields are typed `RichText`
  (so no write path skips the sanitizer); per-chore `ChoreIn.description`
  stays plain `Description`.
- **Projections**: `html_to_text` strips tags for OG meta, ICS, and the
  reminder email context; the 200-char OG truncation still holds; the
  Web Share string carries no tags.
- **Length**: a body whose visible text exceeds 2000 is rejected with the
  field-named 422 (which the edit page already surfaces as a localised
  "too long" toast).
- **e2e**: format a body (bold + a link) in the editor, save, open the
  public page, assert the marks render and the link carries the forced
  `rel`; confirm no script executes.
- **Top card**: all four public pages render through `PublicTopCard`
  (no page defines its own `.event-header` / `.title-card`); the details
  text resolves to the single `.richtext` style; the chore hero sits
  inside the card; the datepoll location renders as a meta row.

## Decisions taken

1. **Sanitized HTML at rest**, sanitized server-side on write via a
   shared `RichText` type; client HTML is never trusted. (confirmed)
2. **`nh3` allowlist**: five marks + `p`/`br`, `href`-only on `<a>`,
   http(s)/mailto schemes, forced `rel`, dropped script/style content.
   (confirmed)
3. **No client sanitizer or Markdown parser in the public bundles**;
   they `v-html` the pre-sanitized value. (confirmed, follows the
   lean-bundle convention)
4. **Rich text on the four entity bodies only**; per-chore item
   description stays plain. (confirmed)
5. **Plaintext projections** (OG, ICS, email, Web Share) strip to text.
   (confirmed)
6. **One shared `PublicTopCard`** across the four public pages: datepoll's
   details text treatment (upright, readable) + the event's info layout
   (icon meta rows, 1.5rem title), hero always inside the card. Deletes
   the four hand-rolled headers. (confirmed)

## Open decisions

1. **Editor library**: Tiptap (recommended, cleanest output) vs PrimeVue
   Editor / Quill (lighter integration). Admin bundle only.
2. **CSP**: add `script-src 'self'` to the public responses as
   defense-in-depth now, or track separately. Recommended now.
3. **Visible-length cap**: keep at 2000 visible characters (recommended,
   matches the number users already see) vs raise it, given markup
   consumes the raw budget.
