#!/usr/bin/env bash
# Karta: οδηγός εγκατάστασης / setup helper
#
#   ./setup.sh          διεύθυνση και Cloudflare → .env → εκκίνηση → αντίγραφα ασφαλείας
#   ./setup.sh check    έλεγχος: ΕΡΓΑΝΗ, Cloudflare, διεύθυνση, προστασία διαχείρισης
#   ./setup.sh usb      αντίγραφα ασφαλείας και σε USB stick
#   ./setup.sh cloud    αντίγραφα ασφαλείας κρυπτογραφημένα σε cloud (Google Drive, Dropbox, Backblaze B2…)
#   ./setup.sh restore  επαναφορά από αντίγραφο (από το μηχάνημα, USB ή cloud)
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

# ---- Αντίγραφα ασφαλείας: backup.sh, USB, cloud -----------------------------------------------
set_conf() {  # set_conf KEY value -> backup.conf (read by backup.sh)
  touch backup.conf
  grep -v "^$1=" backup.conf > backup.conf.tmp || true
  printf '%s="%s"\n' "$1" "$2" >> backup.conf.tmp
  mv backup.conf.tmp backup.conf
}

write_backup_script() {
  # ours (or missing): (re)write it, so an update of setup.sh also updates the backup
  if [ -f backup.sh ] && ! grep -q "^# Karta" backup.sh; then
    say "  Το backup.sh δεν είναι του οδηγού: δεν το αλλάζω."
    return
  fi
  cat > backup.sh <<'SH'
#!/bin/sh
# Karta backup — written by ./setup.sh (it rewrites this file; your settings are in backup.conf).
# Every night, a copy of the whole database (every punch since the start) in backups/:
#   daily/   the last 30 days    monthly/ the last copy of each month, 24 months    yearly/ one per year, kept
# and, when set up, the same on a USB stick (./setup.sh usb) and encrypted in the cloud (./setup.sh cloud).
set -u
cd "$(dirname "$0")" || exit 1
USB_DIR=""; CLOUD_REMOTE=""
[ -f backup.conf ] && . ./backup.conf
mkdir -p backups/daily backups/monthly backups/yearly
for f in backups/karta-*.db; do [ -f "$f" ] && mv -- "$f" backups/daily/; done     # copies of the first version
[ -t 1 ] || exec >> backups/backup.log 2>&1
echo "== $(date '+%F %T')"
today=$(date +%F); month=$(date +%Y-%m); year=$(date +%Y)

keep() {  # keep DIR N: delete the oldest copies beyond N
  ls -1 "$1"/karta-*.db 2>/dev/null | sort -r | tail -n +"$(( $2 + 1 ))" | while read -r f; do rm -f -- "$f"; done
}

local_state=fail; usb_state=-; cloud_state=-
if docker compose exec -T karta python -c "import sqlite3; s=sqlite3.connect('/data/workcard.db'); d=sqlite3.connect('/data/backup.db'); s.backup(d); d.close()" \
   && docker compose cp karta:/data/backup.db "backups/daily/karta-$today.db" >/dev/null \
   && [ -s "backups/daily/karta-$today.db" ]; then
  cp -f "backups/daily/karta-$today.db" "backups/monthly/karta-$month.db"
  cp -f "backups/daily/karta-$today.db" "backups/yearly/karta-$year.db"
  cp -f .env backups/karta.env && chmod 600 backups/karta.env      # needed to restore (PIN_KEY, tunnel)
  keep backups/daily 30
  keep backups/monthly 24
  local_state=ok
fi
echo "local: $local_state"

if [ -n "$USB_DIR" ]; then
  usb_state=fail
  if [ "$local_state" = ok ] && mountpoint -q "$USB_DIR" && mkdir -p "$USB_DIR/karta-backups" \
     && cp -ru backups/daily backups/monthly backups/yearly backups/karta.env "$USB_DIR/karta-backups/"; then
    keep "$USB_DIR/karta-backups/daily" 30
    keep "$USB_DIR/karta-backups/monthly" 24
    sync
    usb_state=ok
  fi
  echo "usb: $usb_state ($USB_DIR)"
fi

if [ -n "$CLOUD_REMOTE" ]; then
  cloud_state=fail
  dest="${CLOUD_REMOTE%/}"; case "$dest" in *:) ;; *) dest="$dest/" ;; esac
  # files removed or replaced here go to deleted/<date> (kept 30 days), never straight to the bin
  if [ "$local_state" = ok ] && command -v rclone >/dev/null 2>&1 \
     && rclone sync backups "${dest}backups" --exclude backup.log --backup-dir "${dest}deleted/$today"; then
    rclone delete --min-age 30d "${dest}deleted" >/dev/null 2>&1 || true
    cloud_state=ok
  fi
  echo "cloud: $cloud_state ($CLOUD_REMOTE)"
