# Opkomst

Event sign-up tool for socialist organising. Privacy-first by design: attendees give a name (real or not), party size, and how they heard about the event. Optional email is encrypted at rest, used **once** to send a feedback form the day after the event, and then deleted.

The whole code base is open source — anyone can verify what the server does with the data.

## Stack

- Backend: FastAPI + SQLAlchemy + Alembic on Postgres (`make db-up` boots a local instance via docker compose), `uv` for deps.
- Frontend: Vue 3 + TypeScript + Vite + Pinia, PrimeVue.
- Auth: passwordless magic-link sign-in. Single-use links by email, JWT after redemption.
- QR: server-rendered PNG via `qrcode[pil]`.
- Encryption: AES-GCM via `cryptography`, key from `EMAIL_ENCRYPTION_KEY` env var.

## Running

```bash
cp .env.example .env
# Edit .env to set JWT_SECRET, EMAIL_ENCRYPTION_KEY, etc.
make db-up
set -a && source .env && set +a && uv run uvicorn backend.main:app --reload
```

Frontend dev server:

```bash
cd frontend && npm install && npm run dev
```

## Local mode

Set `LOCAL_MODE=1` in `.env`, then run the seeder once to populate two test accounts and two demo events:

```bash
uv run python -m backend.cli seed-demo
```

The seeder is idempotent — it never touches rows it didn't create — so re-running it is safe. It refuses to run unless `LOCAL_MODE=1`, so a stray invocation against prod can't fabricate fake users.

| Email                  | Role      |
|------------------------|-----------|
| `admin@local.dev`      | admin     |
| `organiser@local.dev`  | organiser |

Both accounts are pre-approved. To sign in:

1. Open the frontend (default `http://localhost:5173`) and go to `/login`.
2. Enter `admin@local.dev` (or `organiser@local.dev`) and click "Send link".
3. With `EMAIL_BACKEND=console` (the dev default), the backend writes a structured log line for each email it would have sent. Look for `event=email_console` and copy the link out of `urls=[...]`:

   ```
   event=email_console to=admin@local.dev subject='Sign in to opkomst.nu' \
     urls=['http://localhost:5173/auth/redeem?token=<...>']
   ```

4. Paste the URL into your browser. The page redeems the token, stores the JWT, and redirects you to `/events`.

The link works once and expires in 30 minutes. Click "Send link" again to mint a fresh one. The organiser owns one upcoming and one past event; the past event has a signup with an encrypted email so the hourly feedback worker has something real to chew through. Use it locally only.

A first-time visitor whose email isn't seeded will instead receive a "create your account" link — clicking it lands on `/register/complete?token=…`, asks for a name, and signs them in. Same `event=email_console` log shape.

## Privacy posture

- No IP addresses, no User-Agent strings, no analytics, no cookies beyond the JWT bearer in localStorage.
- Email addresses, when supplied, are encrypted with AES-GCM before they hit disk.
- After the feedback email is sent (or after one retry fails), the encrypted email is **hard-deleted** from the database.
- Organisers and admins can never see attendees' email addresses through the UI or API. The only code path that decrypts is the post-event feedback worker.
- Sign-up forms display a one-paragraph notice with a link to this repository.

## License

EUPL-1.2 — see [LICENSE](LICENSE).

This is a copyleft license: anyone running a modified version of
opkomst as a public service must publish their modifications. We
chose this on purpose. The product makes a privacy promise to
attendees ("we hold less email than you'd expect, here's the
source"); a permissive license that lets a fork run with the
promise removed would defeat the contract.
