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

Set `LOCAL_MODE=1` in `.env` and the backend will seed two test accounts and two demo events on every startup (idempotently — it never touches rows it didn't create):

| Email                  | Role      |
|------------------------|-----------|
| `admin@local.dev`      | admin     |
| `organiser@local.dev`  | organiser |

Both accounts are pre-approved. To sign in:

1. Open the frontend (default `http://localhost:5174`) and go to `/login`.
2. Enter `admin@local.dev` (or `organiser@local.dev`) and click "Send sign-in link".
3. With `EMAIL_BACKEND=console` (the dev default), the backend writes a structured log line for each email it would have sent. Look for `event=email_console` and copy the link out of `urls=[...]`:

   ```
   event=email_console to=admin@local.dev subject='Sign in to opkomst.nu' \
     urls=['http://localhost:5174/auth/redeem?token=<...>']
   ```

4. Paste the URL into your browser. The page redeems the token, stores the JWT, and redirects you to `/dashboard`.

The link works once and expires in 30 minutes. Click "Send sign-in link" again to mint a fresh one. The organiser owns one upcoming and one past event; the past event has a signup with an encrypted email so the hourly feedback worker has something real to chew through. Use it locally only.

## Privacy posture

- No IP addresses, no User-Agent strings, no analytics, no cookies beyond the JWT bearer in localStorage.
- Email addresses, when supplied, are encrypted with AES-GCM before they hit disk.
- After the feedback email is sent (or after one retry fails), the encrypted email is **hard-deleted** from the database.
- Organisers and admins can never see attendees' email addresses through the UI or API. The only code path that decrypts is the post-event feedback worker.
- Sign-up forms display a one-paragraph notice with a link to this repository.
