"""Encrypted backups to the cloud, made by Karta itself («Ρυθμίσεις» → «Αντίγραφα ασφαλείας»).

Every night restic (in the image) takes a snapshot of the whole database into a repository in Google Drive, Dropbox
or Backblaze B2, reached through rclone (also in the image). restic encrypts everything on this machine with a
password shown to the admin once, compresses it, and stores only what changed since the previous snapshot: keeping
30 daily, 24 monthly and one yearly snapshot costs little more than a single copy. Each snapshot is still a complete
database and restores on its own.

Each snapshot also holds this installation's PIN_KEY (pin-key, encrypted with everything else), so a restore on a new
machine opens the Ergani password and the PINs sealed with it (see restore.py).

On this machine, next to the database: rclone.conf (access to the cloud), cloud-password and cloud.json (mode 600).
A new connection is tried in a folder of its own (.cloud-new) and takes their place only once it works, so a failed
reconnect never loses the working setup, nor the password of the backups already in the cloud.
"""
import json
import logging
import os
import re
import secrets
import shutil
import sqlite3
import subprocess
import threading
from datetime import datetime, timedelta, timezone

from . import config, db

log = logging.getLogger("workcard.cloud")

PROVIDERS = {"drive": "Google Drive", "dropbox": "Dropbox", "b2": "Backblaze B2"}
RUN_AT = (23, 40)                         # nightly snapshot, local time
KEEP = ("--keep-daily", "30", "--keep-monthly", "24", "--keep-yearly", "1000")
PRUNE_EVERY = timedelta(days=7)           # freeing the space of dropped snapshots lists the whole repository: weekly
SNAPSHOT_ID = re.compile(r"^[0-9a-f]{8,64}$")
FILE_IN_SNAPSHOT = "/karta.db"
KEY_IN_SNAPSHOT = "/pin-key"
RCLONE_START = "5m"                       # how long restic waits for rclone to answer (restic's default: 1m)
STAGE = ".cloud-new"                      # a connection being tried (see _connect)
NO_REPO = "Δεν βρέθηκαν αντίγραφα σε αυτόν τον φάκελο του cloud"
LOCKED = "Τα αντίγραφα είναι κλειδωμένα από προηγούμενη εργασία που διακόπηκε"
WRONG_PASSWORD = "λάθος κωδικός κρυπτογράφησης"
_running = threading.Lock()


class CloudError(Exception):
    pass


def data_dir() -> str:
    return os.path.dirname(os.path.abspath(config.DB_PATH))


def _paths(base: str | None = None) -> tuple[str, str, str]:
    """rclone.conf, cloud-password and cloud.json: the ones in use, or those of a connection being tried (base)."""
    d = base or data_dir()
    return os.path.join(d, "rclone.conf"), os.path.join(d, "cloud-password"), os.path.join(d, "cloud.json")


def conf_path() -> str:
    return _paths()[0]


def _pw_path() -> str:
    return _paths()[1]


def _info_path() -> str:
    return _paths()[2]


def available() -> bool:
    return shutil.which("rclone") is not None and shutil.which("restic") is not None


def _env(base: str | None = None) -> dict:
    conf, pw, _ = _paths(base)
    cache = os.path.join(data_dir(), ".cache")          # the app user has no home folder in the image
    env = {**os.environ, "RCLONE_CONFIG": conf, "RCLONE_CACHE_DIR": os.path.join(cache, "rclone"),
           "XDG_CACHE_HOME": cache, "RESTIC_CACHE_DIR": os.path.join(cache, "restic"),
           "RESTIC_PASSWORD_FILE": pw, "HOME": data_dir(),
           "RCLONE_DRIVE_USE_TRASH": "false"}     # Google Drive: what restic deletes is gone, not kept in the trash
    info = _info(base)
    if info:
        env["RESTIC_REPOSITORY"] = info["repo"]
    return env


