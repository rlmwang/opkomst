# Design: the guided tour (rondleiding)

Status: proposal. Companion to `design-manual.md`, the written manual
whose pictures are shot from this tour's steps. The tour is built
first, because the manual's pictures cannot exist before it.

## 1. Premise

The organisers this app is for do not read documentation and do not
know what a "QR" or an "archive" is until they have used one. They
open the app to put an event up, and the first time they do it they
would like somebody sitting next to them saying "that button, now
that one".

A guided tour is that person. It darkens the whole screen except one
control, says one sentence about it, and waits for the organiser to
press it. The first tour ends with their first event existing and its
link on screen, not with a slideshow about how one could be made.

It is not the only help. The manual (`design-manual.md`) carries the
explanations and the pictures; the tour carries none, because a
person cannot read and act at the same time. And it is not a
replacement for an interface that explains itself: a control that
needs a tour to be understood is a control to redesign first.

## 2. Principles

1. **Nothing starts by itself.** A new account is offered a tour once,
   in a card it can decline. Every tour after that is asked for, from
   the menu, on the page it is about.
2. **A tour is one task and at most five steps.** Five per-page tours
   stay on the page they were started from. The welcome tour is the
   one that follows the person across pages, because its task, a
   first event, crosses them.
3. **A step is one control and at most two sentences.** A step that
   needs a third sentence is two steps or a manual chapter.
4. **Where the action is the person's own, the step is that action.**
   Click here, type there, save. Where the action would change
   something they did not ask for, archiving an event to show
   archiving, the step points and waits for Volgende.
5. **Nothing conventional is explained.** No step says what a search
   box is or what three lines on a button mean.
6. **Stopping is one press away**, on screen and on Escape. Leaving
   the page stops the tour, except when the step itself asked for the
   navigation.
7. **It looks like a guide, not like the app.** The dark mask and a
   popover with an arrow, the one shape the app never uses for
   content.
8. **Nothing moves.** No fade, no pulse, no slide from one control to
   the next.
9. **A tour is data.** A list of controls by name and a rule for
   advancing, with its words in the locale files. No selectors, no
   callbacks, no library.
10. **Nothing is recorded** beyond whether the offer was answered. No
    counters, no step anyone stopped at, nothing sent anywhere.

## 3. Research, and what follows from it

Read for this proposal in September 2026. The first five are
peer-reviewed human-computer interaction work; the rest are
practitioner sources and are marked as such. None of it is research
on this app or its organisers, and chapter 3a says where the evidence
is thin. Chapter 12 says what would be evidence.

**People will not learn first and do later.** Carroll and Rosson,
observing office workers learning word processors at IBM, named the
paradox of the active user: a production bias, where the person's
"paramount goal is throughput" and time spent only learning is time
they will not spend, and an assimilation bias, where they read the
new thing through whatever they already know. They call these
"fundamental properties of learning", not design defects. (Carroll
and Rosson, 1987)

*Consequence:* principles 1 and 4, and the ceiling in principle 2.
The tour never asks anyone to read first; it rides on the thing they
came to do, and it is short because every step is time not spent on
the event. Carroll's "training wheels" interface, which disabled
advanced commands for beginners, is background here and not a
precedent: it is a reduced program, not an overlay.

**A translucent overlay with a hole is a tested technique.** Kelleher
and Pausch built Stencils: "translucent colored stencils containing
holes that direct the user's attention to the correct interface
component and prevent the user from interacting with other
components", with "sticky notes on the stencil's surface" for the
instruction. Against the same tutorial on paper, in the Alice
programming environment, users of Stencils finished 26% faster, made
fewer errors, and needed less help from a person; both groups
learned the same amount. (Kelleher and Pausch, CHI 2005)

*Consequence:* the whole mechanism of chapter 6. The mask, the hole,
the note beside it, and blocking everything else are that design.
The finding that both groups learned equally is why the manual
exists: a stencil gets somebody through a task, it does not make
them know the tool.

