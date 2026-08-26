"""The histogram for a number question.

Two shapes, and which one a question gets depends on **what it allows**
rather than on what came back. A question that takes 1 to 5 has five
bars whether two people answered or two hundred, and the axis says what
could have been said as much as what was:

* **A bar per allowed value**, when the question's own bounds and step
  leave few of them. "How many are you bringing", 1 to 6, is six bars;
  binning that into ranges throws away the only thing it says. Values
  nobody picked are drawn empty, which is a fact about the answers.

* **Binned**, past ``DISCRETE_LIMIT`` allowed values, or when the
  question sets no bounds at all and there is nothing to enumerate.

The bin count uses Freedman-Diaconis, ``width = 2 * IQR / n**(1/3)``,
which is what numpy and matplotlib reach for by default and which is
robust to one person answering 10000: an outlier moves the range but
not the interquartile spread. Where every answer sits inside one
quartile the IQR is zero and the rule divides by nothing, so Sturges
(``ceil(log2 n) + 1``) takes over, which is the classic rule and fine
at these sizes. The result is clamped to ``MIN_BINS``..``MAX_BINS``:
below five a histogram stops being one, and above twenty the bars are
narrower than the labels under them.

Sources for the two rules: Freedman and Diaconis (1981), Sturges
(1926); the clamp is this app's, chosen for the width of a phone.
"""

from __future__ import annotations

import math

from ..schemas.forms import NumberBucket

# Below five bars a histogram stops being one; above twenty the bars are
# narrower than the labels under them, on the width of a phone.
MIN_BINS = 5
MAX_BINS = 20
# A question is drawn one bar per allowed value while its options fit in
# the most bars we would ever draw. The same number, because the reason
# is the same: past it there is no room.
DISCRETE_LIMIT = MAX_BINS


def _quartile(values: list[int], q: float) -> float:
    """Linear-interpolated quantile, the same convention numpy uses, so
    the bin width matches what anyone checking this in a notebook
    gets."""
    if not values:
        return 0.0
    position = (len(values) - 1) * q
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return float(values[low])
    return values[low] * (high - position) + values[high] * (position - low)


def bin_count(values: list[int]) -> int:
    """How many bars, by Freedman-Diaconis with a Sturges fallback."""
    n = len(values)
    ordered = sorted(values)
    spread = ordered[-1] - ordered[0]
    iqr = _quartile(ordered, 0.75) - _quartile(ordered, 0.25)
    if iqr > 0:
        width = 2 * iqr / (n ** (1 / 3))
        count = math.ceil(spread / width) if width > 0 else MIN_BINS
    else:
        count = math.ceil(math.log2(n)) + 1 if n > 1 else 1
    return max(MIN_BINS, min(MAX_BINS, count))


def allowed_values(min_value: int | None, max_value: int | None, step: int | None) -> list[int] | None:
    """Every number this question accepts, or None when it accepts too
    many to enumerate (no bounds, or a range wider than a histogram can
    hold a bar for)."""
    if min_value is None or max_value is None or max_value < min_value:
        return None
    stride = step or 1
    count = (max_value - min_value) // stride + 1
    if count > DISCRETE_LIMIT:
        return None
    return [min_value + i * stride for i in range(count)]


def histogram(
    values: list[int],
    min_value: int | None = None,
    max_value: int | None = None,
    step: int | None = None,
) -> list[NumberBucket]:
    """The bars for one number question, in ascending order.

    The shape follows the question's own options, not the answers: a
    question that allows six numbers gets six bars, including the ones
    nobody picked."""
    if not values:
        return []
    ordered = sorted(values)

    options = allowed_values(min_value, max_value, step)
    if options is not None:
        counts = dict.fromkeys(options, 0)
        for v in ordered:
            # An answer outside the allowed set can only be one stored
            # before the bounds were tightened. It belongs on the
            # nearest bar rather than nowhere.
            nearest = min(options, key=lambda option: abs(option - v))
            counts[nearest] += 1
        return [NumberBucket(label=str(v), count=c) for v, c in counts.items()]

    low = min_value if min_value is not None else ordered[0]
    high = max_value if max_value is not None else ordered[-1]
    span = high - low
    # A question that allows one number, or a run of identical answers:
    # one bar says it.
    if span <= 0:
        return [NumberBucket(label=str(low), count=len(ordered))]

    bins = bin_count(ordered)
    width = max(step or 1, math.ceil((span + 1) / bins))
    buckets: list[NumberBucket] = []
    start = low
    while start <= high:
        end = min(start + width - 1, high)
        count = sum(1 for v in ordered if start <= v <= end)
        buckets.append(NumberBucket(label=str(start) if start == end else f"{start}-{end}", count=count))
        start = end + 1
    return buckets