fi

# the admin page shows the result, and Karta alerts you when backups stop or fail
docker compose exec -T karta python -m app.backupmark "$local_state" "$usb_state" "$cloud_state" >/dev/null 2>&1 || true
tail -n 2000 backups/backup.log > backups/backup.log.tmp 2>/dev/null && mv backups/backup.log.tmp backups/backup.log
[ "$local_state" = ok ] && [ "$usb_state" != fail ] && [ "$cloud_state" != fail ]
SH
  chmod +x backup.sh
}

backup_now() {
  say "  Δοκιμαστικό αντίγραφο τώρα…"
  if ./backup.sh >/dev/null 2>&1; then say "  ✓ Έγινε. Το αποτέλεσμα φαίνεται και στη σελίδα διαχείρισης («Ρυθμίσεις» → «Αντίγραφα ασφαλείας»)."
  else say "  ✗ Κάτι απέτυχε. Δείτε:  tail -n 20 $PWD/backups/backup.log"; return 1; fi
}

usb_setup() {
  step "Αντίγραφα ασφαλείας σε USB"
  say "  Βάλτε ένα USB stick ή δίσκο στο μηχάνημα (FAT32, exFAT, NTFS ή ext4). Ό,τι έχει μέσα μένει όπως είναι."
  say "  (Σε VPS / cloud server δεν υπάρχει USB: χρησιμοποιήστε  ./setup.sh cloud)"
  local root_src root_disk d name fstype size label i=0 choice
  root_src=$(findmnt -no SOURCE / 2>/dev/null || true)
  root_disk=$(lsblk -no PKNAME "$root_src" 2>/dev/null | head -n1 || true)
  local -a parts=()
  for d in $(lsblk -dpno NAME,TRAN 2>/dev/null | awk '$2=="usb"{print $1}'); do
    [ "$(basename "$d")" = "$root_disk" ] && continue            # the disk the system runs from
    while read -r name fstype size label; do
      [ -n "$fstype" ] && [ "$fstype" != swap ] && parts+=("$name|$fstype|$size|${label//\\x20/ }")
    done < <(lsblk -rpno NAME,FSTYPE,SIZE,LABEL "$d")
  done
  if [ ${#parts[@]} -eq 0 ]; then
    say "  ✗ Δεν βρέθηκε USB με αρχεία. Βάλτε το USB και ξανατρέξτε:  ./setup.sh usb"
    return 1
  fi
  for p in "${parts[@]}"; do
    i=$((i + 1)); IFS='|' read -r name fstype size label <<<"$p"
    say "  $i) $name  $size  $fstype  ${label:-(χωρίς όνομα)}"
  done
  read -r -p "  Ποιο να χρησιμοποιηθεί; [1]: " choice
  choice=${choice:-1}
  if ! [[ "$choice" =~ ^[0-9]+$ ]] || [ "$choice" -lt 1 ] || [ "$choice" -gt ${#parts[@]} ]; then say "  Άκυρη επιλογή."; return 1; fi
  IFS='|' read -r name fstype size label <<<"${parts[$((choice - 1))]}"
  local uuid mnt=/mnt/karta-usb type="$fstype" opts="nofail,x-systemd.device-timeout=10s"
  uuid=$(lsblk -no UUID "$name")
  [ -n "$uuid" ] || { say "  ✗ Το $name δεν έχει UUID."; return 1; }
  case "$fstype" in
    vfat|exfat) opts="$opts,uid=$(id -u),gid=$(id -g),umask=077" ;;
    ntfs) type=ntfs-3g; opts="$opts,uid=$(id -u),gid=$(id -g),umask=077"
          command -v ntfs-3g >/dev/null 2>&1 || sudo apt-get install -y ntfs-3g ;;
    ext2|ext3|ext4|btrfs|xfs) ;;
    *) say "  ✗ Το σύστημα αρχείων $fstype δεν υποστηρίζεται εδώ."; return 1 ;;
  esac
  say "  Το $name θα συνδέεται μόνιμα στο $mnt (και μετά από επανεκκίνηση). Θα ζητηθεί ο κωδικός σας."
  ask_yes "Να συνεχίσω;" || return 1
  findmnt -no TARGET "$name" >/dev/null 2>&1 && sudo umount "$name"
  sudo mkdir -p "$mnt"
  sudo sed -i "\# $mnt #d" /etc/fstab
  echo "UUID=$uuid $mnt $type $opts 0 0" | sudo tee -a /etc/fstab >/dev/null
  sudo systemctl daemon-reload 2>/dev/null || true
  if ! sudo mount "$mnt"; then say "  ✗ Δεν έγινε η σύνδεση του USB."; return 1; fi
  case "$fstype" in ext*|btrfs|xfs) sudo chown "$(id -u):$(id -g)" "$mnt" ;; esac
  if ! (touch "$mnt/.karta-test" && rm -f "$mnt/.karta-test"); then say "  ✗ Δεν μπορώ να γράψω στο USB."; return 1; fi
  set_conf USB_DIR "$mnt"
  say "  ✓ Τα αντίγραφα θα γράφονται κάθε βράδυ και στο USB, στον φάκελο karta-backups."
  backup_now
}