**On request beats always on.** Harms, Kerr and Kelleher, working in
the Looking Glass programming tool with children of 10 to 16, found
in a formative study of 46 users that people following persistent
stencils struggled to do a related task afterwards without them. In
a follow-up with 18 users, a stencil that appeared only when the
person pressed "Show me" produced 47% more correct transfer tasks
than one shown for every step, with no difference in tutorial
performance or attitude. Their related work, citing Knabe's 1995
study of Apple Guide, notes that users of paper and separate-window
tutorials "mistake pictures of components for active components".
In the formative study, retitling steps as questions ("How do we
make Sam back-flip three times?") helped users find the step they
needed; that is an observation, with no number behind it. (Harms,
Kerr and Kelleher, IDC 2011)

*Consequence:* principle 1. The finding is about not showing the
overlay until it is asked for, which is what the menu item and the
declinable card do. It says nothing about splitting a tour per page;
that split comes from principle 1 alone, since a tour asked for from
a page should be about that page. Chapter 11's question titles
follow the observation, not a result.

**Coach marks on phones: a tendency, not a proof.** The one
controlled study of instructional overlays on a smartphone interface
found lower task times with the overlay than without, but with a
sample too small for significance. (Noriega and colleagues, AHFE
2019)

*Consequence:* nothing in this design leans on coach marks being
proven. What is proven is the stencil; the phone layout in chapter 6
is a stencil that fits a phone.

**How to find out whether it works.** Grossman, Fitzmaurice and
Attar's survey of learnability research proposes the
question-suggestion protocol: an expert sits beside the person, who
asks questions when stuck and is answered; it exposed significantly
more learnability problems than think-aloud. (Grossman, Fitzmaurice
and Attar, CHI 2009)

*Consequence:* chapter 12 uses it.

**Onboarding written to the minimalist rules.** Froehlich and
colleagues built onboarding flows on Van der Meij and Carroll's four
minimalist principles and found, with 16 participants, that
perceived usability rose; they measured no task success. Strahm, Gray
and Vorvoreanu give the method for reading an onboarding flow against
those principles. (Froehlich and colleagues, DIS 2021; Strahm and
colleagues, DIS 2018)

*Consequence:* chapter 11 writes each step against the four
principles, the same checklist the manual uses.

**The alternatives that were tested.** Grossman and Fitzmaurice's
ToolClips put a short video in a tooltip and had users complete
seven times as many unfamiliar tasks as with the commercial help.
Chilana, Ko and Wobbrock's LemonAid let a person click any element
and see questions others had asked about it, and over 70% of users
across a field deployment found it helpful. (Grossman and
Fitzmaurice, CHI 2010; Chilana and colleagues, CHI 2013)

*Consequence:* chapter 14. Both are help attached to a control the
person is already looking at, and both need content per control:
video, or a corpus of questions. The tour is the cheaper shape of
the same idea, one sentence per control, and the manual's chapter
opened from the menu is where the longer explanation lives.

**Practitioner sources, for the numbers and the failures.** Nielsen
Norman Group's 70-person study of swipe-card tutorials shown before
any task found readers no more successful than skippers (91% against
94%) and rating tasks harder; their overlay guidance says one hint
at a time and minimal text, and warns that people tap polished
overlays thinking they are the app. Userpilot reports about 70% of
tours skipped and a 25% gain for skippable tours, both without a
source, and quotes a vendor benchmark of 72% completion at three
steps, 74% at four and 16% at seven, with nothing measured between.
An accessibility audit guide lists the failures every tour repeats:
focus not moved in or returned, no keyboard exit, no announcement,
Tab reaching the dimmed page. Driver.js and Shepherd.js document the
defaults the common libraries settled on. (Sources in chapter 16.)

*Consequence:* the NN/g result argues against an up-front tutorial,
which is why there is no slideshow and the one push is a card in the
page. The step ceiling of five is a judgement between the vendor's
four and seven, not a finding. The look in chapter 6 and chapter 7
answering each audit failure by name follow the guidance.

## 3a. Where the evidence is thin

* **No study of a guided tour in a web app for adults.** The two
  stencil studies are children learning to program, one of them with
  18 participants; the phone study is not significant. The mechanism
  is tested, the audience is not.
* **The step ceiling** rests on a vendor benchmark that measured
  three, four and seven steps.
* **Titles as questions** is one formative observation.
* **The offer card** has no evidence behind it either way; Carroll's
  production bias predicts it will be declined by most, and chapter 9
  is designed so that costs one glance.
* **Accessibility** follows one practitioner audit guide, not a study.
* **B1 sentences** are government guidance. Trials of plain language
  are mixed: a 2025 self-paced reading study found plain terms
  improved comprehension without changing reading time, a 2023
  randomised trial found no comprehension gain, only higher usability
  ratings, and Jansen has argued that "B1" is not a measurable
  property of a text. The tour writes short sentences because a
  callout has room for nothing else, not because B1 is proven.

## 4. The tours

There are six tours. One is for signing in and runs signed out; one
is the welcome, offered once; three are per kind of page, because the
six products share their list, details and edit pages and the same
control means the same thing on each; one is for the organisation's
admin pages.

Tours are per kind of page rather than per product because a tour is
asked for on the page the person is on (principle 1), and because the
six products are drawn by the same components. The words name the
product, through the fallback `formText()` already uses for
product-specific strings: a key for the event list is looked up
first, then the key for any list.

Every step names the anchor it lights (chapter 5) and how it
advances: `next`, a button in the callout; `click`, the control in
the hole is pressed; or `until`, a named control appears. Copy is
indicative.

**inloggen**, from the link "Hoe werkt inloggen?" under the sign-in
form on both signed-out front pages. No account is involved.

| step | anchor | advances | says |
| --- | --- | --- | --- |
| 1 | `door.form` | next | Er is geen wachtwoord. Je krijgt een link in je mail. |
| 2 | `door.form` | until `door.sent` | Typ je adres en klik op Stuur link. |
| 3 | `door.sent` | next | De link staat nu in je mail. Hij werkt een halfuur en één keer. |
| 4 | `door.sent` | next | Klik erop en je bent ingelogd. |

Step 2 lights the whole form, not the button, because the person has
to type in a field a smaller hole would leave under the mask. It
sends a real link if a real address was typed, which is the point:
the person taking this tour is trying to get in. The form swaps to
the "link sent" paragraph on the same page, and that paragraph
appearing is what ends step 2. The tour ends at step 4 because the
link in the mail opens a new tab and no tour can follow someone into
their inbox. Under an organisation's slug step 4 reads "Klik erop en
je bent ingelogd. De eerste keer vraagt de app je naam, en daarna
laat een beheerder je toe." That is one key chosen by the same switch
the door itself uses to know which app it is in. A lost link is
chapter 11 of the manual, not a step.

**welkom**, offered once, from the card on the signed-in landing page.

| step | page | anchor | advances | says |
| --- | --- | --- | --- | --- |
| 1 | landing | `home.events` | click | We maken samen je eerste evenement. Klik hier. |
| 2 | events list | `list.new` | click | Klik op Nieuw evenement. |
| 3 | new event | `form.card` | until `share.link` | Een naam en een datum zijn genoeg. Klik daarna onderaan op Opslaan. |
| 4 | event details | `share.link` | next | Dit is de link die je deelt. Wie hem opent kan zich aanmelden, zonder account. |
| 5 | event details | `header.menu` | next | Klaar. In dit menu staan de handleiding en een rondleiding per pagina. |

Step 3 lights the whole form and ends when the share link exists on
the details page, so the step neither guesses when the save landed
nor advances on a click inside the form that was not the save.

**lijst**, from the menu on any list page: the new button, the first
row's details button, its share link, its archive button, and the
subtab where the archive went. Five steps, all `next` except the
first: the archive step must not be a click, or the tour would
archive the person's first event to demonstrate archiving. This is
a pointing tour by principle 4.

**details**, from the menu on any details page: the sign-ups card,
the share link, the QR, the edit button, and for an event with
feedback on, the feedback summary. Five steps, all `next`.

**formulier**, from the menu on any create or edit page: the first
section, the product's own section (when, dates, chores or
questions), the fold of extra settings (a click step, it opens the
fold), one switch inside it, and Save. Five steps.

