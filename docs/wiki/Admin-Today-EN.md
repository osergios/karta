[Ελληνικά](Admin-Today) · **English**

# Admin: «Σήμερα» (Today)

The first tab of the admin page (`/admin`). It shows what's happening right now, every
employee with their «Ενέργειες ▾» (actions) menu, and anything that needs your attention.
It refreshes itself every 30 seconds without wiping anything you're typing, and pauses
while the page is in the background.

![Admin, today](https://raw.githubusercontent.com/osergios/karta/main/docs/screenshots/admin-today.png)

There are four tabs: «Σήμερα», «Ωράρια & αργίες», «Αναφορές» and «Ρυθμίσεις». On a
computer they're along the top; on a phone they're an icon bar at the bottom. The page
reopens on the last tab you used. The alert count shows in the header (**«⚠ N»**); click
it to jump to «Ειδοποιήσεις» (alerts). Next to it, the header shows the current mode, the
branch number and your account.

> The old **«Προσωπικό»** (staff) tab was merged into «Σήμερα» in version 1.8.0. Old links
> and bookmarks to it (`/admin#people`) open «Σήμερα».

On every tab, the long help texts are folded behind **«ⓘ Οδηγίες»** (instructions); click
to open.

## «Πρώτα βήματα» (first steps)

On a new installation, the top of this tab shows a **«Πρώτα βήματα»** checklist: the Ergani
connection (ΑΦΜ and user), business details, staff from Ergani, schedules, local holidays,
the shop screen, phone notifications, backups, a trial run with the staff, and going live
on Ergani.

- Each step **ticks itself off** once it's done, and has a **«Πάμε»** (go) button, or
  «Άνοιγμα» (open) once done, that opens the right place.
- «Δοκιμή με το προσωπικό» (trial run with the staff) ticks itself off with the first punch
  in «Δοκιμαστική».
- What Karta can't detect by itself (e.g. "we have no local holidays", or backups you keep
  your own way) you mark with
  **«Έγινε / Παράλειψη»** (done / skip) or **«Δεν χρειάζεται»** (not needed).
  **«Αναίρεση»** (undo) unticks what you marked by hand.
- The notifications step has a **«Δοκιμαστική ειδοποίηση»** (test notification) button.
- **«Απόκρυψη»** hides the checklist.

## Who is where

Every employee is one row, in one of the sections below, with their own **«Ενέργειες ▾»**
menu on the right. When the shop is closed today (holiday or closure), a line at the top
says so.

| Section | Who's in it |
|---|---|
| «Ξέχασαν αποχώρηση» | Anyone with an arrival from an earlier day and no departure, with «Χωρίς αποχώρηση: …» (no departure) and a «Κλείσιμο DD/MM…» button (see below). Only shown when there's someone. |
| «Μέσα τώρα» | Punched in and not out yet, with an «Αποχώρηση…» button. The row shows today's schedule, **«φεύγει έως»** (when they must leave) and, with advance declaration, **«υπερωρία δηλώνεται έως»** (the last moment to declare overtime in Ergani; there's none with the retrospective system, see [Settings](Admin-Settings-EN)). |
| «Έφυγαν νωρίτερα» | Punched out before the end of their day («αποχώρησε 15:40 αντί 17:00», left 15:40 instead of 17:00). Use «Λόγος…» to record why. |
| «Έρχονται σήμερα» | Scheduled today but not in yet (with «θα αργήσει (σίγαση)», will be late, if you set it). |
| «Τελείωσαν» | Finished today's day and left. |
| «Εκτός σήμερα» | Day off («ρεπό»), leave, holiday or closure. |
| «Ανενεργοί (N)» | At the bottom, folded; click to open. People you deactivated, who don't appear on the shop screen. Their menu only has the PIN items, «Μετονομασία», **«Ενεργοποίηση»** (activate) and **«Διαγραφή»** (delete). |

### What each row shows

Under the name, in this order:

