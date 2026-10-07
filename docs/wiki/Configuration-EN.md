[Ελληνικά](Configuration) · **English**

# Configuration (`.env`)

All server settings live in the `.env` file (start from `.env.example`). After changing
it, restart the app with `cd ~/karta && docker compose up -d`. **Never commit your real
`.env`**: it holds your Ergani password and keys.

> **From the admin page:** the mode (`ERGANI_MODE`), the ΑΦΜ (tax number), the branch, the
> employer id in Ergani's QR (`ERGANI_EMPLOYER_ID`), how overtime is declared
> (`TIME_DECLARATION`), the Ergani users and phone
> notifications (`NTFY_*`) can also be set in the admin page's **«Ρυθμίσεις»**, with no
> restart. Whatever is saved there **overrides** `.env` (the page shows «από το .env» next
> to anything that comes from here). So once a value is saved on the page, changing it in
> `.env` has no effect. Passwords saved there are encrypted with `PIN_KEY`.

Day‑to‑day rules such as flexibility minutes, overtime deadlines and weekly limits are
**not** set here. They're on the admin page, under
[«Ρυθμίσεις» → «Όρια και ειδοποιήσεις»](Admin-Settings-EN).

## Ergani

| Variable | Required | Meaning |
|---|---|---|
| `ERGANI_MODE` | no (default `dry_run`) | `dry_run`, `trial` or `production`. See [Going live](Going-Live-EN). The Ergani URL follows the mode; don't set it yourself. |
| `ERGANI_USERNAME` / `ERGANI_PASSWORD` | for `production` (and for importing staff) | The business's Ergani web‑services user. |
| `ERGANI_USER_TYPE` | no (default `01`) | `01` = API / external user, `02` = «ΕΡΓΑΝΗ» user from «Εξωτερικοί Χρήστες Παραρτημάτων». |
| `ERGANI_TRIAL_USERNAME` / `ERGANI_TRIAL_PASSWORD` | no | A user created in the Ergani test environment (`trialv2eservices.yeka.gr`, TaxisNet login of the employer). If left empty, `trial` uses the normal user (`ERGANI_USERNAME`). |
| `ERGANI_TRIAL_USER_TYPE` | no (default `02`) | Same as above, for the test user. |
| `EMPLOYER_AFM` | for `trial` / `production` | The employer's ΑΦΜ (9 digits). |
| `BRANCH_NUMBER` | no (default `0`) | Branch number (Α/Α παραρτήματος). |
| `TIME_DECLARATION` | no | `advance` (declared before, the default) or `retro` (retrospective system): how the business declares schedule changes and overtime in Ergani. See [Settings](Admin-Settings-EN). |
| `ERGANI_EMPLOYER_ID` | no | Your employer id inside Ergani's employee QR (the `id:` part). When set, the shop screen refuses an Ergani QR issued by another employer. |

> In `dry_run`, nothing is ever submitted. The **read** services used by «Έλεγχος ΕΡΓΑΝΗ»
> (employer, branches, staff list) still use the production Ergani in read‑only mode, so
> you need the production user to import your staff even while testing.

## Admin access (Cloudflare Access)

| Variable | Required | Meaning |
|---|---|---|
| `CF_ACCESS_TEAM_DOMAIN` | yes | Your Cloudflare Zero Trust team domain, without `https://`, e.g. `yourteam.cloudflareaccess.com`. |
| `CF_ACCESS_AUD` | yes | The Audience (AUD) tag of the Access application that protects `/admin`. |
| `ADMIN_EMAILS` | yes | Comma‑separated email addresses allowed into the admin page. They must match the Access policy. |

## App

| Variable | Default | Meaning |
|---|---|---|
| `PUBLIC_ORIGIN` | `http://localhost:8000` | The public address of your Karta, e.g. `https://karta.yourshop.gr`. Used to check where requests come from and to build the phone‑card links. **Set this in production.** |
| `DB_PATH` | `/data/workcard.db` | Location of the SQLite database. |
| `LATE_THRESHOLD_SECONDS` | `120` | If a punch reaches Ergani later than this after it happened (e.g. after an internet outage), it's sent as a late declaration with a reason. See [How punches reach Ergani](Ergani-Submissions-EN). |
| `DEBOUNCE_SECONDS` | `60` | Minimum time between two punches of the same person, to stop accidental double punches. |

**Time:** Karta always works in Greek time (`Europe/Athens`), including the summer and
winter changes, whatever timezone your server uses. You don't need to change anything;
`TZ` in `docker-compose.yml` only affects log timestamps.

## Phone alerts (optional)

Karta sends alerts to your phone through [ntfy](https://ntfy.sh): install the ntfy app and
subscribe to your topic. Leave these empty to turn phone alerts off. Alerts then show only
on the admin page.

| Variable | Meaning |
|---|---|
| `NTFY_URL` | The ntfy server, e.g. `https://ntfy.sh` or your own server. |
| `NTFY_TOPIC` | The topic name. Pick something long and random if you use the public server. |
| `NTFY_TOKEN` | Access token, if your ntfy server needs one. |

## Encryption key (`PIN_KEY`)

| Variable | Meaning |
|---|---|
| `PIN_KEY` | A 32‑byte key. The setup assistant writes it. If you set up by hand, generate it once with `python3 -c "import os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"`. |

`PIN_KEY` is **needed**, not optional. With it:

- the admin page stores the Ergani password and the ntfy token encrypted; without it,
  these can only be set in `.env`;
- the admin page shows employees' current PINs and QR cards;
- the link for the QR card on the phone works.

Without `PIN_KEY`, PINs are stored only as one‑way hashes and can never be shown again;
you can only set a new one. If you lose the key:

- PINs and QR cards keep working, but they can't be shown until you give each person a new
  PIN («Νέο PIN») or a new card;
- the Ergani password and the ntfy token saved on the admin page can no longer be read;
  type them again in **«Ρυθμίσεις»**.

`PIN_KEY` travels encrypted inside every cloud backup, and a cloud restore on a new machine
uses it automatically (it keeps it in `pin-key`, next to the database). Without cloud
backups, keep a copy of `.env` (or at least `PIN_KEY`) somewhere safe. See
[Backups](Backups-EN).

## Version

| Variable | Meaning |
|---|---|
| `KARTA_VERSION` | The Karta version `docker-compose.yml` starts, e.g. `1.5.0`. The setup assistant writes it, and «Ενημέρωση τώρα» (or `./setup.sh update`) changes it. If the new version doesn't start properly within two minutes, the previous one is written back and Karta returns to it. Without a value: the newest version (`latest`). |

## Cloudflare Tunnel

| Variable | Meaning |
|---|---|
| `COMPOSE_PROFILES` | `tunnel`: `docker compose` starts the tunnel together with Karta (the setup assistant writes it). Without it only Karta starts, for [your own reverse proxy](Reverse-Proxy-EN). |
| `TUNNEL_TOKEN` | The tunnel's token (the setup assistant writes it). |
| `TUNNEL_PROTOCOL` | How the tunnel connects: `http2` for a machine at the shop or at home (reliable behind a home router), `auto` on a VPS (QUIC/HTTP/3, falling back to HTTP/2). Default `http2`. Only with `docker-compose.yml`. |
