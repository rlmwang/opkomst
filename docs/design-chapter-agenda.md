# Chapter agendas

A chapter's public page lists what is coming up. One URL per chapter,
under its organisation: `/{organisation}/{chapter}`.

An event appears there when the organiser switches "show on the chapter
agenda" on. The sign-up link works either way, so an event can be
public and unlisted at the same time: handed out in a group chat rather
than published.

The page shows upcoming events as cards, with a recent-past section
under them. How far it looks in each direction is the organisation's
own setting (`agenda_future_days`, `agenda_past_days`), because an
organisation that programmes a season wants months and one that runs a
weekly meeting wants a fortnight. The rule is in `services/agenda.py`.

Only a chapter has an agenda. A personal account has no chapters, so it
has no agenda and its create form does not offer the switch.