**beheer**, from the menu on the users, chapters and settings pages,
organisations only. One list: the approve button and the subtabs on
the users page, the new chapter button and a chapter's address on
the chapters page, the agenda window on the settings page. On each
page the steps for that page are the ones that show; it is three
short tours sharing one name.

**A step whose control is not on the page is dropped in silence.**
That one rule lets one tour serve a personal account and an
organisation, an event with feedback on and one with it off, and a
list with rows and one without: the control is not there, so the
step is not there. No tour carries a condition.

*Against the literature.* Kelleher and Pausch's tutorial was one long
task; Harms and colleagues found that the same overlay served on
request taught more. Six short tours reached from the page they are
about are the on-request form. The ceiling is chapter 3's judgement.

*Against the code base.* The list page has two shells: the list view,
and the "pick your chapters" card an organisation member with no
chapters sees instead (`EntityListPage`, the `needsChapters` branch).
The second renders none of the list anchors, so every list step is
dropped and the tour would end at once; the menu does not offer the
list tour in that state, which the header can tell from
`auth.needsChapters`. The share stub renders when a row has a public
page or a QR (`EntityCard`); the `share.link` anchor sits on the copy
button, which is there only with a public page, so the share step is
dropped for an event whose sessions have all passed, which is right.
The feedback summary renders only when feedback is on
(`EventDetailsPage`), and a free account never has it on
(`docs/design-paywall.md`), so the details tour on a free account is
four steps. A personal account never renders the chapter filter or
the admin item, so the dropping rule covers it without a flag.

## 5. Steps and anchors

A tour is a list of steps in one file under `frontend/src/tours/`,
and an index that says which tour the menu offers on which family of
pages. A step holds three things: the page it belongs on, written as
a path pattern in the router's own grammar; the name of the control
it lights; and how it advances, `next` unless the step says `click`
or `until` with a name. Nothing else: no selectors, no callbacks, no
markup. The words for a step are found in the locale files by tour,
product and position. The per-page tours carry no page: they run on
the page they were started from.

A control gets its name where it is rendered, by a Svelte action on
the element. The action writes the element into a module-level
registry under that name on mount and removes it on destroy. The
names form one union type, so a misspelt name is a compile error, and
a unit test walks every tour to confirm every name it uses is
declared somewhere.

Two rules keep the registry simple. Shared components declare fixed
names: the new button in the list component is `list.new` on every
list page, because it means the same on every list page. And where
several elements carry one name, the first in document order wins:
every row card registers `row.details`, and the tour lights the first
row. Nothing is passed to say "this one is the anchor".

The registry counts its changes, and the engine reads that count, so
an `until` step ends the moment its control registers, and a step
whose control appears after a fetch lands shows the moment it does.