def _run(tool: str, *args: str, timeout: int = 900, cwd: str | None = None, stdout=None, base: str | None = None) -> str:
    if not available():
        raise CloudError("Το rclone / restic δεν υπάρχει σε αυτή την εγκατάσταση (χρειάζεται νεότερο image της Karta).")
    try:
        if tool == "restic":    # rclone may need more than restic's 1 minute to reach Google Drive (token, folder lookup)
            args = ("-o", f"rclone.timeout={RCLONE_START}", *args)
        r = subprocess.run([tool, *args], stdout=stdout if stdout is not None else subprocess.PIPE,
                           stderr=subprocess.PIPE, text=stdout is None, timeout=timeout, env=_env(base), cwd=cwd)
    except subprocess.TimeoutExpired:
        raise CloudError("Το cloud δεν απάντησε εγκαίρως.")
    if r.returncode != 0:
        err = r.stderr if isinstance(r.stderr, str) else r.stderr.decode("utf-8", "replace")
        log.warning("%s %s failed (%s): %s", tool, args[0] if args else "", r.returncode, err.strip())
        raise CloudError(explain(err, tool, r.returncode))
    return r.stdout if stdout is None else ""


# what restic / rclone say -> what the admin reads (the first match wins)
_KNOWN = [
    (re.compile(r"Is there a repository|unable to open config file", re.I), NO_REPO),
    (re.compile(r"repository is already locked", re.I), LOCKED),
    (re.compile(r"wrong password", re.I), WRONG_PASSWORD),
    (re.compile(r"quota", re.I), "Ο χώρος στο cloud γέμισε"),               # also a 403: before the next line
    (re.compile(r"\b40[13]\b|invalid_grant|token expired|expired_access_token", re.I),
     "Η πρόσβαση στο cloud έληξε — συνδέστε ξανά"),
    (re.compile(r"context deadline exceeded|Client\.Timeout|timeout awaiting|i/o timeout|TLS handshake timeout", re.I),
     "Το cloud άργησε να απαντήσει (συνήθως προσωρινό)· η Karta θα ξαναδοκιμάσει σε μία ώρα"),
]


def explain(err: str, tool: str = "restic", code: int = 1) -> str:
    """A tool's error output as one short message: a known case in Greek, otherwise its last lines."""
    for pattern, message in _KNOWN:
        if pattern.search(err):
            return message
    lines = [x.strip() for x in err.strip().splitlines() if x.strip()]
    return " · ".join(lines[-3:])[-300:] if lines else f"{tool}: κωδικός {code}"


def _info(base: str | None = None) -> dict | None:
    try:
        with open(_paths(base)[2], encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _write_private(path: str, text: str) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)


def connected() -> bool:
    return _info() is not None and os.path.exists(_pw_path())


def _forget() -> None:
    for p in (conf_path(), _pw_path(), _info_path()):
        try:
            os.remove(p)
        except FileNotFoundError:
            pass


def connect(provider: str, *, token: str = "", account: str = "", key: str = "", bucket: str = "",
            password: str | None = None, local_path: str = "") -> str | None:
    """Sets up the cloud. Without a password a new encrypted repository is made and its password returned (show it
    once); with the password of existing backups (restore on a new machine) it checks that they can be read. Then the
    first snapshot is taken right away (its result: status()); the nightly worker can't start one meanwhile."""
    if not _running.acquire(blocking=False):
        raise CloudError("Ένα ανέβασμα τρέχει ήδη· δοκιμάστε ξανά σε λίγο.")
    try:
        return _connect(provider, token=token, account=account, key=key, bucket=bucket, password=password,
                        local_path=local_path)
    finally:
        _running.release()


