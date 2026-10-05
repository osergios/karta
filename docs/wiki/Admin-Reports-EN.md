[Ελληνικά](Admin-Reports) · **English**

# Admin: «Αναφορές» (Reports)

Excel reports for the accountant, ready to print (landscape, fit to width).

- **«Μηνιαία αναφορά»:** pick a month.
- **«Ετήσια αναφορά»:** pick a year. It has the same sheets for the whole year, plus a
  per‑month sheet.

Reports use the **official names and ΑΦΜ as in Ergani**, never the shop‑screen display
names. The employer line comes from the data saved at «Έλεγχος ΕΡΓΑΝΗ». A report made
outside `production` mode is marked «ΔΟΚΙΜΑΣΤΙΚΑ ΔΕΔΟΜΕΝΑ».

## Sheets

### «Σύνοψη» (summary)

One row per employee with:

«Ημέρες εργασίας», «Ώρες ωραρίου», «Ώρες εργασίας», «Δηλωμένες επιπλέον ώρες
(υπερωρία)», «Επιπλέον ώρες χωρίς δήλωση» (highlighted), «Λιγότερες ώρες», leave days by
type (normal / sick / special purpose, working days only), «Αργίες / κλειστό» and
«Ξεχασμένα χτυπήματα».

Below that is each employee's leave for the period: from–to, working days and type. Then
come the holidays and closures that fell on working days, and who they affected.

### «Απολογιστικές δηλώσεις» (retrospective declarations)

Every day where the punches **don't match the declared schedule to the minute**. The
ministry allows no tolerance. For each day it shows:

- the hours to declare afterwards in Ergani;
- any time beyond them (υπερεργασία / υπερωρία → Ε8);
- what happened;
- the **deadline** (end of the following month).

It follows the ministry's own example: declared 09:00–17:00, punched 08:13–16:19 →
declare 08:13–16:13.

These days are **not** listed:

- a flexible‑arrival day inside its window;
- a punch‑out inside a break «εκτός ωραρίου»;
- a punch‑out up to 10′ after the limit, which counts as *preparation time* (changing
  clothes etc.) under εγκύκλιος 26606/13‑10‑2025 §3; from the 11th minute it's all extra
  work;
- onboarding‑period days.

### «Αναλυτικά» (detail)

**One sheet for all employees** (filterable), with a row per arrival–departure pair:

- the exact punch times;
- the **Ergani protocol numbers** («μόνο στην κάρτα» or «σε αναμονή» when not in Ergani);
- the declared schedule for that day and the hours worked;
- «Παρατηρήσεις» (remarks): forgotten punch‑out, not yet in Ergani, absence, early
  departure and its reason, late declaration (with the Ergani code and text), flexible
  arrival, and so on.

There's a subtotal per employee.

### «Ανά μήνα» (yearly report only)

Each employee month by month, with a yearly total. Months with 3 or more forgotten
punches are highlighted.

## How hours are counted

- **Exact to the minute** (seconds ignored, as in Ergani). Any difference shows, e.g.
  «Λιγότερες ώρες −0:01».
- A day is «όπως το ωράριο» (on schedule) only when every punch is inside the declared
  hours, allowing for the flexible‑arrival shift, the break «εκτός ωραρίου» window and the
  10′ preparation time.
- **Declared overtime** («Υπερωρία / αλλαγή ημέρας…») is counted separately from
  **extra hours without declaration**.
- Work on a day without declared hours counts as extra.
- Reports count from **go‑live** (the first real punch in the current mode), so test days
  before it don't appear as absences.
- Past days always use the schedule that was valid on that day (see
  [Schedules](Admin-Schedules-and-Holidays-EN)).
