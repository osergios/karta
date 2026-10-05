# Πολιτική ασφαλείας

**Ελληνικά** · [English](#security-policy)

## Αναφορά προβλήματος ασφαλείας

Αν βρείτε κενό ασφαλείας στην Karta, **μην το αναφέρετε δημόσια** (issue, συζήτηση,
κοινωνικά δίκτυα). Χρησιμοποιήστε την
[ιδιωτική αναφορά ευπάθειας](https://github.com/osergios/karta/security/advisories/new)
του GitHub. Την αναφορά τη βλέπει μόνο ο συντηρητής του έργου.

Γράψτε:

- τι βρήκατε και ποιο τμήμα αφορά (οθόνη καταστήματος, σελίδα διαχείρισης, αποστολή στο
  ΕΡΓΑΝΗ, κάρτες QR…)·
- βήματα για να αναπαραχθεί, σε λειτουργία `dry_run`·
- την έκδοση (commit) της Karta·
- τι θα μπορούσε να κάνει κάποιος που το εκμεταλλεύεται.

**Μη στέλνετε πραγματικά προσωπικά δεδομένα** (ονόματα εργαζομένων, ΑΦΜ, κωδικούς ΕΡΓΑΝΗ,
PIN, αρχεία `.env` ή βάσεις δεδομένων). Χρησιμοποιήστε φανταστικά στοιχεία.

## Τι να περιμένετε

- Επιβεβαίωση ότι λάβαμε την αναφορά, συνήθως μέσα σε λίγες ημέρες.
- Ενημέρωση για το αν το πρόβλημα επιβεβαιώθηκε και πότε αναμένεται διόρθωση.
- Αφού διορθωθεί, δημοσιεύεται ανακοίνωση ασφαλείας (security advisory). Αν το θέλετε,
  αναφέρεται το όνομά σας ως αυτού που το βρήκε.

Η Karta είναι έργο ενός ατόμου, χωρίς αμοιβή για αναφορές ευπαθειών (bug bounty).

## Ποιες εκδόσεις υποστηρίζονται

Διορθώσεις ασφαλείας γίνονται μόνο στον κλάδο `main`. Κρατάτε την εγκατάστασή σας
ενημερωμένη (δείτε [Εγκατάσταση → Ενημέρωση](https://github.com/osergios/karta/wiki/Installation)).

## Ασφάλεια της δικής σας εγκατάστασης

Οι περισσότεροι κίνδυνοι εξαρτώνται από το πώς είναι στημένη η Karta: μόνο μέσω HTTPS,
σελίδα διαχείρισης πίσω από Cloudflare Access, `.env` ιδιωτικό, κρυπτογραφημένα αντίγραφα
της βάσης. Δείτε τη σελίδα
[Ασφάλεια και προσωπικά δεδομένα](https://github.com/osergios/karta/wiki/Security-and-Privacy)
του wiki.

---

<a id="security-policy"></a>

# Security policy

## Reporting a security problem

If you find a security vulnerability in Karta, **please don't report it publicly** (issue,
discussion, social media). Use GitHub's
[private vulnerability reporting](https://github.com/osergios/karta/security/advisories/new).
Only the project's maintainer can see the report.

Please include:

- what you found and which part it affects (shop screen, admin page, Ergani submission,
  QR cards…);
- steps to reproduce it, in `dry_run` mode;
- the Karta version (commit);
- what an attacker could do with it.

**Don't send real personal data** (employee names, ΑΦΜ, Ergani credentials, PINs, `.env`
files or databases). Use made‑up data.

## What to expect

- An acknowledgement that the report was received, usually within a few days.
- An update on whether the problem is confirmed and when a fix is expected.
- Once fixed, a security advisory is published. If you like, you're credited as the person
  who found it.

Karta is a one‑person project, with no paid bug bounty.

## Supported versions

Security fixes are made on the `main` branch only. Keep your installation up to date (see
[Installation → Updating](https://github.com/osergios/karta/wiki/Installation-EN)).

## Securing your own installation

Most risks depend on how Karta is set up: HTTPS only, the admin page behind Cloudflare
Access, a private `.env`, encrypted database backups. See the wiki page
[Security and privacy](https://github.com/osergios/karta/wiki/Security-and-Privacy-EN).
