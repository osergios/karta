[Ελληνικά](Admin-Schedules-and-Holidays) · **English**

# Admin: «Ωράρια & αργίες» (Schedules and holidays)

![Admin, schedules](https://raw.githubusercontent.com/osergios/karta/main/docs/screenshots/admin-schedules.png)

## Shop hours («Ωράριο καταστήματος»)

Your opening hours per weekday. The editor shows what they mean for staff (hours,
breaks, weekly totals), «Από κατάστημα» can copy them into an employee's row, and on a
closed day the shop screen uses them to say when you reopen. Leave a day empty for
«κλειστά» (closed).

## Employee schedules

One row per employee, one box per weekday (Δευ … Κυρ). Type the **declared** schedule,
exactly as it's declared in Ergani. Leave a box empty for a day off («ρεπό»).

> **Where do I get each day's hours?** Ergani usually gives Karta only **how many hours a
> week** each employee works (and, less often, a schedule in free text), not the hours of
> each day. Type each day's hours from the **schedule your accountant gives you**, as they
> declared it. Under each employee, Karta shows whether the weekly total **matches** the
> Ergani hours («Ταιριάζει … ✓», or by how much it differs). When Ergani has a readable
> per‑day schedule, a button appears to fill it in automatically.

### How to write a schedule

| You write | Meaning |
|---|---|
| `10:00-18:00` | Works 10:00 to 18:00, no break. |
| `10:00-18:30/30` | 30′ break **inside** the hours ("όποτε βολεύει"). Paid time is 8h; leaves at 18:30. |
| `10:00-16:30/+30` | 30′ break **outside** the hours, as Ergani declares it. Paid time is the full 6.5h, and the break comes on top, so a punch‑out anywhere from 16:30 to 17:00 is on schedule. |
| `10:00-14:00+17:00-21:00` | Split shift (up to 3 parts). Each part gets its own reminders and alerts. |

The **−** / **+** buttons under each day change the break. «Διάλειμμα 30′ παντού» adds a
30′ break to every day longer than 4 hours (a break is due after 4 hours of work), and
«Από κατάστημα» copies the shop hours into the row for you to adjust. Nothing is stored
until you press «Αποθήκευση».

The editor warns you as you type, for example:

- weekly totals and **υπερεργασία / υπερωρία** against your contractual and legal week;
- days over the daily limit, or with less than the minimum rest before the next day;
- a break type that doesn't match what Ergani has on file.

The limits it checks against are in [Settings](Admin-Settings-EN) → «Όρια και
ειδοποιήσεις».

### Schedule history («Οι αλλαγές που αποθηκεύεις ισχύουν από»)

Every save is kept with a start date (default: today).

- Past days are always calculated with the schedule that applied **then**, in reports
  and in leave counts.
- You can save a **future** schedule in advance (e.g. from the 1st of next month).
  Reminders, alerts and the shop screen switch over automatically on that date, and the
  employee card shows «νέο ωράριο από 01/10 (μέχρι τότε ισχύει το προηγούμενο)».

### Importing from Ergani

«Ρυθμίσεις» → «ΕΡΓΑΝΗ» → «Ενημέρωση στοιχείων ωραρίου από ΕΡΓΑΝΗ» fetches what Ergani
has declared (schedule, weekly hours, break, flexible arrival) and shows it next to each
employee for comparison.

## «Αργίες και κλειστό κατάστημα» (holidays and closures)

| Type | How it works |
|---|---|
| **Public holidays** | The Greek public holidays are calculated every year, including the moveable ones from Orthodox Easter. Each has a «κλειστά» tick box. Μεγάλη Παρασκευή is open by default. |
| **Local holidays** | Holidays that repeat every year in your area, e.g. your town's patron saint. None are preset. |
| **Closures** | Any date range with a reason, e.g. «Ανακαίνιση». |

On a closed day:

- no reminders or "didn't punch in" alerts;
- the shop screen shows a greeting and «Σήμερα είμαστε κλειστά», and refuses arrivals
  (you get a phone alert if someone tries);
- reports write «Αργία: …» or «Κατάστημα κλειστό: …» instead of an absence, plus a list of
  holidays and closures that fell on working days and who they affected.

Nothing is sent to Ergani for these days; the accountant declares them there. If someone
does work on a closed day, declare it in Ergani, then add it with «Υπερωρία / αλλαγή
ημέρας…».

### Festive decorations

At the end of this section, «Εορταστική διακόσμηση στην οθόνη του καταστήματος» (festive
decorations on the shop screen) turns them on or off («Ενεργοποίηση» / «Απενεργοποίηση»).
They're on by default and appear by themselves: Christmas, Easter, 25 March and
28 October, Καθαρά Δευτέρα (Clean Monday), 1 May. When they're off, the screen always
keeps its normal look; the greetings on closed days still appear.

The preview buttons (Christmas, New Year, Clean Monday, 25 March, Easter, 1 May,
28 October, 15 August, «Κλείσιμο (π.χ. ανακαίνιση)» for a closure) open the shop screen in
a new tab, as it will look on that day. A preview records nothing.
