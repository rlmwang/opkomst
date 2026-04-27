# Security audit — 2026-04-27

Methodical sweep over the backend (FastAPI + SQLAlchemy, ~3300 LOC of
application Python plus migrations) and the security-relevant frontend
glue. Scoring is informal: **HIGH** = exploitable as-shipped, **MEDIUM**
= exploitable under a plausible deploy mistake, **LOW** = hardening
opportunity.

## Findings

### 1. SPA fallback is a path-traversal sink — HIGH

`backend/main.py:130-143`:

```python
@app.get("/{full_path:path}", include_in_schema=False)
def _spa_fallback(full_path: str) -> FileResponse:
    if full_path.startswith("api/") or full_path == "health":
        raise HTTPException(status_code=404, detail="Not found")
    target = _DIST / full_path
    if target.is_file():
        return FileResponse(target)
    return FileResponse(_DIST / "index.html")
```

`_DIST / full_path` is *not* normalised. A request like
`GET /..%2f..%2f..%2f..%2fetc%2fpasswd` (or, depending on the front
proxy, `GET /../../../../etc/passwd`) resolves to a path *outside*
`_DIST`. `target.is_file()` then returns the file's contents.

Whether ASGI / Uvicorn pre-normalises is implementation-defined — we
must not depend on it. Starlette's `:path` converter is a literal
match.

**Fix**: resolve both paths and require the resolved target to live
under `_DIST`. Reject otherwise (return `index.html`, *not* a 404 — a
404 leaks the existence check).

### 2. Scaleway webhook fails open without a configured secret — MEDIUM

`backend/routers/webhooks.py:39-48`:

```python
def _verify_signature(raw_body: bytes, header_value: str | None) -> None:
    secret = os.environ.get("SCALEWAY_WEBHOOK_SECRET", "")
    if not secret:
        # Dev mode — no secret configured, accept everything.
        return
    ...
```

If `SCALEWAY_WEBHOOK_SECRET` is missing in production (env-vars are
copy-pasted from `.env.example`, deploys are routine), the endpoint
accepts unsigned bodies. The blast radius is bounded — webhook only
flips a `feedback_email_status` from `sent` to `bounced`/`complaint` —
but an attacker who finds the URL can mark every signup's email as
bounced for the entire venue, which is exactly the metric organisers
look at on the summary page.

**Fix**: fail closed. Read the secret at module import; if it isn't set
*and* `ENV != "dev"` (some other gate), refuse to register the route —
or, simpler, raise on every request. The current dev-friendliness can
move into an explicit `OPKOMST_ALLOW_UNSIGNED_WEBHOOKS=1` opt-in for
local testing.

### 3. `send-feedback-emails` endpoint is unrate-limited — MEDIUM

`backend/routers/events.py:167-181`. An approved organiser can hit
`POST /api/v1/events/{id}/send-feedback-emails` arbitrarily often. Each
call decrypts the still-pending blobs, mints SMTP traffic, and on
failure re-tries twice per signup. A bored or compromised organiser
could push the venue's outbound email reputation off a cliff in
minutes.

**Fix**: `@limiter.limit("5/hour")` (the action is idempotent for
already-sent signups, so a low cap doesn't break the feature).

### 4. CSP `connect-src` lists three geocoders — LOW

`backend/services/security_headers.py:33-48` allows
`https://photon.komoot.io`, `https://api.pdok.nl`, and
`https://nominatim.openstreetmap.org`. Only PDOK is used today; Photon
and Nominatim are leftover from earlier address-picker iterations.

**Fix**: drop the two unused origins. CSP narrowing is free.

### 5. CORS defaults to localhost — LOW (deploy footgun)

`backend/main.py:94`:

```python
allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")
```

In production the frontend is same-origin so the policy doesn't
actually engage, but the *default* is a localhost CORS allowance — if
a deploy ever serves the API on its own subdomain (`api.opkomst.nu`)
and the env var is forgotten, the prod browser fetches will be
silently rejected and the dev origin still trusted. A boring failure
mode but easy to prevent.

**Fix**: drop the default; require the env var to be set explicitly
(`os.environ["CORS_ORIGINS"]`). Same shape as `JWT_SECRET`.

### 6. JWT TTL = 7 days, no revocation — LOW

`backend/auth.py:16` (`JWT_TTL_HOURS = 24 * 7`). A leaked JWT remains
valid for a week. There is no allowlist / revocation list, no
`token_version` on the user, and no logout-all-devices flow.

For a non-financial volunteer-org tool with bounded blast radius
(create events, view signup tallies) this is acceptable; flagged for
posterity. If we add a "log out everywhere" feature it should bump a
`token_version` claim that we then validate inside `_decode_token`.

### 7. `register` rate-limit is per-IP, not per-email — LOW

`backend/routers/auth.py:77` (`@limiter.limit("5/hour")`). Five
registrations per IP per hour is fine for the global limit but doesn't
prevent an attacker from churning thousands of throwaway emails through
one IP across days, exhausting the SCD2 chain space and burning through
SMTP quota for verification emails.

**Fix (optional)**: add a per-email lock — once `_user_by_email` returns
non-None or `_last_closed_user_by_email` returns non-None, refuse for
24h on that email regardless of IP. The current code already 409s
after the first registration so the abuse case is "register a new
email each time", which is mostly an SMTP-quota concern.

## Non-findings (verified safe)

- **Password hashing**: bcrypt with 72-byte truncation, documented
  rationale. ✅
- **JWT decoding**: `jose.jwt.decode` is called with an
  `algorithms=[JWT_ALGORITHM]` whitelist on every path — alg=none is
  not accepted. ✅
- **Email encryption**: AES-GCM with 12-byte random nonce, key
  validated to be 32 bytes at import. Decrypt is only called from
  `feedback_worker._process_one`, which always wipes the ciphertext
  after the call (privacy invariant — also documented in CLAUDE.md). ✅
- **Feedback privacy contract**: `FeedbackToken` row is deleted on
  submit (`backend/routers/feedback.py:141`); `submission_id` is a
  fresh `secrets.token_urlsafe(16)` per submission. After redemption
  no row in the system can map a response back to a signup. ✅
- **Chapter scoping**: `_scope_filter` and the `chapter_match` filter
  are applied uniformly to every organiser-side event read; events
  outside the user's chapter return 404 (not 403) so existence doesn't
  leak. ✅
- **Self-deletion / self-demotion guards**: `admin.py:164` and
  `admin.py:184` block both. ✅
- **SQL injection**: every query uses SQLAlchemy parameter binding;
  no `f"..."` SQL anywhere. ✅
- **Sentry PII**: `send_default_pii=False` (`main.py:38`). ✅
- **HSTS**: only set when the request was actually served over HTTPS
  (`security_headers.py:64`). ✅
- **bcrypt + JWT secret**: `JWT_SECRET` and `EMAIL_ENCRYPTION_KEY` are
  read with `os.environ[...]` (no defaults), so a missing key
  fails-closed at process start. ✅
- **PII in logs**: structlog calls log `user_id`, `entity_id`, and
  status enums but never email addresses, passwords, or token
  contents. ✅

## Suggested fix order

1. **#1 (path traversal)** — one-line resolve-and-check in
   `_spa_fallback`. Five minutes.
2. **#2 (webhook fail-open)** — flip the default; add an explicit
   opt-in for dev. Ten minutes.
3. **#3 (send-feedback rate limit)** — one decorator. Two minutes.
4. **#4 (CSP narrowing)** — drop two origins. One minute.
5. **#5 (CORS default)** — drop the default. One minute.

#6 and #7 are opportunistic; revisit if the threat model changes.
