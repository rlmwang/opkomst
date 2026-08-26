# Keeping attention on the content

Status: proposal. Research summary plus a list of changes, none built.

The goal: someone who opens a sign-up link should read the event and
fill the form, and should not have their attention pulled sideways. The
page carries advertising in the periphery (`docs/ads.md`), so the
question is what makes the content the obvious target.

## Scope note

Everything below strengthens the content's pull. Nothing below reduces
an ad's rendered visibility: no opacity, no clipping, no pushing a unit
off-screen or under something else. An ad that renders where a human
cannot see it still counts as an impression, which is what invalid
traffic means and what gets an AdSense account closed. The two goals
happen to point the same way, because a page that holds attention on
its content is a page whose periphery goes unread on its own.

## What the research says

**Banner blindness is real and it is automatic.** Nielsen Norman
Group's eye-tracking work, originally on about 230 participants and
revisited over the following decade, found that people ignore anything
that looks like an ad or sits where ads usually sit. This is worth
stating plainly because it inverts the problem: our rails are in the
classic skyscraper position, so they are already being filtered out by
most readers without us doing anything. Effort spent making them less
visible would be effort spent on something the reader's visual system
already does.

**People scan headings, not paragraphs.** The layer-cake pattern is
fixations landing on headings and subheadings, with the body text
between them read only once a heading has caught interest. NN/G calls
it the most effective scanning pattern users have. The F-pattern, by
contrast, is what happens when there is nothing structural to land on,
and it is a failure mode rather than a target.

**Scanning follows the task.** Fixations concentrate on whatever serves
the thing the reader came to do. Someone who arrived from a WhatsApp
link came to sign up, so the closer the form is to the top and the
clearer the action, the less of the page competes.

**Whitespace increases comprehension.** A Wichita State usability lab
study, widely cited since, reported comprehension gains of up to 20%
from margins and paragraph spacing, at some cost in reading speed.
Padding around an element also concentrates attention on it, because
there is nothing adjacent to draw the eye away.

## What that implies for our pages

The periphery is already handled. The work is in the column.

### 1. One accent colour, one primary action

The brand accent is the only saturated colour in the palette
(`brands/*/tokens.css`). It should mark the thing the reader came to
do and nothing else. Any secondary control wearing it splits the target
in two.

Audit: `theme.css` gives `.p-button-secondary` accent-tinted hovers,
links are accent-coloured throughout the body copy, and the public
sign-up page has an accent submit button competing with accent links in
the disclosure card and the add-to-calendar control.

Change: keep the accent for the submit button and for genuine inline
links in prose. Take it off secondary buttons and off the chrome around
the form.

### 2. Shorter measure inside cards

The content column is 720px. At the body size that is roughly 90 to 100
characters a line, above the 50 to 75 that readability work converges
on. The column width is right for the page's layout, but the text
inside a card does not have to fill it.

Change: cap running prose at about 65 characters (`max-width: 34rem` at
the current body size) inside `.card`, leaving headings, form fields
and lists at full width. This is one rule in `theme.css` and it touches
every page at once.

### 3. Give the form's sections real headings

The sign-up page has two headings today, "Jouw aanmelding" and "Help
ons leren". The occurrence picker, the help question and the source
question sit under them without their own. Layer-cake scanning lands on
headings, so a section without one is a section that gets skipped or
read as part of the previous one.

Change: a heading per section on the public forms, at the `h2` size the
app now uses everywhere.

### 4. Raise the fold on the sign-up page

The image, the title, the date and the location come before the first
field. On a phone that can be an entire screen before anything
actionable appears, which puts the task below the fold for the one page
where the task is the whole point.

Change: cap the hero image's height on narrow viewports so the first
field is reachable within the first screen. `PublicHero.vue` fixes a
4:5 frame at up to 320x400; a `max-height` in the phone breakpoint
solves it without touching the desktop layout.

### 5. Quieten the chrome

The language switcher, the share cluster and the add-to-calendar
control are all above or beside the form and all compete for the first
fixation. None of them is what the reader came for.

Change: make them visually subordinate. Muted colour, no accent, no
border unless hovered. The disclosure card already does this correctly
and is a good model.

### 6. Keep the periphery boring

Already true and worth writing down so it stays true: the ad slot's
frame is a dashed muted outline, its empty state is muted text, and the
rails are pinned to the viewport edges rather than to the content, so
on a large display they sit hundreds of pixels out. No animation, no
sticky behaviour, no expansion.

## Two things that were considered and rejected

### A desaturated fade toward the edges

The idea: fade the background to something greyer near the ads, so the
periphery feels less like part of the app.

Rejected on two counts.

The pages that carry ads are already neutral. Measured from
`brands/opkomst/brand.json`, the only brand that ever shows one: the
background is 8.3% saturation, the border 6.5%, the accent 2.2%, the
muted text 1.7%. There is nothing to fade out. An organisation's
palette is saturated, but those pages carry no ads.

More importantly the theory points the other way. Salience is computed
from local contrast against the surround, colour included, and an
element pops out because it differs from what is around it. Desaturating
the field around a full-colour ad widens that difference and makes the
ad more conspicuous, not less. It is the same mechanism that makes a
sparingly used accent colour draw the eye. A vignette would also
introduce a luminance gradient, which is a new peripheral feature where
the aim was to have none.

What the same theory does support is distance and stillness, both of
which are already in place: acuity and colour discrimination fall off
with eccentricity, so a rail 380px out on a large display is barely
resolved, and the slot has no motion, which is the strongest capture
signal there is.

### A full-bleed header

Not rejected, fixed. `AppHeader` was a bar spanning the window, so on a
wide screen the logo and the menu sat at the far edges, which is exactly
where the rails are, while every organiser page below is a centred
720px column. Reading the header therefore meant looking out to the
margins and back.

The bar still spans the window for its background and its bottom rule,
but its contents are capped at 720px and centred, with horizontal
padding matched to `.container` so the logo lines up with the cards
below it. The two catalog pages already constrained their own headers
and needed no change.

## What to measure

None of this is worth guessing at. Two things are cheap to check:

- Time from page load to first interaction with a form field, which is
  the honest version of "did the reader find the task".
- Sign-up completion rate on public pages, before and after.

Both are countable without identifying anyone: a counter, not a
session. If a change does not move either, revert it.

## Sources

- [Banner blindness: the original eye-tracking research](https://www.nngroup.com/articles/banner-blindness-original-eyetracking/)
- [Banner blindness: ad-like elements divert attention](https://www.nngroup.com/videos/banner-blindness/)
- [The layer-cake pattern of scanning content on the web](https://www.nngroup.com/articles/layer-cake-pattern-scanning/)
- [F-shaped pattern of reading: misunderstood, but still relevant](https://www.nngroup.com/articles/f-shaped-pattern-reading-web-content/)
- [Scanning patterns on the web are optimized for the current task](https://www.nngroup.com/articles/eyetracking-tasks-efficient-scanning/)
- [Text scanning patterns: eye-tracking evidence](https://www.nngroup.com/articles/text-scanning-patterns-eyetracking/)
- [How white space affects comprehension and engagement](https://cieden.com/book/sub-atomic/spacing/white-space)
- [Readability research: an interdisciplinary approach](https://arxiv.org/pdf/2107.09615)
- [Visual salience (Scholarpedia)](http://www.scholarpedia.org/article/Visual_salience)
- [Bio-driven visual saliency detection with colour factor](https://www.frontiersin.org/journals/bioengineering-and-biotechnology/articles/10.3389/fbioe.2022.946084/full)
