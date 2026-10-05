# Changes (review fixes 1–7)

1. **Forgotten departures can always be closed.** The admin page lists every arrival without a departure
   (last 62 days) with a «Κλείσιμο DD/MM…» button, even after the person has clocked in again.
   `POST /admin/api/employees/{id}/depart` takes an optional `arrival_id`; the time must fall after that
   arrival and before the next one.
2. **No accidental multi-day shifts.** Closing an arrival from an earlier day requires the actual time on
   that day (the "Τώρα" option is hidden; the server rejects it too).
3. **Each ERGANI_MODE is its own world.** State (in/out), alerts, rest checks and the monthly report only
   count movements of the current mode, so a dry-run/trial arrival can't turn the first real punch into a
   DEPARTURE. A non-production report is labelled «Σύνοψη (ΔΟΚΙΜΗ)».
4. **Atomic punches.** State check, debounce and insert run in one write transaction.
5. **No duplicate submissions after a timeout.** If the submit request may have reached Ergani (read timeout,
   dropped connection mid-response, HTTP 504), the movement becomes `uncertain`: it is not retried
   automatically, an urgent alert is raised, and the admin chooses «Υπάρχει στο ΕΡΓΑΝΗ» (optionally with the
   protocol number) or «Δεν υπάρχει — νέα αποστολή» (`POST /admin/api/movements/{id}/uncertain`).
   Login failures and connection errors before sending are retried as before.
