# FAQ and troubleshooting

### How do I add an employee?

Only from Ergani: «Ρυθμίσεις» → «ΕΡΓΑΝΗ» → «Έλεγχος ΕΡΓΑΝΗ», then import. The person
must already be declared in Ergani. This keeps ΑΦΜ and names exactly as Ergani has them.

### «Έλεγχος ΕΡΓΑΝΗ» fails even in `dry_run`

The read services always use the **production** Ergani (read‑only). Fill in
`ERGANI_USERNAME`, `ERGANI_PASSWORD` and the right `ERGANI_USER_TYPE` (`01` API user,
`02` branch user), then restart.

### The admin page says "Access token missing" or 403

- Open the admin page through your domain, so Cloudflare Access sits in front of it. A
  direct `http://server:8000/admin` has no Access token.
- Check `CF_ACCESS_TEAM_DOMAIN` (no `https://`), `CF_ACCESS_AUD`, and that your email is
  in `ADMIN_EMAILS`.

### The shop screen says the device isn't registered

Create a new code in «Ρυθμίσεις» → «Συσκευές» and enter it at `/enroll` on that device.
This happens after clearing the browser's cookies, using a different browser, or about
400 days after registration.

### The shop screen has no sound

Browsers block sound until someone taps the page. Tap the «Πάτα εδώ για να ενεργοποιηθεί
ο ήχος» button once after the laptop starts.

### The QR camera doesn't start

The camera only works over **HTTPS**, and the browser must be allowed to use it. Check
the camera permission in the browser's site settings.

### Someone forgot to punch out

Use «Αποχώρηση…» → «Ξέχασε να χτυπήσει» (Karta only, with a note). For an earlier day,
use the «Κλείσιμο DD/MM…» button on the [Today](Admin-Today) tab. **Don't** use
«Τεχνικό πρόβλημα» for a forgotten punch: that declares a technical fault to Ergani.

### Someone forgot a whole shift

«Ενέργειες ▾» → «Ξεχασμένη βάρδια…». It's recorded in Karta only, for the report and pay.

### Someone needs to stay late

Declare the overtime in Ergani **before** the deadline («υπερωρία δηλώνεται έως …»),
then add it in Karta with «Υπερωρία / αλλαγή ημέρας…». Reminders and alerts then follow
the new end time.

### Someone needs to start earlier than declared

Declare it in Ergani first, then use «Νωρίτερη προσέλευση σήμερα». Otherwise the shop
screen refuses the early arrival.

### A punch shows «Προς έλεγχο στο ΕΡΓΑΝΗ»

Karta isn't sure whether Ergani received it. Check in Ergani, then choose «Υπάρχει στο
ΕΡΓΑΝΗ» or «Δεν υπάρχει — νέα αποστολή». See
[How punches reach Ergani](Ergani-Submissions).

### Punches are stuck «Σε αναμονή»

Karta keeps retrying. Look at the error in «Κινήσεις» and at the alerts. Common causes:
a wrong Ergani password, Ergani being down, or no internet on the server.

### Can I see an employee's PIN?

Only if `PIN_KEY` was set in `.env` when the PIN was created. Otherwise give them a new
one with «Νέο PIN».

### I changed the schedule but last month's report changed too

It shouldn't: each schedule save applies **from** its «ισχύουν από» date. Check that you
didn't save it with a date in the past.

### How do I update the shop screen after upgrading Karta?

«Σήμερα» → «Οθόνη καταστήματος και αποστολή» → «Ανανέωση οθόνης».
