🇬🇷 [Ελληνικά](Installation) · 🇬🇧 **English**

# Installation

> First time? See [Easy installation, step by step](Easy-Installation-EN), with a Raspberry Pi, an old PC or a free cloud machine.
> The **setup assistant** (`setup.sh`) writes `.env` and sets up the Cloudflare Tunnel and admin protection automatically.

Karta is one small web service: Python, FastAPI and a single SQLite database file.
It runs comfortably on a small VPS, a home server or a Raspberry Pi‑class machine.

## What you need

- **A server with Docker** (or Python 3.12).
- **A domain name with HTTPS**, e.g. `karta.yourshop.gr`. HTTPS is required: the shop
  screen's login cookie is marked `Secure`, and browsers only allow the camera (for QR
  scanning) on HTTPS pages.
- **Cloudflare Access** in front of `/admin`. It's free for small teams. Karta has no
  admin password of its own: it trusts the identity that Cloudflare Access signs and
  checks it against `ADMIN_EMAILS`. See [Security and privacy](Security-and-Privacy-EN).
- **An Ergani web‑services user** for the business. For testing, also get a user for the
  Ergani test environment (`trialv2eservices.yeka.gr`). See [Configuration](Configuration-EN).

## 1. Prepare `.env`

```bash
mkdir karta && cd karta
curl -fsSLO https://raw.githubusercontent.com/osergios/karta/main/.env.example
cp .env.example .env
nano .env        # fill it in; keep ERGANI_MODE=dry_run for now
```

Every setting is explained in [Configuration](Configuration-EN). At minimum you need:
`EMPLOYER_AFM`, `CF_ACCESS_TEAM_DOMAIN`, `CF_ACCESS_AUD`, `ADMIN_EMAILS`,
`PUBLIC_ORIGIN`, and Ergani credentials (needed to import your staff).

## 2. Run it

With the ready‑made image from GitHub (amd64 and arm64, e.g. Raspberry Pi):

```bash
docker run -d --name karta --restart unless-stopped \
  --env-file .env -p 127.0.0.1:8000:8000 -v karta-data:/data \
  ghcr.io/osergios/karta:latest
```

`latest` is always the newest version. To stay on a specific version, use e.g.
`ghcr.io/osergios/karta:1.0.0`. All versions and their changes are on the
[Releases](https://github.com/osergios/karta/releases) page.

Or build the image yourself from the code:

```bash
git clone https://github.com/osergios/karta.git && cd karta
cp /path/to/your/.env .env
docker build -t karta .
docker run -d --name karta --restart unless-stopped \
  --env-file .env -p 127.0.0.1:8000:8000 -v karta-data:/data karta
```

- The database is `/data/workcard.db` inside the container (change it with `DB_PATH`).
- The container runs as an unprivileged user (UID 10001). If you mount a host folder
  instead of a named volume, make sure that user can write to it.
- Check it's up with `curl http://127.0.0.1:8000/healthz`.

Without Docker:

```bash
pip install -r requirements.txt
PYTHONPATH=vendor uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-server-header
```

## 3. Put it behind HTTPS

Any reverse proxy works (Caddy, nginx, Traefik), and so does **Cloudflare Tunnel**
(`cloudflared`), which needs no open ports. Point your domain at `http://127.0.0.1:8000`.

If your proxy sets the client address, pass it as the `X-Real-IP` header. Karta records
the IP of each punch.

## 4. Protect `/admin` with Cloudflare Access

1. In the Cloudflare Zero Trust dashboard, create a **self‑hosted application** for
   `karta.yourshop.gr/admin` (path `admin`, covering `/admin` and everything under it).
2. Add a policy that allows only your email address(es).
3. Copy the application's **Audience (AUD) tag** into `CF_ACCESS_AUD`, and your team
   domain (e.g. `yourteam.cloudflareaccess.com`) into `CF_ACCESS_TEAM_DOMAIN`.
4. Put the same email address(es) in `ADMIN_EMAILS`.

Leave the rest of the site (the shop screen, `/enroll`, `/c/…`, `/api/…`) **outside**
Cloudflare Access. Those pages have their own protection; see
[Security and privacy](Security-and-Privacy-EN).

## 5. First login and setup

1. Open `https://karta.yourshop.gr/admin` and log in through Cloudflare Access.
2. **«Ρυθμίσεις» → «ΕΡΓΑΝΗ» → «Έλεγχος ΕΡΓΑΝΗ»**: reads your employer details,
   branches and current staff from Ergani, and lets you import the employees. This is the
   only way to add staff. Each new employee gets a 6‑digit PIN, shown once. Write it down
   or give it to them.
3. **«Ρυθμίσεις» → «Στοιχεία επιχείρησης»**: shop name, short name, colour and logo.
4. **«Ωράρια & αργίες»**: check each person's schedule (see
   [Schedules and holidays](Admin-Schedules-and-Holidays-EN)).
5. **«Ρυθμίσεις» → «Συσκευές» → «Δημιουργία κωδικού εγγραφής»**: register the shop
   laptop or tablet (see [Shop screen](Kiosk-EN)).
6. When everything looks right, follow [Going live](Going-Live-EN).

## Backups

Everything (employees, PIN hashes, punches, schedules, settings, logo) is in the one
SQLite file. Back up the `/data` volume regularly and keep the copies encrypted: they
contain staff data. Also keep a safe copy of your `.env`, especially `PIN_KEY`.

To copy the database while the app is running, use SQLite's backup command rather than a
plain `cp`:

```bash
docker exec karta python -c "import sqlite3; s=sqlite3.connect('/data/workcard.db'); d=sqlite3.connect('/data/backup.db'); s.backup(d)"
```

## Updating

Check what changed on the [Releases](https://github.com/osergios/karta/releases) page, then:

```bash
docker pull ghcr.io/osergios/karta:latest
docker rm -f karta && docker run -d --name karta ... (same command as above)
```

If you build the image yourself: `git pull`, `docker build -t karta .` and the
`docker run` again.

Database changes are applied automatically at startup. After an update, use
**«Σήμερα» → «Οθόνη καταστήματος και αποστολή» → «Ανανέωση οθόνης»** to make the shop screen reload itself.