*Against the literature.* Stencils located components through the
application's own widget tree, not through screen coordinates, which
is what let the hole follow a component when the window changed. A
name declared on the element is the same idea. Selectors would tie a
tour to markup that the next restyle changes; a registry ties it to
the control's meaning.

*Against the code base.* Most anchors sit on elements a page or shell
owns, where the action goes straight on the element. The new button,
the details button and the archive button are `AppButton`s, which
take named props and no attribute spread, by the rule in `CLAUDE.md`
that a component never spreads over its own attributes; it gains one
optional `anchor` prop and applies the action itself. No `AppInput`
carries an anchor: the sign-in tour lights the form, not the field.
The share stub already wraps its copy button in a span to hang a
tooltip on; `share.link` goes on that span. The sign-in form's two
anchors go on the `<form>` and on the sent paragraph, both plain
markup in `LoginForm`.

## 6. What it looks like

The look has one job: to be unmistakably a guide and not part of the
page. The distinction is carried by the mask and by the callout being
a popover with an arrow, the one shape the app never uses for
content.

**The mask** is one SVG the size of the viewport, fixed, with a single
path: the viewport rectangle minus a rounded rectangle, filled
even-odd in black at 55%, the same family as the dialog backdrop at
40% and a shade darker, so the page under it reads as paused rather
than as the background of a dialog. The path takes pointer events on
its fill, so a click on the dark part lands on the mask and goes no
further, and a click in the hole reaches the real control. Four
rectangles cannot do this, because a rounded hole has corners they
would leave open. The SVG is hidden from assistive technology. A
click on the mask does nothing.

**The hole** is the control's box plus 8px on each side, with the
radius of what it holds, read off the element's computed style: a
card's 10px, a button's or a field's 6px, a pill's full round. A
second rounded rectangle in the same SVG draws a 2px ring in the
brand red, 2px outside the hole. That is the ring `theme.css` gives a
link or button on keyboard focus, so the hole says "look here" in a
language the app already speaks. The hole is empty, not painted, which
is how a click step and typing in a form step work.

**The callout** has the popover's geometry, with the arrow pointing at
the hole: the surface colour, the 1px border, the 6px radius, the
popover shadow, a 10px gutter. It is at most 20rem wide with 1rem of
padding, hung below the hole, flipped above when there is no room, and
centred on the hole. Inside, top to bottom:

* the counter, "2 van 5", at `0.8125rem`, muted;
* the title, at `1rem` and weight 600, at most six words, written as
  the question the step answers (chapter 11);
* the body, at `0.875rem`, one or two sentences;
* one row of buttons: Stoppen as a text button on the left, then on
  the right Vorige (absent on the first step) and Volgende, or Klaar
  on the last step. A click or until step has no Volgende: the body
  ends with what to do and the hole is where to do it.

No icon, no image. The three sizes are ones the app already uses.

**The counter** counts the steps that will show. A per-page tour
resolves its list when it starts, dropping every step whose control
is not registered, because the page it runs on is already drawn. The
welcome and sign-in tours name controls on pages not yet shown, and
neither has a step that can be absent: a fresh event has a public
page, and the sent paragraph is what the step waits for. Their count
is the declared one, and a drop there is a bug the end-to-end test
catches.

**On a phone**, at the header's own 480px breakpoint, the callout is
not a popover but a sheet across the bottom of the viewport, full
width, same padding, no arrow, and the hole is scrolled into the upper
half of the screen so the sheet never covers it. The same sheet is
used at every width when the hole is taller than 60% of the viewport,
which is the form step: a callout beside a card taller than the
screen has nowhere good to be.

**Layering.** The app has a ladder: toasts at 1000, the popover at
1100, the tooltip at 1200, and the browser's top layer above all of
them for the confirm dialog. The mask sits at 990, above the page and
below every floating thing the app already has, and the callout at
1100 beside the popover. Nothing the app floats is ever hidden by
the mask.

**Nothing moves.** No fade, no pulse, no slide from one hole to the
next. `docs/focus.md` asks that nothing on a page move on its own;
the toast's slide-in and the skeleton's shimmer are the two places
the app does not keep that rule today, and the tour does not add a
third. A person who finds animation confusing is who this is for.

*Against the literature.* Kelleher and Pausch's stencil was a coloured
translucent sheet with a hole, an arrow, and a sticky note; this is
that, in the app's own colours, with the popover's arrow doing the
arrow's job. Knabe's users, and NN/g's, mistook pictures or polished
overlays for live controls; here nothing on the overlay is a picture
of a control, and the one live control is the one in the hole.
Driver.js defaults to black at 50%, 10px of padding, a 5px radius, a
300px popover with 15px of padding, a 19px title and a 14px body, a
400ms animation, and a single SVG path for its mask; Shepherd keeps
the target interactive inside an opening. This design follows them on
the mask, the padding and the opening, sizes the callout from the
app's own scale instead, and drops the animation on principle 8.
Driver.js also closes the tour on an overlay click; here the mask
takes the click and does nothing, because an accidental tap on a
phone ending the tour is worse than a tap that does nothing.

