[Ελληνικά](Admin-Schedules-and-Holidays) · **English**

# Admin: «Ωράρια & αργίες» (Schedules and holidays)

![Admin, schedules](https://raw.githubusercontent.com/osergios/karta/main/docs/screenshots/admin-schedules.png)

## Shop hours («Ωράριο καταστήματος»)

The first card is your opening hours per weekday. You fill them in like an employee's
schedule ([below](#each-days-hours)), and a day with no hours is «κλειστά» (closed). The
editor shows what they mean for staff (hours per week, whether one person can cover them,
days longer than the limit), «Αντιγραφή από…» → «Ωράριο καταστήματος» copies them into an employee's card, and on a
closed day the shop screen uses them to say when you reopen. They're saved with their own
**«Αποθήκευση»** (save).

## Employee schedules

Below that, one card per active employee, with one row per weekday (Δευ … Κυρ). Fill in
the **declared** schedule, exactly as it's declared in Ergani. There's no special format
to type: just start and end times.

> **Where do I get each day's hours?** Ergani usually gives Karta only **how many hours a
> week** each employee works (and, less often, a schedule in free text), not the hours of
> each day. Fill in each day's hours from the **schedule your accountant gives you**, as
> they declared it. Under each employee, Karta shows whether the weekly total **matches**
> the Ergani hours («Ταιριάζει … ✓», or by how much it differs).

### Folded cards, search

All cards (the shop's too) are **folded**: one line each, with the name, since when the
schedule applies («ισχύει από 01/09/2026», or that a future one is saved), the week in one
line (e.g. «Δευ–Παρ 09:00–17:00 · διάλ. 30′ · 37ω 30λ/εβδ.») and **✓** or **⚠ N** (how many
remarks it has, e.g. a difference from Ergani). Press the line to open the card; press it
again to fold it. A card that was open stays open after «Αποθήκευση».

Above the cards:

- **«Αναζήτηση εργαζόμενου»** (search): by the name on the tablet or the full name (accents
  don't matter).
- **«Μόνο όσοι θέλουν προσοχή»** (only those that need attention): only the cards with ⚠.
  Next to it: how many are shown and how many need attention.
- **«Κλείσιμο όλων»** (fold all).

### Inside the card

- **«Αντιγραφή από…»** (copy from): «Ωράριο καταστήματος» (the shop hours) or a colleague.
  From a colleague you get the hours **and** the break; not the flexible arrival (it's a
  personal agreement). Adjust and press «Αποθήκευση».
- **«Αποθήκευση»** (save): saves, valid from the «Οι αλλαγές που αποθηκεύεις ισχύουν από»
  date at the top ([below](#schedule-history-οι-αλλαγές-που-αποθηκεύεις-ισχύουν-από)). It
  asks you to confirm, with the date. If nothing changed it says «Καμία αλλαγή» (no
  change); if a day's hours aren't valid it doesn't save and names the day (e.g. «Μαρία,
  Τρίτη: οι ώρες δεν είναι σωστές», Maria, Tuesday: the hours aren't right).

Nothing is stored until you press «Αποθήκευση».

### Each day's hours

- Each day has a **start** and an **end** field. Type the time any way you like: «10»,
  «1000» or «10.00» becomes 10:00 when you leave the field (and «930» becomes 09:30).
- **«✕»** removes the hours: the day becomes a **day off** («ρεπό»; for the shop,
  «κλειστά», closed). On a split shift it removes only that part.
- **«+ σπαστό»** (+ split) adds a second part to the same day, e.g. 10:00–14:00 and
  17:00–21:00: a **split shift**, with 4 punches (in and out for each part). Up to 3 parts
  a day; each part gets its own reminders and alerts.
- **«+ ώρες»** (+ hours) on a day off puts hours back, starting from the nearest earlier
  working day (e.g. Tuesday like Monday); change them if needed.
- On the right of each row you see the day's **net hours**. A row with a problem turns
  orange or red, and the explanation appears under the card.

### Break («Διάλειμμα»)

Each employee has **one break for the whole week**:

- **«Διάλειμμα»:** «Χωρίς» (none), 15′, 20′, 30′, 45′ or 60′.
- **«μέσα στις ώρες»** (inside the hours) or **«εκτός ωραρίου (μετά τη λήξη)»** (outside
  the hours, after the end), as declared in Ergani.

It's applied automatically to every day with **more than 4 hours of continuous work** (a
break is due after 4 hours of work). On a split shift, it's applied only if one part is
longer than 4 hours. Neither kind **needs a card punch**:

| Kind | Meaning |
|---|---|
| **μέσα στις ώρες** (inside) | The break is taken whenever convenient, within the hours. E.g. 10:00–18:30 with 30′: paid time is 8h; leaves at 18:30. |
| **εκτός ωραρίου** (outside) | The break comes on top of the declared hours: all the hours are paid, and the departure may be up to that many minutes after the end. E.g. end 17:00 with 20′: leave by 17:20. |

A break where the person **leaves the shop and punches out and back in** isn't a break as
far as Karta is concerned: enter the day as a split shift («+ σπαστό»).

### Flexible arrival («Ευέλικτη προσέλευση»)

The **«Ευέλικτη προσέλευση»** choice («Όχι», no, or «έως 15′ αργότερα» … «έως 120′
αργότερα», up to N′ later) is the flexible arrival window, as shown in the employee's
«Ψηφιακή Οργάνωση Χρόνου Εργασίας» in Ergani. Set it **only with a written agreement
declared in Ergani**. It applies **immediately** when you press «Αποθήκευση» (not from the
«ισχύουν από» date).

Greek law lets an employee start up to a declared number of minutes after their scheduled
start (ν. 5239/2025, ΠΔ 80/2022 άρθρο 580 παρ. 2Α). With a window set:

- Arriving inside the window shifts the whole day by the same amount: punch‑out
  reminders, alerts, the overtime deadline and «φεύγει έως» follow the actual arrival.
- Arriving later than the window shifts the day by the full window only. The rest counts
  as lateness.
- Punch‑in reminders and the "didn't punch in" alert still count from the declared start.
- Arriving **before** the declared start is still refused.
- The employee's row on «Σήμερα» shows it. E.g. with 10:00–17:00 and a 30′ window:
  «ευέλικτη προσέλευση έως 10:30» while you're waiting for them, and if they arrive at
  10:12, «ευέλικτη +12′ (κανονικά έως 17:00)».
- In the report, such a day counts as on schedule, with a note like «Ευέλικτη προσέλευση:
  11:05 (+0:35 από τις 10:30) → λήξη 17:25».

With «Όχι» (the default), nothing changes.

### «Χρήση στοιχείων ΕΡΓΑΝΗ» (use Ergani details)

Above the choices, the card shows what Ergani has declared for the employee («ΕΡΓΑΝΗ: 40
ώρες/εβδ. · 5ήμερο · πλήρης · διάλειμμα 30′ εκτός ωραρίου …»). If Ergani has a schedule
in text that couldn't be read automatically, it shows that too, for you to enter by hand.

The **«Χρήση στοιχείων ΕΡΓΑΝΗ»** button fills in what Karta read from Ergani:

- each day's **hours**, when the Ergani schedule was readable;
- the **break minutes and kind**;
- the **flexible arrival**.

Check them and press «Αποθήκευση».

### What the editor checks

Under each card, the editor explains what the schedule means as you fill it in, and warns
you, for example about:

- weekly totals and **υπερεργασία / υπερωρία** against your contractual and legal week;
- days over the daily limit, or with less than the minimum rest before the next day;
- days with more than 4 hours in a row without a break (at least 15′ is needed), or a
  break over 30′ (for a longer gap, use a split shift);
- weekly hours, a break (minutes or kind) or a flexible arrival that **differ from
  Ergani**.

The limits it checks against are in [Settings](Admin-Settings-EN) → «Όρια και
ειδοποιήσεις».

### Schedule history («Οι αλλαγές που αποθηκεύεις ισχύουν από»)

Every save is kept with a start date (default: today).

- Past days are always calculated with the schedule that applied **then**, in reports
  and in leave counts.
- You can save a **future** schedule in advance (e.g. from the 1st of next month).
  Reminders, alerts and the shop screen switch over automatically on that date, and the
  employee's schedule card shows «νέο ωράριο από 01/10 (μέχρι τότε ισχύει το
  προηγούμενο)» (new schedule from 01/10, until then the previous one applies).
- The break is part of the schedule and follows the same date. Flexible arrival doesn't:
  it applies as soon as you save.

### Importing from Ergani

«Ρυθμίσεις» → «ΕΡΓΑΝΗ» → «Ενημέρωση στοιχείων ωραρίου από ΕΡΓΑΝΗ» fetches what Ergani
has declared (schedule, weekly hours, break, flexible arrival) and shows it next to each
employee for comparison. This is what «Χρήση στοιχείων ΕΡΓΑΝΗ» fills in.

## «Αργίες και κλειστό κατάστημα» (holidays and closures)

| Type | How it works |
|---|---|
| **Public holidays** | The Greek public holidays of the next 12 months, calculated every year including the moveable ones from Orthodox Easter. Each has a «κλειστά» tick box. Μεγάλη Παρασκευή is open by default. |
| **Local holidays** | Holidays that repeat every year in your area, e.g. your town's patron saint. Type **DD/MM** (e.g. 15/05) and a name, then press **«Προσθήκη»** (add); **«Αφαίρεση»** (remove) deletes it. None are preset. |
| **Closures** | Any date range with a reason, e.g. «Ανακαίνιση». |

On a closed day:

- no reminders or "didn't punch in" alerts;
- the shop screen shows a greeting and «Σήμερα είμαστε κλειστά», and refuses arrivals
  (you get a phone alert if someone tries);
- reports write «Αργία: …» or «Κατάστημα κλειστό: …» instead of an absence, plus a list of
  holidays and closures that fell on working days and who they affected.

**A holiday that was moved** (e.g. 1 May, when it falls near Easter): untick the original
date and add the new one under «Κλείσιμο καταστήματος» (shop closure).

Nothing is sent to Ergani for these days; the accountant declares them there. If someone
does work on a closed day, declare it in Ergani, then add it with «Υπερωρία / αλλαγή
ημέρας…» (on «Σήμερα», the employee's «Ενέργειες ▾»; see
[Overtime or a one‑day change](Admin-Today-EN#overtime-or-a-oneday-change)).

### Festive decorations

At the end of this section, «Εορταστική διακόσμηση στην οθόνη του καταστήματος» (festive
decorations on the shop screen) turns them on or off («Ενεργοποίηση» / «Απενεργοποίηση»).
They're on by default and appear by themselves: Christmas (1/12–6/1: snow, trees, Santa),
Easter (from Palm Sunday: eggs, a candle, flowers), 25 March and 28 October (flags),
Καθαρά Δευτέρα (Clean Monday: kites), 1 May (a wreath). When they're off, the screen always
keeps its normal look; the greetings on closed days still appear.

The preview buttons (Christmas, New Year, Clean Monday, 25 March, Easter, 1 May,
28 October, 15 August, «Κλείσιμο (π.χ. ανακαίνιση)» for a closure) open the shop screen in
a new tab, as it will look on that day. A preview records nothing.
