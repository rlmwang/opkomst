# WhatsApp blast tool

An admin-only page for sending one-off personalised WhatsApp messages
to a list somebody pastes in, through a self-hosted Evolution API.

It exists because the alternative is an organiser copying and pasting
the same message forty times, and because the mail this app sends is
deliberately narrow.

## What it does not do

No database. The pasted list lives in the browser tab and nowhere else,
the backend proxies each send without writing anything down, and
closing the tab loses it. There is no address book, no history and no
delivery log: a tool that remembers who was messaged is a tool that has
a list of members in it.

## Shape

The page takes a CSV-ish paste, normalises the numbers to country-code
form, and offers merge tags so each message can carry a name. It shows a
preview of the formatting WhatsApp will apply. Sending is one request
per recipient, sequential, with the failures reported as they happen.

The backend half is a thin proxy: `services/whatsapp.py` and
`routers/whatsapp.py`, both stateless. The admin surface is hidden
entirely unless the Evolution environment variables are set.