*Against the code base.* `assets/theme.css` gives `a`, `button` and
`[tabindex]` a `2px solid var(--brand-red)` outline at 2px offset on
`:focus-visible`; `AppButton` overrides it with a 1px primary outline
of its own and `AppInput` swaps the outline for a red border, so the
ring the tour draws is the theme's, not what every control shows on
focus. That is fine: the ring marks the hole, not focus, and it is a
colour the reader already reads as "here". The card radius is 10px,
the button and input radius 6px, the header pill 999px, all readable
off the element's computed style, so the hole never guesses. Black
with an alpha is the one colour allowed outside `brands/`, and the
dialog backdrop already uses it. The toast that tells somebody their
event needs a name is at 1000; a mask above it would have hidden the
one message the form step depends on, which is why the mask is at 990
and not, as the first draft had it, at 1150. The 480px breakpoint is
the header's; the sheet appears where the header collapses to a
hamburger.

## 7. Keyboard, focus and screen readers

Each failure the audit guide names has an answer.

* **Focus moves into the tour and back out.** The callout carries
  `role="dialog"`, labelled by its title, and takes focus when a step
  opens. It is not a `<dialog>` element opened modally: that would
  make the whole page inert, and a click step needs one control
  outside the callout to stay live. When the tour ends, focus returns
  to what started it: the menu item, the door link, or the offer
  card's button.
* **A keyboard way out.** Escape stops the tour. Enter and the right
  arrow advance a next step; the left arrow goes back.
* **Tab is contained.** On a next step it cycles through the callout's
  buttons. On a click or until step, Tab from the last button moves
  focus to the highlighted control and Shift+Tab brings it back, so
  the one thing outside the callout that may be used can be reached
  and nothing else can. Inside a lit form, Tab moves between its
  fields as it always does. The engine knows the element, so this is
  one key handler on the callout and not a focus-trap library.
* **Step changes are announced.** The counter and the body sit in a
  polite live region.
* **The page is not hidden from assistive technology**, only the mask
  is, because the highlighted control has to stay in the tree to be
  pressed.
* Nothing auto-advances, so the pause-and-stop criterion is met by
  construction.

*Against the literature.* Shepherd traps focus inside the step and
that is what the audit guide asks for; a strict trap would make a
click step impossible, since the control is outside the callout. The
one-element exception is the smallest hole in the trap that still
lets the step work.

*Against the code base.* The app's Escape handling lives in
`useOverlayPanel`, as a capture-phase listener on the document that
prevents the default, closes the open panel and does not stop
propagation. A document-wide Escape listener for the tour would fire
on the same press and stop the tour while the person only meant to
close a dropdown. The tour's Escape is therefore a listener on the
callout element, so it fires only when focus is in the callout, and a
press with focus in an open select closes the select, as it does
today. The confirm dialog is the browser's own `<dialog>` and manages
its own focus in the top layer; a step that opens one (none do, by
chapter 4) would hand focus to the dialog and get it back when it
closes, with nothing for the tour to do.

## 8. The engine

The tour's state is a module with getters, the way the session is:
which tour is running, for which product, at which step, on which
page it was started, and the verbs start, next, back and stop. That
record is written to session storage on every change and read at
boot, so a tour survives the navigation it asks for: step 2 of the
welcome tour says click Nieuw evenement, the router loads a chunk and
swaps the page, the overlay re-renders, and the tour is at step 3. The
key is scoped to the app the way form drafts are, and it is session
storage rather than local storage so a tour left half-done is gone
when the tab closes.

**Following the route** is one effect over the current path, the
registry's change count, the number of requests in flight, and the
step index, with five outcomes:

1. The path matches the step's page and its control is registered:
   show it.
2. The path matches and a request is in flight: the page is still
   filling. Wait.
3. The path matches, nothing is in flight, and the control is not
   registered: drop the step.
4. The path does not match, and the previous step was a click or
   until step whose page is still the current one: the navigation it
   asked for has not landed. Wait.
5. Otherwise the person went somewhere else. Stop.

The requests in flight are TanStack Query's own count, which the app
already has. Counting frames, as the first draft did, guessed at how
long a fetch takes and guessed wrong for a details page reached by a
save rather than a hover.

**Click steps** advance from the control itself: a one-shot listener
in the capture phase on the resolved element, which does not stop the
event, so the real handler runs and the navigation it causes is what
outcome 4 waits for. A click that does not navigate, opening the
fold, advances on the click alone. **Until steps** advance when the
named control registers, on this page or the next; that is how the
form step learns the save landed, and how the sign-in step learns
the link was sent. Saving with an empty name gets the form's own
toast and the tour stays on the form step, because nothing new
registered.

**Measuring.** On every step the engine scrolls the control into view,
centred, or into the upper half on a phone, measures on the next
frame, and again on resize, on any scroll, and when the control's own
size changes, the way the overlay panel composable follows its field
on resize and scroll, plus a `ResizeObserver` it does not have.

