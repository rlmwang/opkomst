# Design: the manual (handleiding)

Status: proposal. Companion to `design-tour.md`, which produces the
pictures this manual is made of. The tour ships first; the manual's
text can be written alongside it, but its pictures cannot be shot
until the tour's overlay exists.

## 1. Premise

Somebody was made an organiser last week. They have the app open on
one half of the screen and want to know what happens when they press
the button, whether it can be undone, and who will see it. They will
read one chapter, not the book, and they may well print it, or forward
it to the person who runs the bar and does not want an app at all.

The manual is that book: fourteen short chapters, one per thing the
app does and one for when something goes wrong, each illustrated with
a picture per step. It is a PDF, with a cover, a table of contents and
page numbers, because that is what gets printed and forwarded. It is
also the same chapters as web pages, because a link to one chapter is
what the app's menu can offer and what somebody pastes into a group
chat, and because a page anyone can read is a page a search engine
can send them to. Both come from one set of files and one set of
pictures, and neither is written twice.

## 2. Principles

1. **One source, two renderings.** The chapters are markdown; the web
   pages and the PDF are made from them. Nothing is written for the
   PDF alone.
2. **A chapter is one task**, starts with what the thing is for in two
   sentences, and never depends on a chapter before it.
3. **The manual says what the screen says.** A button called Opslaan
   is "de knop Opslaan", in the language the reader is in.
4. **Every picture is a whole screen with one thing lit.** The
   picture is a tour step: the app as the reader sees it, with the
   control in question spotlit, never a crop of the control alone.
5. **Every chapter says how to tell it worked, and what to do if it
   did not.**
6. **The audience is the tenant.** An organisation's rendering has
   three chapters more, about chapters, users and mail, and a
   paragraph more where its screen differs. The root rendering has
   none of that, and so never mentions that an organisation version
   or a paid plan exists.
7. **Readable in the HTML that arrives.** No bundle, no script but the
   ad tag and the consent dialog it brings, on the house-brand pages
   only, like every other page that is read rather than used.
8. **Nothing is recorded.** No counters, no "was this helpful".

## 3. Research, and what follows from it

Read for this proposal in September 2026. The first seven are
peer-reviewed; the rest are guidance from government, a platform and
practitioners, and are marked as such. None of it is research on this
app or its organisers; chapter 3a says where the evidence is thin and
chapter 10 says what would be.

**People do not read manuals, and the ones that work know it.**
Carroll and Rosson's active user wants throughput and "learners at
every level of experience try to avoid reading". Their Guided
Exploration cards, each addressing "a particular functional goal that
users can understand on the basis of their understanding of office
tasks", each written "without reference to material covered on other
cards", each carrying "checkpoint information" and "error recovery
information", plus one general card for "What if something goes
wrong?", were "nearly 3 times as efficient" as the commercial
self-study manual, with better transfer afterwards. (Carroll and
Rosson, 1987)

*Consequence:* principles 2 and 5, and the eleventh chapter. Every
chapter is a card: one task, self-contained, with a checkpoint and a
way back.

**Minimalist instruction, stated as principles.** Van der Meij and
Carroll distilled that work into four principles for any manual:
choose an action-oriented approach; anchor the tool in the task
domain; support error recognition and recovery; and support reading
to do, to study and to locate. (Van der Meij and Carroll, 1995)

*Consequence:* chapter 10's writing rules are those four, applied.

**Which screenshots help, and which hurt.** Gellevij, Van der Meij, De
Jong and Pieters compared a text-only manual with two visual manuals
modelled on commercially successful ones. For learning, the manual
with partial screen captures, cropped to the element, did worse than
both the text manual and the manual with full screen captures, which
did equally well; for use as a job aid, with the manual open beside
the program, the three did not differ. (Gellevij and colleagues,
1999) Gellevij and Van der Meij then named four functions a capture
can serve, switching attention between manual and screen, building a
mental model of the program, locating objects on the screen, and
verifying screen states, and tested them: a manual built on the last
three had users "learn more in less time", 11% faster, at the same
measured cognitive load as text alone, while supporting the
switching of attention did nothing, because users switch constantly
anyway. (Gellevij, 2002; Gellevij and Van der Meij, 2004) An
eye-tracking study of highlighted captures found that a capture with
the target signalled gave more correct task executions than a plain
one, in the same time. (Technical Communication 66(4), 2019)

