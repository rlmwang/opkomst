# Plan: WhatsApp blast tool

A self-contained admin page for one-off WhatsApp blasts via Evolution API. No DB, no PII at rest, session forgets itself when the user leaves.

## 0. Prereqs (out of scope of this codebase)

- Evolution API running as a Coolify service (Postgres + Redis + Evolution + persistent volume), reachable from the backend over the internal network.
- One Evolution instance pre-created with a known name (e.g. `opkomst-blast`), or created on-demand by the backend (preferred. see §2).

## 1. Config (`backend/config.py`)

Add three required Settings fields:
- `EVOLUTION_URL: str`
- `EVOLUTION_API_KEY: str`
- `EVOLUTION_INSTANCE: str` (the instance name to use)

Update `scripts/verify_env.py` accordingly. Update `.env.example`. No defaults. `Settings()` should fail fast at boot if these are missing in the deployed env.

## 2. Backend service (`backend/services/whatsapp.py`)

A thin module wrapping `httpx.AsyncClient` calls to Evolution. One client, reused. Functions:

- `async def ensure_instance() -> None`. idempotent: if instance doesn't exist, `POST /instance/create`. Called by `qr()` and `send()` so the page works from a clean slate.
- `async def status() -> Literal["open", "connecting", "close"]`
- `async def qr() -> {"qr": base64, "pairingCode": str | None}`
- `async def send_text(number: str, text: str) -> dict`
- `async def logout() -> None`
- `async def delete_instance() -> None`. full wipe (logout + remove session keys from volume)
- `async def heartbeat_tick() -> None`. updates module-level `_last_seen`
- `async def watchdog_check() -> None`. if `_last_seen > 60s` ago and `status() == "open"`, call `delete_instance()`

In-memory state only. A single `_last_seen: datetime | None` module-level var. No persistence. restart = clean slate, which is fine.

## 3. Backend router (`backend/routers/whatsapp.py`)

Admin-only via the existing RBAC dependency. All routes prefixed `/api/v1/whatsapp`. Mutating routes carry `@limiter.limit(...)` per the project rule (audit-tested).

| Method | Path | Body / Behaviour |
|---|---|---|
| GET | `/status` | `{state}` |
| GET | `/qr` | `{qr, pairingCode}`. calls `ensure_instance()` first |
| POST | `/heartbeat` | bumps `_last_seen`; returns `{state}` so the frontend gets status + heartbeat in one round-trip |
| POST | `/send` | `{number, text}` → forwards; rate-limited tightly (e.g. `30/minute` per IP) |
| POST | `/logout` | calls `delete_instance()` (full wipe. see "forget" requirement) |

Hook the watchdog: on every request to `/heartbeat`, `/send`, `/status`, also call `watchdog_check()` first. That way "no traffic for 60s → logout" is enforced lazily without a background task. Cheap and self-healing.

Wire the router into `backend/main.py`. Update logging guards: per the "no PII in logs" rule, the `/send` route logs route name + outcome only. never the phone number or text body.

## 4. Auth integration

Add a backend hook so app-level logout tears down WhatsApp too:
- New route `POST /auth/logout` (if not present) → calls `whatsapp.delete_instance()` then returns 204. Frontend calls this on user logout *before* clearing the JWT.
- If `/auth/logout` already exists, just add the WhatsApp call.

## 5. Schemas + OpenAPI

Pydantic DTOs for the four payloads (`StatusResponse`, `QrResponse`, `SendRequest`, `HeartbeatResponse`). Run `make openapi` to regenerate `openapi.json` + `frontend/src/api/schema.ts` (project rule. CI gate fails on drift).

## 6. Backend tests (`tests/test_whatsapp.py`)