def _connect(provider: str, *, token: str, account: str, key: str, bucket: str, password: str | None,
             local_path: str) -> str | None:
    if provider in ("drive", "dropbox"):
        try:
            tok = json.loads(token)
            assert isinstance(tok, dict) and (tok.get("access_token") or tok.get("refresh_token"))
        except (ValueError, AssertionError):
            raise CloudError("Ο κωδικός πρόσβασης δεν μοιάζει σωστός: αντιγράψτε όλο το κείμενο από το { έως το }.")
        store = ["drive", "scope", "drive.file", "token", token] if provider == "drive" else ["dropbox", "token", token]
        base = "karta-store:Karta-backups"
    elif provider == "b2":
        if not (account and key) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{4,48}[a-z0-9]", bucket or ""):
            raise CloudError("Συμπληρώστε keyID, applicationKey και το όνομα του bucket (μικρά γράμματα, αριθμοί, -).")
        store = ["b2", "account", account.strip(), "key", key.strip()]
        base = f"karta-store:{bucket}/karta-backups"
    elif provider == "local" and local_path:          # tests only (not offered by the admin page)
        store, base = ["local"], f"karta-store:{local_path}"
    else:
        raise CloudError("Άγνωστος πάροχος.")
    new = password is None
    # Reconnecting (an expired token, another account) keeps the password of the backups made from this machine:
    # the admin wrote it down once and the backups already in the cloud open only with it.
    known = None
    if new:
        try:
            with open(_pw_path(), encoding="utf-8") as f:
                known = f.read().strip() or None
        except OSError:
            pass
    password = password or known or "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789")
                                            for _ in range(24))
    # Everything is tried in a folder of its own; the working setup is replaced only when the new one works.
    stage = os.path.join(data_dir(), STAGE)
    shutil.rmtree(stage, ignore_errors=True)            # left over by a restart in the middle of a connect
    os.makedirs(stage, mode=0o700)
    created = False
    try:
        conf, pw, info = _paths(stage)
        _run("rclone", "config", "create", "karta-store", *store, "--non-interactive", base=stage)
        os.chmod(conf, 0o600)
        _write_private(pw, password)
        _write_private(info, json.dumps({"provider": provider, "repo": "rclone:" + base}))
        found = False
        if not new or known:            # backups that should be there already: this password must open them
            try:
                found = bool(list_backups(stage)) or new    # a known password: even an empty repository is ours
            except CloudError as e:
                if str(e) == WRONG_PASSWORD and known:
                    raise CloudError("Τα αντίγραφα σε αυτόν τον λογαριασμό έχουν άλλον κωδικό κρυπτογράφησης από "
                                     "αυτόν του μηχανήματος: χρησιμοποιήστε «Έχω ήδη αντίγραφα στο cloud» με τον "
                                     "κωδικό τους.")
                if str(e) != NO_REPO:
                    raise
            if not new and not found:
                raise CloudError("Δεν βρέθηκαν αντίγραφα της Karta σε αυτόν τον λογαριασμό.")
        if new and not found:
            try:
                _run("restic", "init", timeout=300, base=stage)
                created = True
            except CloudError as e:
                if "already" in str(e).lower() or "exist" in str(e).lower():
                    raise CloudError("Υπάρχουν ήδη αντίγραφα της Karta σε αυτόν τον λογαριασμό: χρησιμοποιήστε "
                                     "«Έχω ήδη αντίγραφα στο cloud» με τον κωδικό τους.")
                raise
        for staged, live in zip((conf, pw, info), _paths()):     # cloud.json last: connected() looks for it
            os.replace(staged, live)
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    try:
        _backup()                      # the first snapshot; a failure is recorded and shown, the connection stays
    except Exception:
        pass
    return password if created else None


def password() -> str | None:
    """The encryption password kept on this machine (for «Εμφάνιση κωδικού κρυπτογράφησης»), or None."""
    if not connected():
        return None
    with open(_pw_path(), encoding="utf-8") as f:
        return f.read().strip() or None