**Signing out** stops the tour and clears its storage, in the same
function that clears the form drafts and for the same reason: on a
shared browser the next person should not be met by somebody else's
half-taken tour.

**Where it lives.** One overlay component mounted in the app shell
beside the toast stack and the confirm dialog, rendering nothing
unless a step is showing. Its code is loaded lazily: on the first
start, and at boot when session storage already holds a tour, so the
organiser bundle does not grow for people who never take one.

*Against the literature.* Stencils intercepted "user interface events
over components not needed for the current step" (Harms and
colleagues describing the technique); the mask is that interception,
and the capture-phase listener on the one allowed control is how the
step learns it was pressed without getting in the handler's way.
Harms's users could leave and come back to a step through a
navigation bar; here a person who leaves the page ends the tour and
can start it again from the menu, which is the same freedom with less
machinery.

*Against the code base.* The router's `go` pushes the history entry,
scrolls to the top, then awaits the page chunk; the overlay must not
measure until the page is on screen, which is what waiting for the
registry's count does, since the anchor cannot be registered before
the page mounts. A stale chunk after a deploy makes the router reload
the page; session storage survives a reload, so the tour resumes at
the same step, and the guard against a reload loop is the router's
own. `logout()` already clears every draft under the app's prefix in
local storage; the tour's key lives under the same prefix in session
storage and is cleared in the same function.

## 9. Starting a tour, and remembering the offer

**From the menu.** The header's dropdown gets a fourth group, under
the workspaces and the admin item and above sign-out: Rondleiding and
Handleiding. Rondleiding starts the tour for the kind of page the
person is on, which the header already knows from the route.
Handleiding opens the manual's chapter for the page, by the table in
`design-manual.md` chapter 9. The header's actions cluster keeps its
two controls at every width: nothing is added to the bar, only to the
menu.

**From the door.** The sign-in door gets one text link under the form,
"Hoe werkt inloggen?", which starts the sign-in tour. It is the only
way to start a tour signed out, and the engine allows it because that
tour's steps all live on the landing page, which needs no session.

**Offered once.** The first time an approved account reaches the
signed-in landing page, a card sits above the tiles: "Nieuw hier? In
vijf stappen maak je je eerste evenement", with Start de rondleiding
and Nee, bedankt. Either answer closes the card for good; the tour
stays in the menu. This is the one push the design keeps, and it is a
card in the page rather than a modal or an overlay, so a person who
came to do something can ignore it and do that.

**The record.** The answer is one nullable timestamp on the user's
row, set through one endpoint when either button is pressed and
carried on the session payload as a boolean the landing page reads.
Nothing else is stored.

**No cookies, and no per-device memory.** The offer is shown only to a
signed-in account, which is already known on every request from the
token the browser holds. "Has this person been asked" is a fact about
the person, so it lives on their row and is right on their phone the
day after they answered on a laptop. Browser storage would need no
cookie either, but it forgets per device and per cleared browser, and
the card would come back on each. A cookie would be strictly worse:
sent on every request for no reason, and the first one the app sets.
The tours themselves are not remembered at all; they start from the
menu, on purpose, as often as somebody wants them. The sign-in tour
has no account and nothing about it is stored.

Personal accounts arrive with something already made at the start
door. The offer still fits: the welcome tour makes a second event, and
the person may cancel the form at step 3 without breaking anything,
because leaving the form page is outcome 5 above.

*Against the literature.* Harms's 47% is the difference between a
tutorial that is always on and one that appears on a "Show me"; the
menu item is the Show me. Carroll's production bias says the offer
card will be declined by most people most of the time, and that is
fine: the card costs one glance, and the tour is still there on the
day they want it. No study backs the card itself (chapter 3a).

*Against the code base.* The landing page's signed-in face is one
branch of `HomePage`, above the tile grid, so the card is a sibling of
the tiles inside the same column. The session payload is `UserOut` in
`schemas/auth.py`, served by `/auth/me`, and gains one boolean beside
`participant_mail`; the store's getter sits beside `participantMail`.
The endpoint is a POST and therefore carries a limit, by the audit in
`tests/test_rate_limits_audit.py`; `Limits.ORG_WRITE` is the right
budget, since it is a routine authenticated write. The column is one
Alembic revision on `users`, which already carries `tenant_id` and
needs nothing from the tenancy guard. Both signed-out front pages,
the organisation's and the root's, render the same `OrganiserDoor`,
so the door link is written once.

## 10. The refactors this needs

The tour only needs stable anchors, but reaching some of them cleanly
means finishing consolidations the pages are already halfway through.
Each is worth doing on its own.

**A form section component.** The four edit pages render the same
block 29 times between them, 15 of those with a switch in the
heading: a section, a heading that is sometimes a toggle row, an
optional explainer, then the fields, each copy wiring its own label
id for the switch. One component takes the heading, an optional bound
switch that turns the heading into a toggle row, an optional
explainer, the anchor name and the children. The pages lose about two
hundred lines of markup and every section has an anchor by existing.