*Consequence:* principle 4 and chapter 6. A crop of a button, the
obvious way to illustrate a step, is the one kind of picture shown to
make a manual worse. A whole screen with the control spotlit is the
full capture that did as well as text, with the signalling that did
better than plain. Chapters also carry "after" pictures at
checkpoints, for verifying the state.

**Why people go to a colleague instead.** Novick and Ward interviewed
25 users. Few had paper manuals for the software they used most and
none missed them; online help was consulted more but people were just
as likely to ask a colleague or experiment. The complaints were
navigation, not knowing which words to search for, and "the level of
explanation found". (Novick and Ward, SIGDOC 2006)

*Consequence:* chapter 9. The manual is opened from the page the
person is on, at the chapter for that page, so nobody has to know a
search term; and chapter titles are the question the reader would
ask a colleague.

**Paper reads a little better, when it is paper.** A meta-analysis of
54 studies and 171,055 participants found a small but consistent
advantage for paper over screens (g = -.21), larger for informational
text and under time pressure, and near zero when reading is
self-paced (g = -.09). A follow-up on phones and tablets found the
effect smaller still (g about -.11). (Delgado and colleagues, 2018;
Salmerón and colleagues, 2023)

*Consequence:* chapter 8, but only for the printout. The PDF is
designed for the page, with page numbers a reader can cite and a
picture that does not straddle a break, because a printed chapter is
what the premise says gets forwarded to the person without the app.
A PDF read on a screen gains nothing from this result, and Gellevij's
job-aid finding says a manual open beside the program does as well in
any form. The web page is the rendering for reading beside the
screen; the PDF is the rendering for the printer.

**Guidance, not research.** The Dutch government writes public text
at B1: short active sentences, everyday words, clear headings, an
example where one helps. The Microsoft style guide's rules for
procedures: one action per step, the imperative, say where before
what, the control's name in bold. Diátaxis separates the tutorial
(learning by doing, which here is the tour) from the how-to guide (a
task, which is a chapter) and the explanation (why, which is the mail
chapter). Google's publisher policy allows ads only beside
"publisher-content" that is not "low-value" and where "it must be
clear to the user with which publisher-content the ad is associated".
(Sources in chapter 14.)

*Consequence:* chapter 10's sentence rules, and chapter 7's decision
about which manual pages carry advertising.

## 3a. Where the evidence is thin

* **The screenshot work is twenty years old** and was done with
  Windows applications and a training setting, not a web app used at
  a kitchen table. Nothing newer than the 2019 signalling study was
  found.
* **B1 is guidance.** Trials of plain language are mixed: a 2025
  self-paced reading study found plain terms improved comprehension
  without changing reading time, a 2023 randomised trial found no
  comprehension gain and only higher usability ratings, and Jansen
  has argued that "B1" is not a measurable property of a text. The
  chapters use short sentences because the reader is doing something
  else at the same time, not because B1 is proven.
* **Titles as questions** rests on a formative observation in the
  tour literature and on Novick and Ward's complaint, not on a test.
* **Nothing measures a manual in two languages** or a manual whose
  pictures show a brand other than the reader's.
* **The PDF's value is an argument from the premise**, that printouts
  get forwarded, and not a measurement. Chapter 10's reading test
  will say whether anyone prints it.

## 4. The chapters

Fourteen, numbered in the order somebody meets the app. Each title is
a question, because that is how the reader would put it to a
colleague. The audience column is the one front-matter flag.

| nr | slug | title | audience |
| --- | --- | --- | --- |
| 1 | inloggen | Hoe log ik in zonder wachtwoord? | all |
| 2 | evenement | Hoe maak ik een evenement? | all |
| 3 | aanmeldingen | Wie komt er, en hoe deel ik de link? | all |
| 4 | herhalen | Hoe laat ik een evenement terugkomen? | all |
| 5 | datumplanner | Hoe kiezen we samen een datum? | all |
| 6 | takenrooster | Hoe verdeel ik de klussen? | all |
| 7 | vragenlijst | Hoe maak ik een vragenlijst? | all |
| 8 | quiz | Hoe maak ik een quiz? | all |
| 9 | kompas | Hoe maak ik een kompas? | all |
| 10 | archief | Hoe ruim ik op, en hoe haal ik iets terug? | all |
| 11 | misgaat | Als er iets misgaat | all |
| 12 | afdelingen | Hoe werken afdelingen en de agenda? | organisation |
| 13 | gebruikers | Hoe laat ik nieuwe organisatoren toe? | organisation |
| 14 | mail | Wat gebeurt er met een mailadres? | organisation |

