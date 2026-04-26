"""Outbound email copy.

One function per email kind, each returning ``(subject, body)``. Plain
text only — no HTML, no tracking pixels, no third-party fonts.

Subject lines are short by design (Delighted / SurveyMonkey research:
4–10 words optimal). Body copy reaffirms the privacy contract and
links to the open-source repo so recipients can verify what we do
with their address.
"""


def feedback_invite(*, event_name: str, feedback_url: str, locale: str = "nl") -> tuple[str, str]:
    """The single feedback mail sent ~24h after an event ends. After
    this mail goes out (or fails after one retry), the recipient's
    encrypted address is hard-deleted — see services.feedback_worker.
    """
    if locale == "en":
        subject = f"How was {event_name}?"
        body = (
            f"Thanks for coming to {event_name}.\n\n"
            f"We'd love two minutes of your time to make the next one better:\n"
            f"{feedback_url}\n\n"
            "This is the only email you'll get from us; your address is deleted right after we send this one. "
            "You can read the full source of this app at https://github.com/rlmwang/opkomst.\n"
        )
    else:
        subject = f"Hoe was {event_name}?"
        body = (
            f"Bedankt voor je komst naar {event_name}.\n\n"
            f"Twee minuten van je tijd helpt ons de volgende beter te maken:\n"
            f"{feedback_url}\n\n"
            "Dit is de enige mail die je van ons krijgt; je adres wissen we direct nadat we deze hebben verstuurd. "
            "De volledige broncode van deze app vind je op https://github.com/rlmwang/opkomst.\n"
        )
    return subject, body
