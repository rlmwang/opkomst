# The kompas

A questionnaire that places you on a map. The organiser names two axes
and says, per answer, which way it moves you. You fill it in, see where
you landed, and see the rest of the room around you.

## Not a new engine

A kompas is the `forms` table's third mode, next to a questionnaire and
a quiz. One new answer meaning (a direction instead of a key), one new
derived number (a coordinate instead of a score), one new picture (a map
instead of a histogram). Everything else is the questionnaire it already
was.

## The axes

Exactly two, `x` and `y`, each with a name and a name for both of its
sides. They are a child table rather than four columns on the form,
because the sides are content an organiser writes and translates.

A question points at one side of one axis: `x_low`, `x_high`, `y_low`
or `y_high`.

* **A statement** is rated 1 to 5, and the organiser says which side a
  5 means.
* **A multiple-choice question** carries a side per option, so "Zorg"
  and "Defensie" can pull opposite ways in the same question.

## The arithmetic

One answer is worth a number in [-1, 1]. A rating is
`(answer - 3) / 2` signed by its side, so a 5 is `+1`, a 1 is `-1` and a
3 is `0`. A chosen option is `+1` or `-1` with nothing in between.

A position is the mean per axis of the answers that spoke to it. A mean
rather than a sum, so a kompas with eight questions on one axis and
three on the other still reads on one scale. Unanswered questions drop
out rather than pulling toward the middle.

The domain is fixed at [-1, 1] and never derived from the data. A map
that rescaled as people filled it in would move your dot after you had
seen it.

Positions are derived on every read, never stored. Move an option to the
other side and every dot moves with it, which is what the organiser
meant by editing.

## What people see

During the walk, nothing says which way an answer points. A page that
tells you which button moves you right is a page people aim at.

Afterwards: the map, with your dot and everybody else's. Dots at the
same coordinate merge into one bigger dot rather than being jittered
apart, because jitter puts a dot where nobody is. Under it, per axis,
where you landed and what each answer contributed.

The organiser sees the same map, plus where the room sits on each axis
with a 95% confidence interval around it. The interval, not the range:
the range widens as more people arrive, which reads as the answer
getting less certain the more of it you have.

## Where it lives

```
backend/services/compass.py          contributions, positions, axis stats
backend/models/compass.py            the two axis rows
frontend/src/public_shared/CompassPlot.vue   the map, shared by both sides
frontend/src/public_compass/         the respondent's walk and result
```