cloud_connect() {  # cloud_connect new|existing: creates the rclone remotes karta-store and karta-cloud
  local choice kind token base account key bucket pass ack
  rclone config delete karta-cloud >/dev/null 2>&1 || true
  rclone config delete karta-store >/dev/null 2>&1 || true
  say "  Πού $([ "$1" = new ] && echo να ανεβαίνουν || echo είναι) τα αντίγραφα;"
  say "    1) Google Drive    2) Dropbox    3) Backblaze B2    4) Άλλο (ο οδηγός του rclone, στα αγγλικά)"
  read -r -p "  Επιλογή [1]: " choice
  case "${choice:-1}" in
    1|2)
      kind=$([ "${choice:-1}" = 1 ] && echo drive || echo dropbox)
      say ""
      say "  Χρειάζεται για λίγο ένας υπολογιστής με browser (Windows ή Mac):"
      say "    1. Κατεβάστε το rclone από https://rclone.org/downloads/ και αποσυμπιέστε το zip."
      say "    2. Ανοίξτε τερματικό σε εκείνο τον φάκελο (Windows: δεξί κλικ → «Άνοιγμα στο τερματικό») και τρέξτε:"
      say "         ./rclone authorize \"$kind\""
      say "    3. Στον browser που ανοίγει, συνδεθείτε και πατήστε «Allow»."
      say "    4. Το τερματικό γράφει ένα κείμενο που ξεκινά με {\"access_token\". Αντιγράψτε το (από το { ως το })."
      read -r -p "  Επικολλήστε το εδώ: " token
      [[ "$token" == \{* ]] || { say "  ✗ Δεν μοιάζει σωστό (πρέπει να ξεκινά με {)."; return 1; }
      if [ "$kind" = drive ]; then
        rclone config create karta-store drive scope drive.file token "$token" --non-interactive >/dev/null || return 1
      else
        rclone config create karta-store dropbox token "$token" --non-interactive >/dev/null || return 1
      fi
      base="karta-store:Karta-backups" ;;
    3)
      say "  Στο Backblaze: B2 Cloud Storage → Buckets → Create a Bucket (Private), και Application Keys → Add a New Key."
      read -r -p "  keyID: " account; read -r -s -p "  applicationKey: " key; echo
      read -r -p "  Όνομα bucket: " bucket
      rclone config create karta-store b2 account "$account" key "$key" --non-interactive >/dev/null || return 1
      base="karta-store:$bucket/karta-backups" ;;
    4)
      say "  Στον οδηγό του rclone φτιάξτε έναν χώρο με όνομα  karta-store  (n → karta-store → …)."
      rclone config
      rclone listremotes | grep -qx "karta-store:" || { say "  ✗ Δεν βρέθηκε το karta-store."; return 1; }
      base="karta-store:Karta-backups" ;;
    *) say "  Άκυρη επιλογή."; return 1 ;;
  esac
  if [ "$1" = new ]; then
    pass=$(head -c 32 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | cut -c1-24)
  else
    read -r -s -p "  Ο κωδικός κρυπτογράφησης των αντιγράφων: " pass; echo
  fi
  rclone config create karta-cloud crypt remote "$base" password "$pass" --obscure --non-interactive >/dev/null || return 1
  if [ "$1" = new ]; then
    say ""
    say "  ${bold}Κωδικός κρυπτογράφησης:  $pass${norm}"
    say "  ΓΡΑΨΤΕ ΤΟΝ σε χαρτί ή σε διαχειριστή κωδικών. Χωρίς αυτόν, αν χαλάσει το μηχάνημα,"
    say "  τα αντίγραφα στο cloud ΔΕΝ ανοίγουν. Δεν φυλάγεται πουθενά αλλού εκτός από αυτό το μηχάνημα."
    until [ "${ack:-}" = ok ]; do read -r -p "  Γράψτε  ok  όταν τον έχετε σημειώσει: " ack; done
  fi
}