**A fold component.** The extra-settings fold is copy-pasted into the
four edit pages, each with its own open state, toggle handler and the
two summary strings. One component with a bound open state registers
the fold's anchor on its summary. `docs/design-public-pages-ux.md`
already says every edit page ends the same way; this makes it one
place that can.

**The form shell** registers the card, the title and the submit
button. Nothing to consolidate; it owns all three.

**An anchor prop on the button**, since it does not spread attributes
(chapter 5).

**Anchors in the shared components.** The list page (new, details,
archive), the list view (chapter filter), the share stub (link, QR),
the details header (edit), the header (menu, subtabs), the tile grid
(one per tile), the recover-links pill, and the sign-in form (form,
sent state). The details pages register their own cards: sign-ups and
feedback.

**The router's matcher** is already exported as `matchRoute`, so the
engine matches a step's page with the same code the router uses.

**Panel placement takes an alignment.** A panel's left edge sits on
the anchor's left edge today, right for a menu and wrong for a callout
under a wide card. Start or centre is one line in the arithmetic; the
popover keeps start.

**A locale parity test.** None exists today: `i18n.test.ts` checks
missing-key handling and `form-copy.test.ts` compares only the product
keys. One test that walks both catalogues under the tour's prefix, and
may as well walk all of them.

**The offer card and its column.** A migration, one endpoint, one field
on the session payload, one getter on the session store, one card on
the landing page.

*Against the code base.* `docs/principles-ux.md` says a repeated idiom
becomes a composable at its third use; the section block is at its
twenty-ninth and the fold at its fourth. Both consolidations are owed
regardless of the tour. `EventFormPage` is 899 lines and
`DatepollEditPage` 812; the sections are most of that markup.

## 11. Copy

Every string is in the two locale files under one prefix; the parity
test from chapter 10 fails on a key one language lacks. Dutch first,
written as speech, one sentence per line, and no word the person has
not seen on the screen in front of them: the step about the QR says
"plaatje" and only then "QR-code", because the button it points at
says nothing.

Step titles are the question the step answers: "Hoe deel je de link?"
rather than "De link". The body answers it in one or two short active
sentences, everyday words, one thing per sentence.

Each step is read against the four minimalist principles: it is an
action, it is in the organiser's words, it says what to do if the
action did not take, and a person who knows the step can skip it.

*Against the literature.* Harms and colleagues saw users find the
right step more often after titles became questions, an observation
they did not measure. The Microsoft style guide's rules for
procedures, one action per step, the imperative, and saying where
before what, are the shape of a click step's body. The four principles
are Van der Meij and Carroll's, applied to onboarding the way
Froehlich and colleagues did.

## 12. Trying it on people

Before the copy is final, two organisers who have never used the app
take the welcome tour on their own phone. Somebody sits beside them
and answers only the questions they ask, and writes each question
down; that list is the list of steps that are wrong. What they
stumble on goes back into chapters 4 and 11. That is also the only
evidence this design will have from its own audience (chapter 3a).

*Against the literature.* This is the question-suggestion protocol of
Grossman, Fitzmaurice and Attar, which exposed significantly more
learnability problems than think-aloud in their study, and it costs
an afternoon.

## 13. Tests

* Anchors: every name a tour uses is declared, and every declared name
  is registered by some component.
* Engine, hosted the way the other composable tests are: a missing
  control is dropped once nothing is in flight and waited for while
  something is; a page mismatch after a click or until step waits and
  any other mismatch stops; an until step ends when its control
  registers; first in document order wins; session storage
  round-trips; Tab on a click step reaches the highlighted control and
  nothing else; Escape with focus outside the callout does nothing;
  a per-page tour's counter counts the steps that resolved at start.
* Overlay: the mask path's hole is the control's box plus padding at
  the element's radius, for a control at each corner and one taller
  than the viewport; a click on the fill is swallowed and a click in
  the hole is not; the sheet replaces the popover on a narrow viewport
  and for a tall hole; the mask sits below the toast layer.
* Locales: every key under the tour prefix exists in both languages.
* End to end, welcome: sign in as the seeded organiser who has not
  been offered the tour, press Start on the card, do what each of the
  five steps says, and end on a details page. The one test that
  proves the tour and the app agree, and the one that catches a
  dropped step in a tour whose count is declared.
* End to end, sign-in: signed out, start the sign-in tour from the
  door, type the seeded organiser's address at step 2, and see step 3
  light the sent state.

## 14. Not built

* No record of which step anyone stopped at, no counters, no events
  sent anywhere.
* No "don't show again" per step, no tour on the public pages, no
  tour for the start door: a signed-out visitor there is one form away
  from what they came for.
* No video, no images in callouts. ToolClips showed a short video in
  a tooltip works; it needs a video per control, which is the cost
  this design does not pay.
* No question corpus per control, as LemonAid had. The manual's
  questions at the end of each chapter are the nearest thing, kept by
  hand.
