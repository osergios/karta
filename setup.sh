#!/usr/bin/env bash
# Karta: οδηγός εγκατάστασης / setup helper
#
#   ./setup.sh          ερωτήσεις → .env → εκκίνηση → αντίγραφα ασφαλείας
#   ./setup.sh check    έλεγχος: ΕΡΓΑΝΗ, Cloudflare, διεύθυνση, προστασία διαχείρισης
#
# Χρειάζεται μόνο Docker. Ο οδηγός τρέχει μέσα στο image της Karta, ως ο δικός σας χρήστης.
set -euo pipefail

IMAGE="${KARTA_IMAGE:-ghcr.io/osergios/karta:latest}"
RAW="https://raw.githubusercontent.com/osergios/karta/main"
cd "$(dirname "$(readlink -f "$0")")"
# Run from the home folder (e.g. downloaded again there after reconnecting)? Everything goes in ~/karta,
# unless this home folder already holds an installation.
if [ "$PWD" = "$HOME" ] && [ ! -f .env ] && [ ! -f docker-compose.yml ]; then
  mkdir -p "$HOME/karta"
  cp -f "$0" "$HOME/karta/setup.sh" 2>/dev/null || true
  cd "$HOME/karta"
  printf 'Η Karta εγκαθίσταται στον φάκελο %s\n' "$PWD"
fi

bold=$(tput bold 2>/dev/null || true); norm=$(tput sgr0 2>/dev/null || true)
say()  { printf '%s\n' "$*"; }
step() { printf '\n%s%s%s\n' "$bold" "$*" "$norm"; }
ask_yes() {  # ask_yes "Ερώτηση" -> 0 for yes (default yes)
  local a; read -r -p "  $1 (Ν/ο): " a || return 1
  case "${a,,}" in ""|ν|ναι|nai|y|yes) return 0 ;; *) return 1 ;; esac   # "n" (English) means no
}

# ---- Docker -----------------------------------------------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
  say "Δεν βρέθηκε το Docker σε αυτό το μηχάνημα."
  if ask_yes "Να εγκατασταθεί τώρα; (θα ζητηθεί ο κωδικός σας)"; then
    curl -fsSL https://get.docker.com | sudo sh
    sudo usermod -aG docker "$USER"
    say ""
    say "Το Docker εγκαταστάθηκε. Αποσυνδεθείτε (exit), συνδεθείτε ξανά και τρέξτε πάλι:"
    say "  cd $PWD && ./setup.sh"
  else
    say "Οδηγίες: https://github.com/osergios/karta/wiki/Easy-Installation"
  fi
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  say "Το Docker υπάρχει αλλά ο χρήστης σας δεν έχει πρόσβαση."
  say "Τρέξτε:  sudo usermod -aG docker \$USER   , αποσυνδεθείτε, συνδεθείτε ξανά και ξανατρέξτε:"
  say "  cd $PWD && ./setup.sh"
  exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
  say "Λείπει το «docker compose». Εγκαταστήστε το Docker με: curl -fsSL https://get.docker.com | sudo sh"
  exit 1
fi

[ -f docker-compose.yml ] || { say "Κατέβασμα docker-compose.yml…"; curl -fsSLO "$RAW/docker-compose.yml"; }
say "Κατέβασμα της τελευταίας έκδοσης της Karta…"
docker pull -q "$IMAGE" >/dev/null 2>&1 || say "  (δεν έγινε λήψη· χρησιμοποιείται η έκδοση που υπάρχει ήδη στο μηχάνημα)"

run_wizard() {
  local tty=-i; [ -t 0 ] && tty=-it
  docker run --rm $tty --user "$(id -u):$(id -g)" -e HOME=/tmp -e PYTHONPATH=/srv:/srv/vendor \
    -v "$PWD:/work" -w /work "$IMAGE" python -m app.setup "$@"
}

if [ "${1:-}" = "check" ]; then
  run_wizard check
  exit $?
fi

# ---- Ερωτήσεις → .env ---------------------------------------------------------------------------
run_wizard setup

# ---- Εκκίνηση ------------------------------------------------------------------------------------
step "Εκκίνηση"
if ask_yes "Να ξεκινήσει (ή να ξαναξεκινήσει) η Karta τώρα;"; then
  docker compose up -d
  say "  Αναμονή να ξεκινήσει…"
  for _ in $(seq 1 30); do
    if docker compose exec -T karta python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz',timeout=3).status==200 else 1)" >/dev/null 2>&1; then
      say "  ✓ Η Karta τρέχει."
      break
    fi
    sleep 2
  done
fi

# ---- Αντίγραφα ασφαλείας ------------------------------------------------------------------------
step "Αντίγραφα ασφαλείας"
if [ ! -f backup.sh ]; then
  cat > backup.sh <<'SH'
#!/bin/sh
# Karta: αντίγραφο της βάσης με την ημερομηνία· κρατά τα 30 τελευταία
set -e
cd "$(dirname "$0")"
mkdir -p backups
docker compose exec -T karta python -c "import sqlite3; s=sqlite3.connect('/data/workcard.db'); d=sqlite3.connect('/data/backup.db'); s.backup(d); d.close()"
docker compose cp karta:/data/backup.db "backups/karta-$(date +%F).db"
ls -1t backups/karta-*.db | tail -n +31 | xargs -r rm --
SH
  chmod +x backup.sh
  say "  ✓ Δημιουργήθηκε το backup.sh"
fi
if crontab -l 2>/dev/null | grep -q "$PWD/backup.sh"; then
  say "  ✓ Το αυτόματο αντίγραφο κάθε βράδυ είναι ήδη ρυθμισμένο."
elif command -v crontab >/dev/null 2>&1 && ask_yes "Να γίνεται αυτόματα αντίγραφο κάθε βράδυ στις 23:30;"; then
  ( crontab -l 2>/dev/null; echo "30 23 * * * $PWD/backup.sh >/dev/null 2>&1" ) | crontab -
  say "  ✓ Ρυθμίστηκε. Τα αντίγραφα μπαίνουν στον φάκελο $PWD/backups"
fi
say "  Θυμηθείτε: αντιγράφετε τακτικά τον φάκελο backups και το .env και ΕΚΤΟΣ του μηχανήματος (USB, άλλος υπολογιστής)."

# ---- Επόμενα βήματα -----------------------------------------------------------------------------
origin=$(grep -E '^PUBLIC_ORIGIN=' .env | cut -d= -f2- || true)
step "Επόμενα βήματα"
say "  1. Ανοίξτε ${origin:-τη διεύθυνσή σας}/admin και συνδεθείτε με το email σας."
say "  2. Ακολουθήστε τα «Πρώτα βήματα» στην καρτέλα «Σήμερα»."
say "  3. Σε ένα λεπτό, ελέγξτε ότι όλα είναι σωστά με:  ./setup.sh check"
say "  Βοήθεια: https://github.com/osergios/karta/discussions/categories/q-a"