English has the same fourteen, same numbers, its own slugs. Chapter
14 is the privacy contract in plain words and is the one chapter that
links to the policy. Chapter 11 is Carroll's general card: a lost
sign-in link, a wrong date after people signed up, something archived
by accident, a sign-in mail that did not arrive, a link that says it
expired. Each entry is three lines: what you see, what happened, what
to do.

Inside a chapter, the order is fixed: two sentences on what the thing
is for; the steps, one action each, a picture per step; a checkpoint
("Je ziet nu…") with its picture; then the questions people ask about
this thing, three or four, one paragraph each.

**Where the organisation's screen differs, a paragraph does.** The
organisation's door asks a first-time address for a name and then
waits for an admin; the root's door does neither. The organisation's
event form has a chapter picker; the root's has none. Those
paragraphs are written once, in the chapter they belong to, and
marked for the organisation with the attribute syntax the written
pages already use for the note box (`{: .organisation }`). The root
rendering drops them; the organisation's keeps them. A chapter never
carries a paragraph marked for the root, because the root is the
default.

**Mail is an organisation chapter** because mail to participants is
the paid plan and an organisation is born paid (`docs/design-paywall.md`).
A personal account is born free, its sign-up form has no email field,
its event form has no mail sections and its details page no feedback
card, and the written pages say there is no paid version with more
features. So the root manual has no mail chapter to describe a
feature the reader does not have, and says nothing about a plan. The
one address a free account touches, a volunteer's at the roster's
enrol page, used once for their personal link and not stored, is a
question at the end of chapter 6.

*Against the literature.* This is the Guided Exploration card, with
the checkpoint and the recovery information Carroll found did the
work, and the general "what if" card as its own chapter. The
question titles follow the observation in the tour literature and
Novick and Ward's complaint about search terms, answered in the table
of contents. Diátaxis would call chapters 1 to 10 and 12 to 13 how-to
guides and chapter 14 an explanation; the tutorial is the tour, and
the manual does not try to be one.

*Against the code base.* Chapter 12 is the organisation's chapter
agenda, whose window the settings page sets (`agenda_future_days`,
`agenda_past_days`) and whose public pages `ChapterGrid` links to from
the landing page; chapter 13 is the users page with its approve
button and the pending badge the header shows admins. Chapter 14's
screens, the mail sections in the fold and the feedback summary,
render only when the toggles may be on, which on a personal account
they may not (`auth.participantMail`, `limits.can_send_participant_mail`).
All three exist only for an organisation, which is why the audience
flag exists. The door's two behaviours are `routers/auth.py`: with a
tenant an unknown address gets a registration token and a name step,
without one it gets a sign-in link and nothing else. A personal
account has no chapters by construction (`Tenant.is_personal`, the
`needsChapters` getter), so the chapter-picker paragraph in chapter 2
is the only place chapters 1 to 11 may mention one, and the pictures
for those chapters are shot in a personal account so no chapter chip
appears in them.

## 5. The source

The chapters live in the backend beside the written pages, one folder
per language, one file per chapter, the chapter number in the file
name, and a folder of pictures per language next to them. The number
is the order and nothing else reads it; the chapter's address is its
file name without the number, and two files claiming the same number
fail at import the way two written pages claiming the same order
already do.

The front matter is the lines the written pages already carry, the
title and the description, minus the call to action, plus the
audience. A missing line is a broken chapter at import, not a chapter
with a default.

A manual service mirrors the content service: the chapters per
language as a tuple, a lookup by slug, parsed at import and rendered
on first read with the same markdown renderer and the same two
extensions, then kept for the process. The two services do not merge.
A written page has a call to action and one language; a chapter has
an audience and two languages. What they share, the front-matter
parser and the parse-at-import shape, moves into one small module
both import.

