🇬🇷 [Ελληνικά](Admin-Settings) · 🇬🇧 **English**

# Admin: «Ρυθμίσεις» (Settings)

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

## «Στοιχεία επιχείρησης» (business details)

What staff see on the shop screen, the phone QR card and the links:

- **«Επωνυμία»:** the business name customers know.
- **«Σύντομο όνομα»:** used in page titles and messages.
- **«Χρώμα»:** the main colour, with a readability check.
- **Logo:** PNG, JPG or WebP up to 1 MB, ideally square with a transparent background.
  It's stored in the database, so it's included in your backups. With no logo, the name
  is shown instead.

The official employer details in the accountant's report always come from Ergani, not
from here.

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
