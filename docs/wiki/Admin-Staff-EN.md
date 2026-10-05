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
| **«Έκδοση QR»** / **«Κάρτα QR»** | «Έκδοση QR» (issue QR) when they have no card: creates it. «Κάρτα QR» when they have one: shows the same card (no new code). From there you download, print, send the **phone link**, make a «Νέα κάρτα» (new card) or cancel. See [QR cards](QR-Cards-EN). |
| **«Νέο PIN»** | Generate a new random PIN (this also unlocks a locked PIN). |
| **«Εμφάνιση PIN»** | Show the current PIN for 20 seconds. Only there with `PIN_KEY` set in `.env`. |
| **«Ορισμός PIN»** | Set a PIN yourself: exactly 6 digits; easy ones like `123456` or `111111` are refused. |
| **«Μετονομασία»** | Change the display name on the shop screen. |
| **«Απενεργοποίηση»** / **«Ενεργοποίηση»** | Hide them from the shop screen (e.g. left the job) while keeping their history. «Ενεργοποίηση» (activate) brings them back. |
| **«Διαγραφή»** | Remove the employee completely. Only allowed when they have **no real (production) punches**, e.g. test entries or someone imported by mistake. Real punches are legal working‑time records and must be kept; use «Απενεργοποίηση» instead. |

## What the employee card shows

Under the name: today's schedule (and whether it's declared overtime or a day change),
«φεύγει έως» (leaves by), leave and future day changes, and notes such as «Θα αργήσει»
(will be late), «Επιτρέπεται νωρίτερη προσέλευση σήμερα» (early arrival allowed today),
«Ευέλικτη προσέλευση N′» and «Χωρίς αποχώρηση: …» (no departure).

**«Κλειδωμένο PIN»** (PIN locked): after 5 wrong PINs in a row the PIN is locked for 5
minutes (protection against guessing). It unlocks by itself, or at once with «Νέο PIN» /
«Ορισμός PIN». The QR card keeps working meanwhile.

## Cancelling leave, a day change or a note

The «Άδεια…», «Υπερωρία / αλλαγή ημέρας…» and «Έφυγε νωρίτερα…» windows list what's
already recorded underneath. **«Ακύρωση»** (cancel: leave, day changes) or **«Διαγραφή»**
(delete: early‑leave reason) removes it. Nothing is sent to Ergani; if you had declared it
there, change it in Ergani too.

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