**Dropping a paragraph by audience** is done on the rendered HTML,
not the markdown: the renderer tags the paragraph with the class, and
the root rendering removes every element carrying it before the
template sees the text. One pass over the tree, done once per chapter
per audience and kept with the rest.

*Against the code base.* `services/content.py` parses front matter
with a loop over colon-separated lines and no YAML; the manual keeps
that. Its `Page.html` is a cached property, rendered on first read
and kept, and the chapter does the same. The words `handleiding` and
`manual` join `RESERVED_SLUGS` in `services/slug.py`, so no chapter of
an organisation can take the address, and `tests/test_content.py` has
a test that the written slugs are all reserved, which the manual's
test copies. The markdown extensions stay `tables` and `attr_list`:
the note box the written pages use is the one styled box a chapter
needs, and the same attribute syntax carries the audience class.

## 6. The pictures

Every picture in the manual is a screenshot of a tour step, and every
tour step is shot. A script in the frontend's end-to-end folder, run
by a make target and never by the test suite, signs in as the seeded
organiser, sets the language in local storage, starts each tour
through its store, and for every step writes one picture named after
the tour, the product and the step into that language's folder. It
also shoots the "after" state that a chapter's checkpoint shows: the
sent paragraph on the door, the details page after a save, the row in
the archive.

The viewport is 1024px wide at device scale 2, so the same file is
sharp on a laptop screen and on paper. The pictures are committed,
because a Docker build has no browser and no database, and
regenerated when a screen changes. A chapter refers to a picture by
the tour, product and step in its name, so a renamed step is a broken
reference and never a stale picture; the renderer resolves the name
in the reader's language, and the test suite fails on a reference to
a picture that is not on disk. The picture's alternative text is its
caption, printed under it, because a reader on paper cannot hover.

Two languages of pictures, one brand. The screens for chapters 1 to
11 are shot in the house brand, in a personal account, and an
organisation's rendering shows them as they are: the palette differs,
the layout does not, and a manual that said "your buttons are a
different colour than in these pictures" would be telling the reader
something they can see. Chapters 12 to 14 are shot under the seeded
organisation, because their screens exist only there.

Size: the six tours have 29 steps, but a step on a list, details or
form page is a different picture per product, and each chapter adds
its checkpoint, so about 80 pictures per language at 150 to 250 KB
each after compression: 25 to 40 MB in the repository and the same
again each time the whole set is reshot. That is the cost of pictures
that are always right, stated here so it is not discovered later.

*Against the literature.* Gellevij's result decides the shape: the
picture is the whole screen, because cropped captures made the manual
worse, and it has one control lit, because locating an object and
verifying a state are two of the three functions that helped and the
2019 study found a signalled capture beat a plain one. The tour's
mask is the signal. The checkpoint pictures are the verification
function on its own. Dual coding, which the cognitive load
measurements supported, is why a picture sits beside its step and not
in a gallery at the end.

*Against the code base.* The end-to-end tests already sign in through
`/api/v1/auth/dev-issue-token`, the local-mode fixture, which can also
issue a token for a personal user when no tenant is given, and the
seed gives the organiser two chapters. The tests never set the UI
language today; the script writes the `locale` key the i18n module
reads before it loads a page. The script adds a personal account
through the start endpoint for the house-brand shots. The tour's
store is the thing the script drives, one step at a time, waiting for
the overlay's callout to render before capturing; that is why the
pictures cannot exist before the tour does. The pre-push hook already
needs a seeded dev database for its e2e run, so the script asks for
nothing the developer does not already have.

## 7. The web pages

Server-rendered with no bundle, like every page that is read rather
than used. One page per base, the whole book on it:

| address | language | audience |
| --- | --- | --- |
| `/handleiding` | Dutch | personal, the root being the personal app |
| `/manual` | English | personal |
| `/{tenant}/handleiding` | Dutch | organisation, in that brand |
| `/{tenant}/manual` | English | organisation |

A chapter is an anchor on that page, `#evenement`, not a page of its
own. A link to a chapter is the page's address with the anchor, which
is what the app's menu offers and what somebody pastes into a group
chat, and the browser lands on the chapter's heading.

