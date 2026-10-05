[Ελληνικά](Admin-Today) · **English**

# Admin: «Σήμερα» (Today)

The first tab of the admin page (`/admin`). It shows what's happening right now and
anything that needs your attention. It refreshes itself every 30 seconds without wiping
anything you're typing, and pauses while the page is in the background.

![Admin, today](https://raw.githubusercontent.com/osergios/karta/main/docs/screenshots/admin-today.png)

On a computer the tabs are along the top; on a phone they're an icon bar at the bottom.
The page reopens on the last tab you used. The alert count shows in the header (**«⚠ N»**);
click it to jump to «Ειδοποιήσεις» (alerts). Next to it, the header shows the current mode,
the branch number and your account.

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

| Section | Who's in it |
|---|---|
| «Ξέχασαν αποχώρηση» | Anyone with an arrival from an earlier day and no departure, with a «Κλείσιμο DD/MM…» button (see below). Only shown when there's someone. |
| «Μέσα τώρα» | Punched in and not out yet. Each card shows today's schedule, **«φεύγει έως»** (when they must leave) and, with advance declaration, **«υπερωρία δηλώνεται έως»** (the last moment to declare overtime in Ergani; there's none with the retrospective system, see [Settings](Admin-Settings-EN)). |
| «Έρχονται σήμερα» | Scheduled today but not in yet (with «θα αργήσει (σίγαση)», will be late, if you set it). |
| «Έφυγαν νωρίτερα» | Punched out before the end of their day. Use «Λόγος…» to record why. |
| «Τελείωσαν» | Finished today's day and left. |
| «Εκτός σήμερα» | Day off («ρεπό»), leave, holiday or closure. |

Each person has the same **«Ενέργειες ▾»** menu as on the [Staff](Admin-Staff-EN) tab.

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