* No tour library. Driver.js is 7 kB gzipped by measurement (its
  readme says 5) and would do most of this, but it animates, closes on
  overlay click, positions by CSS selector and brings its own
  stylesheet, and every one of those would be configured away. The
  overlay here is one SVG path and the popover the app already has.

## 15. Cost

| piece | new | changed |
| --- | --- | --- |
| anchors, store, engine, overlay | ~500 lines | the app shell, `logout()` |
| six tours and their copy | ~100 lines, ~80 keys in each language | |
| form section and fold components | ~120 lines | four edit pages, about 200 lines fewer |
| anchor prop, anchors in shared components | | eleven components |
| header help group, door link | | header, door, sign-in form |
| offer card and its column | migration, one endpoint, one field | session store, landing page |
| tests | six files | |
| two organisers | one afternoon | |

Roughly a week, half of it the copy and the two end-to-end tests.
Nothing is added to the public bundles.

## 16. Sources

Peer-reviewed:

* Carroll, J. M. and Rosson, M. B. (1987). *Paradox of the Active
  User.* In Carroll (ed.), *Interfacing Thought: Cognitive Aspects of
  Human-Computer Interaction*, MIT Press, pp. 80-111.
  <https://research.cs.vt.edu/ns/cs5724papers/4.mental.mental.carroll.paradox.pdf>
* Kelleher, C. and Pausch, R. (2005). *Stencils-based tutorials:
  design and evaluation.* CHI 2005, pp. 541-550.
  <https://dl.acm.org/doi/10.1145/1054972.1055047>
* Harms, K. J., Kerr, J. H. and Kelleher, C. L. (2011). *Improving
  learning transfer from stencils-based tutorials.* IDC 2011.
  <https://kharms.infosci.cornell.edu/downloads/harmsk-idc-2011.pdf>
* Noriega, P., Carvalho, F., Correia, N., Alves, C., Oliveira, D. and
  Rebelo, F. (2019). *Effectiveness of Coach Marks or Instructional
  Overlay in Smartphone Apps Interfaces.* AHFE 2019, Springer.
  <https://link.springer.com/chapter/10.1007/978-3-030-20227-9_7>
* Grossman, T., Fitzmaurice, G. and Attar, R. (2009). *A survey of
  software learnability: metrics, methodologies and guidelines.* CHI
  2009, pp. 649-658. <https://dl.acm.org/doi/10.1145/1518701.1518803>
* Grossman, T. and Fitzmaurice, G. (2010). *ToolClips: an
  investigation of contextual video assistance for functionality
  understanding.* CHI 2010.
* Chilana, P. K., Ko, A. J. and Wobbrock, J. O. (2013). *LemonAid:
  selection-based crowdsourced contextual help for web applications.*
  CHI 2013 (with the field deployment paper of the same year).
* Froehlich, M., Kobiella, C., Schmidt, A. and Alt, F. (2021). *Is it
  Better With Onboarding? Improving First-Time Cryptocurrency App
  Experiences.* DIS 2021; and Strahm, B., Gray, C. M. and Vorvoreanu,
  M. (2018). *Generating Mobile Application Onboarding Insights Through
  Minimalist Instruction.* DIS 2018.
* Van der Meij, H. and Carroll, J. M. (1995). *Principles and
  heuristics for designing minimalist instruction.* Technical
  Communication 42(2), pp. 243-261.
* On plain language: Jansen, C., *'Teksten op B1-niveau' als leeg
  begrip* (Tekstblad); a 2025 self-paced reading study in the
  International Journal of Applied Linguistics (n = 117); a 2023
  randomised trial in JAMA Pediatrics (n = 268).

Practitioner:

* Nielsen Norman Group, *Mobile Tutorials: Wasted Effort or Efficiency
  Boost?* <https://www.nngroup.com/articles/mobile-tutorials/>;
  *Instructional Overlays and Coach Marks for Mobile Apps*
  <https://www.nngroup.com/articles/mobile-instructional-overlay/>;
  *Onboarding Tutorials vs. Contextual Help*
  <https://www.nngroup.com/articles/onboarding-tutorials/>
* Userpilot, *Why Product Tours Get Skipped*
  <https://userpilot.com/blog/everybody-hates-product-tours/>
* ExceedAbility, *Product Tours & Walkthroughs: Accessibility Guide*
  <https://exceedability.com/product-tours.html>
* Driver.js, *Configuration* <https://driverjs.com/docs/configuration>
  and its stylesheet; Shepherd.js, *Usage*
  <https://docs.shepherdjs.dev/guides/usage/>
* CommunicatieRijk, *Taalniveau B1*
  <https://www.communicatierijk.nl/vakkennis/rijkswebsites/aanbevolen-richtlijnen/taalniveau-b1>
* Microsoft Writing Style Guide, *Writing step-by-step instructions*
  <https://learn.microsoft.com/en-us/style-guide/procedures-instructions/writing-step-by-step-instructions>
