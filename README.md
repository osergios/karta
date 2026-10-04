# Karta: digital work card for Ergani

**Karta** is a self-hosted *ψηφιακή κάρτα εργασίας* (digital work card) for small
Greek businesses. Employees clock in and out on a shop kiosk with a PIN or a QR
code. Karta sends each arrival and departure to the Ministry of Labour's
**Ergani II** system and gives the owner an admin page with schedules, alerts and
monthly reports.

> Η Karta είναι μια ψηφιακή κάρτα εργασίας για μικρές επιχειρήσεις: χτύπημα κάρτας
> με PIN ή QR στο κατάστημα, αυτόματη αποστολή στο ΕΡΓΑΝΗ ΙΙ, ειδοποιήσεις και
> μηνιαίες αναφορές.

## Features

- **Kiosk** (`/`): PIN pad and camera QR scanner. It accepts the shop's own QR
  cards and the employee's personal Ergani or myErgani QR.
- **Phone card** (`/c/…`): each employee can install their own QR card on their phone.
- **Ergani submission:** a queue with retries and late-declaration reasons. A
  submission that may already have reached Ergani is never retried automatically;
  it goes to a "needs checking" state for the admin to decide.
- **Three modes:** `dry_run` (nothing is sent), `trial` (Ergani test environment)
  and `production`.
- **Admin page** (`/admin`, protected by Cloudflare Access): employees, PINs,
  schedules, leave, holidays and closures, forgotten departures, training mode, and
  the business name, colour and logo.
- **Live checks:** missed punches, shift over-runs, daily/weekly limits and rest
  periods. Alerts go to the admin page, the shop screen and optionally your phone
  (via [ntfy](https://ntfy.sh)).
- **Monthly report** exported as an Excel file.

See [`CHANGES.md`](CHANGES.md) for the detailed history.

## Requirements

- Docker, or Python 3.12
- An Ergani web-services user for your business (or a test user from
  `trialv2eservices.yeka.gr`)
- A [Cloudflare Access](https://www.cloudflare.com/zero-trust/products/access/)
  application in front of `/admin`

## Quick start

```bash
cp .env.example .env        # then fill it in; keep ERGANI_MODE=dry_run at first
docker build -t karta .
docker run -d --name karta --env-file .env -p 8000:8000 -v karta-data:/data karta
```

The SQLite database lives at `/data/workcard.db` (change it with `DB_PATH`), so
**back up that volume**. It holds your employees' data.

Without Docker:

```bash
pip install -r requirements.txt
PYTHONPATH=vendor uvicorn app.main:app --host 0.0.0.0 --port 8000
```

All settings are documented in [`.env.example`](.env.example). **Never commit
your real `.env`.**

## Going live

1. Run in `dry_run` and check the stored payloads on the admin page.
2. Switch to `trial` and check the movements in the Ergani test environment.
3. Switch to `production`.

You are responsible for the declarations made to Ergani from your installation.
This software is provided as-is, without warranty (see the license).

## Third-party code

Karta bundles the [Ergani Python SDK](https://github.com/withlogicco/ergani-python-sdk)
(MIT, by LOGIC), [jsQR](https://github.com/cozmo/jsQR) (Apache-2.0) and the
[Inter](https://github.com/rsms/inter) typeface (SIL OFL 1.1). Details and the
local changes are in [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

## License

[MIT](LICENSE) for Karta's own code. Bundled third-party components keep their
own licenses.
