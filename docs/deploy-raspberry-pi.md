# Deploying opkomst on a Raspberry Pi 5

This is a full, self-contained walkthrough for hosting opkomst on a
Raspberry Pi 5 at home, reached publicly over a **Cloudflare Tunnel**
(public HTTPS on `opkomst.nu` with **no port-forwarding**, a hidden
home IP, and immunity to a dynamic residential IP).

It replaces the Coolify/VPS setup in [`deploy.md`](deploy.md). The two
docs share the same secrets, Scaleway TEM, bootstrap-admin and cron
*concepts* — this one is the concrete recipe for a Pi using plain
`docker compose` instead of Coolify. Where a step is identical, it
points back to `deploy.md` rather than repeating the prose.

> **Why the Pi.** The production VPS is 2 vCPU / 1.9 GB and lives
> permanently ~1 GB into swap (Coolify's own 7 containers eat ~250 MB,
> the app ~170 MB, the Evolution/WhatsApp stack ~133 MB, plus
> Postgres). Any memory bump tips it into swap-thrash → the
> intermittent stalls. A Pi 5 with **8 GB (16 GB ideal)** runs the
> whole stack in RAM with zero swap, and dropping Coolify for plain
> compose removes another ~250 MB of overhead.

---

## 0. What runs on the Pi

One `docker compose` project, four containers:

| Container     | Image                          | Role                                            |
|---------------|--------------------------------|-------------------------------------------------|
| `api`         | built from this repo's `Dockerfile` | FastAPI + the built Vue SPA (served by the SPA fallback) + the one-shot cron CLI |
| `postgres`    | `postgres:16-alpine`           | the application database                        |
| `cloudflared` | `cloudflare/cloudflared`       | outbound-only tunnel; publishes `opkomst.nu` → `api:8000` |
| `evolution-*` | optional                       | WhatsApp blast tool (see §11) — only if you use it |

The Pi never opens an inbound port. `cloudflared` makes an **outbound**
connection to Cloudflare's edge; Cloudflare terminates TLS for
`opkomst.nu` and forwards requests down the tunnel to `api:8000` over
the compose network. The cron jobs run from the **host crontab** via
`docker compose exec`, mirroring the one-shot model `deploy.md`
describes (there is no long-running scheduler container).

Everything is ARM64-native: the `python` base image, `postgres:16-alpine`,
and `cloudflared` are all multi-arch, and the image builds fine on the
Pi itself (8 GB is plenty for `npm run build` + `uv sync`).

---

## 1. Hardware & OS prep

**Hardware**

- **Raspberry Pi 5, 8 GB or 16 GB.** 4 GB works but leaves little
  headroom once Postgres' page cache warms.
- **Boot from an NVMe/USB SSD, not a microSD card.** This is not
  optional for a database host: Postgres' write pattern destroys SD
  cards in months and SD random-I/O is glacial. Use the Pi 5 M.2
  HAT + a small NVMe SSD, or a good USB-3 SSD.
- A reliable PSU (the official 27 W USB-C) and ideally a small UPS so
  a flicker doesn't corrupt Postgres.

**OS** — **Raspberry Pi OS Lite (64-bit, Bookworm)** or Ubuntu Server
24.04 arm64. Headless. Flash with Raspberry Pi Imager; in the imager's
advanced settings preset the hostname, your SSH public key (disable
password login), and Wi-Fi/locale. Then:

```bash
sudo apt update && sudo apt full-upgrade -y

# Enable cgroup v2 memory accounting so docker can enforce limits.
# (Raspberry Pi OS only — Ubuntu has it on already.)
sudo sed -i 's/$/ cgroup_enable=memory cgroup_memory=1/' /boot/firmware/cmdline.txt
# ^ append to the SINGLE existing line; verify it's still one line.

# Headless: hand RAM back from the GPU.
echo 'gpu_mem=16' | sudo tee -a /boot/firmware/config.txt

sudo reboot
```

Hardening (do it now, the box is about to be internet-reachable):