1. **Today's schedule,** e.g. «09:00–17:00 · διάλ. 30′» (30′ break) or «09:00–17:00 ·
   διάλ. 20′ εκτός ωραρίου» (20′ break outside the hours); a split shift reads
   «10:00–14:00 + 17:00–21:00». Depending on the section, it adds «· δηλωμένη υπερωρία»
   (declared overtime), «· φεύγει έως 17:20» (leaves by), «· ευέλικτη προσέλευση έως 09:30»
   (flexible arrival until, while you're waiting for them) or «· ευέλικτη +12′ (κανονικά
   έως 17:00)» (once they came in inside the window). See [Flexible
   arrival](Admin-Schedules-and-Holidays-EN#flexible-arrival-ευέλικτη-προσέλευση).
2. **Warnings** (highlighted):
   - **«Κλειδωμένο PIN»** (PIN locked): after 5 wrong PINs in a row the PIN is locked for 5
     minutes (protection against guessing). It unlocks by itself, or at once with «Νέο
     PIN» / «Ορισμός PIN». The QR card keeps working meanwhile.
   - **«Ξεχασμένα χτυπήματα μήνα: N»** (forgotten punches this month), from 3 upwards.
3. **The last punch,** to the second: «Τελευταίο χτύπημα: προσέλευση σήμερα 08:57:12»
   (last punch: arrival today 08:57:12), or with the date when it wasn't today
   («Τελευταίο χτύπημα: αποχώρηση 03/10/2026 17:02:45»). Someone who has never punched
   shows «Δεν έχει χτυπήσει ακόμα κάρτα» (hasn't punched yet).
4. **The official name and ΑΦΜ** from Ergani (e.g. «Παπαδοπούλου Μαρία · ΑΦΜ 000000000»).
5. **Leave** («Κανονική άδεια: 12/10–16/10») and **upcoming day changes** («Αλλαγές: …»)
   when there are any, and «Επιτρέπεται νωρίτερη προσέλευση σήμερα» (early arrival allowed
   today).

## Adding employees

Employees come **only from Ergani**: «Ρυθμίσεις» → «ΕΡΓΑΝΗ» → «Έλεγχος ΕΡΓΑΝΗ» (see
[Settings](Admin-Settings-EN)). This guarantees that ΑΦΜ and full name are exactly as in
Ergani, which the declarations need. You choose a short **display name** for the shop
screen (e.g. "Μαρία"). Reports for the accountant always use the official name.

Each new employee gets an automatic 6‑digit PIN, shown once. You set their schedule in
[«Ωράρια & αργίες»](Admin-Schedules-and-Holidays-EN).

## The «Ενέργειες» menu

Every row has an **«Ενέργειες ▾»** (actions) button. Frequent actions are at the top, rare
ones at the bottom; the menu only shows what fits at that moment (e.g. «Αποχώρηση…» only
for someone who's in). On a phone the menu opens as a bottom sheet.

### Day to day

| Action | What it does |
|---|---|
| **«Αποχώρηση…»** | Record a departure: now, forgotten (Karta only), or a technical problem. See [below](#recording-a-departure-αποχώρηση). |
| **«Κλείσιμο DD/MM…»** | Close a forgotten arrival from an earlier day. See [below](#forgotten-punchouts-from-earlier-days). |
| **«Υπερωρία / αλλαγή ημέρας…»** | For one day: overtime (a later end), different hours, or no work. Enter it **after** declaring it in Ergani. Reminders, alerts, the early/closed checks and the report then follow the new hours. This is also how someone works on a holiday or a closed day. See [below](#overtime-or-a-oneday-change). |
| **«Άδεια…»** | Leave from–to (inclusive), with a type: «Κανονική άδεια», «Άδεια ασθενείας» or «Άδεια ειδικού σκοπού», plus an optional note. On leave: no reminders, no "didn't punch in" alerts, and the report shows leave with 0 scheduled hours. A punch during leave alerts you. Nothing is sent to Ergani (the accountant declares leave there). |
| **«Έφυγε νωρίτερα…»** | Why someone left before the end of the day: sickness, personal, or other (+ note), for any of the last 62 days. For sickness, it can also add sick leave from the next day in one step. |
| **«Ξεχασμένη βάρδια…»** | Enter a whole shift that was never punched, **in Karta only** (for the report and pay; never sent to Ergani). |
| **«Νωρίτερη προσέλευση σήμερα»** | Lets today's arrival before the declared start through. Use it only after declaring the earlier start in Ergani. |
| **«Θα αργήσει σήμερα (σίγαση)»** | For today only: mutes their punch‑in reminder and the "didn't punch in" phone alert. «Άρση σίγασης προσέλευσης» undoes it. Punch‑out reminders are never muted. |
| **«Έκδοση QR»** / **«Κάρτα QR»** | «Έκδοση QR» (issue QR) when they have no card: creates it. «Κάρτα QR» when they have one: shows the same card (no new code). From there you download, print, send the **phone link**, make a «Νέα κάρτα» (new card) or cancel. See [QR cards](QR-Cards-EN). |

### PIN, name and deactivation

| Action | What it does |
|---|---|
| **«Νέο PIN»** | Generate a new random PIN (this also unlocks a locked PIN). |
| **«Εμφάνιση PIN»** | Show the current PIN for 20 seconds. Only there with `PIN_KEY` set in `.env`. |
| **«Ορισμός PIN»** | Set a PIN yourself: exactly 6 digits; easy ones like `123456` or `111111` are refused. |
| **«Μετονομασία»** | Change the display name on the shop screen. |
| **«Απενεργοποίηση»** / **«Ενεργοποίηση»** | Hide them from the shop screen (e.g. left the job) and move them to «Ανενεργοί», while keeping their history. «Ενεργοποίηση» (activate) brings them back. |
| **«Διαγραφή»** | Remove the employee completely. Only allowed when they have **no real (production) punches**, e.g. test entries or someone imported by mistake. Real punches are legal working‑time records and must be kept; use «Απενεργοποίηση» instead. |

Flexible arrival is no longer in this menu: it's set on the employee's schedule card in
[«Ωράρια & αργίες»](Admin-Schedules-and-Holidays-EN#flexible-arrival-ευέλικτη-προσέλευση).

## Overtime or a one‑day change

«Υπερωρία / αλλαγή ημέρας…» opens a window with **«Ημέρα»** (day), **«Είδος»** (kind:
«Υπερωρία (αργότερη αποχώρηση)» overtime, «Άλλο ωράριο αυτή την ημέρα» other hours that
day, or «Δεν δουλεύει (ρεπό)» not working) and an optional note.

- The **day's hours** are entered as in the weekly schedule: start and end, «+ σπαστό»
  for a second part, «✕» to remove one. They start from that day's normal schedule, which
  is also shown above («Κανονικό ωράριο αυτής της ημέρας: …»).
- The **break** is added by itself: the one of that weekday (or of the week), on every
  part longer than 4 hours.
- Underneath you see the **paid hours**, the break, the **departure time** and the
  difference from the normal day, e.g. «Πληρωμένες ώρες 9ω · διάλειμμα 30′ · αποχώρηση
  στις 19:30 · +1ω σε σχέση με το κανονικό».
- For today, with advance declaration, it reminds you of the overtime deadline (or that it
  has passed); with the retrospective system, that it's declared by the end of the next
  month.

## Recording a departure («Αποχώρηση…»)

Use this when someone left without punching out. You choose how:

- **«Φεύγει τώρα»:** they're leaving now; sent to Ergani in real time.
- **«Ξέχασε να χτυπήσει»:** they forgot. The shift is closed **in Karta only**, with a
  required note and the status «Μόνο στην κάρτα». It's **never sent** to Ergani. A
  forgotten punch is not a technical fault, so no Ergani late‑declaration code applies.
- **«Τεχνικό πρόβλημα»:** only for a real fault (power cut, your systems down, Ergani
  down). Sent as a late declaration with code 001 / 002 / 003.

## Forgotten punch‑outs from earlier days

Every arrival without a departure in the last 62 days is listed with a «Κλείσιμο DD/MM…»
button, even if the person has punched in again since. For an earlier day you must enter
the actual time on that day (no "now" option), so a shift can never accidentally span
several days.

The monthly count of forgotten punches per employee («Ξεχασμένα χτυπήματα μήνα») turns
into a warning from 3.

## Cancelling leave, a day change or a note

The «Άδεια…», «Υπερωρία / αλλαγή ημέρας…» and «Έφυγε νωρίτερα…» windows list what's
already recorded underneath. **«Ακύρωση»** (cancel: leave, day changes) or **«Διαγραφή»**
(delete: early‑leave reason) removes it. Nothing is sent to Ergani; if you had declared it
there, change it in Ergani too.

## «Ειδοποιήσεις» (alerts)

Everything the live checks have flagged today: not punched in, still in after the end,
undeclared overtime, rest or weekly limits, Ergani errors, backups that stopped or
failed. **«Εντάξει»** (OK) next to each marks it done; **«Εκκαθάριση λίστας»** clears the
whole list. Ergani
rejections stay until you handle them.
See [Alerts and reminders](Alerts-and-Reminders-EN).

If phone alerts aren't configured, a note says so here (they're set up in «Ρυθμίσεις» →
«Ειδοποιήσεις στο κινητό»).

## «Οθόνη καταστήματος και αποστολή» (shop screen and sending)

- **«Υπενθυμίσεις στο κατάστημα»:** shop‑screen reminders on or off. (Festive
  decorations are under [«Ωράρια & αργίες»](Admin-Schedules-and-Holidays-EN#festive-decorations).)
- **«Ανανέωση οθόνης»:** make the shop screen reload itself. Only needed after an update
  made on the machine; after «Ενημέρωση τώρα» the screen reloads by itself.
- **«Λειτουργία: …» (mode):** one line with the current mode, using the same names as
  «Ρυθμίσεις». It's information only; the mode is changed in «Ρυθμίσεις» → «Επιχείρηση και
  σύνδεση με το ΕΡΓΑΝΗ» → «Λειτουργία» (see [Going live](Going-Live-EN)).

  | Line | Meaning |
  |---|---|
  | «Λειτουργία: **Δοκιμαστική** · τίποτα δεν στέλνεται στο ΕΡΓΑΝΗ» | Testing and staff practice; nothing is sent. |
  | «Λειτουργία: **Περίοδος προσαρμογής** · … η αποστολή ξεκινά [date]» | Onboarding period: the card is used as usual; sending starts by itself on that date. |
  | «Λειτουργία: **Κανονική λειτουργία** · οι κινήσεις στέλνονται στο ΕΡΓΑΝΗ» | Normal operation: every punch is a declaration to Ergani. |
  | «Λειτουργία: **Δοκιμαστικό ΕΡΓΑΝΗ** · …χωρίς ισχύ» | Advanced: sent to Ergani's test environment, no legal effect. |

  If anything is waiting or needs your check, the same line adds «σε αναμονή/επανάληψη: N»
  (pending/retrying) or «προς έλεγχο: N» (to check, see «Κινήσεις»). See
  [How punches reach Ergani](Ergani-Submissions-EN).
- **«Πώς τα πάνε»** (how it's going): during the onboarding period, a table of how each
  employee is punching (punches, days done correctly, corrections, days without punches).
  It stays visible for a month after the period ends.
