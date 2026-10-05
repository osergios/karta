[Ελληνικά](Going-Live) · **English**

# Going live

Karta has three **modes**, changed in «Ρυθμίσεις» (settings). Use them in this order, so
you never send a wrong declaration to Ergani.

## The three modes

| Mode | What happens to punches | Use it for |
|---|---|---|
| «Δοκιμαστική» (`dry_run`) | **Nothing is sent.** Karta stores the exact payload it *would* send, so you can inspect it («Τι θα στελνόταν»). | First setup, testing, training; checking schedules, PINs and the shop screen. |
| «Περίοδος προσαρμογής» (onboarding period, `production` with a date) | Recorded as usual, but **not sent** until the mandatory day; from then on they're sent by themselves. | While the card isn't mandatory for the business yet. |
| «Κανονική λειτουργία» (normal operation, `production`) | Sent to the **real Ergani**. | Normal use. |

For the advanced there's also the **Ergani test environment** (`trial`): punches are sent to
Ergani's test environment (`trialv2eservices.yeka.gr`), where they're stamped «ΑΚΥΡΟ» and
have no legal effect.

The current mode always shows with the same name in three places: the admin page
header, the **«Λειτουργία: …»** (mode) line in «Σήμερα» → «Οθόνη καταστήματος και
αποστολή», and «Ρυθμίσεις» («· τώρα»). The shop screen shows a small «Δοκιμαστική
λειτουργία» (or «Περιβάλλον δοκιμών ΕΡΓΑΝΗ») label only in «Δοκιμαστική» and the Ergani
test environment; during the onboarding period and in normal operation it shows nothing.

**Each mode is its own world.** Punches made in one mode never count in another:
who's in or out, alerts, rest checks and reports only look at the current mode. A test
arrival in `dry_run` can never turn your first real punch into a departure. Reports only
count from the first real punch of the current mode, so test days before it don't show
as absences. A report made outside production has «… — ΔΟΚΙΜΑΣΤΙΚΑ ΔΕΔΟΜΕΝΑ» (test data)
in its title.

When you've finished testing, «Ρυθμίσεις» → «Κινήσεις» → **«Διαγραφή δοκιμαστικών
κινήσεων»** removes the test punches.

## Recommended path

Everything happens in one place: **«Ρυθμίσεις» → «Επιχείρηση και σύνδεση με το ΕΡΓΑΝΗ» →
«Λειτουργία»** (mode), with no restart. The current mode is marked «· τώρα» (now).

1. **«Δοκιμαστική»** (test, `dry_run`): for testing and training. Import staff, set
   schedules, register the shop screen, and let everyone try punching. Nothing is sent to
   Ergani. See [A trial run with the staff](#a-trial-run-with-the-staff).
2. **«Περίοδος προσαρμογής»** (onboarding period): if the card isn't mandatory for the
   business yet. Pick the **«Υποχρεωτική από»** (mandatory from) date and press
   **«Έναρξη»** (start). Staff use the card as usual, but nothing is sent until that day;
   then sending starts by itself. See [below](#onboarding-period-περίοδος-προσαρμογής).
3. **«Κανονική λειτουργία»** (normal operation, `production`): every punch is a legal
   declaration to Ergani.

### How to change the mode

- For the onboarding period or normal operation from «Δοκιμαστική», you're asked to type
  **the business's ΑΦΜ** (tax number) to confirm, and Karta **tests the connection** to
  Ergani first. If it fails, nothing changes.
- During the onboarding period, **«Αλλαγή ημερομηνίας»** (change date) moves the mandatory
  day, and **«Τέλος περιόδου τώρα»** (end the period now, right below it) switches to normal
  operation and starts sending right away.
- Going back to «Δοκιμαστική» just needs an «ΟΚ» (and ends an onboarding period).
- Every change is logged (who, when, from what to what).

**For the advanced: the Ergani test environment** (`trial`). At the end of the section, it sends
punches to Ergani's test environment, with no legal effect, to try the connection before
normal operation. Fill in the **«Χρήστης για το δοκιμαστικό ΕΡΓΑΝΗ»** (user for the Ergani
test environment; if empty, the normal user is used). It isn't a required step.

If something the mode needs is missing (e.g. the Ergani password), the page says so in
red, and punches **wait** without being lost until you fill it in. The mode can also be set
in `.env` (`ERGANI_MODE`); whatever is chosen on the admin page takes priority.

## A trial run with the staff

Staff practise in **«Δοκιμαστική»**, before the onboarding period or normal operation.
(The old separate training mode, «Λειτουργία εκπαίδευσης», was removed in version 1.7.0.)

- The shop screen works exactly as always: arrival → departure, by PIN or QR, reminders
  with sound. Every punch is recorded in Karta but **not sent to Ergani**; the screen says
  «Δοκιμαστική λειτουργία: δεν στάλθηκε στο ΕΡΓΑΝΗ».
- In «Πρώτα βήματα» (first steps), «Δοκιμή με το προσωπικό» (trial run with the staff)
  ticks itself off with the first test punch.
- Afterwards: «Ρυθμίσεις» → «Κινήσεις» → **«Διαγραφή δοκιμαστικών κινήσεων»** (delete test
  punches), and change the mode in «Ρυθμίσεις».

## Onboarding period («Περίοδος προσαρμογής»)

For a business that has time before the digital card becomes mandatory for it. Start it
from «Λειτουργία» → «Περίοδος προσαρμογής» → «Υποχρεωτική από [date]» → «Έναρξη» (it's
part of normal operation: punches made in «Δοκιμαστική» don't count, and «Διαγραφή
δοκιμαστικών κινήσεων» removes them). The header says «Περίοδος προσαρμογής», and
«Σήμερα» (today) shows one line: «Λειτουργία: Περίοδος προσαρμογής · τίποτα δεν
στέλνεται στο ΕΡΓΑΝΗ· η αποστολή ξεκινά [date]» (nothing is sent to Ergani; sending
starts on [date]).

Until that date:

- Staff use the card **exactly as in real life**. Punches are recorded with the status
  «Προσαρμογή (δεν στάλθηκε)», and reminders, phone alerts, corrections and reports all
  work.
- **Nothing is sent to Ergani.**
- The shop screen looks exactly as normal (no banner, no "test" wording), so nobody
  takes it less seriously. After a punch, only a faint «✓ καταγράφηκε» line appears for a
  few seconds.
- A **«Πώς τα πάνε»** (how it's going) table on «Σήμερα» shows, per employee, from the
  start of the period up to yesterday: punches (and how many by QR), days done correctly,
  corrections you had to make, and days without punches. It stays visible (as «Πώς τα
  πήγαν στην περίοδο προσαρμογής») for a month after the period ends.

On the mandatory date, sending starts by itself. You can end it earlier with «Τέλος
περιόδου τώρα», or move the date with «Αλλαγή ημερομηνίας». A departure always follows its arrival: a shift
that started during the period is closed in Karta only, so Ergani never receives a
departure without its arrival.

You'll get a notice on the last day of the period and on the first mandatory day. That
notice is urgent if the mode is still not `production`.
