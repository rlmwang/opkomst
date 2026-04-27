# Security audit — 2026-04-27

Methodical sweep over the backend (FastAPI + SQLAlchemy, ~3300 LOC of
application Python plus migrations) and the security-relevant frontend
glue. Scoring is informal: **HIGH** = exploitable as-shipped, **MEDIUM**
= exploitable under a plausible deploy mistake, **LOW** = hardening
opportunity.

All findings flagged as actionable were fixed in commit **61ba2a6**.

## Findings

### 1. SPA fallback path traversal — HIGH — fixed

`backend/main.py:_spa_fallback` built `target = _DIST / full_path`
without normalising. A request like `GET /../../../../etc/passwd`
resolved to a path outside the dist directory; `target.is_file()` then
served the file. Whether the ASGI server pre-normalises is
implementation-defined and we should not depend on it.

**Fix**: resolve the candidate path and require it to live under
`_DIST_RESOLVED` (`relative_to` raises `ValueError` otherwise). Anything
that fails the check falls back to `index.html` rather than 404 — a 404
would leak the existence check.

### 2. Scaleway webhook failed open without a configured secret — MEDIUM — fixed

`_verify_signature` returned silently when `SCALEWAY_WEBHOOK_SECRET`
was unset. The blast radius was bounded — the webhook only flips a
`feedback_email_status` between `sent`, `bounced`, and `complaint` —
but an attacker who found the URL could mark every signup's email as
bounced for the entire venue, which is exactly the metric organisers
look at on the summary page.

**Fix**: fail closed — missing secret returns 503. Local development
that wants to fire unsigned posts sets `OPKOMST_ALLOW_UNSIGNED_WEBHOOKS=1`
as an explicit opt-in.

### 3. `send-feedback-emails` was unrate-limited — MEDIUM — fixed

`POST /api/v1/events/{id}/send-feedback-emails` could be hit
arbitrarily often. Each call decrypted the still-pending blobs, minted
SMTP traffic, and on failure retried twice per signup. A bored or
compromised organiser could push the venue's outbound email reputation
off a cliff in minutes.

**Fix**: `@limiter.limit("5/hour")`. The action is idempotent for
already-sent signups, so a low cap doesn't break the feature.

### 4. CSP `connect-src` listed unused geocoders — LOW — fixed

The policy still allowed `https://photon.komoot.io` and
`https://nominatim.openstreetmap.org` from earlier address-picker
iterations. Only PDOK is in use today.

**Fix**: dropped both. CSP narrowing is free.

### 5. CORS defaulted to localhost — LOW (deploy footgun) — fixed

`allow_origins` defaulted to `http://localhost:5173`. In production the
frontend is same-origin so the policy doesn't engage; the danger was a
future deploy on a separate API subdomain forgetting the env var and
having prod browsers silently rejected while the dev origin stayed
trusted.

**Fix**: dropped the default. Unset `CORS_ORIGINS` now fails the
process at boot, matching how `JWT_SECRET` and `EMAIL_ENCRYPTION_KEY`
already behave. Added to `.env`.

### Incidental: structlog `event` keyword collision — fixed

`logger.info("scaleway_event_unmatched", event=event_type, ...)`
shadowed structlog's reserved `event` message-name kwarg and would have
crashed any unmatched-event log line. Renamed every webhook log key
from `event=` to `event_type=`.

## Findings — accepted, not fixed

### 6. JWT TTL = 7 days, no revocation — LOW

A leaked JWT remains valid for a week. There is no allowlist /
revocation list, no `token_version` on the user, and no
logout-all-devices flow.

For a non-financial volunteer-org tool with bounded blast radius
(create events, view signup tallies) this is acceptable. If we add a
"log out everywhere" feature it should bump a `token_version` claim
that we then validate inside `_decode_token`.

### 7. `register` rate limit is per-IP, not per-email — LOW

Five registrations per IP per hour is a fine global limit but doesn't
prevent an attacker from churning thousands of throwaway emails through
one IP across days, exhausting SCD2 chain space and burning through
SMTP quota for verification emails.

The current code already 409s after the first registration so the
abuse case is "register a new email each time", which is an SMTP-quota
concern more than a security concern. Revisit if abuse appears.

## Verified safe

- **Password hashing**: bcrypt with 72-byte truncation, documented.
- **JWT decoding**: `jose.jwt.decode` is called with an
  `algorithms=[JWT_ALGORITHM]` whitelist on every path — alg=none is
  not accepted.
- **Email encryption**: AES-GCM with 12-byte random nonce, key
  validated to 32 bytes at import. Decrypt is only called from
  `feedback_worker._process_one`, which always wipes the ciphertext
  after the call (privacy invariant — also documented in CLAUDE.md).
- **Feedback privacy contract**: `FeedbackToken` row is deleted on
  submit; `submission_id` is a fresh `secrets.token_urlsafe(16)` per
  submission. After redemption no row in the system can map a response
  back to a signup.
- **Chapter scoping**: `_scope_filter` and the `chapter_match` filter
  are applied uniformly to every organiser-side event read; events
  outside the user's chapter return 404 (not 403) so existence
  doesn't leak.
- **Self-deletion / self-demotion guards**: blocked at the admin
  router level.
- **SQL injection**: every query uses SQLAlchemy parameter binding;
  no `f"..."` SQL anywhere.
- **Sentry PII**: `send_default_pii=False`.
- **HSTS**: only set when the request was actually served over HTTPS.
- **Required secrets**: `JWT_SECRET`, `EMAIL_ENCRYPTION_KEY`, and
  (post-audit) `CORS_ORIGINS` are read with `os.environ[...]`, so a
  missing key fails-closed at process start.
- **PII in logs**: structlog calls log `user_id`, `entity_id`, and
  status enums but never email addresses, passwords, or token
  contents.
