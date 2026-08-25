# Design: images come from opkomst.nu, and stop piling up

Status: proposed. Every hero image an organiser uploads is public at
`raw.githubusercontent.com/{account}/{repo}/main/events/{id}/{ts}.jpg`.
That URL is on every event page, every agenda card, every link preview
and inside reminder and feedback mail, so the account that hosts them is
visible to everyone who ever sees an event. Nothing deletes anything
either: removing an image clears the database column and leaves the
file, replacing one leaves the old file next to the new one, and an
archived event keeps its picture for good.

Two changes, both small: the app serves the bytes under its own domain,
and a daily sweep deletes what nothing points at any more.

## What already holds

Uploads are normalised before they are stored, and that part stays as
it is: EXIF rotation applied and the block dropped, centre-cropped to
4:5, resized to 1200x1500, flattened to sRGB, JPEG q85 progressive,
with an 8 MiB ceiling on what may be sent in. A stored file is
typically 150 to 350 KB. There is one size and one ratio, and every
surface reads the same file.

## The URL

The row stores the storage path, not a URL:

```
image_path = "events/01931f.../1748962311000.jpg"
```

and everything that renders an image asks for it at

```
https://opkomst.nu/i/events/01931f.../1748962311000.jpg
```

`GET /i/{path}` is a public route on the API. It reads the file from
the images host server-side and answers with the JPEG. The path carries
the upload's timestamp, so a given URL is one specific file for ever:
the response is `Cache-Control: public, max-age=31536000, immutable`,
which Cloudflare and every browser will hold on to, and the origin sees
each image roughly once.

`raw.githubusercontent.com` comes out of the CSP's `img-src` at the
same time, because images are now same-origin.

The repo stays public. What this buys, then, is that nobody reading a
page, a link preview or an email learns where the file is kept: the
account name is out of every URL the app hands out. It is not a
guarantee of secrecy, and the doc should be honest about the
difference. Somebody who finds the repository by other means can still
browse every image in it. Making it private is the version that would
close that, and it stays available later at the cost of breaking the
pictures in mail already delivered, which is why it was not taken now.

Email keeps working unchanged: mail clients need an absolute URL that
answers without a session, and `https://opkomst.nu/i/…` is one.

The path shape stays readable (`{kind}/{entity id}/{timestamp}.jpg`).
It names the app's own entities and nothing about where the file
sleeps, so there is nothing to hide in it.

## What deletes what

Three moments, one helper:

- **Replacing an image** deletes the file it replaces. The row points
  at one file; the previous one has no reader the moment the column is
  overwritten.
- **Removing an image** deletes the file as well as clearing the
  column. Today it only clears the column, which is how the repo
  collected files nothing references.
- **A daily sweep** deletes the image of anything archived longer than
  21 days, and clears the column with it. Restoring inside the window
  gets the picture back; past it, the entity comes back without one.
  Three weeks is long enough that archiving is still reversible in
  practice and short enough that a season's worth of finished events
  doesn't sit around.

The sweep is a CLI subcommand next to the others (`reap-images`), run
by the same cron that runs `reap-expired`, with the same Sentry
check-in, so a sweep that stops running is noticed.

Deleting through GitHub's Contents API needs the file's blob sha, so
each delete is a read then a delete. That is two calls per file on a
sweep that has nothing to do most days.

**Git history keeps the bytes.** A file deleted this way is gone from
the current tree, so a checkout stays small, but the blob stays in the
repository's history for ever and the repository only grows. That is
accepted here rather than worked around: the growth is a few hundred KB
per image ever uploaded, and the alternative is either rewriting
history on a schedule or moving the bytes to object storage, which is a
service to run and pay for. If the repo ever does become unwieldy, the
answer is to start a fresh images repo, not to rewrite the old one.

## Failure

The proxy route answers 404 for a path that isn't there, and 502 if
the images host is unreachable, and it never names that host in a
response, a header or an error shown to anyone. A failed delete is logged and left:
the file stays, the sweep tries again tomorrow, and nothing user-facing
depends on it having worked.

An entity whose image the sweep already removed renders exactly like
one that never had a picture, which every surface already handles: the
public pages fall back to the poster placeholder, and the link-preview
card falls back to the organisation's favicon.

## What changes, by file

- `backend/models/{events,forms,datepolls,chores}.py` and their
  mixin: `image_url` becomes `image_path`.
- `backend/alembic/versions/…` — rename the column and rewrite the
  values, stripping the `raw.githubusercontent.com/{owner}/{repo}/
  {branch}/` prefix off the rows that carry one.
- `backend/services/image.py` — `public_url(path)` builds the
  `/i/{path}` URL; `fetch(path)` reads a file back; `delete(path)`
  removes one; the upload returns a path rather than a URL.
- `backend/routers/images.py` — the public `GET /i/{path}` route.
- `backend/services/image_reaper.py` — the grace-period sweep across
  the four kinds, plus `backend/cli.py` for the subcommand and its
  monitor slug.
- `backend/routers/{events,forms,datepolls,chores}.py` — the delete
  endpoint deletes the file; the upload endpoint deletes the one it
  replaces.
- `backend/schemas/…` and `backend/services/…` — the DTOs keep
  emitting `image_url`, now built from the path, so the frontend and
  the mail templates are untouched.
- `backend/services/security_headers.py` — `img-src` drops
  `raw.githubusercontent.com`.
- `docs/deploy.md` — the images repo keeps its current visibility and
  its token keeps its current scope; what changes is that image URLs
  are the app's own, so a deploy without the images host reachable
  serves 502s from one route rather than broken images everywhere.
- `tests/test_images.py` — the proxy answers, caches and hides its
  upstream; replace and remove delete the old file; the sweep respects
  the grace period and leaves live entities alone.

## Decisions

1. **The app serves the bytes.** Not a Cloudflare rule: the mapping
   belongs in the repository with everything else, next to the route
   that produces the URLs.
2. **The repo stays public.** The account is out of every URL the app
   hands out, which is what was asked for. Going private would also
   hide the repository itself, and it would break the pictures in mail
   already delivered, so it is left as a later choice rather than a
   condition of this one.
3. **The bytes stay on GitHub.** Deleting at HEAD keeps the working
   tree small without adding a storage service to run. History growing
   for ever is the accepted cost, and starting a fresh repo is the
   escape hatch.
4. **Twenty-one days after archiving.** Archiving is reversible and
   organisers use it that way, so deleting on archive would quietly
   cost them the picture. Nothing is ever deleted while an entity is
   live.
5. **The processing pipeline is unchanged.** One ratio, one size, one
   quality. If files ever need to be smaller, 1080x1350 at q82 is about
   a third off and still sharp on a retina phone, but that is a
   separate decision from where they live.
