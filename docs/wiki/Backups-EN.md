🇬🇷 [Ελληνικά](Backups) · 🇬🇧 **English**

# Backups and restore

The punches of the digital work card must be **kept for at least 5 years** (confirm this
with your accountant). Karta **never deletes** a real punch: everything stays in its
database. The risk is the machine breaking (e.g. the Raspberry Pi's microSD card), so you
need a backup **off the machine as well**.

Every backup is **the whole database**: all employees, every punch from the start,
schedules and settings. So the most recent one is enough to get everything back.

## What happens automatically

The setup assistant (`./setup.sh`) creates `backup.sh` and sets it to run **every night at
23:30**. In the `~/karta/backups` folder it keeps:

| Folder | What's in it |
|---|---|
| `daily/` | one backup for each of the last 30 days |
| `monthly/` | the last backup of each month, for 24 months |
| `yearly/` | the last backup of each year, **forever** |
| `karta.env` | a copy of the settings (`.env`), needed for a restore |

Each night's result shows on the admin page, in **«Ρυθμίσεις» → «Αντίγραφα ασφαλείας»**
(backups): «Τελευταίο αντίγραφο: … · στο μηχάνημα ✓ · USB ✓ · cloud ✓». If backups stop or
one fails, you get an **alert** (on your phone too).

## A backup off the machine

Choose **one or both**. On Karta's machine (through `ssh`):

### To a USB stick: `./setup.sh usb`

For a Raspberry Pi or PC in the shop or at home.

1. Plug in a USB stick (FAT32, exFAT, NTFS or ext4; whatever is already on it stays).
2. `cd ~/karta && ./setup.sh usb`
3. Pick the USB stick from the list. The assistant mounts it permanently (also after a
   restart) and makes a test backup straight away.

Every night the backups are also written to the USB stick, in the `karta-backups` folder.
The USB stick is in the same place as the machine (fire, theft), so now and then take a
copy somewhere else too, or also use the cloud.

### Encrypted in the cloud: `./setup.sh cloud`

For everyone, and **the only option on a VPS / cloud server** (e.g. Oracle Cloud), where
there's no USB. Backups are uploaded **encrypted** with the
[rclone](https://rclone.org) tool: not even the cloud provider can read them.

1. `cd ~/karta && ./setup.sh cloud` (it installs rclone if needed).
2. Choose where: **Google Drive**, **Dropbox**, **Backblaze B2** (10 GB free), or another.
3. For Google Drive / Dropbox you briefly need a computer with a browser:
   - download rclone from [rclone.org/downloads](https://rclone.org/downloads/) and unzip
     it;
   - in a terminal in that folder run `./rclone authorize "drive"` (or `"dropbox"`); on
     Windows `.\rclone.exe authorize "drive"`;
   - log in in the browser and press «Allow»;
   - copy the text it prints (it starts with `{"access_token"`) and paste it into the
     assistant.
4. The assistant creates an **encryption password** and shows it to you once.
   **Write it on paper or in a password manager.** Without it, if the machine breaks, the
   backups in the cloud **can't be opened**.

On Google Drive the files go into the `Karta-backups` folder (with encrypted names).
Anything deleted locally (e.g. daily backups older than 30 days) first goes to the
`deleted` folder and is permanently deleted after 30 days.

## Downloading from the admin page

In **«Ρυθμίσεις» → «Αντίγραφα ασφαλείας»**:

- **«Λήψη αντιγράφου τώρα»** (download a backup now): downloads the whole database as one
  file, to keep wherever you like. It contains staff data: keep it somewhere safe.
- **«Αρχείο χτυπημάτων (Excel)»** (punch archive): every punch of a year, one per row: date,
  time, employee, status, **Ergani protocol number**, when it was submitted, the reason for
  a late declaration, method (PIN/QR) and device. It opens **without Karta**, e.g. during
  an inspection. Good practice: every January, download the previous year's file and keep
  it with your accounting records.

## Restore: `./setup.sh restore`

If the machine breaks, or you need to go back to an earlier day:

1. On a **new machine**: follow [Easy installation](Easy-Installation-EN) up to and
   including installing Docker, download `setup.sh` into `~/karta` and run
   `./setup.sh restore` **before** `./setup.sh`. On the same machine: just
   `cd ~/karta && ./setup.sh restore`.
2. Choose where from: the machine, the USB stick, or the cloud (you give access to the
   cloud again, and the **encryption password**).
3. The assistant suggests the most recent backup (or you type another file), also brings
   back the settings (`karta.env`) if they're missing, and checks that `PIN_KEY` is the
   same as the backup's (without it, the Ergani password and the PINs can't be read).
4. Before replacing the database, it keeps a copy of the current one.

You can also give a file directly:
`./setup.sh restore /mnt/karta-usb/karta-backups/daily/karta-2026-10-05.db`.

On a new machine, after the restore run `./setup.sh` for Cloudflare (the tunnel can stay
the same: the assistant finds it and reuses it).

## Without the assistant

If you don't use `setup.sh`, back up the database while Karta is running with SQLite's
backup command (not a plain `cp`):

```bash
docker compose exec -T karta python -c "import sqlite3; s=sqlite3.connect('/data/workcard.db'); d=sqlite3.connect('/data/backup.db'); s.backup(d); d.close()"
docker compose cp karta:/data/backup.db karta-$(date +%F).db
```

Also keep `.env` safe, especially `PIN_KEY`.