The language is the address, because a server page cannot read the
language the app keeps in the browser, and each page links to its
twin in the other language at the top, where the language switch sits
on every other surface.

At the top, the book's title with the PDF download beside it. The
contents sit in a column on the left on a wide screen, kept in view
while the chapters scroll past, and jump to a chapter's anchor; on a
phone they sit above the text. The chapters follow in order, each
under its own heading, with its sections one level down.

The template is its own rather than a block in the written pages'
template: it wears the brand it is served under, which the written
pages do not, and it has a chapter column the written pages have no
use for. The footer is the same colophon.

**The audience rule is the tenant.** Under an organisation's prefix
the chapters flagged for organisations are in and the marked
paragraphs stay; at the root the chapters are out and the paragraphs
are dropped. The organisation chapters are the last three, so the
root counts 1 to 11 and the organisation 1 to 14, and a number means
the same chapter in both. This is what keeps the rule that public
copy never mentions the organisation version: the root rendering has
no chapter and no paragraph that could.

**Indexing and advertising.** The root manual is indexable, in the
sitemap, and carries advertising as the written pages do: house brand
only, rails beside the column on a wide viewport and one banner at the
foot below it, behind the consent dialog Google's tag brings, nothing
until a client id is configured. It is a page of prose with pictures,
which is what the policy asks an ad to sit beside. An organisation's
manual is marked not to be indexed, like the rest of its pages, and
carries no advertising, like every page in its brand.

*Against the literature.* Google's publisher policy asks for
"publisher-content" that is not "low-value", with a clear association
between the ad and the content beside it. A chapter is a thousand
words of original prose with pictures, on a subject people search for
("aanmeldlijst maken", "datumprikker zonder account"), which is the
kind of page the policy describes and the written pages already are.
The index is a list, which is the kind of page it does not. Novick
and Ward's readers wanted a level of explanation they did not get
from help systems; a chapter that is findable from a search engine
by the question in its title is also a page a stranger lands on, and
`docs/seo.md` says a few pages of forms is a thin site.

*Against the code base.* `routers/privacy.py` shows the two chromes
side by side: the written pages get the ad slot and `/privacy` gets
none, and `tests/test_ads.py` pins that. The manual router does the
same split by audience and page kind, and sets `request.state.ads_allowed`
the way `_written_page` does, so the security middleware, which reads
that one flag and keeps no page list, picks the loosened policy only
for the root chapter pages. `_SITEMAP_PATHS` in `routers/root_files.py`
is a tuple of the root, the blog, the content pages and the policy;
it gains the root manual's index and chapters in both languages. The
SPA fallback serves `/{tenant}/…` as the organiser app, except a
second segment that is a live chapter, which is the public agenda; the
reserved words keep a chapter from being called `handleiding`, and
the manual's tenant routes are registered before the fallback, as the
written pages' routes are. `brand.palette_css` and `brand.manifest`
already render any committed brand by slug, which is all the template
needs to wear an organisation's colours; a personal tenant's
`brand_slug` is the house brand.

## 8. The PDF

One file per language per brand, rendered from the same chapters by
WeasyPrint, which does paged media properly: page size and margins, a
running footer with the page number, a page break before every
chapter, and a table of contents whose page numbers are computed by
the renderer rather than typed (`target-counter`). Chromium's
print-to-PDF was the alternative and cannot do the last one.

**Built in its own image stage.** The Dockerfile has two stages, a
Node builder for the bundle and the Python runtime. The PDF gets a
third, `manual-builder`: `python:3.13-slim` with Pango, HarfBuzz and
one open font package from apt, the same lockfile synced with a
`manual` dependency group that holds WeasyPrint and nothing else, the
backend source and `brands/`. It runs one script and the runtime
stage copies the files out of it the way it copies the bundle out of
the Node stage. The runtime image gains nothing: no Pango, no font, no
WeasyPrint, because a render takes seconds and none of it belongs in
the request path.

**Its own entry point, not a CLI subcommand.** `backend/cli.py` builds
`Settings` when it is imported, which needs every required
environment variable, and its preamble runs the migrations and the
tenant reconcile against the database before any subcommand. A build
stage has neither. The script is `python -m backend.manual_pdf
<out-dir>`, and it imports the manual service, the folder-reading
half of the brand service, and WeasyPrint. The brand service reads
`settings` at import today, for the public base and the ad ids; those
two reads move into the functions that use them (`asset_url`,
`payload`), so `manifest` and `palette_css` import nothing from
`config`. That is a refactor the brand service is owed anyway: a
folder reader should not need a JWT secret to open a folder.

