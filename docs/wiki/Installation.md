**Ελληνικά** · [English](Installation-EN)

# Εγκατάσταση

> Πρώτη φορά; Δείτε την [Εύκολη εγκατάσταση, βήμα προς βήμα](Easy-Installation), με Raspberry Pi, παλιό PC ή δωρεάν server στο cloud.
> Ο **οδηγός ρύθμισης** (`setup.sh`) φτιάχνει το `.env`, το Cloudflare Tunnel και την προστασία της διαχείρισης αυτόματα.

Η Karta είναι μία μικρή διαδικτυακή υπηρεσία: Python, FastAPI και ένα μόνο αρχείο βάσης
SQLite. Τρέχει άνετα σε μικρό VPS, σε server στο σπίτι ή σε μηχάνημα του μεγέθους ενός
Raspberry Pi.

## Τι χρειάζεστε

- **Έναν server με Docker** (ή Python 3.12).
- **Ένα όνομα domain με HTTPS**, π.χ. `karta.tokatastimamou.gr`. Το HTTPS είναι
  υποχρεωτικό: το cookie εγγραφής της οθόνης του καταστήματος είναι `Secure`, και οι
  browsers επιτρέπουν την κάμερα (για το σκανάρισμα QR) μόνο σε σελίδες HTTPS.
- **Cloudflare Access** μπροστά από το `/admin`. Είναι δωρεάν για μικρές ομάδες. Η Karta
  δεν έχει δικό της κωδικό διαχειριστή: εμπιστεύεται την ταυτότητα που υπογράφει το
  Cloudflare Access και την ελέγχει με το `ADMIN_EMAILS`. Δείτε
  [Ασφάλεια και προσωπικά δεδομένα](Security-and-Privacy).
- **Έναν χρήστη web services του ΕΡΓΑΝΗ** για την επιχείρηση. Για δοκιμές, και έναν
  χρήστη για το δοκιμαστικό περιβάλλον του ΕΡΓΑΝΗ (`trialv2eservices.yeka.gr`). Δείτε
  [Ρυθμίσεις server](Configuration).

## 1. Ετοιμάστε το `.env`

```bash
mkdir karta && cd karta
curl -fsSLO https://raw.githubusercontent.com/osergios/karta/main/.env.example
cp .env.example .env
nano .env        # συμπληρώστε το· κρατήστε ERGANI_MODE=dry_run προς το παρόν
```

Κάθε ρύθμιση εξηγείται στις [Ρυθμίσεις server](Configuration). Χρειάζεστε τουλάχιστον:
`CF_ACCESS_TEAM_DOMAIN`, `CF_ACCESS_AUD`, `ADMIN_EMAILS`, `PUBLIC_ORIGIN` και `PIN_KEY`.
ΑΦΜ, στοιχεία σύνδεσης στο ΕΡΓΑΝΗ, λειτουργία και ειδοποιήσεις μπορούν να μπουν εδώ ή στη
σελίδα διαχείρισης («Ρυθμίσεις»).

## 2. Εκκίνηση

Με το έτοιμο image από το GitHub (amd64 και arm64, π.χ. Raspberry Pi):

```bash
docker run -d --name karta --restart unless-stopped \
  --env-file .env -p 127.0.0.1:8000:8000 -v karta-data:/data \
  ghcr.io/osergios/karta:latest
```

