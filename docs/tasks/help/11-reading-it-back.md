# 11: Reading it back with two organisers

Design: `docs/design-tour.md` chapter 12 and `docs/design-manual.md`
chapter 10. Not code. One afternoon, two people who have never used
the app, their own phones and one laptop.

## Protocol

The question-suggestion protocol (Grossman, Fitzmaurice and Attar):
one person sits beside the participant and answers only the questions
the participant asks, writing each question down verbatim with the
screen it was asked on. No prompting, no hints unless asked.

1. **The welcome tour**, on the participant's own phone, from the
   offer card, to Klaar.
2. **One per-page tour of their choosing**, from the menu.
3. **One chapter**, on the laptop with the app open on the other half
   of the screen: the participant picks a thing to make from the
   index and does what the chapter says.
4. **The printout question**: hand them the PDF's first chapter on
   paper and ask whether they would print it or send it to someone.
   Write the answer down; it is the only evidence the PDF gets.

## What comes out

- The list of questions, by screen. Each is a step or a paragraph
  that is wrong. Fix the copy in `tours.ts`'s locale keys and in the
  chapter files, reshoot any picture whose screen changed, and note
  in the commit which question drove it.
- Any place they pressed something the tour did not expect, which is
  an engine or anchor bug and goes back to task 03 or 01.
- The printout answers, recorded in `docs/design-manual.md` chapter
  3a, which currently says there is no evidence.

## Done when

The two sessions have happened, every question on the list has either
changed copy or has a one-line reason written next to it for not
changing anything, and the design docs' "where the evidence is thin"
sections say what was learned.