- `/status`, `/qr`, `/send`, `/logout` are admin-only (403 for non-admin, 401 for anon).
- `/send` is rate-limited (audit test already covers presence of `@limiter.limit`).
- `/send` log line contains route + outcome but **not** the phone or text. extend `test_privacy.py` with a grep that fails if the WhatsApp module logs `to=` or message bodies.
- Watchdog: with `_last_seen` >60s old and a stub `status()` returning `"open"`, hitting `/heartbeat` invokes `delete_instance()`.
- All Evolution HTTP calls are mocked with `respx` or similar. no real network in tests.

## 7. Frontend route + guard (`frontend/src/`)

- New page `pages/AdminWhatsApp.vue`, route `/admin/whatsapp`.
- Add to admin nav as a tab. Protected by the existing admin guard (`stores/auth.ts`).
- i18n strings in `locales/{nl,en}/*.json`: page title, step labels, errors, formatting help, confirmation copy.

## 8. Frontend composable (`composables/useWhatsApp.ts`)

Not Vue Query (state is ephemeral, not server-cached). Plain `ref`-based composable exposing:

- `state: Ref<"disconnected" | "connecting" | "open" | "unknown">`
- `qr: Ref<string | null>`
- `startStatusPolling()`, `stopStatusPolling()`. 2s interval; doubles as heartbeat (calls `/heartbeat` instead of `/status` so one ping does both)
- `disconnect()`. calls `/logout`, stops polling
- `send(number, text)`. single send, returns `{ok, error?}`

## 9. Frontend page UI

Three sections in one page, no router transitions between them. they're conditionally shown by `state` and a local `step` ref.

**Section A. Connect** (visible when `state !== "open"`)
- Big QR rendered from base64.
- Caption: "Scan with WhatsApp → Settings → Linked Devices."
- Auto-refreshes when Evolution rotates the QR (poll `/qr` every 20s while disconnected).
- Once `state === "open"`, advance to Section B.

**Section B. Recipients** (built; see `frontend/src/lib/csv.ts`)

CSV with a header row, parsed client-side. The first non-empty line is the header; header names are lowercased and trimmed.

- **Phone column is user-configurable.** A small `InputText` (default `number`) names which column holds the phone numbers. The chosen column must appear in the header row, otherwise the parser emits a fatal `missingPhoneColumn` error.
- **Other columns become merge tags.** Any non-phone column shows up as a `{column}` chip under the preview, usable in the Section C composer. So a CSV with `phone,name,color` lets the user write `Hi {name}, your color is {color}.`
- **Default country code field.** Defaults to `31` (NL) since that's the typical case for this app. Empty means no auto-prefixing.
- **Phone cleansing rules** (`normalisePhone`, in order):
  1. Strip ` `, `+`, `-`, `(`, `)`, `.`
  2. Drop a leading `00` (international dialing prefix).
  3. If a country code is set:
     - Leading `0` (national prefix) → strip and prepend the code. So `0612345678` becomes `31612345678` with code `31`.
     - Already starts with the code → leave alone (no double-prefix).
     - Anything else → prepend the code. So a 9-digit `612345678` becomes `31612345678`.
  4. Validation requires 8 to 15 final digits.
- **Per-row status.** `ok`, or `invalid` with one of: `emptyNumber`, `invalidNumber`, `duplicateNumber`. Duplicates are detected after normalisation, so `0612345678` and `+31612345678` count as the same recipient.
- **RFC-4180 quoting.** Cells with embedded commas, doubled quotes, and CRLF line endings round-trip cleanly. UTF-8 BOM is stripped.
- **UI.** Textarea + file picker (both feed the same `csvText` ref). Inline example pre-block. Live preview table with row #, every header column, and a status badge (✓ or ✗ with the reason). Counter: "N valid, M invalid". Merge-tag chips listed below the counts.
- Tested in `frontend/src/__tests__/csv.test.ts` (33 cases covering parsing, normalisation, merge tags, and `applyMerge`).

