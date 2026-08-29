"""Helpers for the form / quiz / kompas payload shapes.

Choices are rows with ids (``docs/design-question-edits.md``), so a
public answer is submitted by option id rather than by the label a
person read. The tests know the labels, so they translate here.
"""

from typing import Any


def option_ids(question: dict[str, Any], *labels: str) -> list[str]:
    """The ids of the named options on a public question shape."""
    by_label = {o["label"]: o["id"] for o in question["options"]}
    return [by_label[label] for label in labels]
