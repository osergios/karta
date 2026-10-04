🇬🇷 [Ελληνικά](Going-Live) · 🇬🇧 **English**

# Going live

Karta has three **modes** (`ERGANI_MODE` in `.env`) and two **practice features** on the
admin page. Use them in this order, so you never send a wrong declaration to Ergani.

## The three modes

| Mode | What happens to punches | Use it for |
|---|---|---|
| `dry_run` | **Nothing is sent.** Karta stores the exact payload it *would* send, so you can inspect it («Τι θα στελνόταν»). | First setup; checking schedules, PINs and the shop screen. |
| `trial` | Sent to the **Ergani test environment** (`trialv2eservices.yeka.gr`). Submissions there are stamped «ΑΚΥΡΟ» and have no legal effect. | Checking that sending really works with your credentials. |
| `production` | Sent to the **real Ergani**. | Normal use. |

The header of the admin page always shows the current mode, and the shop screen shows a
small «Δοκιμαστική λειτουργία» label when not in production.

**Each mode is its own world.** Punches made in one mode never count in another:
who's in or out, alerts, rest checks and reports only look at the current mode. A test
arrival in `dry_run` can never turn your first real punch into a departure. Reports only
count from the first real punch of the current mode, so test days before it don't show
as absences. A report made outside production is titled «Σύνοψη (ΔΟΚΙΜΗ)».

When you've finished testing, «Ρυθμίσεις» → «Κινήσεις» → **«Διαγραφή δοκιμαστικών
κινήσεων»** removes the test punches.

## Recommended path

1. **`dry_run`.** Import staff, set schedules, register the shop screen, and let everyone
   try punching. Check the stored payloads on the admin page.
2. **`trial`.** Set `ERGANI_TRIAL_*` in `.env`, switch the mode and restart. Make a few
   punches and confirm they appear in the Ergani test environment.
3. **`production`.** Switch the mode and restart. From now on every punch is a legal
   declaration.

## Training mode («Λειτουργία εκπαίδευσης»)

For showing staff how the shop screen works. Turn it on from «Σήμερα» → «Οθόνη
καταστήματος και αποστολή».

- The shop screen behaves exactly as usual (arrival → departure, PIN and QR), but
  **nothing is stored, sent or counted**. Practice state lives in memory only.
- A red «ΕΚΠΑΙΔΕΥΣΗ» banner and a red frame make it obvious, and the confirm and result
  screens carry a warning.
- It switches itself off after 60 minutes, or with «Τέλος εκπαίδευσης».
- While it's on, real punches can't be made. When you turn it on, Karta warns you who is
  really at work at that moment.

## Onboarding period («Περίοδος προσαρμογής»)

For a business that has time before the digital card becomes mandatory for it. Start it
from «Σήμερα» → «Οθόνη καταστήματος και αποστολή» → «Υποχρεωτική από [date]» → «Έναρξη».

Until that date:

- Staff use the card **exactly as in real life**. Punches are recorded with the status
  «Προσαρμογή (δεν στάλθηκε)», and reminders, phone alerts, corrections and reports all
  work.
- **Nothing is sent to Ergani.**
- The shop screen looks exactly as normal (no banner, no "test" wording), so nobody
  takes it less seriously. After a punch, only a faint «✓ καταγράφηκε» line appears for a
  few seconds.
- A «Πώς τα πάνε» table shows, per employee: punches (and how many by QR), days done
  correctly, corrections you had to make, and days without punches.

On the mandatory date, sending starts by itself. You can end it earlier with «Τέλος
τώρα», or move the date with «Αλλαγή». A departure always follows its arrival: a shift
that started during the period is closed in Karta only, so Ergani never receives a
departure without its arrival.

You'll get a notice on the last day of the period and on the first mandatory day. That
notice is urgent if `ERGANI_MODE` is still not `production`.