ensure_rclone() {
  command -v rclone >/dev/null 2>&1 && return 0
  ask_yes "Να εγκατασταθεί το rclone; (θα ζητηθεί ο κωδικός σας)" || return 1
  if command -v apt-get >/dev/null 2>&1; then sudo apt-get update -qq && sudo apt-get install -y rclone
  else curl -fsSL https://rclone.org/install.sh | sudo bash; fi
  command -v rclone >/dev/null 2>&1 || { say "  ✗ Δεν εγκαταστάθηκε το rclone."; return 1; }
}

cloud_setup() {
  step "Κρυπτογραφημένο αντίγραφο στο cloud"
  say "  Κάθε βράδυ τα αντίγραφα ανεβαίνουν κρυπτογραφημένα σε έναν χώρο cloud που έχετε (με το εργαλείο rclone)."
  say "  Μόνο όποιος έχει τον κωδικό κρυπτογράφησης μπορεί να τα ανοίξει, ούτε ο πάροχος του cloud."
  ensure_rclone || return 1
  if rclone listremotes 2>/dev/null | grep -qx "karta-cloud:"; then
    say "  Υπάρχει ήδη ρύθμιση cloud (karta-cloud)."
    if ! ask_yes "Να την κρατήσω;"; then
      say "  Προσοχή: τα αντίγραφα που ήδη ανέβηκαν ανοίγουν μόνο με τον παλιό κωδικό."
      cloud_connect new || return 1
    fi
  fi
  if ! rclone listremotes 2>/dev/null | grep -qx "karta-cloud:"; then
    cloud_connect new || return 1
  fi
  say "  Δοκιμή σύνδεσης…"
  if ! (echo test | rclone rcat karta-cloud:.karta-test && rclone deletefile karta-cloud:.karta-test); then
    say "  ✗ Δεν έγινε η σύνδεση με το cloud. Ξανατρέξτε  ./setup.sh cloud"; return 1
  fi
  set_conf CLOUD_REMOTE "karta-cloud:"
  say "  ✓ Τα αντίγραφα θα ανεβαίνουν κάθε βράδυ, κρυπτογραφημένα."
  backup_now
}


