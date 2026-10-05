#!/usr/bin/env bash
# Karta: οδηγός εγκατάστασης / setup helper
#
#   ./setup.sh          διεύθυνση και Cloudflare → .env → εκκίνηση → αντίγραφα ασφαλείας
#   ./setup.sh check    έλεγχος: ΕΡΓΑΝΗ, Cloudflare, διεύθυνση, προστασία διαχείρισης
#   ./setup.sh usb      αντίγραφα ασφαλείας και σε USB stick
#   ./setup.sh restore  επαναφορά από αντίγραφο στο μηχάνημα ή στο USB (από cloud: στη σελίδα διαχείρισης)
#   ./setup.sh update   ενημέρωση στη νεότερη έκδοση (ή «Ενημέρωση τώρα» στη σελίδα διαχείρισης)
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

# An installation from before the "tunnel" profile: docker compose starts cloudflared only with COMPOSE_PROFILES=tunnel
tunnel_profile() {
  if [ -f .env ] && grep -qE '^TUNNEL_TOKEN=.' .env && ! grep -q '^COMPOSE_PROFILES=' .env; then
    [ -z "$(tail -c1 .env)" ] || echo >> .env          # the last line may lack its newline
    printf 'COMPOSE_PROFILES=tunnel\n' >> .env
  fi
}
tunnel_profile

# ---- Αντίγραφα ασφαλείας: backup.sh, USB ---------------------------------------------------------
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
# and, when set up, the same on a USB stick (./setup.sh usb). The encrypted cloud copy is made by Karta itself
# («Ρυθμίσεις» → «Αντίγραφα ασφαλείας»).
set -u
cd "$(dirname "$0")" || exit 1
USB_DIR=""
[ -f backup.conf ] && . ./backup.conf
mkdir -p backups/daily backups/monthly backups/yearly
for f in backups/karta-*.db; do [ -f "$f" ] && mv -- "$f" backups/daily/; done     # copies of the first version
[ -t 1 ] || exec >> backups/backup.log 2>&1
echo "== $(date '+%F %T')"
today=$(date +%F); month=$(date +%Y-%m); year=$(date +%Y)

keep() {  # keep DIR N: delete the oldest copies beyond N
  ls -1 "$1"/karta-*.db 2>/dev/null | sort -r | tail -n +"$(( $2 + 1 ))" | while read -r f; do rm -f -- "$f"; done
}

local_state=fail; usb_state=-
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

# the admin page shows the result, and Karta alerts you when backups stop or fail
docker compose exec -T karta python -m app.backupmark "$local_state" "$usb_state" - >/dev/null 2>&1 || true
tail -n 2000 backups/backup.log > backups/backup.log.tmp 2>/dev/null && mv backups/backup.log.tmp backups/backup.log
[ "$local_state" = ok ] && [ "$usb_state" != fail ]
SH
  chmod +x backup.sh
}

write_update_script() {
  cat > update.sh <<'SH'
#!/bin/sh
# Karta update — written by ./setup.sh (it rewrites this file). Runs every 2 minutes from cron: when «Ενημέρωση τώρα»
# is pressed in the admin page, it keeps a backup, switches to the newest version (KARTA_VERSION in .env) and waits for
# Karta to report healthy; if it doesn't within about 2 minutes, it goes back to the previous version (its image is
# still on this machine). The admin page only leaves a request; Karta itself never gets control of Docker here.
#   ./update.sh now   update without waiting for the admin page (what ./setup.sh update does)
set -u
cd "$(dirname "$0")" || exit 1
if [ "${1:-}" != now ]; then
  r=$(docker compose exec -T karta python -m app.updatemark poll 2>/dev/null) || exit 0
  [ "$r" = update ] || exit 0
  mkdir -p backups && exec >> backups/update.log 2>&1
fi
echo "== $(date '+%F %T') update"

use() {  # use VERSION: the version docker compose starts
  ( umask 077; { grep -v '^KARTA_VERSION=' .env; echo "KARTA_VERSION=$1"; } > .env.new ) && cat .env.new > .env && rm -f .env.new
}
healthy() {  # Karta's healthcheck says healthy, within about 2 minutes
  for _ in $(seq 1 60); do
    sleep 2
    case $(docker inspect -f '{{.State.Health.Status}}' "$(docker compose ps -q karta)" 2>/dev/null) in
      healthy) return 0 ;;
      unhealthy) return 1 ;;
    esac
  done
  return 1
}
mark() { docker compose exec -T karta python -m app.updatemark "done" "$1" >/dev/null 2>&1 || true; }

