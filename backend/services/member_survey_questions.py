"""Static question set for the new-members feedback survey.

A separate, single-purpose questionnaire from the per-event
``feedback_questions`` module: this one runs *outside* the
event-feedback flow, has its own answer columns (no
``question_key`` / ``answer_int`` row-per-question shape), and
asks questions specifically about activation of new members.

The barrier keys are an enum-ish allowlist — the submit
endpoint validates incoming Q4 selections against this set so a
malicious / drifting client can't insert arbitrary strings into
the column. Adding a barrier: append a key here, add the i18n
string under ``memberSurvey.barriers.<key>`` in
``frontend/src/locales/{nl,en}.json``.
"""

# Stable identifiers for the Q4 multi-select. Order is also the
# rendering order in the form. Mapped to the Civic Voluntarism
# Model components in nieuwe-leden-feedback.md.
BARRIER_KEYS: tuple[str, ...] = (
    "no_time",
    "distance_or_cost",
    "lacks_knowledge",
    "no_clear_step",
    "knows_no_one",
    "nobody_asked",
    "not_for_me",
    "doubts_impact",
)

BARRIER_KEY_SET: frozenset[str] = frozenset(BARRIER_KEYS)
