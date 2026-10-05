# Συνεισφορά στην Karta

**Ελληνικά** · [English](#contributing-to-karta)

Ευχαριστούμε που θέλετε να βοηθήσετε! Κάθε συνεισφορά μετράει: αναφορά σφάλματος,
διόρθωση στον οδηγό χρήσης, μετάφραση ή κώδικας.

Όλοι όσοι συμμετέχουν ακολουθούν τον [κώδικα δεοντολογίας](CODE_OF_CONDUCT.md).

## Αναφορά σφάλματος ή πρόταση

Για **ερωτήσεις** («πώς κάνω…;») γράψτε στις [Συζητήσεις](https://github.com/osergios/karta/discussions). Τα issues είναι για σφάλματα και συγκεκριμένες προτάσεις.

Ανοίξτε ένα [issue](https://github.com/osergios/karta/issues) και γράψτε:

- τι κάνατε, τι περιμένατε να γίνει και τι έγινε τελικά·
- τη λειτουργία (`dry_run`, `trial` ή `production`) και την έκδοση της Karta («Ρυθμίσεις» → «Έκδοση και ενημέρωση»)·
- τον browser και τη συσκευή, αν το πρόβλημα αφορά την οθόνη του καταστήματος.

**Μη βάζετε ποτέ πραγματικά προσωπικά δεδομένα** σε issues: ονόματα εργαζομένων, ΑΦΜ,
κωδικούς ΕΡΓΑΝΗ, PIN, το αρχείο `.env` ή στιγμιότυπα με πραγματικά στοιχεία. Χρησιμοποιήστε
φανταστικά στοιχεία.

**Προβλήματα ασφαλείας** μην τα αναφέρετε δημόσια. Χρησιμοποιήστε την
[ιδιωτική αναφορά ευπάθειας](https://github.com/osergios/karta/security/advisories/new)
του GitHub.

## Στήσιμο για ανάπτυξη

```bash
git clone https://github.com/osergios/karta.git
cd karta
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Για τοπική δουλειά, στο `.env` βάλτε `ERGANI_MODE=dry_run`,
`PUBLIC_ORIGIN=http://localhost:8000`, `DB_PATH=./data/workcard.db`, ένα ΑΦΜ δοκιμής στο
`EMPLOYER_AFM`, και οποιεσδήποτε τιμές στα `CF_ACCESS_*` και `ADMIN_EMAILS`. Μετά:

```bash
mkdir -p data
set -a; . ./.env; set +a
PYTHONPATH=vendor uvicorn app.main:app --reload --port 8000
```

Χρήσιμο να ξέρετε:

- Η σελίδα διαχείρισης (`/admin`) δέχεται μόνο token του Cloudflare Access, οπότε τοπικά
  απαντά 403. Για να τη δοκιμάσετε, χρησιμοποιήστε μια δοκιμαστική εφαρμογή Cloudflare
  Access (π.χ. μέσω `cloudflared tunnel`) σε δικό σας domain.
- Το cookie εγγραφής της οθόνης καταστήματος είναι `Secure`, και η κάμερα θέλει HTTPS.
  Για πλήρη δοκιμή της οθόνης, χρησιμοποιήστε HTTPS (π.χ. το ίδιο tunnel).
- **Δοκιμάζετε πάντα σε `dry_run`**, ή σε `trial` με χρήστη του δοκιμαστικού ΕΡΓΑΝΗ. Μη
  στέλνετε ποτέ δοκιμαστικά χτυπήματα στο πραγματικό ΕΡΓΑΝΗ.

## Αυτόματα τεστ

Τα τεστ βρίσκονται στον φάκελο `tests/` και τρέχουν σε `dry_run` με προσωρινή βάση, χωρίς
ποτέ να επικοινωνούν με το ΕΡΓΑΝΗ:

```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest
```

Τρέχουν και αυτόματα στο GitHub σε κάθε pull request. Αν αλλάξετε συμπεριφορά, προσθέστε ή
ενημερώστε το αντίστοιχο τεστ. Για ό,τι εξαρτάται από την ώρα (νωρίτερη προσέλευση,
αργίες, υπενθυμίσεις), χρησιμοποιήστε το `clock` του `tests/conftest.py`, που «παγώνει» την
ώρα.

## Οδηγίες για τον κώδικα

- **Ακολουθήστε το ύφος του υπάρχοντος κώδικα**: ονόματα, δομή, πυκνότητα σχολίων.
- **Κείμενα οθόνης στα ελληνικά**, όπως τα υπόλοιπα. Τα σχόλια του κώδικα στα αγγλικά.
- **Όχι νέες εξαρτήσεις** χωρίς λόγο. Η Karta μένει σκόπιμα μικρή (FastAPI, SQLite,
  χωρίς build για το frontend, χωρίς εξωτερικά CDN).
- Το **Content‑Security‑Policy** είναι αυστηρό: όχι inline `<script>` ή `style="…"`.
  Βάλτε τον κώδικα στα αρχεία `.js` και `.css`.
- Οι αλλαγές στη βάση πρέπει να εφαρμόζονται **αυτόματα και με ασφάλεια** σε υπάρχουσες
  εγκαταστάσεις (δείτε τα `ALTER TABLE` στο `app/db.py`).
- Ό,τι αγγίζει **δηλώσεις στο ΕΡΓΑΝΗ, ωράρια ή αναφορές** έχει νομικές συνέπειες για τις
  επιχειρήσεις. Εξηγήστε στο pull request τη λογική και, όπου υπάρχει, την πηγή (νόμο,
  εγκύκλιο, οδηγίες του υπουργείου).
- Αν προσθέσετε κώδικα από άλλο έργο, πρέπει να έχει **συμβατή άδεια** (π.χ. MIT, BSD,
  Apache‑2.0, LGPL/GPL‑3.0) και να καταγραφεί στο
  [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) μαζί με το κείμενο της άδειάς του.

## Pull requests

1. Κάντε fork και δημιουργήστε branch από το `main`.
2. Κρατήστε κάθε pull request μικρό και με ένα θέμα.
3. Τρέξτε τα τεστ (`python -m pytest`), ελέγξτε την αλλαγή σε `dry_run`, και περιγράψτε
   στο pull request τι δοκιμάσατε.
4. Αν αλλάζει κάτι που βλέπει ο χρήστης, ενημερώστε:
   - το [`CHANGES.md`](CHANGES.md)·
   - τον οδηγό χρήσης στο [`docs/wiki/`](docs/wiki/), **και στις δύο γλώσσες** (π.χ.
     `Kiosk.md` και `Kiosk-EN.md`). Το wiki δημοσιεύεται αυτόματα από εκεί, οπότε μην
     επεξεργάζεστε απευθείας τις σελίδες του wiki στο GitHub.
5. Υπογράψτε τα commits σας με `git commit -s` (δείτε παρακάτω).

## Άδεια των συνεισφορών

Η Karta διατίθεται με την άδεια [GNU AGPL‑3.0](LICENSE). Υποβάλλοντας μια συνεισφορά
(με το `-s` στα commits σας):

1. δηλώνετε ότι η συνεισφορά είναι δική σας δουλειά, ή ότι έχετε το δικαίωμα να την
   υποβάλετε, σύμφωνα με το [Developer Certificate of Origin](https://developercertificate.org/)·
2. τη διαθέτετε με την άδεια **AGPL‑3.0**, όπως και το υπόλοιπο έργο·
3. παραχωρείτε επιπλέον στον δημιουργό του έργου (osergios) μια μη αποκλειστική,
   παγκόσμια, δωρεάν και αμετάκλητη άδεια να χρησιμοποιεί, να τροποποιεί και να διανέμει
   τη συνεισφορά σας **και με άλλους όρους**, μαζί και με εμπορικές άδειες. Έτσι το έργο
   μπορεί να προσφέρει εμπορική άδεια σε όποιον δεν μπορεί να χρησιμοποιήσει την AGPL,
   και να χρηματοδοτεί τη συνέχισή του. Η συνεισφορά σας παραμένει πάντα διαθέσιμη και με
   AGPL‑3.0, και κρατάτε τα πνευματικά σας δικαιώματα.

Αν δεν συμφωνείτε με τον όρο 3, αναφέρετέ το στο pull request πριν γίνει merge.

---

<a id="contributing-to-karta"></a>

# Contributing to Karta

Thank you for wanting to help! Every contribution counts: a bug report, a fix to the
user guide, a translation, or code.

Everyone taking part follows the [code of conduct](CODE_OF_CONDUCT.md#code-of-conduct).

## Reporting a bug or suggesting something

For **questions** ("how do I…?") use [Discussions](https://github.com/osergios/karta/discussions). Issues are for bugs and concrete proposals.

Open an [issue](https://github.com/osergios/karta/issues) and include:

- what you did, what you expected, and what happened instead;
- the mode (`dry_run`, `trial` or `production`) and the Karta version («Ρυθμίσεις» → «Έκδοση και ενημέρωση»);
- the browser and device, if it's about the shop screen.

**Never put real personal data** in issues: employee names, ΑΦΜ, Ergani credentials, PINs,
your `.env` file, or screenshots with real details. Use made‑up data.

**Security problems** must not be reported publicly. Use GitHub's
[private vulnerability reporting](https://github.com/osergios/karta/security/advisories/new).

## Development setup

```bash
git clone https://github.com/osergios/karta.git
cd karta
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

For local work, set in `.env`: `ERGANI_MODE=dry_run`,
`PUBLIC_ORIGIN=http://localhost:8000`, `DB_PATH=./data/workcard.db`, a test ΑΦΜ in
`EMPLOYER_AFM`, and any values for `CF_ACCESS_*` and `ADMIN_EMAILS`. Then:

```bash
mkdir -p data
set -a; . ./.env; set +a
PYTHONPATH=vendor uvicorn app.main:app --reload --port 8000
```

Good to know:

- The admin page (`/admin`) only accepts a Cloudflare Access token, so locally it returns
  403. To test it, use a test Cloudflare Access application (e.g. through
  `cloudflared tunnel`) on a domain of your own.
- The shop screen's registration cookie is `Secure`, and the camera needs HTTPS. To test
  the shop screen fully, use HTTPS (e.g. the same tunnel).
- **Always test in `dry_run`**, or in `trial` with an Ergani test‑environment user. Never
  send test punches to the real Ergani.

## Automated tests

The tests live in `tests/` and run in `dry_run` against a temporary database, never talking
to Ergani:

```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest
```

They also run automatically on GitHub for every pull request. If you change behaviour, add
or update the matching test. For anything that depends on the time (early arrivals,
holidays, reminders), use the `clock` fixture from `tests/conftest.py`, which freezes the
time.

## Code guidelines

- **Match the existing code**: naming, structure, comment density.
- **Screen texts in Greek**, like the rest. Code comments in English.
- **No new dependencies** without good reason. Karta stays small on purpose (FastAPI,
  SQLite, no frontend build step, no external CDNs).
- The **Content‑Security‑Policy** is strict: no inline `<script>` or `style="…"`. Put code
  in the `.js` and `.css` files.
- Database changes must apply **automatically and safely** to existing installations (see
  the `ALTER TABLE` migrations in `app/db.py`).
- Anything that touches **Ergani declarations, schedules or reports** has legal
  consequences for businesses. Explain the reasoning in the pull request and, where there
  is one, the source (law, circular, ministry guidance).
- Code taken from another project must have a **compatible license** (e.g. MIT, BSD,
  Apache‑2.0, LGPL/GPL‑3.0) and be listed in
  [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) with its license text.

## Pull requests

1. Fork the repository and branch from `main`.
2. Keep each pull request small and about one thing.
3. Run the tests (`python -m pytest`), check your change in `dry_run`, and describe in the
   pull request what you tested.
4. If something users see changes, update:
   - [`CHANGES.md`](CHANGES.md);
   - the user guide in [`docs/wiki/`](docs/wiki/), **in both languages** (e.g.
     `Kiosk.md` and `Kiosk-EN.md`). The wiki is published automatically from there, so
     don't edit the wiki pages on GitHub directly.
5. Sign off your commits with `git commit -s` (see below).

## License of contributions

Karta is licensed under the [GNU AGPL‑3.0](LICENSE). By submitting a contribution (with
`-s` on your commits):

1. you certify that the contribution is your own work, or that you have the right to
   submit it, under the [Developer Certificate of Origin](https://developercertificate.org/);
2. you license it under **AGPL‑3.0**, like the rest of the project;
3. you additionally grant the project's author (osergios) a non‑exclusive, worldwide,
   royalty‑free, irrevocable license to use, modify and distribute your contribution
   **under other terms as well**, including commercial licenses. This lets the project
   offer a commercial license to those who can't use the AGPL, and fund its future. Your
   contribution always stays available under AGPL‑3.0, and you keep your copyright.

If you don't agree with point 3, say so in the pull request before it's merged.
