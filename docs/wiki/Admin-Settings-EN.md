🇬🇷 [Ελληνικά](Admin-Settings) · 🇬🇧 **English**

# Admin: «Ρυθμίσεις» (Settings)

## «Επιχείρηση και σύνδεση με το ΕΡΓΑΝΗ» (business and Ergani connection)

Anything saved here applies immediately (no restart) and **overrides** `.env`. A value
that comes from `.env` is marked «από το .env».

- **«Λειτουργία» (mode):** test (`dry_run`), Ergani test environment (`trial`) or live
  (`production`). For `trial` / `production` you type the ΑΦΜ (tax number) to confirm, and
  Karta tests the connection first. See [Going live](Going-Live-EN).
- **«Επιχείρηση» (business):** employer ΑΦΜ (the check digit is verified), branch number
  (usually 0) and, optionally, your employer id in Ergani (the «id:» in Ergani's QR, so a
  QR from another employer is refused).
- **«Χρήστης web services του ΕΡΓΑΝΗ» (Ergani web‑services user):** username, password and
  type (`01` API user, `02` branch «ΕΡΓΑΝΗ» user). **«Δοκιμή σύνδεσης»** (test connection)
  connects read‑only. The password is stored **encrypted** (with `PIN_KEY`) and is never
  shown again; to keep it unchanged, leave the box empty.
- **«Χρήστης για το δοκιμαστικό ΕΡΓΑΝΗ»** (user for the Ergani test environment, optional):
  for `trial` mode, if you have a separate user on `trialv2eservices.yeka.gr`.

If something the current mode needs is missing, a red «Χρειάζεται συμπλήρωση» (needs
filling in) line appears, and punches wait until it's filled in.

## «ΕΡΓΑΝΗ»

Reads from Ergani and compares with Karta. **It never submits anything.** Of everything
Ergani returns, Karta keeps only ΑΦΜ, full name and the declared schedule (data
minimisation; the rest is discarded and never logged).

| Button | What it does |
|---|---|
| **«Έλεγχος ΕΡΓΑΝΗ»** | Reads the employer, branches and current staff. Each person is marked «Νέος», «Υπάρχει ✓» or «Διαφορετική γραφή ονόματος». Tick the new ones and import them: this is how employees are added. |
| **«Ενημέρωση στοιχείων ωραρίου από ΕΡΓΑΝΗ»** | Refreshes each employee's declared schedule, weekly hours, break and flexible arrival from Ergani, shown next to their schedule for comparison. |
| **«Υπηρεσίες ΕΡΓΑΝΗ»** | Lists the Ergani web services available to your user (useful when checking credentials). |

## «Όρια και ειδοποιήσεις» (limits and alerts)

The daily and weekly limits depend on the employment contract and on whether you work
5 or 6 days. **Confirm them with your accountant.**

| Setting | Default | Meaning |
|---|---|---|
| «Ευελιξία προσέλευσης / αποχώρησης (λεπτά)» | 5 | Phone alert if someone hasn't punched in this many minutes after their start, or is still in this long after their end. It only controls notifications; it's not a tolerance in the reports. |
| «Επείγον μετά από (λεπτά)» | 30 | Still in this long after that → the alert becomes urgent. |
| «Προσέλευση πριν το ωράριο (λεπτά)» | 0 | How early an arrival is accepted. Ergani has no tolerance, so 0 is the safe value. |
| «Προθεσμία δήλωσης υπερωρίας πριν τη λήξη (λεπτά)» | 60 | Overtime or a later end must be declared in Ergani at least this long before the declared end. Shown as «υπερωρία δηλώνεται έως …». |
| «Υπενθύμιση προθεσμίας υπερωρίας (λεπτά πριν)» | 0 (off) | Phone reminder this long before that deadline, naming who's in. |
| «Όριο ημέρας, μετά υπερωρία (ώρες)» | 9 | Daily maximum; beyond it is υπερωρία. |
| «Συμβατική εβδομάδα, μετά υπερεργασία (ώρες)» | 40 | Contractual week; beyond it is υπερεργασία (+20%). |
| «Νόμιμη εβδομάδα, μετά υπερωρία (ώρες)» | 45 | Legal week (45 for a 5‑day week, 48 for 6‑day); beyond it is υπερωρία. |
| «Ελάχιστη ανάπαυση (ώρες)» | 11 | Minimum rest between two working days. |