The file is served under each base at `handleiding.pdf` and
`manual.pdf`, cached the way the built assets are, and linked at the
top of the page as "Download als PDF". A dev checkout has no build,
so in local mode the route renders the file on request instead; that
is the one place Pango is allowed in the request path.

**What is on the page.**

* A cover: the brand's logo and wordmark, "Handleiding", the app's
  name, and the month the image was built, from the build stage's
  clock, so a reader can tell an old printout from a new one. The
  build has no `.git`, so it cannot be the commit date.
* The table of contents with page numbers.
* The chapters, each on a fresh page, pictures at the column width
  with the caption under them, the checkpoint picture beside its
  "Je ziet nu" line.
* Links printed as their address after the link text, since paper has
  no cursor.
* A footer line with the chapter title on the left and the page number
  on the right. No advertising, no colophon.
* A4, 20mm margins, an 11pt body on a measure of about 65 characters,
  ragged right.

**Fonts.** The web pages use the system font stack, and a container
has no system font worth printing. The build stage installs one open
font package from apt and the print stylesheet names it. No font file
in the repository.

**Print stylesheet.** The page-break and caption rules sit in the
template under a print media query, so a person printing the web page
from the browser gets the same breaks and captions, minus the cover
and the numbered contents. The PDF is that stylesheet plus the page
rules.

*Against the literature.* Delgado's meta-analysis says the same text
is understood a little better on paper, most of all informational
text read under time pressure, and hardly at all when self-paced or
on a handheld. That is a reason to make the printout good, not a
reason to prefer the PDF on a screen, and chapter 3 says so. The
printout is designed rather than exported because the premise says it
gets forwarded to someone without the app: page numbers a colleague
can cite, a measure a reader can hold, and a picture that does not
straddle a page break. WeasyPrint's documentation lists the
paged-media features this needs as supported; Chromium lists
cross-references under future work; a survey of HTML-to-PDF engines
finds cross-reference page numbers work in WeasyPrint and Prince and
nowhere else.

*Against the code base.* The runtime image is `python:3.13-slim` with
an apt layer for `libpq5`, a Postgres client, curl and tini, and it
stays that way. `.dockerignore` drops `.git`, `docs` and root-level
markdown; `backend/content/*.md` and the chapter files beside it get
in, because the pattern matches only the root. `pyproject.toml` has a
`dev` dependency group already; `manual` is a second, synced only in
the build stage, so the runtime's `uv sync --frozen --no-dev` never
sees WeasyPrint. The pre-push hook re-syncs the environment on a
lockfile change. The brand folders are committed, so every
organisation's PDF can be built without the environment's `TENANTS`.

## 9. Where it is reached from

* The app's menu, help group: Handleiding opens the page at the
  chapter for the page the person is on, by its anchor, in the brand
  and language they are in (`design-tour.md`, chapter 9), by this
  table:

  | page | chapter |
  | --- | --- |
  | landing | the index |
  | event list, new, edit | 2 |
  | event details | 3 |
  | datepoll pages | 5 |
  | roster pages | 6 |
  | form pages | 7 |
  | quiz pages | 8 |
  | compass pages | 9 |
  | any archive subtab | 10 |
  | chapters, settings | 12 |
  | users | 13 |

  Chapter 4 is reached from chapter 2's page, and chapter 14 from
  the fold that holds the mail toggles.
* The colophon on the root and the create pages gets a link next to
  Blog for the house brand, and an organisation's pages get it too,
  since the manual is theirs to read, unlike the blog.
* The written pages' footer and the blog get the same link.
* The mail sent to somebody who made something at the start door gets
  one line, that more explanation is in the manual, with the root
  link. It is the one mail every personal account receives, at the
  moment they most need it, and it is sent on every start-door
  create, so the line is short.
* A search engine, for the root chapters, by the question in the
  title.