restore() {  # restore [file.db]: puts a backup back into Karta
  step "Επαναφορά από αντίγραφο ασφαλείας"
  local src="${1:-}" dir="" choice latest
  if [ -z "$src" ]; then
    say "  Από πού;"
    say "    1) από αυτό το μηχάνημα (φάκελος backups)    2) από USB    3) από το cloud"
    read -r -p "  Επιλογή [1]: " choice
    case "${choice:-1}" in
      1) dir="$PWD/backups" ;;
      2) dir="/mnt/karta-usb/karta-backups"
         mountpoint -q /mnt/karta-usb || { say "  Συνδέστε πρώτα το USB:  ./setup.sh usb  (ή δώστε το αρχείο:  ./setup.sh restore /διαδρομή/karta-….db)"; return 1; } ;;
      3) ensure_rclone || return 1
         if ! rclone listremotes 2>/dev/null | grep -qx "karta-cloud:"; then cloud_connect existing || return 1; fi
         dir="$PWD/restore"; mkdir -p "$dir"
         say "  Κατέβασμα από το cloud…"
         rclone copy karta-cloud:backups "$dir" || { say "  ✗ Δεν κατέβηκαν (λάθος κωδικός κρυπτογράφησης;)"; return 1; } ;;
      *) say "  Άκυρη επιλογή."; return 1 ;;
    esac
    latest=$(ls -1 "$dir"/daily/karta-*.db 2>/dev/null | sort | tail -n1 || true)
    [ -n "$latest" ] || { say "  ✗ Δεν βρέθηκε αντίγραφο στο $dir/daily"; return 1; }
    say "  Πιο πρόσφατο: $(basename "$latest")"
    read -r -p "  Αυτό; Ή γράψτε άλλο αρχείο (Enter = αυτό): " src
    src=${src:-$latest}
  fi
  [ -s "$src" ] || { say "  ✗ Δεν βρέθηκε το $src"; return 1; }
  src=$(readlink -f "$src")
  # settings: a new machine has no .env yet; PIN_KEY must be the one the backup was made with
  local envcopy; envcopy="$(dirname "$(dirname "$src")")/karta.env"
  if [ ! -f .env ] && [ -f "$envcopy" ]; then
    cp "$envcopy" .env && chmod 600 .env && say "  ✓ Οι ρυθμίσεις (.env) ήρθαν από το αντίγραφο."
  elif [ -f .env ] && [ -f "$envcopy" ]; then
    local old new
    old=$(grep -E '^PIN_KEY=' "$envcopy" | cut -d= -f2- || true); new=$(grep -E '^PIN_KEY=' .env | cut -d= -f2- || true)
    if [ -n "$old" ] && [ "$old" != "$new" ]; then
      say "  Το PIN_KEY του αντιγράφου διαφέρει από το τωρινό. Χωρίς το παλιό, ο κωδικός ΕΡΓΑΝΗ και τα PIN δεν διαβάζονται."
      if ask_yes "Να μπει το PIN_KEY του αντιγράφου στο .env;"; then
        cp .env ".env.bak-$(date +%Y%m%d-%H%M%S)"
        { grep -v '^PIN_KEY=' .env || true; echo "PIN_KEY=$old"; } > .env.tmp; mv .env.tmp .env; chmod 600 .env
      fi
    fi
  fi
  [ -f .env ] || { say "  ✗ Λείπει το .env: τρέξτε πρώτα  ./setup.sh"; return 1; }
  [ -f docker-compose.yml ] || curl -fsSLO "$RAW/docker-compose.yml"
  say "  Η τωρινή βάση της Karta θα αντικατασταθεί από το $(basename "$src")."
  ask_yes "Να γίνει η επαναφορά;" || return 1
  if docker compose ps --status running karta 2>/dev/null | grep -q karta; then
    say "  Πρώτα ένα αντίγραφο της τωρινής βάσης…"; ./backup.sh >/dev/null 2>&1 || true
  fi
  docker compose stop karta >/dev/null 2>&1 || true
  cp "$src" "$PWD/.restore.db" && chmod 644 "$PWD/.restore.db"      # readable by the container's user
  if docker compose run --rm --no-deps -T --entrypoint sh -v "$PWD/.restore.db:/restore.db:ro" karta \
       -c 'cp /restore.db /data/workcard.db && rm -f /data/workcard.db-wal /data/workcard.db-shm'; then
    rm -f "$PWD/.restore.db"
    docker compose up -d >/dev/null
    say "  ✓ Η επαναφορά έγινε. Ανοίξτε τη σελίδα διαχείρισης και ελέγξτε τα τελευταία χτυπήματα."
  else
    rm -f "$PWD/.restore.db"
    docker compose up -d >/dev/null
    say "  ✗ Η επαναφορά απέτυχε· η Karta ξεκίνησε με τη βάση που είχε."; return 1
  fi
}

