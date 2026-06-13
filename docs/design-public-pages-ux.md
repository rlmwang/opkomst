# Design: aligning the three public pages (events · forms · datepolls)

Status: proposed → implementing. The public sign-up/fill-out pages for
Events, Forms, and Datepolls drifted apart. **Events is the golden
standard**; Forms and Datepolls converge on it. This plan is the
checklist for that convergence — every row is a property the events
page has that the other two must match.

## The shared skeleton (from `src/public/PublicEvent.vue`)

```
<div class="container stack">              ← global theme classes, 720px, vertical rhythm
  <header class="public-header">           ← BrandMark (left) + language switcher (right)
    <BrandMark />
    <lang-switcher>🇳🇱 🇬🇧</lang-switcher>
  </header>

  <!-- state cards: load-failed / not-found / unavailable -->

  <div class="card …">  title + description (+ event meta)        </div>
  <div class="card …">  open-source / privacy disclosure (details) </div>
  <form class="card stack">
     pseudonym (top)  →  the body  →  error  →  submit (btn-primary + spinner)
  </form>
  <!-- on success: a single "thanks" card replaces the form -->
</div>
```

## Convergence checklist

| Property | Events (standard) | Forms (before) | Datepolls (before) |
|---|---|---|---|
| Root layout | `.container.stack` (global) | `.page` + own `.container` | `.wrap` (own) |
| Content width | 720px | 720px ✓ (just fixed) | 720px ✓ (just fixed) |
| Header | `public-header`: BrandMark **+ language switcher** | BrandMark, **no switcher** | **no BrandMark, no switcher** |
| Language switcher | 🇳🇱/🇬🇧 flag toggle, `setLocale` | ✗ | ✗ |
| Title block | name + description/topic in a card | name only, no description | name + description, but outside cards |
| Open-source disclosure | `details` card + GitHub link (**invariant**) | **absent** | one-liner, **no link** |
| Pseudonym field | `(Schuil)naam`, **at the top** of the form | **absent** | present but **at the bottom** |
| Cards | title card · disclosure card · one form card | card-per-question | ad-hoc `.card`/`.wrap` |
| Submit | `.btn-primary`, label+spinner, no resize | `.primary`, no spinner | `.submit`, no spinner |
| Success state | single "thanks" card | ✓ | ✓ |

## What each page changes

**Forms** (`src/public_form/`)
- Add the language switcher (flags + `setLocale`) to `public-header`.
- Show the form **description** under the name (new field, see
  `design-forms.md`).
- Add an optional **pseudonym field at the top** of the form
  (`(Schuil)naam`), posted as `display_name`.
- Add the **open-source disclosure** (a `details` card with the GitHub
  link) — currently missing entirely; the disclosure is a project
  invariant.
- Card usage: a title card, a disclosure card, and the questions +
  pseudonym + submit inside the form, matching the events grouping
  rather than a card-per-question.
- Submit button → the events `btn-primary` + spinner pattern.

**Datepolls** (`src/public_datepoll/`)
- Add `BrandMark` + the language switcher to a real `public-header`.
- Move the **pseudonym field to the top** (currently bottom).
- Title + description in a card; legend + calendar + date list + submit
  follow, using the same `.card` treatment as events.
- Add the **open-source disclosure** with the GitHub link (currently a
  link-less one-liner).
- Submit button → `btn-primary` + spinner.

**Events** — the reference; unchanged.

## Shared-code note

The three mini-apps deliberately ship without vue-i18n and re-declare
small chrome (`public-header`, `lang-switcher`, `flag`, `btn-primary`,
`.input`) per app. Two reasonable end-states:

1. **Hand-aligned** (this pass): copy the events markup + CSS into the
   other two. Fast, but consistency is maintained by vigilance.
2. **Extracted** (follow-up): a shared `PublicShell.vue` (header +
   lang switcher + disclosure slot) and a `usePublicLocale()` helper
   that all three import. Removes the drift structurally.

This pass does (1) to reach parity now; (2) is the clean follow-up once
the shape has settled, and is the recommended next step so a fourth
public page can't drift again.