def disconnect() -> None:
    """Stops the uploads on this machine. What is already in the cloud stays there."""
    _forget()
    with db.tx() as c:
        c.execute("DELETE FROM settings WHERE key IN ('cloud_status', 'cloud_last_ok', 'cloud_last_try')")


def _prune_due(now: datetime) -> bool:
    try:
        last = datetime.fromisoformat(db.setting("cloud_last_prune") or "").replace(tzinfo=timezone.utc)
    except ValueError:
        return True
    return now - last >= PRUNE_EVERY


def _record(state: str, error: str = "", seconds: float | None = None) -> None:
    with db.tx() as c:
        if state == "ok":
            db.put_setting(c, "cloud_last_ok", datetime.now(config.TZ).replace(tzinfo=None).isoformat(timespec="seconds"))
        db.put_setting(c, "cloud_status", json.dumps({
            "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"), "state": state, "error": error[:300],
            "seconds": None if seconds is None else round(seconds)}))


def status() -> dict | None:
    """Provider and the last snapshot (with its local time), or None when the cloud is not set up."""
    if not connected():
        return None
    out = {"provider": PROVIDERS.get((_info() or {}).get("provider", ""), "cloud"), "state": None, "when": None, "error": "",
           "seconds": None}
    try:
        s = json.loads(db.setting("cloud_status") or "null")
        if s:
            out.update(state=s["state"], error=s.get("error", ""), seconds=s.get("seconds"),
                       when=datetime.fromisoformat(s["at"]).replace(tzinfo=timezone.utc).astimezone(config.TZ).replace(tzinfo=None))
    except (ValueError, KeyError, TypeError):
        pass
    return out


def snapshot(path: str) -> None:
    """A consistent copy of the live database (SQLite online backup)."""
    dst = sqlite3.connect(path)
    try:
        with db._lock:
            db._conn.backup(dst)
    finally:
        dst.close()


def empty() -> bool:
    """A database with no employees at all: a new installation, nothing worth keeping yet."""
    return db.one("SELECT 1 FROM employees LIMIT 1") is None


def run_backup(now: datetime | None = None) -> None:
    """Tonight's snapshot (or one asked for in the admin page)."""
    if not _running.acquire(blocking=False):
        raise CloudError("Ένα ανέβασμα τρέχει ήδη.")
    try:
        _backup()
    finally:
        _running.release()


def _restic_unlocked(*args: str, **kw) -> str:
    """restic, and once more after removing stale locks if a run that was cut short (power cut, restart) left the
    repository locked. `unlock` removes only stale locks, never the one of a backup that is running."""
    try:
        return _run("restic", *args, **kw)
    except CloudError as e:
        if str(e) != LOCKED:
            raise
    _run("restic", "unlock", timeout=300)
    return _run("restic", *args, **kw)