case "${1:-}" in
  restore) write_backup_script; restore "${2:-}"; exit $? ;;
  usb)   write_backup_script; usb_setup; exit $? ;;
  cloud) write_backup_script; cloud_setup; exit $? ;;
  ""|check) ;;
  *) say "Χρήση: ./setup.sh [check|usb|cloud|restore]"; exit 2 ;;
esac

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
say "  Τα χτυπήματα πρέπει να φυλάσσονται για χρόνια. Κάθε βράδυ γίνεται αντίγραφο όλης της βάσης."
write_backup_script
if crontab -l 2>/dev/null | grep -q "$PWD/backup.sh"; then
  say "  ✓ Το αυτόματο αντίγραφο κάθε βράδυ είναι ήδη ρυθμισμένο."
elif command -v crontab >/dev/null 2>&1 && ask_yes "Να γίνεται αυτόματα αντίγραφο κάθε βράδυ στις 23:30;"; then
  ( crontab -l 2>/dev/null; echo "30 23 * * * $PWD/backup.sh >/dev/null 2>&1" ) | crontab -
  say "  ✓ Ρυθμίστηκε. Τα αντίγραφα μπαίνουν στον φάκελο $PWD/backups"
fi
if ! grep -qE '^(USB_DIR|CLOUD_REMOTE)="..*"' backup.conf 2>/dev/null; then
  say "  Χρειάζεται και ένα αντίγραφο ΕΚΤΟΣ του μηχανήματος: αν χαλάσει η κάρτα ή ο δίσκος, χάνονται όλα."
  say "    1) σε USB stick στο μηχάνημα     2) κρυπτογραφημένο σε cloud (Google Drive, Dropbox…)     3) αργότερα"
  read -r -p "  Επιλογή [3]: " offsite
  case "${offsite:-3}" in
    1) usb_setup || true ;;
    2) cloud_setup || true ;;
    *) say "  Αργότερα:  ./setup.sh usb  ή  ./setup.sh cloud" ;;
  esac
fi

# ---- Επόμενα βήματα -----------------------------------------------------------------------------
origin=$(grep -E '^PUBLIC_ORIGIN=' .env | cut -d= -f2- || true)
step "Επόμενα βήματα"
say "  1. Ανοίξτε ${origin:-τη διεύθυνσή σας}/admin και συνδεθείτε με το email σας."
say "  2. Ακολουθήστε τα «Πρώτα βήματα» στην καρτέλα «Σήμερα»."
say "  3. Σε ένα λεπτό, ελέγξτε ότι όλα είναι σωστά με:  ./setup.sh check"
say "  Βοήθεια: https://github.com/osergios/karta/discussions/categories/q-a"