old=$(sed -n 's/^KARTA_VERSION=//p' .env | tail -n1)
[ -n "$old" ] || old=$(docker compose exec -T karta printenv KARTA_VERSION 2>/dev/null | sed 's/^v//')
repo=$(docker compose config --images 2>/dev/null | grep '/karta:' | head -n1); repo=${repo%:*}
new=""
[ -n "$repo" ] && docker pull -q "$repo:latest" >/dev/null && new=$(docker image inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$repo:latest" | sed -n 's/^KARTA_VERSION=v\{0,1\}//p')
if [ -z "$old" ] || [ -z "$new" ]; then
  echo "failed: current '$old', newest '$new'"; mark fail; exit 1
fi
if [ "$new" = "$old" ]; then echo "already $new"; use "$old"; mark ok; exit 0; fi
[ -x ./backup.sh ] && ./backup.sh >/dev/null 2>&1      # a copy of the database first
use "$new"
if docker compose pull -q karta && docker compose up -d && healthy; then
  echo "ok: $old -> $new"; mark ok; exit 0
fi
echo "failed: $new is not healthy, back to $old"
use "$old"
docker compose up -d && healthy
mark fail
exit 1
SH
  chmod +x update.sh
  command -v crontab >/dev/null 2>&1 || return 0
  # every 2 minutes; a check only reads one row of the database (an earlier per-minute line is replaced)
  ( crontab -l 2>/dev/null | grep -v "$PWD/update.sh"; echo "*/2 * * * * $PWD/update.sh >/dev/null 2>&1" ) | crontab -
  say "  ✓ Ενημερώσεις με ένα κουμπί από τη σελίδα διαχείρισης («Ρυθμίσεις» → «Έκδοση και ενημέρωση»)."
}

pin_version() {  # pin_version [image]: KARTA_VERSION in .env, the running version (or that of the image)
  grep -qE '^KARTA_VERSION=.' .env 2>/dev/null && return 0
  local v
  v=$(docker compose exec -T karta printenv KARTA_VERSION 2>/dev/null || true)
  [ -n "$v" ] || v=$(docker image inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "${1:-$IMAGE}" 2>/dev/null | sed -n 's/^KARTA_VERSION=//p')
  v=${v#v}
  case "$v" in ""|dev) return 0 ;; esac
  [ -z "$(tail -c1 .env)" ] || echo >> .env
  echo "KARTA_VERSION=$v" >> .env
}

# docker-compose.yml as downloaded by an earlier version and not changed by hand: replaced by the current one
# (when docker-compose.yml changes, add the sha256 of the new file here; tests/test_update_script.py checks it)
OLD_COMPOSE="ea57c0f256f5734edc18d4e3aa4e1a10e30ff23e197a3ee5a2e00859e0b3446a 22a84e76aca50d22d7d4f18bd5ed873e142df99cc75abb693c13d5eb0590c009
032a33cf46bb0e6c5f1c82d8dbd5f9234f79673d1b7008309b153cb4b3291350 48552098ba8113312df6bfc339b45e3582f0199cbf54e09c9c33f62f87b83960
3abca45802e2ab3a81160a954a142e22e45b0ff967e145909236a8f60f8c215e
12a54674f35525c4b75cae781474d7e65b3f4113e65b7c9ad4972c1b06375c2f"
refresh_compose() {
  local h; h=$(sha256sum docker-compose.yml 2>/dev/null | cut -d' ' -f1)
  printf '%s\n' $OLD_COMPOSE | grep -qx "${h:-none}" || return 0
  curl -fsSL "$RAW/docker-compose.yml" -o docker-compose.yml.new 2>/dev/null || { rm -f docker-compose.yml.new; return 0; }
  if cmp -s docker-compose.yml docker-compose.yml.new; then rm -f docker-compose.yml.new; return 0; fi
  cp docker-compose.yml docker-compose.yml.bak && mv docker-compose.yml.new docker-compose.yml
  say "  ✓ Ενημερώθηκε το docker-compose.yml (το προηγούμενο: docker-compose.yml.bak)"
}

backup_now() {
  say "  Δοκιμαστικό αντίγραφο τώρα…"
  if ./backup.sh >/dev/null 2>&1; then say "  ✓ Έγινε. Το αποτέλεσμα φαίνεται και στη σελίδα διαχείρισης («Ρυθμίσεις» → «Αντίγραφα ασφαλείας»)."
  else say "  ✗ Κάτι απέτυχε. Δείτε:  tail -n 20 $PWD/backups/backup.log"; return 1; fi
}

