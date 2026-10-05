[Ελληνικά](Backups) · **English**

# Backups and restore

The punches of the digital work card must be **kept for at least 5 years** (confirm this
with your accountant). Karta **never deletes** a real punch: everything stays in its
database. The risk is the machine breaking (e.g. the Raspberry Pi's microSD card), so you
need a backup **off the machine as well**.

Every backup is **the whole database**: all employees, every punch from the start,
schedules and settings. So the most recent one is enough to get everything back.

## What happens automatically

Two backups every night, independent of each other:

| Where | Who makes it | What it keeps |
|---|---|---|
| **On the machine** (`~/karta/backups`) and, if you set it up, **on a USB stick** | `backup.sh`, set up by the setup assistant, at 23:30 | `daily/` 30 days · `monthly/` the last one of each month, for 24 months · `yearly/` one for each year, **forever** · `karta.env` (the settings, for a restore) |
| **In the cloud**, encrypted | Karta itself, at 23:40 | a "snapshot" for each of the last 30 days, one for each month (24 months) and one for each year, **forever** |

The result shows on the admin page, in **«Ρυθμίσεις» → «Αντίγραφα ασφαλείας»** (Settings →
Backups): «Στο μηχάνημα: … ✓ · USB ✓» and «Cloud (…): … ✓». If backups stop or one fails,
you get an **alert** (on your phone too).

## A backup off the machine

Set up **one or both**.

### Encrypted in the cloud (from the admin page)

For everyone, and **the only option on a VPS / cloud server** (e.g. Oracle Cloud), where
there's no USB. Backups are encrypted on your machine before they're uploaded (with
[restic](https://restic.net), which is built into Karta): not even the cloud provider can
read them.

**They take very little space:** each snapshot is the whole database and restores on its
own, but the cloud only stores what changed since the previous one, compressed. Example: a
database of about 6 MB → about 1 MB a day, 20–25 MB for the 30 daily snapshots, and about
1 MB for each monthly one: around 50 MB after two years, instead of half a GB with whole
copies every night. A free Google Drive account (15 GB) is plenty.

In **«Ρυθμίσεις» → «Αντίγραφα ασφαλείας»**:

1. In **«Πού»** (where) choose **Google Drive**, **Dropbox** or **Backblaze B2** (10 GB
   free).
2. For **Google Drive / Dropbox** you briefly need a computer with a browser (the page
   shows the same steps):
   - download rclone from [rclone.org/downloads](https://rclone.org/downloads/) and unzip
     it;
   - open a terminal in that folder (Windows: right-click inside the folder → «Open in
     Terminal») and run, for Google Drive:
     - Windows: `.\rclone.exe authorize "drive"`
     - Mac / Linux: `./rclone authorize "drive"`

     (for Dropbox write `"dropbox"` instead of `"drive"`);
   - log in in the browser that opens and press «Allow»;
   - copy the text it prints (it starts with `{"access_token"`) and paste it into the
     page.

   For **Backblaze B2**: create a bucket (Private) and an Application Key, and enter the
   keyID, the applicationKey and the bucket name.
3. Press **«Σύνδεση και πρώτο ανέβασμα»** (connect and first upload). Connecting takes a
   moment: at the end the first backup is uploaded straight away, and the page says whether it
   worked. Karta shows an
   **encryption password** once. **Write it on paper or in a password manager.** To close
   the box you type its last 4 characters and press «Τον σημείωσα» (I've noted it).

> **⚠ The encryption password can't be recovered in any way.** The backups are encrypted on
> the machine before they're uploaded, and only this password opens them. There's no
> "forgot my password": neither Karta, nor Google, Dropbox or Backblaze, nor anyone else can
> recover it. While the machine works the password is stored on it; you need it **exactly
> when the machine breaks or is lost**, and then without it the punch records (which must be
> kept for years) are gone. Keep it on paper **outside the shop** or in a password manager,
> and tell someone you trust where it is. (The copies on the machine and on USB aren't
> encrypted and don't need it.)

On Google Drive the files go into the `Karta-backups` folder (encrypted pieces that don't
open with a double click; Karta can only see the files it creates itself). **«Ανέβασμα τώρα»** (upload now) uploads a
backup straight away; **«Αποσύνδεση cloud»** (disconnect cloud) stops the uploads (what's
already uploaded stays).

**«Η πρόσβαση στο cloud έληξε — συνδέστε ξανά»** (cloud access expired, connect again): repeat
steps 2–3 with a new access code. Karta keeps the **same encryption password** and carries on
with the same backups; you don't need to type it. If the new connection fails, the previous
setup stays as it was (Karta tries the new one separately and keeps it only if it works).

### To a USB stick: `./setup.sh usb`

For a Raspberry Pi or PC in the shop or at home. Connecting a USB stick needs administrator
rights on the machine, which the admin page deliberately doesn't have, so it's done once
from the terminal (through `ssh`):

1. Plug in a USB stick (FAT32, exFAT, NTFS or ext4; whatever is already on it stays).
2. `cd ~/karta && ./setup.sh usb`
3. Pick the USB stick from the list. The assistant mounts it permanently (also after a
   restart) and makes a test backup straight away.

Every night the backups are also written to the USB stick, in the `karta-backups` folder.
The USB stick is in the same place as the machine (fire, theft), so combine it with the
cloud.

> **The USB copies are not encrypted.** They are the databases as they are, together with
> `karta.env`, which holds `PIN_KEY` (and the Ergani password, if you keep it in `.env`).
> With those, the Ergani password and the PINs that Karta stores can be read too. Whoever
> takes the stick can read it all: keep it somewhere safe, like the shop's keys.

## Downloading from the admin page

- **«Λήψη αντιγράφου τώρα»** (download a backup now): downloads the whole database as one
  file, to keep wherever you like. It contains staff data: keep it somewhere safe.
- **«Αρχείο χτυπημάτων (Excel)»** (punch archive): every punch of a year, one per row: date,
  time, employee, status, **Ergani protocol number**, when it was submitted, the reason for
  a late declaration, method (PIN/QR) and device. It opens **without Karta**, e.g. during
  an inspection. Good practice: every January, download the previous year's file and keep
  it with your accounting records.

## Restore

### From the admin page

In **«Ρυθμίσεις» → «Αντίγραφα ασφαλείας» → «Επαναφορά»** (restore):

- **«Από αρχείο…»** (from a file): a backup you have (from «Λήψη αντιγράφου τώρα», from the
  USB stick, or from the `backups` folder).
- **«Από το cloud…»** (from the cloud): you pick a snapshot (date and time) from the list.

First it shows **what the backup contains** (business, employees, punches, last punch), and
nothing changes. With **«Επαναφορά τώρα»** (restore now) the current database is kept as
`before-restore-….db` (next to the database) and the backup takes its place, without a
restart. If the backup was made with a different `PIN_KEY`, the page tells you: then the
Ergani password and the PINs aren't shown until you put the old `PIN_KEY` in `.env` (it's
in the backups' `karta.env`) or enter them again.

### On a new machine, from the cloud

The cloud snapshot holds **only the database**, not `karta.env` or `PIN_KEY`. If your
Karta is on a VPS, or your only backup is in the cloud, keep a copy of `.env` (at least
`PIN_KEY`) in a password manager. Without the old `PIN_KEY`, after the restore the Ergani
password and the ntfy token must be typed again in «Ρυθμίσεις», and PINs and QR cards
can't be shown until you issue new ones. PINs and QR cards still work on the shop screen.

1. Install Karta with [Easy installation](Easy-Installation-EN) (`./setup.sh`: same
   address and a Cloudflare API key, old or new; the assistant reuses the tunnel). If you
   have the old `PIN_KEY`, put it in `.env` and restart (`cd ~/karta && docker compose up -d`)
   before restoring.
2. On the admin page: «Αντίγραφα ασφαλείας» → **«Έχω ήδη αντίγραφα στο cloud»** (I already
   have backups in the cloud): same provider, a new access code (`rclone authorize`), and
   the **encryption password** you wrote down → «Σύνδεση στα υπάρχοντα αντίγραφα» (connect
   to the existing backups).
3. «Επαναφορά» → «Από το cloud…» → the most recent one → «Επαναφορά τώρα».

### From the terminal: `./setup.sh restore`

For when the admin page won't open. It takes a backup from the machine (`backups/`) or from
the USB stick, also brings back the settings (`karta.env`) if `.env` is missing, checks
`PIN_KEY`, keeps a copy of the current database and does the restore:

```bash
cd ~/karta && ./setup.sh restore
./setup.sh restore /mnt/karta-usb/karta-backups/daily/karta-2026-10-05.db   # or a specific file
```

## Without the assistant

If you don't use `setup.sh`, the admin page's cloud backup works as usual. To back up the
database while Karta is running, use SQLite's backup command (not a plain `cp`):

```bash
docker compose exec -T karta python -c "import sqlite3; s=sqlite3.connect('/data/workcard.db'); d=sqlite3.connect('/data/backup.db'); s.backup(d); d.close()"
docker compose cp karta:/data/backup.db karta-$(date +%F).db
```

Also keep `.env` safe, especially `PIN_KEY`.