def _backup() -> None:
    """A snapshot. Every restic run starts rclone afresh, which on Google Drive takes long to log in and find its
    folders (some 40 seconds), so a night is a single run: the backup. Once a week the old snapshots are thinned out
    (30 daily, 24 monthly, yearly for good) and their space freed (forget --prune, which lists every file of the
    repository: slow on Google Drive). The caller holds _running."""
    if empty():
        # A new installation (no employees yet), e.g. a new machine that has just connected to the existing backups
        # to restore them: its empty database must never become the newest snapshot in the list.
        log.info("Cloud backup skipped: the database has no employees yet")
        return
    folder = os.path.join(data_dir(), "cloud-snapshot")
    started = datetime.now(timezone.utc)
    try:
        os.makedirs(folder, exist_ok=True)
        snapshot(os.path.join(folder, "karta.db"))
        files = ["karta.db"]
        if config.PIN_KEY:                 # what the Ergani password and the PINs in it are sealed with
            fd = os.open(os.path.join(folder, "pin-key"), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(config.PIN_KEY)
            files.append("pin-key")
        _restic_unlocked("backup", "--quiet", "--host", "karta", "--tag", "karta", *files, cwd=folder)
        if _prune_due(started):
            _restic_unlocked("forget", "--quiet", "--host", "karta", *KEEP, "--prune")
            with db.tx() as c:
                db.put_setting(c, "cloud_last_prune", started.strftime("%Y-%m-%dT%H:%M:%S"))
        _record("ok", seconds=(datetime.now(timezone.utc) - started).total_seconds())
        log.info("Cloud backup done")
    except Exception as e:
        _record("fail", str(e), seconds=(datetime.now(timezone.utc) - started).total_seconds())
        log.warning("Cloud backup failed: %s", e)
        raise
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def list_backups(base: str | None = None) -> list[dict]:
    """The snapshots in the cloud, newest first: [{id, time (local, ISO), kind}]."""
    raw = _run("restic", "snapshots", "--json", "--host", "karta", timeout=300, base=base)
    out = []
    for s in json.loads(raw or "[]") or []:
        try:
            t = datetime.fromisoformat(s["time"][:19]).replace(tzinfo=timezone.utc).astimezone(config.TZ).replace(tzinfo=None)
        except (KeyError, ValueError):
            continue
        out.append({"id": s.get("short_id") or s["id"][:8], "time": t.isoformat(timespec="minutes")})
    out.sort(key=lambda x: x["time"], reverse=True)
    return out


def download(snapshot_id: str, dest: str) -> str | None:
    """Writes the snapshot's database to dest and returns the PIN_KEY kept with it (None for a snapshot made before
    Karta 1.7.5). One restic run for both: each run costs the time to reach the cloud again."""
    if not SNAPSHOT_ID.match(snapshot_id or ""):
        raise CloudError("Μη έγκυρο αντίγραφο.")
    work = os.path.join(data_dir(), ".cloud-download")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work, mode=0o700)
    try:
        _run("restic", "restore", snapshot_id, "--target", work,
             "--include", FILE_IN_SNAPSHOT, "--include", KEY_IN_SNAPSHOT)
        got = os.path.join(work, FILE_IN_SNAPSHOT.lstrip("/"))
        if not os.path.isfile(got):
            raise CloudError("Το αντίγραφο δεν έχει βάση δεδομένων της Karta.")
        os.replace(got, dest)
        try:
            with open(os.path.join(work, KEY_IN_SNAPSHOT.lstrip("/")), encoding="utf-8") as f:
                return f.read().strip() or None
        except OSError:
            return None
    finally:
        shutil.rmtree(work, ignore_errors=True)


def due(now: datetime) -> bool:
    """Tonight's snapshot is due after 23:40 once a day; any time when the last good one is over 36 hours old
    (the machine was off at night), or the last attempt failed (a slow cloud is usually fine an hour later).
    After an attempt, wait an hour before the next."""
    if not connected():
        return False
    last_try = db.setting("cloud_last_try")
    if last_try and now - datetime.fromisoformat(last_try) < timedelta(hours=1):
        return False
    raw = db.setting("cloud_last_ok")
    last_ok = datetime.fromisoformat(raw) if raw else None
    tonight = now.replace(hour=RUN_AT[0], minute=RUN_AT[1], second=0, microsecond=0)
    if now >= tonight and (last_ok is None or last_ok < tonight):
        return True
    try:
        if json.loads(db.setting("cloud_status") or "null")["state"] == "fail":
            return True
    except (ValueError, KeyError, TypeError):
        pass
    return last_ok is None or now - last_ok >= timedelta(hours=36)


def worker(stop: threading.Event) -> None:
    while not stop.wait(60):
        try:
            now = datetime.now(config.TZ).replace(tzinfo=None)
            if due(now):
                with db.tx() as c:
                    db.put_setting(c, "cloud_last_try", now.isoformat(timespec="seconds"))
                run_backup(now)
        except CloudError:
            pass
        except Exception:
            log.exception("cloud worker failed")