```bash
sudo apt install -y unattended-upgrades fail2ban
sudo dpkg-reconfigure -plow unattended-upgrades   # automatic security updates
# SSH: key-only (PasswordAuthentication no) is set by the imager; confirm:
sudo sshd -T | grep -E 'passwordauthentication|permitrootlogin'
```

There is **no inbound firewall rule to open** — the tunnel is
outbound-only. Keep your router's port-forwarding empty. A default-deny
`ufw` that still allows outbound + your LAN SSH is fine.

---

## 2. Install Docker

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"        # log out/in afterwards
docker compose version                 # confirm the compose plugin is present
```

---

## 3. Get the code

```bash
sudo mkdir -p /opt/opkomst && sudo chown "$USER" /opt/opkomst
git clone https://github.com/rlmwang/opkomst.git /opt/opkomst
cd /opt/opkomst
git checkout main
```

---

## 4. Generate secrets

Same as `deploy.md` §1. **If you are migrating an existing
deployment, copy the live `JWT_SECRET` and `EMAIL_ENCRYPTION_KEY`
verbatim from the old `.env`** — the encryption key decrypts the
`encrypted_email` ciphertext of any pending reminder/feedback
dispatches, so a fresh key silently breaks every queued email. Only
generate new ones for a brand-new install:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"                       # JWT_SECRET
python3 -c "import secrets,base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"  # EMAIL_ENCRYPTION_KEY
```

---

## 5. `.env`

Copy the template and fill it in. The full annotated reference is in
[`.env.example`](../.env.example); the Pi-specific values are called
out below.

```bash
cp .env.example .env
chmod 600 .env
$EDITOR .env
```

```bash
# --- Required ---
JWT_SECRET=<from step 4 / copied from old box>
EMAIL_ENCRYPTION_KEY=<from step 4 / copied from old box>

# Talk to the compose postgres service by name. (docker-compose.prod
# also injects this, so it can't accidentally inherit a localhost dev
# value — but set it correctly here too.)
DATABASE_URL=postgresql+psycopg://opkomst:opkomst@postgres:5432/opkomst

# The public origin every email link + QR code resolves against.
PUBLIC_BASE_URL=https://opkomst.nu
MESSAGE_ID_DOMAIN=opkomst.nu
# Same-origin SPA, so CORS is rarely exercised; set it to the domain.
CORS_ORIGINS=https://opkomst.nu

# --- Email (Scaleway TEM) ---
EMAIL_BACKEND=smtp
SMTP_HOST=smtp.tem.scw.cloud
# Residential ISPs almost always block outbound port 25 but allow 587
# (STARTTLS). Use 587. The VPS used 2587 only because Scaleway blocks
# 587 from *their* instances — that constraint does not apply on a
# home line. If your ISP also blocks 587, fall back to 2587 (same host,
# same creds, same STARTTLS).
SMTP_PORT=587
SMTP_USER=<TEM SMTP user>
SMTP_PASSWORD=<TEM SMTP password>
SMTP_FROM=noreply@opkomst.nu

# First user to register with this email becomes admin. Set to yours.
BOOTSTRAP_ADMIN_EMAIL=you@example.org

# --- Production knobs ---
LOCAL_MODE=                 # MUST stay empty in production
DISABLE_SCHEDULER=          # leave empty; cron is host-driven (§9)
RATE_LIMIT_STORAGE_URI=memory://   # single replica → in-process is correct
# The Pi 5 has 4 cores and real RAM. 2 workers is a sane start
# (~150–200 MB each); bump to 3 if you like. Don't run 4+ on 8 GB
# alongside Postgres + Evolution.
WEB_CONCURRENCY=2

# --- Optional: Sentry (recommended) ---
SENTRY_DSN=<dsn>
SENTRY_ENVIRONMENT=production
SENTRY_TRACES_SAMPLE_RATE=0
VITE_SENTRY_DSN=<same dsn>
VITE_SENTRY_ENVIRONMENT=production
VITE_SENTRY_TRACES_SAMPLE_RATE=0

# --- Optional: event-image storage (GitHub Contents API) ---
# Leave all unset to hide the picker. Set all four together. See
# deploy.md §5 for the PAT scoping.
GITHUB_IMAGES_REPO_OWNER=
GITHUB_IMAGES_REPO_NAME=
GITHUB_IMAGES_BRANCH=main
GITHUB_IMAGES_TOKEN=

# --- Optional: WhatsApp blast (Evolution API) — see §11 ---
EVOLUTION_URL=
EVOLUTION_API_KEY=
EVOLUTION_INSTANCE=opkomst-blast

# --- Postgres container credentials (used by docker-compose.prod) ---
POSTGRES_USER=opkomst
POSTGRES_PASSWORD=opkomst        # change me; keep in sync with DATABASE_URL
POSTGRES_DB=opkomst

# --- Cloudflare Tunnel (filled in step 7) ---
CLOUDFLARE_TUNNEL_TOKEN=
```

