# Opkomst

Event sign-up tool for socialist organising. Privacy-first by design: attendees give a name (real or not), party size, and how they heard about the event. Optional email is encrypted at rest, used **once** to send a feedback form the day after the event, and then deleted.

The whole code base is open source — anyone can verify what the server does with the data.

## Stack

- Backend: FastAPI + SQLAlchemy + Alembic, SQLite locally / Postgres-ready, `uv` for deps.
- Frontend: Vue 3 + TypeScript + Vite + Pinia, PrimeVue.
- Auth: JWT with bcrypt password hashing.
- QR: server-rendered PNG via `qrcode[pil]`.
- Encryption: AES-GCM via `cryptography`, key from `EMAIL_ENCRYPTION_KEY` env var.

## Running

```bash
cp .env.example .env
# Edit .env to set JWT_SECRET, EMAIL_ENCRYPTION_KEY, etc.
set -a && source .env && set +a
uv run uvicorn backend.main:app --reload
```

Frontend dev server:

```bash
cd frontend && npm install && npm run dev
```

## Privacy posture

- No IP addresses, no User-Agent strings, no analytics, no cookies beyond the JWT bearer in localStorage.
- Email addresses, when supplied, are encrypted with AES-GCM before they hit disk.
- After the feedback email is sent (or after one retry fails), the encrypted email is **hard-deleted** from the database.
- Organisers and admins can never see attendees' email addresses through the UI or API. The only code path that decrypts is the post-event feedback worker.
- Sign-up forms display a one-paragraph notice with a link to this repository.