usb_setup() {
  step "Αντίγραφα ασφαλείας σε USB"
  say "  Βάλτε ένα USB stick ή δίσκο στο μηχάνημα (FAT32, exFAT, NTFS ή ext4). Ό,τι έχει μέσα μένει όπως είναι."
  say "  (Σε VPS / cloud server δεν υπάρχει USB: το αντίγραφο στο cloud ρυθμίζεται στη σελίδα διαχείρισης.)"
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

restore() {  # restore [file.db]: puts a backup back into Karta
  step "Επαναφορά από αντίγραφο ασφαλείας"
  local src="${1:-}" dir="" choice latest
  if [ -z "$src" ]; then
    say "  Από πού;"
    say "    1) από αυτό το μηχάνημα (φάκελος backups)    2) από USB"
    say "  (Από το cloud ή από αρχείο στον υπολογιστή σας: «Ρυθμίσεις» → «Αντίγραφα ασφαλείας» → «Επαναφορά».)"
    read -r -p "  Επιλογή [1]: " choice
    case "${choice:-1}" in
      1) dir="$PWD/backups" ;;
      2) dir="/mnt/karta-usb/karta-backups"
         mountpoint -q /mnt/karta-usb || { say "  Συνδέστε πρώτα το USB:  ./setup.sh usb  (ή δώστε το αρχείο:  ./setup.sh restore /διαδρομή/karta-….db)"; return 1; } ;;
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
  tunnel_profile                         # a .env from an older backup
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
  cloud) say "Το αντίγραφο στο cloud ρυθμίζεται πλέον στη σελίδα διαχείρισης: «Ρυθμίσεις» → «Αντίγραφα ασφαλείας»."; exit 0 ;;
  update) [ -f docker-compose.yml ] || { say "Δεν βρέθηκε η Karta σε αυτόν τον φάκελο."; exit 1; }
          write_backup_script                    # the helpers of this version of setup.sh
          write_update_script
          refresh_compose
          pin_version "ghcr.io/osergios/karta:latest"     # the version that runs now: the way back if needed
          say "Ενημέρωση (πρώτα αντίγραφο ασφαλείας)…"
          if ./update.sh now; then say "✓ Η Karta ενημερώθηκε: $(sed -n 's/^KARTA_VERSION=//p' .env | tail -n1)"; exit 0; fi
          say "✗ Η ενημέρωση απέτυχε· η Karta συνεχίζει με την έκδοση $(sed -n 's/^KARTA_VERSION=//p' .env | tail -n1)."; exit 1 ;;
  ""|check) ;;
  *) say "Χρήση: ./setup.sh [check|usb|restore|update]"; exit 2 ;;
esac

[ -f docker-compose.yml ] || { say "Κατέβασμα docker-compose.yml…"; curl -fsSLO "$RAW/docker-compose.yml"; }
refresh_compose
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
pin_version                              # a new installation: the version just downloaded
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
say "  Χρειάζεται και ένα αντίγραφο ΕΚΤΟΣ του μηχανήματος: αν χαλάσει η κάρτα ή ο δίσκος, χάνονται όλα."
say "  · κρυπτογραφημένο σε cloud (Google Drive, Dropbox, Backblaze B2): «Ρυθμίσεις» → «Αντίγραφα ασφαλείας»"
if ! grep -qE '^USB_DIR="..*"' backup.conf 2>/dev/null; then
  say "  · σε USB stick στο μηχάνημα:  ./setup.sh usb"
  if ask_yes "Να ρυθμίσουμε τώρα το USB; (αν δεν έχετε USB ή είστε σε VPS: ο)"; then usb_setup || true; fi
fi

# ---- Ενημερώσεις -------------------------------------------------------------------------------
step "Ενημερώσεις"
write_update_script

# ---- Επόμενα βήματα -----------------------------------------------------------------------------
origin=$(grep -E '^PUBLIC_ORIGIN=' .env | cut -d= -f2- || true)
step "Επόμενα βήματα"
say "  1. Ανοίξτε ${origin:-τη διεύθυνσή σας}/admin και συνδεθείτε με το email σας."
say "  2. Ακολουθήστε τα «Πρώτα βήματα» στην καρτέλα «Σήμερα»."
say "  3. Σε ένα λεπτό, ελέγξτε ότι όλα είναι σωστά με:  ./setup.sh check"
say "  Βοήθεια: https://github.com/osergios/karta/discussions/categories/q-a"