`backend/config.py::Settings` validates this at boot and **fails fast**
on anything missing or malformed — a bad `.env` stops the container
rather than booting half-configured. You can dry-run the check before
starting anything:

```bash
docker compose -f docker-compose.prod.yml run --rm api uv run python scripts/verify_env.py
```

---

## 6. The production compose file

The repo's `docker-compose.yml` is the dev convenience stack. Add a
production overlay **`docker-compose.prod.yml`** next to it:

```yaml
services:
  postgres:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    volumes:
      - postgres-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 10s
      timeout: 5s
      retries: 5

  api:
    build: .
    image: opkomst:latest
    restart: unless-stopped
    env_file: .env
    environment:
      # Force the in-compose DB hostname regardless of what .env's
      # DATABASE_URL says, so a copied dev value can't leak in.
      DATABASE_URL: postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
    volumes:
      # Backups (scripts/backup.sh writes to /app/data/backups) persist
      # on the host SSD instead of vanishing on the next image build.
      - ./data:/app/data
    depends_on:
      postgres:
        condition: service_healthy
    # No published ports: cloudflared reaches it over the compose
    # network. (Add "127.0.0.1:8000:8000" temporarily if you want to
    # curl it from the Pi during setup.)
    expose:
      - "8000"
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:8000/health"]
      interval: 30s
      timeout: 5s
      retries: 3

  cloudflared:
    image: cloudflare/cloudflared:latest
    restart: unless-stopped
    command: tunnel --no-autoupdate run
    environment:
      TUNNEL_TOKEN: ${CLOUDFLARE_TUNNEL_TOKEN}
    depends_on:
      - api

volumes:
  postgres-data:
```

This file is **self-contained** — it redefines `postgres`/`api` with
production settings (restart policy, no host-published port, the
backups volume) rather than layering on the dev `docker-compose.yml`,
so use it alone, not merged with the dev file:

```bash
alias dc='docker compose -f docker-compose.prod.yml'   # used in every command below
```

(The image's `CMD` runs `python -m backend.cli migrate` before uvicorn,
so the schema is brought to HEAD automatically on every `up`. No manual
migration step.)

---

## 7. Cloudflare Tunnel

Prereq: your domain's DNS is managed by Cloudflare (free plan is fine).
Move the `opkomst.nu` nameservers to Cloudflare first if they aren't
already, and remove any old A/AAAA record pointing at the VPS — the
tunnel creates its own.

1. **Cloudflare dashboard → Zero Trust → Networks → Tunnels →
   Create a tunnel** → **Cloudflared** → name it `opkomst-pi`.