*Against the literature.* Novick and Ward's users asked a colleague
because the help was not where they were and did not speak their
words. The menu item is the colleague at the desk: it opens the right
chapter without a search box, and the chapter is titled in the words
the person would have used.

*Against the code base.* `SiteFooter` shows the colophon on the root
and on the create pages only, by the `startable` route flag; the
colophon itself is `public_shared/Colophon.svelte`, and its blog link
is behind the house-brand check; the manual link goes beside it
without that check. The started mail is `mail_templates/nl/started.html`
and its English twin, which already carry the sign-in link and the
"you did not do this yourself" line; the manual line is one sentence
under them. The header's help group is the tour proposal's, shared.
The archive subtabs are the `/{resource}/archived` routes.

## 10. Writing it

`docs/style-nederlands.md` and `docs/style-copy.md` apply, and the
four minimalist principles are the checklist a chapter is read
against:

* **Action first.** The steps start on the first screen of the
  chapter, after two sentences of what the thing is for. Nothing to
  read before the first click.
* **Anchored in the organiser's world.** A chapter is "hoe verdeel ik
  de klussen", not "the roster module". Examples use a real evening: a
  bar, a kassa, a ledenvergadering.
* **Errors are expected.** Every chapter ends its steps with a
  checkpoint and names the two or three ways it goes wrong there,
  with the way back; chapter 11 holds the rest.
* **Read to do, to study, to locate.** Steps are numbered and
  imperative for the person doing; the questions at the end are for
  the person wondering; the question titles and the contents are for
  the person looking.

Sentences are short, active, everyday words, one thing each. The
control's name is what the screen says, in bold, and the step says
where before what: "Onderaan het formulier klik je op **Opslaan**."

Chapters are short. Two printed pages is the ceiling; a chapter that
needs more is two chapters, which is why the questionnaire, the quiz
and the kompas are three. When the screen's word changes, the chapter
changes in the same commit, which the reshot picture forces anyway.

Before the text is final it is read by the same two organisers who
try the tour (`design-tour.md`, chapter 12), with the app open, doing
what a chapter says. Where they stop and look up, the chapter is
wrong. They are also asked whether they would print it, which is the
only evidence chapter 8 will get.

*Against the literature.* The four bullets are Van der Meij and
Carroll's four principles in order. The checkpoint and recovery
lines are what Carroll found made the cards work. The sentence rules
follow the government's B1 guidance and Microsoft's procedure rules,
with chapter 3a's caveat that the guidance is not a result; the bold
control name is Microsoft's one permitted use of bold. The reading
test is the question-suggestion protocol again.

## 11. Tests

* Every chapter parses with every front-matter line; both languages
  have the same chapter numbers; every picture a chapter names is on
  disk; the root rendering contains no organisation chapter and no
  element with the organisation class, and the tenant rendering has
  both; the index and each chapter answer in both languages under
  both bases; a root chapter page carries the ad slot and the index,
  the tenant pages and the PDF do not; the PDF the script writes
  starts with the PDF signature and has more pages than chapters.
  The last test needs Pango in CI, one apt line in the workflow, and
  is the one test that imports WeasyPrint.
* The reserved-slug test the written pages have, copied for the two
  manual words.
* The sitemap test extends to the root manual's pages.
* The brand service's folder half imports nothing from `config`, a
  static check like the one that keeps `decrypt` in one module.
* The privacy tests gain nothing: the manual reads no data.

## 12. Not built

* No search over the manual. Fourteen chapters titled as questions
  and the browser's find is enough.
* No comments, no "was this helpful", no counters.
* No per-organisation chapters or edits: an organisation reads the
  same manual as everybody, with three chapters and a few paragraphs
  more.
* No pictures per brand.
* No tagged PDF for screen readers in the first version. WeasyPrint
  can emit PDF/UA; whether the output is clean enough to promise is a
  check for when the first PDF exists, and the web rendering is the
  accessible one meanwhile.

## 13. Cost

| piece | new | changed |
| --- | --- | --- |
| fourteen chapters, two languages | 28 files, about 4 000 words per language | |
| pictures | about 160 files, the shooting script, one make target | |
| service, router, template, shared front-matter module | ~450 lines | the app, reserved slugs, the sitemap |
| PDF: entry point, print stylesheet, image stage, dependency group | ~150 lines | the Dockerfile, the project file, the lockfile, the CI workflow, the brand service |
| links: menu, colophon, written pages, one mail | | five files |
| tests | one file | the content test, the sitemap test |