The shop‑screen reminders and festive decorations switches are on the
[Today](Admin-Today-EN) tab.

## «Ειδοποιήσεις στο κινητό» (phone notifications)

The ntfy server and topic, and optionally a token. The page suggests a random topic: add
it in the ntfy app («+»), then press «Αποθήκευση» (save) and «Δοκιμαστική ειδοποίηση»
(test notification). See [Alerts and reminders](Alerts-and-Reminders-EN#setting-up-ntfy).

## «Αντίγραφα ασφαλείας» (backups)

- The result of the last nightly backup: on the machine and on USB (from `backup.sh`),
  and in the cloud.
- **Cloud:** connect to Google Drive, Dropbox or Backblaze B2 («Σύνδεση και πρώτο
  ανέβασμα», connect and first upload, with an encryption password shown once),
  **«Ανέβασμα τώρα»** (upload now), **«Αποσύνδεση cloud»** (disconnect cloud), and
  **«Έχω ήδη αντίγραφα στο cloud»** (I already have backups in the cloud) for a new
  machine.
- **«Λήψη αντιγράφου τώρα»** (download a backup now): the whole database in one file.
- **«Αρχείο χτυπημάτων (Excel)»** (punch archive): every punch of a year, with its Ergani
  protocol number, for your records and for inspections.
- **«Επαναφορά»** (restore) «Από αρχείο…» (from a file) or «Από το cloud…» (from the
  cloud): first it shows what the backup contains, and then «Επαναφορά τώρα» (restore now)
  puts it in place of the current database (which is kept as a copy).

See [Backups and restore](Backups-EN).

## «Στοιχεία επιχείρησης» (business details)

What staff see on the shop screen, the phone QR card and the links:

- **«Επωνυμία»:** the business name customers know.
- **«Σύντομο όνομα»:** used in page titles and messages.
- **«Χρώματα» (colours):**
  - **«Έτοιμο θέμα»** (ready theme): Karta (turquoise), «Θάλασσα» (sea, blue), «Μπορντό»
    (burgundy), «Ελιά» (olive, green), «Τερακότα» (terracotta), «Γραφίτης» (graphite),
    «Νύχτα» (night, dark). It fills in the colours, which you can then change one by one.
  - **Main colour** (buttons, titles, QR card), **Background**, **Side panel**, **Text**,
    **«Προσέλευση» button** (clock in) and **«Αποχώρηση» button** (clock out). Text on the
    buttons automatically turns black or white, whichever reads better, and the page
    warns you if something isn't readable.
  - **Dark theme**, separately for the shop screen and for the admin page.
  - A small **preview** of the screen changes as you choose; the admin page takes the
    colours when you save, the shop screen the next time it opens or with «Ανανέωση
    οθόνης» (refresh screen). «Αρχικά χρώματα» (original colours) goes back to Karta's
    theme.
- **Logo:** PNG, JPG or WebP up to 1 MB, ideally square with a transparent background.
  It's stored in the database, so it's included in your backups. With no logo, the name
  is shown instead.

The official employer details in the accountant's report always come from Ergani, not
from here.

## «Έκδοση και ενημέρωση» (version and update)

The running version, and whether a newer one is out (checked every few hours), with a
«Τι αλλάζει» (what's new) link. **«Ενημέρωση τώρα»** (update now) leaves a request for
`update.sh` on the machine, which within a minute keeps a backup, downloads the new version
and restarts Karta; the page and the shop screen reload by themselves. If the button is
missing, run `cd ~/karta && ./setup.sh update` once on the machine (it updates and installs
`update.sh`).

## «Συσκευές» (devices)

The registered shop screens: name, when registered and last seen. Create a registration
code with **«Δημιουργία κωδικού εγγραφής»** (see [Shop screen](Kiosk-EN)), revoke a device,
or remove it from the list.

## «Κινήσεις» (movements)

The last 300 punches, with their status (see
[How punches reach Ergani](Ergani-Submissions-EN)) and protocol number. From here you can:

- see **«Τι θα στελνόταν»**: the exact payload, in `dry_run`;
- **retry** a failed submission;
- decide on an **uncertain** one («Υπάρχει στο ΕΡΓΑΝΗ» / «Δεν υπάρχει — νέα αποστολή»);
- **«Διαγραφή δοκιμαστικών κινήσεων»:** remove every punch made in `dry_run` or `trial`
  mode. Punches made in `production` mode are never touched, including onboarding‑period
  ones.
