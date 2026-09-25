# 10: Writing the chapters

Design: `docs/design-manual.md` chapters 4 and 10. Not a code task,
but it is the largest task in the series: fourteen chapters in two
languages, about 4,000 words per language. The text can be written
against the app before the pictures exist (task 08); the picture
references go in as the pictures are shot.

## The checklist per chapter

Before a chapter is committed, read it against these, in order:

1. **Two sentences on what it is for**, then the first step. Nothing
   else above the first numbered step.
2. **One action per step**, imperative, where before what, the
   control's name in bold and spelled as the screen spells it:
   "Onderaan het formulier klik je op **Opslaan**."
3. **A picture per step**, referenced by tour, product and step name.
   No crops, no pictures that are not tour steps.
4. **A checkpoint** ("Je ziet nu …") with its `after.` picture, then
   the two or three ways it goes wrong here and the way back.
5. **Three or four questions** people ask about this thing, each one
   paragraph, titled as the question.
6. **Two printed pages at most.** Longer is two chapters.
7. **Organisation-only paragraphs** carry `{: .organisation }` and
   there are none in the other direction. Chapter 1: the name step
   and the wait for an admin. Chapter 2: the chapter picker. Nothing
   in chapters 1 to 11 otherwise mentions a chapter, an admin, a
   plan, or an organisation.
8. **Short sentences, everyday words, one thing each.** No term the
   screen does not use; where the screen uses none, the everyday word
   first and the term after it ("het plaatje, de QR-code").
9. **Dutch first, written natively**; the English is its own text, not
   a translation. `docs/style-nederlands.md` and `docs/style-copy.md`.
10. **No dashes.**

## Chapter notes

- **1 inloggen**: the four sign-in tour steps are the four steps. The
  lost-link case belongs to chapter 11, not here.
- **3 aanmeldingen**: what a sign-up shows the organiser (name, party
  size, how they heard), the share link and the QR, the recover-links
  pill. No email is mentioned in the root text.
- **4 herhalen**: the k-week cycle in the organiser's words; the
  picker's own labels.
- **6 takenrooster**: one question at the end is the volunteer's
  address at the enrol page, used once for their personal link and
  not kept.
- **10 archief**: archive, the archived subtab, restore. Say plainly
  what is gone and what comes back.
- **11 misgaat**: the general card. Entries, three lines each: what you
  see, what happened, what to do. Lost sign-in link; wrong date after
  people signed up; archived by accident; sign-in mail not arrived;
  link says it expired.
- **12 to 14**: organisation only. 14 is the only chapter that links
  to `/privacy`, and it is the privacy contract in plain words:
  encrypted at rest, used once for the feedback form the day after,
  then deleted; reminders the same.

## Done when

- `tests/test_manual.py`'s reference test is green with the full
  picture set.
- Each chapter has been walked once with the app open, doing exactly
  what it says, by somebody other than its author.
- Both languages complete, the parity of chapter numbers holding.
