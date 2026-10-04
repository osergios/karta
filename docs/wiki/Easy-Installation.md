🇬🇷 **Ελληνικά** · 🇬🇧 [English](Easy-Installation-EN)

# Εύκολη εγκατάσταση, βήμα προς βήμα

Αυτός ο οδηγός είναι για όσους **δεν** είναι προγραμματιστές. Στο τέλος θα έχετε την Karta
να τρέχει σε ένα μικρό μηχάνημα, με ασφαλή σύνδεση (HTTPS) στο δικό σας όνομα, π.χ.
`https://karta.tokatastimamou.gr`, **χωρίς** να πειράξετε ρυθμίσεις στο router.

Θα χρειαστείτε περίπου **1–2 ώρες** την πρώτη φορά. Αν κολλήσετε κάπου, δείτε τις
[Συχνές ερωτήσεις](FAQ) ή ανοίξτε ένα [issue](https://github.com/osergios/karta/issues/new/choose).

> Αν είστε πιο έμπειρος, η σύντομη έκδοση είναι στην [Εγκατάσταση](Installation).

---

## Βήμα 0: Τι θα χρειαστείτε

| | Τι | Κόστος |
|---|---|---|
| 1 | **Ένα όνομα (domain)**, π.χ. `tokatastimamou.gr` | περίπου 10–20 € τον χρόνο |
| 2 | **Ένα μηχάνημα που μένει ανοιχτό** (δείτε παρακάτω) | 0 € (παλιό PC ή δωρεάν cloud) ή ~60–100 € για Raspberry Pi |
| 3 | **Δωρεάν λογαριασμό Cloudflare** | 0 € |
| 4 | **Χρήστη web services του ΕΡΓΑΝΗ** (σας τον φτιάχνει ο λογιστής ή τον φτιάχνετε στο ΕΡΓΑΝΗ) | 0 € |

### «Γίνεται χωρίς domain;»

Δυστυχώς **όχι** για κανονική χρήση, για δύο λόγους:

- Η σελίδα διαχείρισης προστατεύεται από το **Cloudflare Access**, που λειτουργεί μόνο σε
  domain που έχετε εσείς στο Cloudflare.
- Η κάμερα για τις κάρτες QR και το cookie της οθόνης καταστήματος δουλεύουν μόνο με
  **HTTPS**, που το δίνει δωρεάν το Cloudflare για το domain σας.

Το domain είναι το **μόνο** σίγουρο έξοδο. Όλα τα υπόλοιπα μπορούν να είναι δωρεάν.

### Ποιο μηχάνημα;

| Επιλογή | Υπέρ | Κατά |
|---|---|---|
| **A. Raspberry Pi 4 ή 5** (2 GB RAM και πάνω), στο κατάστημα ή στο σπίτι | Μικρό, αθόρυβο, ~5 W ρεύμα (λίγα ευρώ τον χρόνο). Τα δεδομένα μένουν σε εσάς. | Κόστος αγοράς. Αν κοπεί ρεύμα ή internet εκεί, η Karta δεν είναι διαθέσιμη. |
| **B. Παλιό laptop ή μικρό PC** | Δωρεάν αν το έχετε ήδη. Το laptop έχει μπαταρία για διακοπές ρεύματος. | Περισσότερο ρεύμα· ίδιο θέμα με το internet. |
| **C. Δωρεάν cloud: Oracle Cloud «Always Free»** | Πάντα ανοιχτό, γρήγορο internet, 0 €. | Θέλει κάρτα για επιβεβαίωση. Η εγγραφή μερικές φορές λέει «out of capacity». Το Oracle μπορεί να κλείσει μηχανήματα που δεν χρησιμοποιούνται σχεδόν καθόλου· κρατάτε αντίγραφα. |

**Προσοχή στα προσωπικά δεδομένα (GDPR):** η Karta κρατά στοιχεία του προσωπικού σας. Αν
διαλέξετε cloud, διαλέξτε **περιοχή μέσα στην Ευρωπαϊκή Ένωση** (π.χ. Frankfurt,
Amsterdam, Milan).

**Πού να μπει;** Αν το μηχάνημα είναι στο κατάστημα, η οθόνη του καταστήματος μιλά με την
Karta μέσα από το internet του καταστήματος. Αν πέσει το internet, η οθόνη το λέει και οι
εργαζόμενοι χτυπούν από την εφαρμογή του ΕΡΓΑΝΗ. Αυτό ισχύει όπου κι αν βρίσκεται η Karta.

---

## Βήμα 1: Πάρτε domain και βάλτε το στο Cloudflare

1. Φτιάξτε δωρεάν λογαριασμό στο [cloudflare.com](https://dash.cloudflare.com/sign-up).
2. Αγοράστε ένα domain:
   - **`.com` / `.eu` κ.λπ.:** απευθείας από το Cloudflare (**Domain Registration →
     Register Domains**), σε τιμή κόστους. Μπαίνει αυτόματα στο Cloudflare: πηγαίνετε στο
     βήμα 2.
   - **`.gr`:** από έναν Έλληνα καταχωρητή (registrar). Μετά, στο Cloudflare πατήστε
     **Add a domain**, διαλέξτε το **Free** πλάνο, και το Cloudflare σας δίνει δύο
     **nameservers**. Στη σελίδα του καταχωρητή, αλλάξτε τους nameservers του domain σε
     αυτούς τους δύο. Η αλλαγή θέλει από λίγα λεπτά έως 24 ώρες· το Cloudflare σας στέλνει
     email όταν είναι έτοιμο.

Αν έχετε ήδη domain για το site σας, μπορείτε να χρησιμοποιήσετε ένα **υπο‑όνομα** του,
π.χ. `karta.tokatastimamou.gr`, χωρίς να επηρεαστεί το site.

---

## Βήμα 2: Ετοιμάστε το μηχάνημα

Διαλέξτε **μία** από τις τρεις επιλογές.

### Επιλογή A: Raspberry Pi

1. Χρειάζεστε: Raspberry Pi 4 ή 5, το τροφοδοτικό του, κάρτα microSD 32 GB καλής ποιότητας
   (ή, καλύτερα, δίσκο SSD με USB), και καλώδιο δικτύου (προτιμότερο από Wi‑Fi).
2. Σε έναν υπολογιστή, κατεβάστε το [Raspberry Pi Imager](https://www.raspberrypi.com/software/).
3. Διαλέξτε: συσκευή → το μοντέλο σας· λειτουργικό → **Raspberry Pi OS Lite (64‑bit)**·
   αποθήκευση → την κάρτα σας.
4. Στις ρυθμίσεις (**Edit settings**) ορίστε: όνομα μηχανήματος (π.χ. `karta`), **όνομα
   χρήστη και κωδικό**, και στην καρτέλα **Services** ενεργοποιήστε το **SSH** με κωδικό.
5. Γράψτε την κάρτα, βάλτε τη στο Pi, συνδέστε καλώδιο δικτύου και ρεύμα. Περιμένετε 2
   λεπτά.

### Επιλογή B: Παλιό PC ή laptop

1. Κατεβάστε το [Ubuntu Server LTS](https://ubuntu.com/download/server) και γράψτε το σε
   ένα USB με το [balenaEtcher](https://etcher.balena.io/).
2. Ξεκινήστε το PC από το USB και εγκαταστήστε το (οι προεπιλογές είναι εντάξει).
   Ορίστε όνομα χρήστη και κωδικό, και τσεκάρετε **Install OpenSSH server**.
3. Σε laptop: ρυθμίστε να **μην κοιμάται όταν κλείνει το καπάκι**. Ρωτήστε μας αν
   χρειάζεστε βοήθεια· είναι μία ρύθμιση.

### Επιλογή C: Oracle Cloud Always Free

1. Εγγραφείτε στο [oracle.com/cloud/free](https://www.oracle.com/cloud/free/). Στην εγγραφή
   διαλέξτε **Home Region** μέσα στην ΕΕ (δεν αλλάζει αργότερα).
2. **Compute → Instances → Create instance**:
   - Image: **Ubuntu** (22.04 ή νεότερο)·
   - Shape: **Ampere (VM.Standard.A1.Flex)**, 1 OCPU και 6 GB μνήμη (μέσα στα δωρεάν όρια)·
   - κατεβάστε το **SSH key** που σας δίνει (θα το χρειαστείτε για να συνδεθείτε).
3. Πατήστε **Create**. Σημειώστε τη **Public IP** του μηχανήματος.

Δεν χρειάζεται να ανοίξετε καμία θύρα στο firewall του Oracle: το tunnel του βήματος 4
συνδέεται προς τα έξω.

---

## Βήμα 3: Συνδεθείτε στο μηχάνημα και εγκαταστήστε το Docker

Από τον υπολογιστή σας ανοίξτε ένα τερματικό (Windows: **PowerShell**· Mac: **Terminal**)
και συνδεθείτε:

```bash
ssh ONOMA_XRISTI@karta.local          # Raspberry Pi στο ίδιο δίκτυο
ssh ONOMA_XRISTI@192.168.1.50         # ή με τη διεύθυνση IP του μηχανήματος
ssh -i kleidi.key ubuntu@PUBLIC_IP    # Oracle Cloud
```

Μετά, αντιγράψτε και τρέξτε αυτές τις εντολές μία μία:

```bash
sudo apt update && sudo apt -y upgrade
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
exit
```

Συνδεθείτε ξανά με `ssh` (ώστε να ισχύσει η τελευταία εντολή) και ελέγξτε:

```bash
docker run --rm hello-world
```

Αν δείτε «Hello from Docker!», όλα είναι εντάξει.

---

## Βήμα 4: Φτιάξτε το Cloudflare Tunnel

Το tunnel είναι μια ασφαλής «γραμμή» από το μηχάνημά σας προς το Cloudflare. Έτσι η Karta
είναι προσβάσιμη στο `https://karta.tokatastimamou.gr` χωρίς ανοιχτές θύρες στο router.

1. Στο Cloudflare, ανοίξτε το **Zero Trust** (από το αριστερό μενού). Την πρώτη φορά:
   διαλέξτε ένα **team name** (π.χ. `tokatastimamou`) και το **Free** πλάνο (έως 50
   χρήστες). Μπορεί να ζητήσει κάρτα, αλλά το Free πλάνο δεν χρεώνει.
2. Πηγαίνετε στο **Networks → Tunnels → Create a tunnel → Cloudflared**. Δώστε όνομα
   (π.χ. `karta`) και πατήστε **Save**.
3. Στη σελίδα που ανοίγει υπάρχει μια εντολή με ένα μακρύ **token** (μετά το `--token`).
   **Αντιγράψτε μόνο το token** και φυλάξτε το· δεν χρειάζεται να τρέξετε την εντολή.
4. Πατήστε **Next**. Στο **Public hostname**:
   - Subdomain: `karta` · Domain: το domain σας·
   - Service: **Type** `HTTP`, **URL** `karta:8000`.
5. Πατήστε **Save tunnel**.

> Τα ονόματα των μενού του Cloudflare αλλάζουν κάπου κάπου. Αν δεν βρίσκετε κάτι, ψάξτε
> «Tunnels» μέσα στο Zero Trust.

---

## Βήμα 5: Προστατέψτε τη σελίδα διαχείρισης (Cloudflare Access)

1. Στο Zero Trust: **Access → Applications → Add an application → Self‑hosted**.
2. Όνομα: `Karta admin`. Στο **Public hostname / Application domain**: subdomain `karta`,
   domain το δικό σας, και στο **Path** γράψτε `admin`.
3. Προσθέστε **policy**: Action **Allow**, κανόνας **Emails** → το δικό σας email (και όποιου
   άλλου θέλετε να έχει πρόσβαση).
4. Αποθηκεύστε. Ως τρόπος σύνδεσης αρκεί ο προκαθορισμένος **One‑time PIN** (σας έρχεται
   κωδικός στο email).
5. Ανοίξτε την εφαρμογή που φτιάξατε και αντιγράψτε το **Application Audience (AUD) Tag**.
   Θα το χρειαστείτε στο επόμενο βήμα.

---

## Βήμα 6: Κατεβάστε και ρυθμίστε την Karta

Στο μηχάνημα (μέσω `ssh`):

```bash
mkdir ~/karta && cd ~/karta
curl -fsSLO https://raw.githubusercontent.com/osergios/karta/main/docker-compose.yml
curl -fsSL  https://raw.githubusercontent.com/osergios/karta/main/.env.example -o .env
python3 -c "import os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
nano .env
```

Η τρίτη εντολή τυπώνει ένα τυχαίο κλειδί: αντιγράψτε το για το `PIN_KEY`. Στο `nano`
συμπληρώστε (μετακινηθείτε με τα βελάκια):

| Γραμμή | Τι βάζετε |
|---|---|
| `ERGANI_MODE=` | `dry_run` (στην αρχή **πάντα** αυτό) |
| `ERGANI_USERNAME=` / `ERGANI_PASSWORD=` | ο χρήστης web services του ΕΡΓΑΝΗ |
| `EMPLOYER_AFM=` | το ΑΦΜ της επιχείρησης |
| `BRANCH_NUMBER=` | ο αριθμός παραρτήματος (συνήθως `0`) |
| `CF_ACCESS_TEAM_DOMAIN=` | `tokatastimamou.cloudflareaccess.com` (το team name σας + `.cloudflareaccess.com`) |
| `CF_ACCESS_AUD=` | το AUD tag του βήματος 5 |
| `ADMIN_EMAILS=` | το email σας (το ίδιο με την policy) |
| `PUBLIC_ORIGIN=` | `https://karta.tokatastimamou.gr` |
| `PIN_KEY=` | το κλειδί που τύπωσε η εντολή |
| `TUNNEL_TOKEN=` | το token του βήματος 4 |

Αποθηκεύστε με **Ctrl+O**, **Enter**, και βγείτε με **Ctrl+X**. Το `.env` περιέχει
κωδικούς: μην το στείλετε πουθενά.

Τα `NTFY_*` (ειδοποιήσεις στο κινητό) μπορείτε να τα συμπληρώσετε αργότερα· δείτε
[Ειδοποιήσεις](Alerts-and-Reminders).

---

## Βήμα 7: Ξεκινήστε την Karta

```bash
cd ~/karta
docker compose up -d
docker compose ps
```

Και οι δύο γραμμές (`karta` και `cloudflared`) πρέπει να γράφουν **running** ή **Up**.
Μετά από ένα λεπτό, ανοίξτε στον browser:

- `https://karta.tokatastimamou.gr/healthz` → πρέπει να δείτε `{"ok":true,"mode":"dry_run"}`.
- `https://karta.tokatastimamou.gr/admin` → το Cloudflare ζητά το email σας, σας στέλνει
  κωδικό, και μετά βλέπετε τη σελίδα διαχείρισης.

Η Karta ξεκινά μόνη της κάθε φορά που ανοίγει το μηχάνημα.

**Κάτι δεν πάει καλά;** Δείτε τι λέει:

```bash
docker compose logs --tail 50 karta
docker compose logs --tail 50 cloudflared
```

Συνηθισμένα λάθη: λάθος ή κενή τιμή στο `.env` (η Karta γράφει ποια λείπει), λάθος token
στο tunnel, ή λάθος `PUBLIC_ORIGIN` (πρέπει να είναι ακριβώς η διεύθυνση, με `https://`
και χωρίς `/` στο τέλος).

---

## Βήμα 8: Πρώτες ρυθμίσεις και η οθόνη του καταστήματος

Συνεχίστε από το [Εγκατάσταση → Πρώτη σύνδεση και αρχικές ρυθμίσεις](Installation#5-πρώτη-σύνδεση-και-αρχικές-ρυθμίσεις):
φέρνετε το προσωπικό από το ΕΡΓΑΝΗ, βάζετε το όνομα και το λογότυπο, ελέγχετε τα ωράρια
και γράφετε το laptop του καταστήματος ([Οθόνη καταστήματος](Kiosk)).

Όταν όλα δουλεύουν, ακολουθήστε την [Έναρξη κανονικής λειτουργίας](Going-Live) για να
περάσετε από το `dry_run` στο πραγματικό ΕΡΓΑΝΗ.

---

## Βήμα 9: Αντίγραφα ασφαλείας (σημαντικό!)

Όλα τα δεδομένα είναι σε ένα αρχείο. Αυτές οι εντολές φτιάχνουν ένα μικρό script που
κρατά αντίγραφο με την ημερομηνία (και σβήνει όσα είναι παλαιότερα από τα 30 τελευταία), και
το δοκιμάζουν μία φορά:

```bash
cat > ~/karta/backup.sh <<'SH'
#!/bin/sh
# Karta: nightly copy of the database, keeping the last 30
set -e
cd "$(dirname "$0")"
mkdir -p backups
docker compose exec -T karta python -c "import sqlite3; s=sqlite3.connect('/data/workcard.db'); d=sqlite3.connect('/data/backup.db'); s.backup(d); d.close()"
docker compose cp karta:/data/backup.db "backups/karta-$(date +%F).db"
ls -1t backups/karta-*.db | tail -n +31 | xargs -r rm --
SH
chmod +x ~/karta/backup.sh
~/karta/backup.sh && ls ~/karta/backups
```

Για να γίνεται **αυτόματα κάθε βράδυ** στις 23:30, γράψτε `crontab -e` (την πρώτη φορά
διαλέξτε `nano`) και προσθέστε στο τέλος αυτή τη γραμμή:

```text
30 23 * * * $HOME/karta/backup.sh
```

Το αντίγραφο πρέπει να φεύγει και **από το μηχάνημα**: αντιγράψτε τακτικά τον φάκελο
`backups` σε USB ή σε άλλον υπολογιστή, και φυλάξτε το `.env`. Αν χαλάσει η κάρτα του
Raspberry Pi, χωρίς αντίγραφο χάνονται τα δεδομένα.

---

## Ενημέρωση σε νέα έκδοση

Όταν βγει νέα έκδοση ([Releases](https://github.com/osergios/karta/releases)):

```bash
cd ~/karta
docker compose pull
docker compose up -d
```

Μετά πατήστε **«Σήμερα» → «Οθόνη καταστήματος και αποστολή» → «Ανανέωση οθόνης»**.
