# Configuration (`.env`)

All server settings live in the `.env` file (start from `.env.example`). Restart the app
after changing it. **Never commit your real `.env`**: it holds your Ergani password and keys.

Day‑to‑day rules such as flexibility minutes, overtime deadlines and weekly limits are
**not** set here. They're on the admin page, under
[«Ρυθμίσεις» → «Όρια και ειδοποιήσεις»](Admin-Settings).

## Ergani

| Variable | Required | Meaning |
|---|---|---|
| `ERGANI_MODE` | yes | `dry_run`, `trial` or `production`. See [Going live](Going-Live). The Ergani URL follows the mode; don't set it yourself. |
| `ERGANI_USERNAME` / `ERGANI_PASSWORD` | for `production` (and for importing staff) | The business's Ergani web‑services user. |
| `ERGANI_USER_TYPE` | no (default `01`) | `01` = API / external user, `02` = «ΕΡΓΑΝΗ» user from «Εξωτερικοί Χρήστες Παραρτημάτων». |
| `ERGANI_TRIAL_USERNAME` / `ERGANI_TRIAL_PASSWORD` | for `trial` | A user created in the Ergani test environment (`trialv2eservices.yeka.gr`, TaxisNet login of the employer). |
| `ERGANI_TRIAL_USER_TYPE` | no (default `02`) | Same as above, for the test user. |
| `EMPLOYER_AFM` | yes | The employer's ΑΦΜ (9 digits). |
| `BRANCH_NUMBER` | no (default `0`) | Branch number (Α/Α παραρτήματος). |
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
| `LATE_THRESHOLD_SECONDS` | `120` | If a punch reaches Ergani later than this after it happened (e.g. after an internet outage), it's sent as a late declaration with a reason. See [How punches reach Ergani](Ergani-Submissions). |
| `DEBOUNCE_SECONDS` | `60` | Minimum time between two punches of the same person, to stop accidental double punches. |

## Phone alerts (optional)

Karta sends alerts to your phone through [ntfy](https://ntfy.sh): install the ntfy app and
subscribe to your topic. Leave these empty to turn phone alerts off. Alerts then show only
on the admin page.

| Variable | Meaning |
|---|---|
| `NTFY_URL` | The ntfy server, e.g. `https://ntfy.sh` or your own server. |
| `NTFY_TOPIC` | The topic name. Pick something long and random if you use the public server. |
| `NTFY_TOKEN` | Access token, if your ntfy server needs one. |

## Viewing PINs (optional)

| Variable | Meaning |
|---|---|
| `PIN_KEY` | A 32‑byte key that lets the admin page show employees' current PINs. Generate it once with `python3 -c "import os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"`. |

Without `PIN_KEY`, PINs are stored only as one‑way hashes and can never be shown again;
you can only set a new one. If you lose the key, PINs keep working, but they can't be
shown until you give each person a new PIN («Νέο PIN»).