Το `latest` είναι πάντα η τελευταία έκδοση. Για να μείνετε σε συγκεκριμένη έκδοση, γράψτε
π.χ. `ghcr.io/osergios/karta:1.4`. Όλες οι εκδόσεις και οι αλλαγές τους είναι στις
[Releases](https://github.com/osergios/karta/releases).

Ή χτίστε το image μόνοι σας από τον κώδικα:

```bash
git clone https://github.com/osergios/karta.git && cd karta
cp /path/to/your/.env .env
docker build -t karta .
docker run -d --name karta --restart unless-stopped \
  --env-file .env -p 127.0.0.1:8000:8000 -v karta-data:/data karta
```

- Η βάση δεδομένων είναι το `/data/workcard.db` μέσα στο container (αλλάζει με το
  `DB_PATH`).
- Το container τρέχει ως χρήστης χωρίς δικαιώματα διαχειριστή (UID 10001). Αν
  χρησιμοποιήσετε φάκελο του server αντί για named volume, βεβαιωθείτε ότι ο χρήστης
  αυτός μπορεί να γράψει εκεί.
- Ελέγξτε ότι λειτουργεί με `curl http://127.0.0.1:8000/healthz`.

Χωρίς Docker:

```bash
pip install -r requirements.txt
PYTHONPATH=vendor uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-server-header
```

## 3. Βάλτε την πίσω από HTTPS

Δουλεύει οποιοσδήποτε reverse proxy (Caddy, nginx, Traefik), αλλά και το **Cloudflare
Tunnel** (`cloudflared`), που δεν χρειάζεται ανοιχτές θύρες. Κατευθύνετε το domain σας
στο `http://127.0.0.1:8000`.

Αν ο proxy σας δίνει τη διεύθυνση του χρήστη, περάστε τη στην κεφαλίδα `X-Real-IP`. Η
Karta καταγράφει την IP κάθε χτυπήματος. Παραδείγματα για Caddy και nginx:
[Πίσω από δικό σας reverse proxy](Reverse-Proxy).

## 4. Προστατέψτε το `/admin` με Cloudflare Access

1. Στο Cloudflare Zero Trust, δημιουργήστε μια **self‑hosted application** για το
   `karta.tokatastimamou.gr/admin` (διαδρομή `admin`, ώστε να καλύπτει το `/admin` και ό,τι
   είναι κάτω από αυτό).
2. Προσθέστε μια πολιτική (policy) που επιτρέπει μόνο τα δικά σας email.
3. Αντιγράψτε το **Audience (AUD) tag** της εφαρμογής στο `CF_ACCESS_AUD`, και το team
   domain σας (π.χ. `yourteam.cloudflareaccess.com`) στο `CF_ACCESS_TEAM_DOMAIN`.
4. Βάλτε τα ίδια email στο `ADMIN_EMAILS`.

Αφήστε το υπόλοιπο site (οθόνη καταστήματος, `/enroll`, `/c/…`, `/api/…`) **έξω** από το
Cloudflare Access. Αυτές οι σελίδες έχουν δική τους προστασία· δείτε
[Ασφάλεια και προσωπικά δεδομένα](Security-and-Privacy).

## 5. Πρώτη σύνδεση και αρχικές ρυθμίσεις

1. Ανοίξτε το `https://karta.tokatastimamou.gr/admin` και συνδεθείτε μέσω Cloudflare
   Access.
2. **«Ρυθμίσεις» → «Επιχείρηση και σύνδεση με το ΕΡΓΑΝΗ»**: ΑΦΜ, παράρτημα και χρήστης
   ΕΡΓΑΝΗ, με «Δοκιμή σύνδεσης». Μετά **«Ρυθμίσεις» → «ΕΡΓΑΝΗ» → «Έλεγχος ΕΡΓΑΝΗ»**: διαβάζει από το ΕΡΓΑΝΗ τα στοιχεία
   του εργοδότη, τα παραρτήματα και το τρέχον προσωπικό, και σας αφήνει να φέρετε τους
   εργαζόμενους. Μόνο έτσι προστίθεται προσωπικό. Κάθε νέος εργαζόμενος παίρνει PIN 6
   ψηφίων, που εμφανίζεται μία φορά: σημειώστε το ή δώστε το στον εργαζόμενο.
3. **«Ρυθμίσεις» → «Στοιχεία επιχείρησης»**: όνομα, σύντομο όνομα, χρώματα (έτοιμα θέματα
   ή δικά σας) και λογότυπο (δείτε [Ρυθμίσεις](Admin-Settings#στοιχεία-επιχείρησης)).
4. **«Ωράρια & αργίες»**: ελέγξτε το ωράριο κάθε εργαζόμενου (δείτε
   [Ωράρια και αργίες](Admin-Schedules-and-Holidays)).
5. **«Ρυθμίσεις» → «Συσκευές» → «Δημιουργία κωδικού εγγραφής»**: γράψτε το laptop ή
   το tablet του καταστήματος (δείτε [Οθόνη καταστήματος](Kiosk)).
6. Όταν όλα είναι σωστά, ακολουθήστε την
   [Έναρξη κανονικής λειτουργίας](Going-Live).

## Αντίγραφα ασφαλείας

Τα πάντα (εργαζόμενοι, PIN σε κρυπτογραφική σύνοψη, χτυπήματα, ωράρια, ρυθμίσεις,
λογότυπο) βρίσκονται στο ένα αρχείο SQLite. Τα χτυπήματα πρέπει να φυλάσσονται για
τουλάχιστον 5 χρόνια: κρατάτε τακτικά αντίγραφα του volume `/data`, και εκτός μηχανήματος,
κρυπτογραφημένα, γιατί περιέχουν στοιχεία του προσωπικού. Φυλάξτε επίσης αντίγραφο του
`.env`, ιδίως του `PIN_KEY`. Το `setup.sh` στήνει το νυχτερινό αντίγραφο στο μηχάνημα,
το αντίγραφο σε USB και την επαναφορά από το τερματικό. Το κρυπτογραφημένο αντίγραφο στο
cloud ρυθμίζεται στις **«Ρυθμίσεις» → «Αντίγραφα ασφαλείας»** και λειτουργεί με κάθε
εγκατάσταση, με ή χωρίς `setup.sh`. Δείτε [Αντίγραφα ασφαλείας και επαναφορά](Backups).

Για να αντιγράψετε τη βάση ενώ η εφαρμογή τρέχει, χρησιμοποιήστε την εντολή backup της
SQLite και όχι απλό `cp`:

```bash
docker exec karta python -c "import sqlite3; s=sqlite3.connect('/data/workcard.db'); d=sqlite3.connect('/data/backup.db'); s.backup(d)"
```

## Ενημέρωση σε νέα έκδοση

Με το `setup.sh` αρκεί το **«Ενημέρωση τώρα»** στη σελίδα διαχείρισης («Ρυθμίσεις» →
«Έκδοση και ενημέρωση»). Αλλιώς, δείτε τι άλλαξε στις
[Releases](https://github.com/osergios/karta/releases), και μετά:

```bash
docker pull ghcr.io/osergios/karta:latest
docker rm -f karta && docker run -d --name karta ... (η ίδια εντολή όπως παραπάνω)
```

Αν χτίζετε μόνοι σας το image: `git pull`, `docker build -t karta .` και ξανά το
`docker run`.

Οι αλλαγές στη βάση εφαρμόζονται αυτόματα στην εκκίνηση. Μετά από τέτοια χειροκίνητη
ενημέρωση, πατήστε **«Σήμερα» → «Οθόνη καταστήματος και αποστολή» → «Ανανέωση οθόνης»**
για να ξαναφορτώσει μόνη της η οθόνη του καταστήματος. Με το «Ενημέρωση τώρα» αυτό
γίνεται μόνο του.
