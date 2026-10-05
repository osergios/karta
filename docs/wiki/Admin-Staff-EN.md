[Ελληνικά](Admin-Staff) · **English**

# Admin: «Προσωπικό» (Staff)

One card per employee, showing their status («Σε βάρδια», «Εκτός», «Σε άδεια»,
«Κλειστά», «Ανενεργός»), their official name and ΑΦΜ, and today's schedule.

![Admin, staff](https://raw.githubusercontent.com/osergios/karta/main/docs/screenshots/admin-staff.png)

## Adding employees

Employees come **only from Ergani**: «Ρυθμίσεις» → «ΕΡΓΑΝΗ» → «Έλεγχος ΕΡΓΑΝΗ» (see
[Settings](Admin-Settings-EN)). This guarantees that ΑΦΜ and full name are exactly as in
Ergani, which the declarations need. You choose a short **display name** for the shop
screen (e.g. "Μαρία"). Reports for the accountant always use the official name.

Each new employee gets an automatic 6‑digit PIN, shown once.

## The «Ενέργειες ▾» menu

Frequent actions are at the top, rare ones at the bottom. On a phone the menu opens as a
bottom sheet.

### Day to day

| Action | What it does |
|---|---|
| **«Αποχώρηση…»** | Record a departure: now, forgotten (Karta only), or a technical problem. See [Today](Admin-Today-EN). |
| **«Άδεια…»** | Leave from–to (inclusive), with a type: «Κανονική άδεια», «Άδεια ασθενείας» or «Άδεια ειδικού σκοπού», plus an optional note. On leave: no reminders, no "didn't punch in" alerts, and the report shows leave with 0 scheduled hours. A punch during leave alerts you. Nothing is sent to Ergani (the accountant declares leave there). |
| **«Υπερωρία / αλλαγή ημέρας…»** | For one day: overtime (a later end), different hours, or no work. Enter it **after** declaring it in Ergani. Reminders, alerts, the early/closed checks and the report then follow the new hours. This is also how someone works on a holiday or a closed day. |
| **«Θα αργήσει σήμερα (σίγαση)»** | For today only: mutes their punch‑in reminder and the "didn't punch in" phone alert. «Άρση σίγασης προσέλευσης» undoes it. Punch‑out reminders are never muted. |
| **«Νωρίτερη προσέλευση σήμερα»** | Lets today's arrival before the declared start through. Use it only after declaring the earlier start in Ergani. |
| **«Έφυγε νωρίτερα…»** | Why someone left before the end of the day: sickness, personal, or other (+ note), for any of the last 62 days. For sickness, it can also add sick leave from the next day in one step. |
| **«Ξεχασμένη βάρδια…»** | Enter a whole shift that was never punched, **in Karta only** (for the report and pay; never sent to Ergani). |

### Setup and cards

| Action | What it does |
|---|---|
| **«Ευέλικτη προσέλευση…»** | Flexible arrival window in minutes (0–120), as shown in the employee's «Ψηφιακή Οργάνωση Χρόνου Εργασίας» in Ergani. See below. |
| **«Κάρτα QR»** | Issue, show or cancel their QR card. See [QR cards](QR-Cards-EN). |
| **«Σύνδεσμος για το κινητό»** | A 24‑hour link that delivers the QR card to their phone. |
| **«Νέο PIN»** | Generate a new random PIN. You can also set one yourself («Ορισμός PIN»): exactly 6 digits, and easy ones like `123456` or `111111` are refused. |
| **PIN view** | Show the current PIN. Only works with `PIN_KEY` set in `.env`. |
| **«Μετονομασία»** | Change the display name on the shop screen. |
| **«Απενεργοποίηση»** | Hide them from the shop screen (e.g. left the job) while keeping their history. |
| **«Διαγραφή»** | Remove the employee completely. Only allowed when they have **no real (production) punches**, e.g. test entries or someone imported by mistake. Real punches are legal working‑time records and must be kept; use «Απενεργοποίηση» instead. |

## Flexible arrival («Ευέλικτη προσέλευση»)

Greek law lets an employee start up to a declared number of minutes after their scheduled
start (ν. 5239/2025, ΠΔ 80/2022 άρθρο 580 παρ. 2Α). With a window set:

- Arriving inside the window shifts the whole day by the same amount: punch‑out
  reminders, alerts, the overtime deadline and «φεύγει έως» follow the actual arrival.
- Arriving later than the window shifts the day by the full window only. The rest counts
  as lateness.
- Punch‑in reminders and the "didn't punch in" alert still count from the declared start.
- Arriving **before** the declared start is still refused.
- In the report, such a day counts as on schedule, with a note like «Ευέλικτη προσέλευση:
  11:05 (+0:35 από τις 10:30) → λήξη 17:25».

With the window at 0 (the default), nothing changes.