2. Copy the **tunnel token** it shows (a long `eyJ…` string) into
   `.env` as `CLOUDFLARE_TUNNEL_TOKEN=`. (The `cloudflared` container
   uses the token; you don't install cloudflared on the host.)
3. On the tunnel's **Public Hostname** tab, add:
   - **Subdomain**: *(blank)* · **Domain**: `opkomst.nu` · **Path**: *(blank)*
   - **Service**: `HTTP` → `api:8000`
   - (optional) add a second hostname `www` → same service.
4. Cloudflare auto-creates the proxied DNS records for `opkomst.nu`.
5. SSL/TLS mode: **Full** (Cloudflare ↔ tunnel is already encrypted;
   the origin is plain HTTP inside the compose network, which is fine).

The public hostname maps to the **compose service name** `api`, which
`cloudflared` resolves on the shared compose network — no host ports,
no `localhost`.

---

## 8. First boot

```bash
cd /opt/opkomst
dc up -d --build      # builds the arm64 image, starts everything
dc logs -f api        # watch: migrate runs, then "Uvicorn running"
```

Verify locally on the Pi, then publicly:

```bash
dc exec api curl -fsS http://localhost:8000/health     # {"status":"ok"}
curl -fsS https://opkomst.nu/health                     # via the tunnel
```

**Bootstrap the admin** exactly as `deploy.md` §7: open
`https://opkomst.nu/login`, enter your `BOOTSTRAP_ADMIN_EMAIL`, click
the magic link from your inbox, set your name. The first completion
matching that address lands as `role=admin, is_approved=true`.

---

## 9. Cron (scheduled tasks)

No Coolify scheduler — the host crontab fires the same one-shot CLI
subcommands `deploy.md` §6 lists, via `docker compose exec` into the
running `api` container. `crontab -e`:

```cron
# opkomst scheduled tasks (UTC). DC points at the prod compose project.
DC=docker compose -f /opt/opkomst/docker-compose.prod.yml

0  *  * * *  cd /opt/opkomst && $DC exec -T api uv run --no-dev python -m backend.cli dispatch reminder   >> /opt/opkomst/data/cron.log 2>&1
0  *  * * *  cd /opt/opkomst && $DC exec -T api uv run --no-dev python -m backend.cli dispatch feedback   >> /opt/opkomst/data/cron.log 2>&1
30 *  * * *  cd /opt/opkomst && $DC exec -T api uv run --no-dev python -m backend.cli reap-partial        >> /opt/opkomst/data/cron.log 2>&1
0  3  * * *  cd /opt/opkomst && $DC exec -T api uv run --no-dev python -m backend.cli reap-expired        >> /opt/opkomst/data/cron.log 2>&1
45 3  * * *  cd /opt/opkomst && $DC exec -T api uv run --no-dev python -m backend.cli reap-auth-tokens    >> /opt/opkomst/data/cron.log 2>&1
0  9  * * 1  cd /opt/opkomst && $DC exec -T api uv run --no-dev python -m backend.cli pending-digest      >> /opt/opkomst/data/cron.log 2>&1
0  4  * * *  cd /opt/opkomst && $DC exec -T api bash scripts/backup.sh                                    >> /opt/opkomst/data/cron.log 2>&1
```

`-T` disables TTY allocation (required from cron). Each subcommand
exits non-zero on failure; with Sentry wired the exceptions land in the
same project as request errors. The Pi runs on local time unless you
set it to UTC — `sudo timedatectl set-timezone UTC` so these schedules
match the comments (the app stores timestamps in UTC).

---

## 10. Backups & restore

`scripts/backup.sh` writes a **redacted** `pg_dump` (it NULLs
`encrypted_email`, per the privacy contract) to `/app/data/backups`,
which the §6 volume maps to `/opt/opkomst/data/backups` on the SSD. The
§9 cron runs it daily. Two things to add at home:

- **Off-Pi copies.** A home SSD is a single point of failure. Push the
  dumps somewhere else nightly — e.g. `rclone copy
  /opt/opkomst/data/backups remote:opkomst-backups` to any cloud
  remote, or `scp` to another machine. Add it after the backup line in
  cron.
- **Restore drill.** `scripts/restore_drill.sh` documents the
  restore path; run it once so you trust it.

**Migrating the live data off the VPS** (one-time, at cutover): the
redacted backup is for routine snapshots, not migration — you want the
*real* rows including pending `encrypted_email` ciphertext. With the
app **stopped on the VPS** (so no new writes), dump the full DB there
and restore here:

```bash
# On the old VPS / from your laptop, against the Coolify Postgres:
pg_dump "$OLD_DATABASE_URL" -Fc -f opkomst-full.dump

# Copy to the Pi, then load it into the fresh compose Postgres:
scp opkomst-full.dump pi:/opt/opkomst/data/
dc exec -T postgres pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  --clean --if-exists < /opt/opkomst/data/opkomst-full.dump
```

This only decrypts correctly if the Pi's `EMAIL_ENCRYPTION_KEY` matches
the VPS's (step 4). After restoring, `dc restart api` so it re-reads at
HEAD (the dump already carries the `alembic_version` row).

---

## 11. Optional: WhatsApp blast (Evolution API)

The Pi finally has RAM for it. Add to `docker-compose.prod.yml`:

```yaml
  evolution:
    image: atendai/evolution-api:latest   # pin a tag in practice
    restart: unless-stopped
    environment:
      AUTHENTICATION_API_KEY: ${EVOLUTION_API_KEY}
      DATABASE_ENABLED: "true"
      DATABASE_PROVIDER: postgresql
      DATABASE_CONNECTION_URI: postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/evolution
    depends_on:
      postgres:
        condition: service_healthy
    expose:
      - "8080"
```

Then set in `.env`: `EVOLUTION_URL=http://evolution:8080`,
`EVOLUTION_API_KEY=<a strong key>`, `EVOLUTION_INSTANCE=opkomst-blast`,
and create an `evolution` database in the same Postgres
(`dc exec postgres createdb -U $POSTGRES_USER evolution`). Leave all
three unset and the WhatsApp tab stays hidden, the route guard
redirects, and the API returns 503 — exactly as on the VPS. Full tool
walkthrough: `docs/plan-whatsapp-blast.md`.

---

## 12. Updates / redeploy

No git-push automation; pull and rebuild on the Pi (8 GB builds the
SPA comfortably):

```bash
cd /opt/opkomst && git pull --ff-only
dc up -d --build           # rebuild changed layers; migrate runs on boot
dc image prune -f          # reclaim old image layers
```

Wrap it in `/opt/opkomst/deploy.sh` if you like. For push-button
deploys you can later add a Cloudflare Tunnel webhook or a tiny
`git pull && dc up -d --build` on a cron/systemd-path watch — but
manual is fine for this traffic and avoids building unattended.

---

## 13. Survive reboots & power loss

`restart: unless-stopped` brings the containers back when the Docker
daemon starts, and Docker starts on boot by default
(`sudo systemctl enable docker`). That covers a reboot or power
restoration with no further work. For belt-and-braces (and to control
*ordering* / run a pre-flight), a oneshot unit:

```ini
# /etc/systemd/system/opkomst.service
[Unit]
Description=opkomst (docker compose)
Requires=docker.service
After=docker.service network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/opkomst
ExecStart=/usr/bin/docker compose -f docker-compose.prod.yml up -d --build
ExecStop=/usr/bin/docker compose -f docker-compose.prod.yml down

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now opkomst.service
```

Postgres' WAL makes it crash-safe, but a UPS that lets the Pi shut down
cleanly on outage is cheap insurance for the DB.

---

## 14. Monitoring

- **Health**: `https://opkomst.nu/health` returns `{"status":"ok"}`.
  Point an external uptime check (UptimeRobot, Cloudflare Health
  Checks) at it — a home line *will* blip, and you want to know.
- **Sentry**: backend exceptions and frontend errors land in the same
  project (step 5). Cron failures surface here too.
- **Cloudflare** dashboard shows tunnel up/down and request analytics.
- **Resources**: `docker stats` and `free -h` — on an 8 GB Pi you
  should see **zero swap in use**. If swap creeps up, that's the signal
  to drop `WEB_CONCURRENCY` or move Evolution off.

---

## 15. Cutover checklist

1. Stand the Pi up fully and verify on a temporary hostname (e.g. add
   a `pi.opkomst.nu` public hostname on the tunnel and test there).
2. Stop writes on the VPS (scale it to 0 / stop the app container).
3. Dump + restore the full DB (§10).
4. Point the tunnel's `opkomst.nu` public hostname at the Pi's `api`
   (it already is, if you built the tunnel on the Pi) and delete the
   old VPS A/AAAA record. Propagation is seconds — it's Cloudflare's
   own record.
5. Send yourself a test sign-up + confirm the feedback/reminder cron
   fires (check `data/cron.log`).
6. Keep the VPS around, stopped, for a week as a rollback.

Once stable, the VPS (and its Coolify overhead) can be retired.