6. **Report sheet names** are sanitised (`[]:*?/\`, quotes, length) and de-duplicated.
7. **Phone alerts (ntfy)** are sent on a background thread and never delay a punch.

# Fixes from the end-to-end test pass (dry_run + trial against a simulated Ergani)

8. **Unreadable Ergani answer = «Προς έλεγχο», not a retry.** If Ergani answered the submission but the
   answer could not be read (HTML page with 200, unexpected fields or date format), the movement was retried
   automatically and the card was stored twice. Such failures now count as "may have been delivered" and go
   to `uncertain` like a read timeout.
9. **«Προς έλεγχο» alerts close when you decide.** «Δεν υπάρχει — νέα αποστολή» now also closes the urgent
   alert (before, it stayed open after a successful resend). Each uncertain attempt has its own alert, so a
   resend that times out again the same day alerts again instead of being silently swallowed.
10. **Error text keeps the HTTP status.** Ergani errors without a message (e.g. an HTML 504 page) were
    shown as `APIError: Error message:` and the alert quoted «». They now read `APIError (HTTP 504) …`.
11. **Report:** today's running shift is shown as «Σε βάρδια» and is not counted in «Ημέρες χωρίς
    αποχώρηση». Also removes a Python `SyntaxWarning` (invalid escape in a docstring of report.py).
12. **Report:** late declarations show the Ergani code and Greek text (e.g. «Εκπρόθεσμη 18:00: 001 Διακοπή
    ρεύματος») instead of the internal English name (`POWER_OUTAGE`).
13. **Temporary DNS failures are retried, not «Προς έλεγχο».** "Temporary failure in name resolution" was not
    recognised as "never sent", so a DNS hiccup made the card wait for a manual check. The cause of the
    connection error is now checked (urllib3 `NewConnectionError`, incl. `NameResolutionError`).

# Reminders, leave, flexibility (29/09)

14. **Shop-screen punch reminders.** From the scheduled start (not yet punched in) and from the scheduled end (still
    in) the kiosk shows a coloured card per person, plays a «ding-dong» and shows a Windows notification — every 30″ until the person punches. Split shifts: per part.
    Tapping the card opens that person's PIN pad. On/off from the admin page («Υπενθυμίσεις στο κατάστημα»).
    A «Πάτα εδώ για να ενεργοποιηθεί ο ήχος» button appears if the browser blocked sound after boot.
15. **Leave.** «Άδεια…» per employee: from/to dates (inclusive), note, cancel. On leave: no reminders, no
    «δεν χτύπησε» alerts, report shows «Άδεια» with 0 scheduled hours. A punch during leave alerts you.
    Nothing is sent to Ergani (the accountant declares leave there).
16. **Flexibility 10′ (phone).** «Ευελιξία» (was «Ανοχή», default 10′): not punched in 10′ after the start of a
    scheduled part → phone alert «δεν έχει χτυπήσει προσέλευση»; still in 10′ after the end → phone alert.
    The shop screen no longer shows the old one-off «η βάρδια έληξε» banners (the repeating reminder replaces them).
17. **One sound for everything:** every alert and reminder on the shop screen is a doorbell «ding-dong» (no voice).
    The QR scan keeps its short beep.
18. **Ergani's own employee QR works at the kiosk.** The same camera scanner (no extra button) accepts both the
    shop's QR card and the personal QR from Ergani / myErgani («erg|nm:…;ln:…;afm:…;id:…»). It is matched on
    ΑΦΜ + surname (accents ignored); with `ERGANI_EMPLOYER_ID` set in .env, a QR from another employer is refused.
    Punches show «QR ΕΡΓΑΝΗ» in the movements list. Note: Ergani's QR has no secret — a copy works like the original.
19. **«Παύση αποστολής» → «Λειτουργία εκπαίδευσης».** For showing staff how it works: the kiosk behaves as usual
    (arrival → departure, PIN and QR), but nothing is stored, sent or counted — practice state lives in memory only.
    Red «ΕΚΠΑΙΔΕΥΣΗ» banner + red frame on the shop screen, a warning on the confirm screen and on the result.
    Switches itself off after 60′ (or «Τέλος εκπαίδευσης»). Turning it on warns you who is really at work now,
    because their real punches can't be made while it is on. The old hold-and-send-later is gone: if it was left on,
    the punches it held are released for sending at startup.
20. **Forgotten punches are never declared late.** A forgotten punch is not a technical fault, so no Ergani code applies.
    «Αποχώρηση…» / «Κλείσιμο …» now offers: «Φεύγει τώρα» (sent in real time) · «Ξέχασε να χτυπήσει» (closes the shift
    **in karta only**, note required, status «Μόνο στην κάρτα», never sent) · «Τεχνικό πρόβλημα» (late declaration with
    001/002/003, only for a real fault). New «Ξεχασμένη βάρδια…» enters a whole unpunched shift in karta only (report/pay).
    Each employee shows «Ξεχασμένα χτυπήματα μήνα» (warning from 3). The monthly report marks these punches and counts
    them in the summary. Movements carry the admin note.
21. **Kiosk guard: no arrival at going-home time.** If someone hasn't punched in for the part of today's schedule that is
    ending (last hour) or over, the kiosk asks first: «Φεύγω — ενημέρωσε τη διαχείριση» (records nothing, sends nothing,
    phone alert to you, the reminder stops) or «Έρχομαι τώρα» (normal arrival). A forgotten punch-out from a previous day
    still gives «Προσέλευση» the next working day, with the note to tell the management.
22. **Hidden from search engines and crawlers.** `/robots.txt` → `Disallow: /` for everyone, and every response carries
    `X-Robots-Tag: noindex, nofollow, noarchive, nosnippet, noimageindex, notranslate` (pages, API, static files).
23. **Kiosk «Αύρα».** Soft teal/white light drifting very slowly behind the side panel (CSS transform only; off with
    Windows «reduce animations»).
24. **New monthly report for the accountant.** Official names (ΕΠΩΝΥΜΟ ΟΝΟΜΑ as in Ergani, never the kiosk names) and
    ΑΦΜ; employer line (name saved at «Έλεγχος ΕΡΓΑΝΗ»). «Σύνοψη»: per employee days, scheduled hours, worked hours,
    extra/less hours, leave days, forgotten punches, open issues. «Προς ενέργεια»: one line per issue with what to do
    (extra hours → pay + was it declared beforehand, work outside the declared hours, work without schedule, days without
    punches, open arrivals, forgotten punches, not yet in Ergani, late declarations). «Αναλυτικά»: ONE sheet for all
    employees (filterable), a row per arrival–departure pair with the exact punch times and the Ergani protocol numbers
    («μόνο στην κάρτα» / «σε αναμονή» when not in Ergani), declared schedule, hours (rounded to the quarter; deviations
    under 15′ count as on schedule) and notes, with a subtotal per employee. Print-ready (landscape, fit to width).
25. **Leave of the month per employee** on the «Σύνοψη» sheet: each leave (from–to, clipped to the month), its
    working days (days with a declared schedule; a leave over a day off doesn't count) and type/note, with a total per
    employee. «Ημέρες άδειας (εργάσιμες)» in the summary counts working days only.
26. **No punch-in before the declared start.** At the kiosk, an arrival earlier than the start of the next part of
    today's schedule is refused («Είναι νωρίς: το ωράριό σου ξεκινά στις 10:30») — also enforced on the server — and you
    get a phone alert (once a day per person). «Όρια» → «Προσέλευση πριν το ωράριο (λεπτά)», default 0 (Ergani has no
    tolerance). Admin «Νωρίτερη προσέλευση σήμερα» lets today's early arrival through — use it only after declaring the
    earlier start in Ergani. Training mode ignores the rule.
27. **Yearly report.** Admin «Αναφορές» → «Ετήσια αναφορά» (year field): the same sheets for the whole year
    (Σύνοψη with the leave of the year, Προς ενέργεια, Αναλυτικά) plus «Ανά μήνα»: each employee month by month with a
    yearly total (forgotten punches ≥3 in a month highlighted). `/admin/api/report-year.xlsx?year=YYYY`.
28. **Schedule history.** Each schedule save is kept with «Οι αλλαγές ισχύουν από» (default today): past days are
    always computed with the schedule that was in force then (reports, leave working days), and a future schedule can
    be saved in advance (e.g. from 01/10) — reminders, alerts and the kiosk switch automatically on that date. The
    card shows «νέο ωράριο από 01/10 (μέχρι τότε ισχύει το προηγούμενο)». Existing schedules become the baseline.
29. **Reports count from go-live** (the first real movement of the current mode): test days before it are not shown
    as absences.
30. **Punctual shop reminders.** The server tells the shop screen when the next reminder moment is, so it wakes up
    exactly then: punch-in reminder at the exact start, then every 30″ until they punch; before a punch-out, a
    countdown card «Σε λίγο αποχώρηση — σε 2′ / σε 1′ (16:30)» with a ding-dong at 2′ and at 1′, then at the exact end
    «ώρα για αποχώρηση» with a ding-dong every 30″ until they punch out. The end is the declared end (it already
    includes the break: 10:00-16:30/30 = 6h paid, out at 16:30). The 15′ «τελειώνει» heads-up is phone-only now.
31. **Phone alerts at 5′.** «Ευελιξία» default 5′ (a saved 10 — the old default — is moved to 5 once; other values
    are kept). The monitor checks every 15″, so the alert arrives right at the 5th minute.
32. **Break «εκτός ωραρίου» (as Ergani declares it).** Write it `/+30`, e.g. `10:00-16:30/+30`: the declared hours
    10:00–16:30 are all paid (6.5 h) and the 30′ break comes on top, so the punch-out may be anywhere 16:30–17:00
    (Ministry Q&A: declared 09:00–17:00 with 30′ break outside → expected departure 17:30). Reminders count down to
    17:00 (2′, 1′, then every 30″), the phone alert comes at 17:05, the report treats any punch-out 16:30–17:00 as
    «όπως το ωράριο» with 6.5 h, and later than 17:00 as extra work. `/30` keeps meaning «break inside the hours».
    The schedule editor warns if the break type doesn't match Ergani, and «Διάλειμμα … από ΕΡΓΑΝΗ» writes `/+N`.
33. **Three leave types.** «Άδεια…» asks the type: Κανονική άδεια, Άδεια ασθενείας, Άδεια ειδικού σκοπού (+ optional
    note). Monthly and yearly reports have a column per type (working days) in «Σύνοψη» and «Ανά μήνα», and the leave
    list shows the type with a total per type per employee. A holiday or shop closure inside a leave is not a leave day.
    Existing leaves become «Κανονική άδεια».
34. **Holidays and shop closures.** New admin section «Αργίες και κλειστό κατάστημα»: the Greek public holidays are
    computed every year (moveable ones from Orthodox Easter), each with a «κλειστά» checkbox (Μεγάλη Παρασκευή open by
    default); local holidays repeating every year (none preset — add your city's own, e.g. the patron saint); and closures for any
    date range with a reason (renovation…). On those days: no reminders or «δεν χτύπησε» alerts, the shop screen
    shows «Σήμερα κλειστά · …» and refuses an arrival («Σήμερα είμαστε κλειστά», phone alert to you), and the reports
    write «Αργία: …» / «Κατάστημα κλειστό: …» instead of absence, with a list of the holidays/closures that fell on
    working days and who they affected. Ergani is not touched: the accountant declares those days there.
35. **Declared overtime / one-day changes.** «Υπερωρία / αλλαγή ημέρας…» per employee: overtime (later end), other
    hours for a day, or no work — entered AFTER declaring it in Ergani. The kiosk countdown, alerts, early/closed
    refusal and the report follow the new hours for that day (also how someone works on a holiday or closed day).
    «Όρια» → «Προθεσμία δήλωσης υπερωρίας πριν τη λήξη» (default 60′): the employee list shows every day «φεύγει έως
    17:00 · υπερωρία δηλώνεται έως 16:00», and the panel warns if the deadline has passed. Optional phone reminder
    before the deadline («Υπενθύμιση προθεσμίας υπερωρίας», default off): one message per end time naming who is in.
    Staying past the declared end without declared overtime: the phone alert now says «μη δηλωμένη υπερωρία — να
    χτυπήσει αποχώρηση ΤΩΡΑ, με την πραγματική ώρα». Reports: «Δηλωμένες επιπλέον ώρες (υπερωρία)» separate from
    «Επιπλέον ώρες χωρίς δήλωση» (the latter highlighted); work on a day without declared hours counts as extra.
36. **«Στοιχεία επιχείρησης» (sellable to any shop).** Admin section with the business name, a short name, the main
    colour (with a readability check) and the logo (PNG/JPG/WebP up to 1 MB, stored in the database so it is in the
    backups). Pages are filled in when served (titles, logo alt, the app name in the manifest, «η κάρτα εργασίας σου
    για το …» on the phone card and in the Viber/WhatsApp message), colours come from `/brand.css`, the logo from
    `/brand/logo` (no logo → the name is shown). No shop name is written in the code any more. An existing install
    keeps the name and logo it was set up with; a new install starts blank. Still
    shop-specific: the icons in `static/brand/icons` (favicon / installed-app icon).
37. **Closed-day screen.** On a holiday or closure the shop screen shows no QR / PIN: a greeting for the day
    («Καλά Χριστούγεννα!», «Χριστός Ανέστη!», «Καλή Σαρακοστή!», «Χρόνια πολλά! 28η Οκτωβρίου…», «Σήμερα είμαστε
    κλειστά · Ανακαίνιση»…), «δεν γίνονται χτυπήματα κάρτας» and «Σας περιμένουμε ξανά την Τρίτη 29 Δεκεμβρίου»
    (next day that is not closed and has shop hours). If someone has declared hours that day («Υπερωρία / αλλαγή
    ημέρας…»), or in training mode, the normal screen stays. It switches by itself at midnight or when a closure is
    added/removed.
38. **Festive decorations** (admin toggle, on by default), following the calendar: Christmas 1/12–6/1 (falling snow,
    trees with twinkling lights, a garland, Santa peeking and waving), Easter from Κυριακή των Βαΐων to Δευτέρα του
    Πάσχα (red eggs, λαμπάδα with a flickering flame, flowers, butterflies), 25η Μαρτίου / 28η Οκτωβρίου (waving Greek
    flag and blue-white bunting), Καθαρά Δευτέρα weekend (kites), Πρωτομαγιά (flower wreath, petals). On a closed
    holiday the greeting gets a big picture too. All original vector art, CSS motion only (off with «reduce
    animations»), never in the way of the clock, the logo or the reminders. «Προεπισκόπηση» buttons open each
    holiday's screen in a new tab (`/?preview=christmas`…, nothing recorded).
39. **Restart the shop screen from admin.** «Συσκευές» → «Ανανέωση οθόνης»: the kiosk app on the laptop reloads
    itself with the latest version within ~30″ (it waits if someone is in the middle of a punch), and admin shows
    «✓ η οθόνη ανανεώθηκε» when it has. No need to close and reopen the app after an update any more.
    (The screen that is running before this update doesn't know the button yet: it picks up this version at its
    automatic reload — idle 6 h — or when the app is reopened once.)
40. **Admin panel reorganized, mobile first.** Five tabs — «Σήμερα» (who is in / coming / off today with their end
    and overtime deadline, forgotten punch-outs, alerts, shop screen and sending), «Προσωπικό», «Ωράρια & αργίες»,
    «Αναφορές», «Ρυθμίσεις» (ΕΡΓΑΝΗ, όρια, στοιχεία επιχείρησης, συσκευές, κινήσεις). Tabs on top on the PC, a
    bottom icon bar on the phone; opens on the last tab used (`#today`, `#people`…). Alert count in the header and
    on «Σήμερα». Employees are cards; their 12 links are one «Ενέργειες ▾» menu (frequent actions first, PIN /
    rename / deactivate / delete at the bottom) — a bottom sheet on the phone. Άδεια / Υπερωρία / Αποχώρηση / QR /
    Ξεχασμένη βάρδια open as a dialog on the PC and full screen on the phone (✕, Esc or tap outside to close).
    Devices and movements show as cards on the phone. Long explanations are folded under «ⓘ Οδηγίες».

41. **Περίοδος προσαρμογής (onboarding mode).** For a business that has time before the card becomes mandatory.
    «Σήμερα» → «Οθόνη καταστήματος και αποστολή» → «Υποχρεωτική από [ημερομηνία]» → «Έναρξη». Until that date the card
    is used exactly as in real life — punches are recorded with status «Προσαρμογή (δεν στάλθηκε)», reminders, phone
    alerts, forgotten-punch corrections and the reports all work — but NOTHING is sent to Ergani. On the date itself sending
    starts by itself (or earlier with «Τέλος τώρα»; the date can be moved with «Αλλαγή»).
    The shop screen shows NOTHING different (so nobody takes it less seriously): no banner, no «test» wording; after a
    punch only a faint log line bottom right «✓ καταγράφηκε · 06:45:12» for 8″, and the result screen has no Ergani line.
    A departure always follows its arrival: a shift punched in during the period is closed in karta only even if the period
    ended in between (Ergani never gets a departure without its arrival), and a shift that was sent is closed with a sent
    departure. «Αποχώρηση…» for such a shift offers «Φεύγει τώρα» / «Ξέχασε να χτυπήσει» (no Ergani late code).
    «Πώς τα πάνε» table per employee (kept for 31 days after the period): punches (share by QR), «σωστές ημέρες» (both
    punches by the employee, no correction), corrections you made, days without punches. Phone/admin notice on the last
    day of the period and on the first mandatory day (urgent if ERGANI_MODE is not production). Reports note the period
    in the header; the Ergani protocol cells of those punches say «δοκιμή». These records are kept (they are not test data: «Διαγραφή δοκιμαστικών κινήσεων» doesn't touch them).
    Training mode still works on top of it (red banner, nothing recorded).
42. **Touch screens (phone, tablet, touch laptop) — admin.** Tested with touch emulation on 320–1180 px screens:
    - one tap = one action: a fast double/triple tap used to send the request 2–3 times (e.g. three saves); now the
      button is disabled while it runs, plus a short cool-down;
    - the action sheet of an inactive employee was see-through and its last item («Διαγραφή») hid under the bottom
      tab bar (the card's opacity trapped the sheet); now only the card's text is dimmed;
    - the 30″ auto-refresh no longer wipes what you are typing (closures, local holidays, onboarding date, business
      details) or closes an open «Τι θα στελνόταν»; it also pauses while the page is in the background and refreshes
      as soon as you come back to it;
    - every control is at least 44 px on touch screens (links were 17 px tall, the break −/+ 30 px); fields use 16 px
      text so iPhone/iPad no longer zoom the page when you tap into a field; hover colours only where there is a mouse;
    - the bottom tab bar hides while typing (it sat on top of the keyboard); a panel's ✕ stays visible while scrolling;
    - tapping outside an «Ενέργειες» menu closes it on iPad too (iOS sends no click for taps on plain areas); near the
      bottom of the screen the menu opens upwards.
43. **Shop screen sizes.** From Full HD up everything grows with the screen (keys 103 px at 1920×1080, 137 px at
    2560×1440, 180 px at 4K; before: 96 px everywhere); up to 1366×768 nothing changes. On phone-sized screens the PIN
    pad and the choices are a bit more compact, so the PIN screen fits a 390×844 phone without scrolling. Reminder
    cards are redrawn only when they change (a redraw at the moment of a tap could swallow it).
44. **Cleaner code.** Settings are read/written through `db.setting()` / `db.put_setting()` (25 copies of the same
    SQL removed); admin panels close through one helper; small duplicates and indentation tidied. No behaviour change
    (same results as before in the regression run against the 30/09 version).
45. **«Επόμενο χτύπημα» on the result screen.** After a successful punch the shop screen shows a button that goes
    straight back to the start, so the next person doesn't wait; a thin bar inside it empties during the 6″ before
    the automatic return. Enter / Esc / space do the same, and a QR card can be scanned right on the result screen.
    Also fixed: the automatic return timer was never cancelled, so leaving the result screen early (e.g. by tapping a
    reminder card) sent the next person back to the start in the middle of typing their PIN.
46. **Ευέλικτη προσέλευση (flexible arrival), as the law sets it** (ν. 5239/2025 → ΠΔ 80/2022 άρθρο 580 παρ. 2Α,
    εγκύκλιος 26606/13-10-2025). Per employee, in minutes (0–120), from «Ενέργειες → Ευέλικτη προσέλευση…»; enter
    what Ergani shows in the employee's «Ψηφιακή Οργάνωση Χρόνου Εργασίας». The window counts FROM the declared start:
    - arriving inside the window moves the whole day by the same amount: punch-out reminders, «έληξε / είναι ακόμα
      μέσα» alerts, the overtime deadline and «φεύγει έως» in admin follow the actual arrival; arriving later moves
      it by the full window only (the rest is lateness); a day never moves past midnight;
    - a break «εκτός ωραρίου» keeps its meaning on the moved day: the punch-out is fine anywhere from the (moved) end
      to the (moved) end + break. Absolute limit = declared end + window + break (e.g. 15:30 + 60′ + 30′ = 17:00);
    - punch-in reminders and the «δεν χτύπησε προσέλευση» alert are unchanged (from the declared start, as before);
    - an arrival BEFORE the declared start is still refused, exactly as before;
    - report: such a day is «όπως το ωράριο» with a note «Ευέλικτη προσέλευση: 11:05 (+0:35 από τις 10:30) → λήξη
      17:25»; the declared schedule shows «ευέλικτη προσέλευση 60′». Also (all employees): a late arrival / early
      departure whose hours still come out right is now «Καθυστέρηση ή νωρίτερη αποχώρηση» (informational) instead of
      «Εργασία εκτός των δηλωμένων ωρών», which is kept for work before the start or after the end;
    - «Έλεγχος ΕΡΓΑΝΗ» keeps what Ergani returns as flexible hours and shows it next to the employee's facts.
    Employees with 0 behave exactly as before (same regression results as the previous version).
47. **«Θα αργήσει σήμερα (σίγαση)».** Employee menu (and «Σήμερα»), when someone is expected and not in yet: mutes,
    for today only, their punch-in reminder on the shop screen and the «δεν χτύπησε προσέλευση» phone alert (one
    already sent is marked done). «Άρση σίγασης προσέλευσης» undoes it. Punch-out notices are never muted.
48. **No phone notice before the end of the shift.** The «η βάρδια τελειώνει στις …» heads-up (and its setting
    «Προειδοποίηση πριν τη λήξη») is gone. The shop screen still counts down the last 2′, and «είναι ακόμα μέσα» after
    the end is unchanged.
49. **«Έφυγε νωρίτερα…» (e.g. got sick).** The person punches out as always (sent to Ergani with the real time). If
    that is 15′ or more before the end of the day (flexible arrival included; the break «εκτός ωραρίου» not counted),
    the admin list shows a note (no phone alert) and «Σήμερα» moves them to «Έφυγαν νωρίτερα» (before, they showed
    as «Έρχονται σήμερα»). «Λόγος…» / «Ενέργειες → Έφυγε νωρίτερα…» records why (ασθένεια / προσωπικός / άλλος +
    note, any day of the last 62) and, for sickness, can add sick leave from the next day in one step. Report: the
    day shows «Αποχώρηση νωρίτερα — ασθένεια: …» with what to do; sick leave entered from that same day no longer
    gives «Εργασία σε ημέρα άδειας». Nothing extra is sent to Ergani.
50. **Report sheet «Απολογιστικές δηλώσεις».** Every day whose punches do not match the declared schedule to the
    minute (the ministry gives no tolerance), with the hours to declare afterwards in Ergani, any time beyond them
    (υπερεργασία/υπερωρία → Ε8), what happened, and the deadline (end of the next month). Same rule as the ministry's
    example (09:00–17:00, punched 08:13–16:19 → declare 08:13–16:13). Flexible arrival inside the window and a
    punch-out inside a break «εκτός ωραρίου» match and are not listed; onboarding-period days are not listed.
    Flexible arrival now moves the day in whole minutes.
51. **No tolerance in the report.** «όπως το ωράριο» only when every punch is exactly (to the minute) inside the
    declared hours — with the flexible-arrival shift and the break «εκτός ωραρίου» window, e.g. Ελένη 60′ late:
    any punch-out 16:30–17:00 matches, 17:01 does not. Before: 15′ either way counted as «όπως το ωράριο» and times
    were rounded to 5′, hours to the quarter. Now times and hours are exact to the minute (seconds ignored, as in
    Ergani) and any difference shows (e.g. «Λιγότερες ώρες −0:01»). «Έφυγε νωρίτερα» likewise from 1′ before the end.
    Shop screen (unchanged, verified in real time): sound at −2′, −1′, at the absolute limit, then every 30″ until
    the punch-out. Phone alerts keep their «Ευελιξία» setting (notifications only, not a tolerance).
52. **Χρόνος προετοιμασίας (εγκύκλιος 26606/13-10-2025 §3).** A punch-out up to 10′ after the absolute limit is
    preparation time (changing etc.), which is not working time: the hours stay as declared, the day is not in
    «Απολογιστικές δηλώσεις», and «Προς ενέργεια» has an informational line «Αποχώρηση 2′ μετά το όριο (17:02, έως
    17:00)» (the punch should be made at the end, before the preparation). From 11′ on it is extra work as before
    (all of it: +0:11). Punching out early, even by 1′, is still «Λιγότερες ώρες» (preparation time is after the end).
53. **Shop screen, light visual refresh (same layout and behaviour).** One shape scale (keys and pills round,
    everything else 16px), soft shadows tinted to the brand sand, bolder headings (600), keypad keys ~10% larger
    (81px on 1366×768, 114px on Full HD), the interaction column centred on wide screens, every tappable surface
    presses in slightly on touch (off with «reduce motion»), screens fade in. Reminder colours darkened so white text
    passes WCAG AA (the amber «σε λίγο» card was 2.9:1, now 5.3:1). With reminders showing, the clock steps back so
    the side panel fits (1366×768 and 1024×600 with logo and three reminders: no scrolling). Texts: no pictographs or
    long dashes on the shop screen; the sound button has a minimal speaker icon (Tabler Icons «volume», MIT, same
    line style as the keypad icons). Service-worker cache v26 so the shop screen picks it up.
54. **Festive decorations checked on every theme, size and holiday screen** (Christmas, Easter, 25/3 and 28/10
    flags, Καθαρά Δευτέρα kites, Πρωτομαγιά; the 12 holiday greetings; 1024×600 to 4K; phone). Fixed:
    - falling snow, petals and butterflies drift over the whole screen (side panel and punch screen alike); they
      never catch a tap (checked: every key and button works through them);
    - with reminders showing, Santa, the Easter flowers and the kites (middle of the side panel, where the cards go)
      fade out instead of peeking from behind the cards;
    - in production (no test-mode pill) the 28/10 flag and the May wreath touched the clock's seconds on 1366×768:
      they are a little smaller and further right, and on screens up to 820px high all side pieces are 22% smaller
      (38% up to 640px); checked against the clock and date text while the pieces move: nothing touches;
    - «reduce motion» did not stop the slow background glow (a CSS rule was overridden): now everything stops.
55. **Report: the 10′ preparation time is not flagged at all.** A punch-out up to 10′ after the limit counts as
    «όπως το ωράριο» (no remark, hours as declared, not in «Απολογιστικές δηλώσεις»); likewise up to 10′ beyond the
    declared length in «Απολογιστικές δηλώσεις» is not shown as «Επιπλέον» (as in the ministry's own example).
    **No «Προς ενέργεια» sheet any more**: what has to be declared is in «Απολογιστικές δηλώσεις»; other remarks
    (forgotten punch-out, Ergani pending, absence…) stay in «Αναλυτικά» → «Παρατηρήσεις», and «Σύνοψη» counts them.
56. **Docker: a new volume works out of the box (1.0.1).** The image creates `/data` owned by the app user, so
    a brand-new named volume mounted there is writable. Before, a fresh `-v karta-data:/data` made the start-up
    fail with «unable to open database file». Existing installations are not affected. The Tests workflow now
    starts the built image with a fresh volume on every change.
57. **Setup assistant (1.1.0).** `./setup.sh` asks in Greek for the business ΑΦΜ (checked), the Ergani user (the
    login is tested, read-only), the address and admin emails, and writes `.env` (mode 600; an existing one is kept
    as `.env.bak-…`; it always starts in `dry_run`). With a Cloudflare API key it creates the tunnel, the DNS record
    and the Access application for `/admin` by itself (safe to run again; asks before replacing a DNS record),
    otherwise it asks for the values by hand. Optional ntfy topic with a test notification. It then starts Karta
    and can install a nightly backup (keeps the last 30). `./setup.sh check` tests the settings, the Ergani login,
    the Cloudflare team domain, that the address answers, and warns if `/admin` is NOT behind Cloudflare Access. It
    runs inside the Karta image as the host user, so the machine only needs Docker (which it offers to install).
58. **«Πρώτα βήματα» in admin (1.1.0).** On «Σήμερα», a checklist for a new installation: business details, staff
    from Ergani, schedules, local holidays, shop screen, phone notifications, a trial run in training mode, going
    live. Steps tick themselves off from what is in place («Πάμε» opens the right section); the ones Karta can't
    detect can be marked done or skipped; the list can be hidden. New «Δοκιμαστική ειδοποίηση» sends a phone
    notification right away and reports whether ntfy accepted it.
59. **Settings in the admin page (1.2.0).** «Ρυθμίσεις» → «Επιχείρηση και σύνδεση με το ΕΡΓΑΝΗ»: employer ΑΦΜ
    (checksum), branch, Ergani employer id, the Ergani web-services user (production) and an optional separate
    trial user, each with «Δοκιμή σύνδεσης» (read-only login). «Ειδοποιήσεις στο κινητό»: ntfy server, topic
    (a random one is suggested) and token. Values are stored in the database as `cfg.*` and take precedence over
    `.env` (shown «από το .env» otherwise); passwords and the ntfy token are sealed with `PIN_KEY` (AES-GCM) and
    never sent back to the page. Every change is in the audit log. While the current mode lacks the user, password
    or ΑΦΜ, the page says what is missing and the queue waits without using up attempts.
60. **Mode switch in the admin page (1.2.0).** «Λειτουργία»: `dry_run` / `trial` / `production` without editing
    `.env` or restarting. Going to `trial` or `production` needs the employer ΑΦΜ typed again and a successful
    login to that Ergani environment first; back to `dry_run` is a plain confirmation. Logged with who and when.
    `ERGANI_MODE` in `.env` still works as the default.
61. **Setup assistant: only the address and Cloudflare (1.2.0).** `./setup.sh` asks for the address, the admin
    emails and the Cloudflare key (or the manual values); ΑΦΜ, Ergani user, phone alerts and mode are set in the
    admin page. Values already in `.env` are kept. «n» now means no (it was read as «ν»), unclear answers get a hint,
    after installing Docker it says which folder to rerun it in, and run from the home folder it installs in
    `~/karta`. «Πρώτα βήματα» gains «Σύνδεση με το ΕΡΓΑΝΗ» (first) and «Αντίγραφα ασφαλείας».
62. **Backups kept for years (1.2.0).** The nightly `backup.sh` keeps 30 daily, 24 monthly (last copy of each month)
    and one copy per year for good, plus `karta.env`; `./setup.sh usb` mounts a USB stick permanently (by UUID,
    `nofail`) and copies there every night. **Cloud backups are made by Karta itself**: rclone is in the image, and
    «Ρυθμίσεις» → «Αντίγραφα ασφαλείας» connects Google Drive (`drive.file` scope), Dropbox (token from
    `rclone authorize` pasted in the page) or Backblaze B2 through an rclone crypt remote (`/data/rclone.conf`); the
    generated encryption password is shown once. Every night at 23:40 (or as soon as the last good upload is over
    36 h old) it uploads daily/monthly/yearly copies and prunes daily > 30 days, monthly > 24 months; «Ανέβασμα
    τώρα», «Αποσύνδεση cloud», and «Έχω ήδη αντίγραφα στο cloud» (connect with the old password on a new machine).
    **Restore from the admin page**: from an uploaded file or a cloud copy, in two steps (what the backup holds, a
    quick_check and whether `PIN_KEY` can open its sealed values; then «Επαναφορά τώρα», which keeps the current
    database as `before-restore-….db` and swaps it in while Karta runs, with migrations and settings reloaded).
    `./setup.sh restore` does the same from the machine or the USB when the admin page is not available. The admin
    page shows the last result of each; alerts follow when backups stop (over 50 h) or a copy fails. «Λήψη
    αντιγράφου τώρα» (consistent SQLite copy) and «Αρχείο χτυπημάτων», every punch of a year in Excel with Ergani
    protocol number, submission time, late reason, method and device.
63. **Slow Ergani, clear answers (1.2.0).** Reads from Ergani («Έλεγχος ΕΡΓΑΝΗ», services) give up after 60″ with
    «Το ΕΡΓΑΝΗ δεν απάντησε…», before Cloudflare's 100″ limit; Cloudflare errors (524, 502/503/530, 522/523) are
    explained in Greek instead of «Σφάλμα 524».
64. **Schedules: where the daily hours come from.** The «Ωράρια» tab and «Πρώτα βήματα» say that Ergani usually
    gives only the weekly hours, so each day's hours come from the accountant's timesheet; the editor shows whether
    the week matches Ergani.
65. **Colours (1.2.0).** «Στοιχεία επιχείρησης» → «Χρώματα»: ready themes (Karta, Θάλασσα, Μπορντό, Ελιά, Τερακότα,
    Γραφίτης, Νύχτα), and main colour, background, side panel, text, «Προσέλευση» and «Αποχώρηση» buttons one by
    one, with automatic black/white text on buttons, readability warnings and a live preview. Dark theme separately
    for the shop screen and the admin page. The admin page now follows the brand colours too. Hard-coded colours in
    both stylesheets became variables; with the default colour and nothing else changed, `/brand.css` is unchanged.
66. **Leftovers of the original private version removed (1.2.0).** The one-time upgrade steps for databases of the
    private versions (old fixed logo file, the old 10′ alert flexibility and «Παύση αποστολής», the single timeless
    schedule table and the columns added over time) are gone: the schema now creates every column directly. The
    unused `schedules` table is no longer written or read (an existing one is simply left alone). Texts no longer
    assume a particular shop or a Windows laptop. Databases made by the public versions 1.0.0–1.1.0 work unchanged.
67. **Tunnel protocol by where Karta runs (1.2.0).** The setup assistant asks whether Karta runs at the shop/home
    (Raspberry Pi, old PC, local server) or on a VPS, and writes `TUNNEL_PROTOCOL=http2` or `auto` (QUIC/HTTP/3 with
    HTTP/2 fallback); `docker-compose.yml` passes it to cloudflared (default `http2`). Behind home and shop routers
    QUIC over UDP can make pages slow. `setup.sh` updates an unchanged first-version `docker-compose.yml`.
68. **Cloud setup: the exact command for Windows (1.2.1).** The admin page and the guide show `.\rclone.exe authorize
    "drive"` for Windows PowerShell (which doesn't run programs from the current folder without `.\`) and
    `./rclone authorize "drive"` for Mac/Linux.
69. **«Ενημέρωση τώρα» (1.3.0).** «Ρυθμίσεις» → «Έκδοση και ενημέρωση» shows the running version (baked into the image
    by the release workflow) and, every few hours, checks GitHub for a newer release («Τι αλλάζει» links to it). The
    button only leaves a request: `update.sh`, installed by `./setup.sh` with a per-minute cron line, takes it
    (`python -m app.updatemark poll`, every 2 minutes, read-only unless asked; the "alive" mark is refreshed every 30 minutes), makes a backup, runs `docker compose pull && up -d`, and the new container
    reports the result (`updatemark done ok|fail`) and asks the shop screen to reload. Karta never gets access to
    Docker. The page follows the update and reloads when the new version answers. `./setup.sh update` does the
    same from the terminal.
70. **Cloud backups with restic (1.4.0).** The nightly cloud copy is now a restic snapshot (restic in the image, through
    rclone): encrypted on the machine, compressed, and deduplicated (restic re-uploads only the ~1 MB pieces that
    changed): measured on a 6 MB database with daily punches, ~1 MB a day, ~20–25 MB for the 30 daily snapshots and
    ~1 MB per monthly one, about a tenth of whole copies. Each snapshot is a complete database; restore
    picks one by date. Retention by `restic forget --keep-daily 30 --keep-monthly 24 --keep-yearly 1000 --prune`;
    a stale lock is cleared first. `init` refuses to start a new repository over existing backups (use «Έχω ήδη
    αντίγραφα στο cloud»). Connections made with 1.2–1.3 (rclone crypt copies) need to be connected again; the
    older copies stay in the folder.
71. **Disclaimer.** New `DISCLAIMER.md` (Greek and English; also in the wiki, the README and the admin page):
    no warranty, not official software, the employer is responsible for Ergani declarations, fines, backups,
    record retention and personal data, limitation of liability to the extent the law allows. `./setup.sh`
    asks once for «ναι» before installing and keeps the date in `.env` (`DISCLAIMER_ACCEPTED`).
72. **Docs.** "Free cloud" now says what it is (your own VPS, reached over SSH). Wiki pages brought up to date:
    `PIN_KEY` is required, festive decorations live in «Ωράρια & αργίες», backup alerts, the full path to
    «Λειτουργία», what `./setup.sh check` tests, keeping `.env` safe when the only copy is in the cloud.
73. **Hardened container.** `docker-compose.yml` runs Karta read-only (only `/data` and a 16 MB `/tmp` are writable),
    with no Linux capabilities, `no-new-privileges`, 512 MB memory and 128 processes at most, and a healthcheck on
    `/healthz` (`docker ps` shows «healthy»). cloudflared is read-only too, without capabilities. Checked with the
    whole stack: healthy at ~50 MB, cloud backup and restore (restic writes only to `/data/.cache`), and `backup.sh`.
74. **Karta without the tunnel, behind your own reverse proxy.** cloudflared is now in the `tunnel` Compose profile:
    `docker compose up -d` without `TUNNEL_TOKEN` starts Karta alone. `./setup.sh` writes `COMPOSE_PROFILES=tunnel`
    next to `TUNNEL_TOKEN` (and adds it to an existing `.env` that has a token), so tunnel installations, `backup.sh`
    and `update.sh` work as before. `./setup.sh check` doesn't ask for a tunnel without one. New wiki page «Πίσω από
    δικό σας reverse proxy»: Caddy and nginx, Cloudflare Access for `/admin`, and `X-Real-IP`.
75. **Updates go back by themselves when a version doesn't start.** The version is pinned in `.env`
    (`KARTA_VERSION`, used by `docker-compose.yml` as `ghcr.io/osergios/karta:${KARTA_VERSION:-latest}`). `update.sh`
    finds the newest version (what `:latest` points to), keeps the previous one, takes the backup, switches, and waits
    up to about 2 minutes for the healthcheck; if Karta isn't healthy, it writes the previous version back and starts it
    again (its image is still on the machine). The admin page shows «ενημερώθηκε σε X» or «απέτυχε — επέστρεψε στην X».
    `./setup.sh update` runs the same `update.sh now`, pins the running version first, and replaces a
    `docker-compose.yml` that is an untouched official copy (by its sha256; the old one is kept as `.bak`).
76. **Supply chain.** Every action in the workflows is pinned to its full commit SHA (the version stays as a comment;
    Dependabot keeps both current). The release image is built with `provenance: mode=max` and an SBOM, and
    `actions/attest-build-provenance` signs it: `gh attestation verify oci://ghcr.io/osergios/karta:<version> --owner
    osergios`. cloudflared is pinned (`2026.9.3`); Dependabot's new `docker-compose` entry offers new versions.
77. **Database migrations.** `app/db.py` keeps an ordered list of schema steps (`MIGRATIONS`) and applies the ones above
    the database's `PRAGMA user_version` at start-up, in one transaction. Step 1 is empty: it marks today's schema as
    version 1. Steps only add (`ALTER TABLE … ADD COLUMN` guarded by `PRAGMA table_info`), so going back to an older
    version stays safe; a database made by a newer version is left alone. The old unused `schedules` table stays.
78. **The first cloud backup runs at the end of connecting.** `cloud.connect()` holds the same lock as the nightly
    worker from the start, and takes the first snapshot itself once the repository exists (new or existing backups),
    so the worker can no longer start a backup before `restic init` has finished (it did, and the first backup failed
    with an alert although nothing was wrong). The admin page says «το πρώτο αντίγραφο ανέβηκε ✓» or shows the reason
    it failed; the connection (and the password shown once) stays either way.
79. **Clear cloud errors.** A failed restic / rclone command no longer shows only its last line (for a missing
    repository that was just «rclone:karta-store:Karta-backups»). Known cases read in Greek: no backups in that cloud
    folder, backups locked by an interrupted job, wrong encryption password, the cloud is full, access expired
    (401 / 403 / `invalid_grant`); anything else shows its last 2–3 lines (up to 300 characters). The full output is
    logged at WARNING.
80. **A cloud backup cut off half-way no longer blocks the next ones.** Each backup starts with `restic unlock`
    (without `--remove-all`: only stale locks, of a process that no longer exists or older than 30 minutes, never a
    running backup), and a failing unlock no longer stops the backup: the backup itself reports any real problem.
81. **A first cloud backup that never worked has its own alert.** «Το πρώτο αντίγραφο στο cloud δεν έγινε: ‹the
    reason›» instead of «δεν ανέβηκε τις τελευταίες δύο ημέρες» (which it said even minutes after connecting). The
    two-day wording stays for a cloud copy that worked before and is now over 50 hours old. A cloud-only installation
    (a VPS) whose cloud never worked now gets this alert, instead of the Monday «Δεν γίνεται αντίγραφο ασφαλείας»,
    which is now only for no backup set up at all.
82. **Backup alerts close by themselves.** On each check (at any hour) the open backup alerts whose problem is gone get
    `resolved_at`, like the «please punch out» banners on departure: `backup_none` once any backup is set up,
    `backup_old` after a recent local copy, `backup_cloud_old` after a recent cloud copy, `backup_failed` when the last
    result is no longer a failure. The rows stay as history; the check writes only when something is open.
83. **Docs: the USB copies are not encrypted.** The README no longer reads as if they were, and the Backups page (Greek
    and English) says so plainly: the databases and `karta.env` (`PIN_KEY`, and the Ergani password if kept in
    `.env`) are plain files on the stick, so keep it somewhere safe, like the shop's keys. The behaviour is unchanged.
84. **Docs: Karta always uses Greek time.** Configuration and FAQ (Greek and English): all times are in
    `Europe/Athens`, summer and winter changes included, whatever the server's timezone; `TZ` in `docker-compose.yml`
    only affects log timestamps.
85. **Release notes end with «Αναβάθμιση / Upgrading».** What users do to update, whether the database changes
    (and to which schema version), and whether going back is safe. Template in `docs/releases/TEMPLATE.md`, pointed to
    from `CONTRIBUTING.md`; the note for the next release (`docs/releases/v1.5.0.md`) already has it.
86. **The IP kept with each punch can no longer be set by the browser.** Karta took it from `X-Real-IP`, which passes
    the Cloudflare Tunnel unchanged, so a hand-made request could record any address. It now takes Cloudflare's
    `CF-Connecting-IP` (Cloudflare writes it itself, replacing what the browser sent), then `X-Real-IP`, then the
    connection's address. The wiki page «Πίσω από δικό σας reverse proxy» says to let only Cloudflare reach the proxy.
