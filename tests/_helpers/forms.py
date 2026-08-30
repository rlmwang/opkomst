"""Helpers for the form / quiz / kompas payload shapes.

Choices are rows with ids (``docs/design-question-edits.md``), so a
public answer is submitted by option id rather than by the label a
person read. The tests know the labels, so they translate here.
"""

import csv
import io
from typing import Any


def option_ids(question: dict[str, Any], *labels: str) -> list[str]:
    """The ids of the named options on a public question shape."""
    by_label = {o["label"]: o["id"] for o in question["options"]}
    return [by_label[label] for label in labels]


def csv_rows(response: Any) -> list[list[str]]:
    """A download parsed back into rows, header first.

    What somebody answered is read here rather than off a JSON
    endpoint: the download is the only place the app writes an answer
    out, and it is written by the database (``services/csv_export``)."""
    assert response.status_code == 200, response.text
    return list(csv.reader(io.StringIO(response.text.lstrip("﻿"))))


def answer_cells(client: Any, headers: Any, form: dict[str, Any], mode: str = "form") -> list[list[str]]:
    """One list of answer cells per submission, in question order. The
    two fixed columns (the pseudonym and when) are dropped, and a
    kompas' two coordinates with them."""
    rows = csv_rows(client.get(f"/api/v1/{mode}/{form['id']}/submissions.csv", headers=headers))
    fixed = 4 if mode == "compass" else 2
    return [row[fixed:] for row in rows[1:]]