**Section C. Compose & send**
- PrimeVue `Textarea` (not `Editor`. see "Formatting" decision).
- Live preview pane on the right. Renders `{tag}` placeholders against the first valid recipient via `applyMerge` from `lib/csv.ts` — any column from Section B is a valid tag. Unknown tags are left in the rendered output as-is so typos surface visually. Renders WhatsApp markdown (`*bold*`, `_italic_`, `~strike~`, `` ` `` mono) so the user sees what recipients will see.
- Small "Formatting help" disclosure showing the four markers.
- "Send to N recipients" button → confirm dialog with the count and a preview of the first message → starts the send loop.

**Send loop (in the page, not the composable):**

```
for each row in validRows:
  if cancelled: break
  while paused: await
  text = applyMerge(template, row.fields)
  res = await send(row.phone, text)
  row.sendStatus = res.ok ? 'sent' : 'failed'
  row.sendError = res.error
  progress = (i+1) / total
  await sleep(jitter(4000, 9000))
on done: call disconnect(); show summary table; offer CSV download of results
```

Pause / Resume / Cancel buttons. Live progress bar + per-row status table.

## 10. "Forget on leave" wiring

- `pagehide` listener: `navigator.sendBeacon('/api/v1/whatsapp/logout', ...)`.
- `onBeforeUnmount`: call `disconnect()`.
- App logout flow (in `stores/auth.ts`): `await api.post('/auth/logout')` *before* clearing the JWT.
- Server watchdog (§2) is the safety net for browser crashes.

## 11. Manual QA checklist (the part that matters)

Type-check + tests aren't enough; verify in a real browser against a real Evolution instance:

- [ ] Fresh page load shows QR. Scan with phone → state flips to `open` within 2s.
- [ ] Paste a 3-row CSV (header + 3 rows, one bad number) → invalid row shown with reason; valid count = 2.
- [ ] Change the "Phone number column" field to a non-existent column → fatal error appears; rows clear.
- [ ] Set "Default country code" to `31`, paste numbers in mixed shapes (`0612345678`, `612345678`, `+31612345678`, `0031612345678`) → all normalise to the same `31612345678`; the duplicates are flagged.
- [ ] Compose with `Hoi {name}, …`. Preview shows merged with the first valid recipient's data. Type a tag for a non-existent column → it stays as literal `{typo}` in the preview.
- [ ] Bold/italic markers render in preview.
- [ ] Send 3 messages → all arrive on real phones with names merged correctly.
- [ ] Pause mid-blast → next send doesn't fire until Resume.
- [ ] Cancel mid-blast → loop stops, partial results shown.
- [ ] Click "Disconnect" → linked device removed from phone's WhatsApp linked-devices list.
- [ ] Close tab → within 60s the watchdog logs out the instance (verify by reopening: fresh QR appears).
- [ ] App-level logout → linked device removed.
- [ ] Backend logs (`docker logs`) contain no phone numbers or message bodies during a real send.

## 12. Docs

- `docs/runbook.md`: short "WhatsApp blast" section. how to run Evolution in Coolify, how to verify the link, what to do if the QR won't scan.
- Note in `CLAUDE.md` under "What's where" that `routers/whatsapp.py` is a stateless proxy with no DB writes. defends future-Claude from "harmonising" it into the lifecycle worker pattern.

## Sequencing

1. Config + service module (§1, §2). local-only, no UI yet, exercise via curl. **Done.**
2. Router + privacy tests (§3, §6). `make openapi`. **Done.**
3. Auth integration (§4). **Done.**
4. Composable + Connect section (§7, §8, §9-A). verify QR + status loop end-to-end. **Done.**
5. Recipients section (§9-B), pure client-side. **Done** — CSV-with-header parser, configurable phone column, default country code (`31`), normalisation chain, merge-tag chips, 33 unit tests.
6. Compose + send loop + forget wiring (§9-C, §10). Next.
7. Manual QA (§11).
8. Docs (§12).

Total: ~1 day if everything cooperates; 1.5 days with realistic Evolution-API debugging time.
