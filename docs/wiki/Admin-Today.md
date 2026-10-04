# Admin: «Σήμερα» (Today)

The first tab of the admin page (`/admin`). It shows what's happening right now and
anything that needs your attention. It refreshes itself every 30 seconds without wiping
anything you're typing, and pauses while the page is in the background.

![Admin, today](https://raw.githubusercontent.com/osergios/karta/main/docs/screenshots/admin-today.png)

On a computer the tabs are along the top; on a phone they're an icon bar at the bottom.
The page reopens on the last tab you used. The alert count shows in the header.

## Who is where

| Section | Who's in it |
|---|---|
| «Μέσα τώρα» | Punched in and not out yet. Each card shows today's schedule, **«φεύγει έως»** (when they must leave) and **«υπερωρία δηλώνεται έως»** (the last moment to declare overtime in Ergani). |
| «Έρχονται σήμερα» | Scheduled today but not in yet. |
| «Έφυγαν νωρίτερα» | Punched out before the end of their day. Use «Λόγος…» to record why. |
| «Εκτός σήμερα» | Day off («ρεπό»), leave, holiday or closure. |

Each person has the same **«Ενέργειες ▾»** menu as on the [Staff](Admin-Staff) tab.

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
undeclared overtime, rest or weekly limits, Ergani errors. Mark each one done, or clear
the whole list with «Εκκαθάριση λίστας». Ergani rejections stay until you handle them.
See [Alerts and reminders](Alerts-and-Reminders).

If phone alerts aren't configured, a note says so here («συμπλήρωσε NTFY_URL / NTFY_TOPIC
στο .env»).

## «Οθόνη καταστήματος και αποστολή» (shop screen and sending)

- **«Υπενθυμίσεις στο κατάστημα»:** shop‑screen reminders on or off.
- **Festive decorations** on or off, with «Προεπισκόπηση» buttons for each holiday.
- **«Λειτουργία εκπαίδευσης»:** training mode (see [Going live](Going-Live)).
- **Onboarding period** («Υποχρεωτική από … → Έναρξη»), see [Going live](Going-Live).
- **«Ανανέωση οθόνης»:** make the shop screen reload itself (e.g. after an update).
- The state of the sending queue: anything pending, failed or waiting for your check.
  See [How punches reach Ergani](Ergani-Submissions).