The code is three days. The writing is the work: fourteen chapters
twice, in a voice that does not sound like a language model, is a
week of writing and a second of reading it back with the people it is
for. The tour has to exist first.

## 14. Sources

Peer-reviewed:

* Carroll, J. M. and Rosson, M. B. (1987). *Paradox of the Active
  User.* In Carroll (ed.), *Interfacing Thought: Cognitive Aspects of
  Human-Computer Interaction*, MIT Press, pp. 80-111.
  <https://research.cs.vt.edu/ns/cs5724papers/4.mental.mental.carroll.paradox.pdf>
* Van der Meij, H. and Carroll, J. M. (1995). *Principles and
  heuristics for designing minimalist instruction.* Technical
  Communication 42(2), pp. 243-261.
  <https://www.ingentaconnect.com/content/stc/tc/1995/00000042/00000002/art00007>
* Gellevij, M., Van der Meij, H., De Jong, T. and Pieters, J. (1999).
  *The effects of screen captures in manuals: a textual and two visual
  manuals compared.* IEEE Transactions on Professional Communication
  42, pp. 77-91.
* Gellevij, M. (2002). *Visuals in Instruction: Functions of Screen
  Captures in Software Manuals.* Thesis, University of Twente.
  <https://ris.utwente.nl/ws/files/6073421/t0000018.pdf>; and
  Gellevij, M. and Van der Meij, H. (2004). *Empirical proof for
  presenting screen captures in software documentation.* Technical
  Communication 51(2).
* *Effects of Visual Signaling in Screenshots: An Eye Tracking Study.*
  Technical Communication 66(4), 2019.
* Novick, D. G. and Ward, K. (2006). *Why don't people read the
  manual?* SIGDOC 2006. <https://dl.acm.org/doi/10.1145/1166324.1166329>
* Delgado, P., Vargas, C., Ackerman, R. and Salmerón, L. (2018).
  *Don't throw away your printed books: a meta-analysis on the effects
  of reading media on reading comprehension.* Educational Research
  Review 25, pp. 23-38.
  <https://www.uv.es/lasalgon/papers/Delgado%202018%20dont%20throw%20away%20your%20printed%20books.pdf>
* Salmerón, L., Altamura, L., Delgado, P., Karagiorgi, A. and Vargas,
  C. (2023). *Reading comprehension on handheld devices vs. on paper:
  a narrative review and meta-analysis.* Journal of Educational
  Psychology. <https://www.uv.es/lasalgon/papers/Salmeron%202023%20manuscript_tablets.pdf>
* On plain language: Jansen, C., *'Teksten op B1-niveau' als leeg
  begrip* (Tekstblad); a 2025 self-paced reading study in the
  International Journal of Applied Linguistics (n = 117); a 2023
  randomised trial in JAMA Pediatrics (n = 268).

Guidance and practitioner:

* CommunicatieRijk, *Taalniveau B1*
  <https://www.communicatierijk.nl/vakkennis/rijkswebsites/aanbevolen-richtlijnen/taalniveau-b1>;
  Gebruiker Centraal, *Direct Duidelijk: duidelijke teksten schrijven*
  <https://www.gebruikercentraal.nl/themas/direct-duidelijk/duidelijke-teksten-schrijven/>
* Microsoft Writing Style Guide, *Writing step-by-step instructions*
  <https://learn.microsoft.com/en-us/style-guide/procedures-instructions/writing-step-by-step-instructions>
* Procida, D., *Diátaxis* <https://diataxis.fr/start-here/>
* Google, *Publisher Policies*
  <https://support.google.com/adsense/answer/10502938>
* WeasyPrint, *Features* <https://doc.courtbouillon.org/weasyprint/stable/api_reference.html>
  and *First steps* <https://doc.courtbouillon.org/weasyprint/stable/first_steps.html>
* Accreditly, *Can I use it in a PDF? CSS support across HTML to PDF
  engines* <https://dev.to/accreditly/can-i-use-it-in-a-pdf-css-support-across-html-to-pdf-engines-4n53>
