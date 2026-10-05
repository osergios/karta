"""Encrypted backups to the cloud, made by Karta itself («Ρυθμίσεις» → «Αντίγραφα ασφαλείας»).

Every night restic (in the image) takes a snapshot of the whole database into a repository in Google Drive, Dropbox
or Backblaze B2, reached through rclone (also in the image). restic encrypts everything on this machine with a
password shown to the admin once, compresses it, and stores only what changed since the previous snapshot: keeping
30 daily, 24 monthly and one yearly snapshot costs little more than a single copy. Each snapshot is still a complete
database and restores on its own.

On this machine, next to the database: rclone.conf (access to the cloud), cloud-password and cloud.json (mode 600).
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
SNAPSHOT_ID = re.compile(r"^[0-9a-f]{8,64}$")
FILE_IN_SNAPSHOT = "/karta.db"
_running = threading.Lock()


class CloudError(Exception):
    pass


def data_dir() -> str:
    return os.path.dirname(os.path.abspath(config.DB_PATH))


def conf_path() -> str:
    return os.path.join(data_dir(), "rclone.conf")


def _pw_path() -> str:
    return os.path.join(data_dir(), "cloud-password")


def _info_path() -> str:
    return os.path.join(data_dir(), "cloud.json")


def available() -> bool:
    return shutil.which("rclone") is not None and shutil.which("restic") is not None


def _env() -> dict:
    cache = os.path.join(data_dir(), ".cache")          # the app user has no home folder in the image
    env = {**os.environ, "RCLONE_CONFIG": conf_path(), "RCLONE_CACHE_DIR": os.path.join(cache, "rclone"),
           "XDG_CACHE_HOME": cache, "RESTIC_CACHE_DIR": os.path.join(cache, "restic"),
           "RESTIC_PASSWORD_FILE": _pw_path(), "HOME": data_dir()}
    info = _info()
    if info:
        env["RESTIC_REPOSITORY"] = info["repo"]
    return env


def _run(tool: str, *args: str, timeout: int = 900, cwd: str | None = None, stdout=None) -> str:
    if not available():
        raise CloudError("Το rclone / restic δεν υπάρχει σε αυτή την εγκατάσταση (χρειάζεται νεότερο image της Karta).")
    try:
        r = subprocess.run([tool, *args], stdout=stdout if stdout is not None else subprocess.PIPE,
                           stderr=subprocess.PIPE, text=stdout is None, timeout=timeout, env=_env(), cwd=cwd)
    except subprocess.TimeoutExpired:
        raise CloudError("Το cloud δεν απάντησε εγκαίρως.")
    if r.returncode != 0:
        err = r.stderr if isinstance(r.stderr, str) else r.stderr.decode("utf-8", "replace")
        log.warning("%s %s failed (%s): %s", tool, args[0] if args else "", r.returncode, err.strip())
        raise CloudError(explain(err, tool, r.returncode))
    return r.stdout if stdout is None else ""


# what restic / rclone say -> what the admin reads (the first match wins)
_KNOWN = [
    (re.compile(r"Is there a repository|unable to open config file", re.I),
     "Δεν βρέθηκαν αντίγραφα σε αυτόν τον φάκελο του cloud"),
    (re.compile(r"repository is already locked", re.I),
     "Τα αντίγραφα είναι κλειδωμένα από προηγούμενη εργασία που διακόπηκε"),
    (re.compile(r"wrong password", re.I), "λάθος κωδικός κρυπτογράφησης"),
    (re.compile(r"quota", re.I), "Ο χώρος στο cloud γέμισε"),               # also a 403: before the next line
    (re.compile(r"\b40[13]\b|invalid_grant|token expired|expired_access_token", re.I),
     "Η πρόσβαση στο cloud έληξε — συνδέστε ξανά"),
]


def explain(err: str, tool: str = "restic", code: int = 1) -> str:
    """A tool's error output as one short message: a known case in Greek, otherwise its last lines."""
    for pattern, message in _KNOWN:
        if pattern.search(err):
            return message
    lines = [x.strip() for x in err.strip().splitlines() if x.strip()]
    return " · ".join(lines[-3:])[-300:] if lines else f"{tool}: κωδικός {code}"


def _info() -> dict | None:
    try:
        with open(_info_path(), encoding="utf-8") as f:
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
    password = password or "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789")
                                   for _ in range(24))
    _forget()
    try:
        _run("rclone", "config", "create", "karta-store", *store, "--non-interactive")
        os.chmod(conf_path(), 0o600)
        _write_private(_pw_path(), password)
        _write_private(_info_path(), json.dumps({"provider": provider, "repo": "rclone:" + base}))
        if new:
            try:
                _run("restic", "init", timeout=300)
            except CloudError as e:
                if "already" in str(e).lower() or "exist" in str(e).lower():
                    raise CloudError("Υπάρχουν ήδη αντίγραφα της Karta σε αυτόν τον λογαριασμό: χρησιμοποιήστε "
                                     "«Έχω ήδη αντίγραφα στο cloud» με τον κωδικό τους.")
                raise
        elif not list_backups():
            raise CloudError("Δεν βρέθηκαν αντίγραφα της Karta σε αυτόν τον λογαριασμό.")
    except Exception:
        _forget()
        raise
    try:
        _backup()                      # the first snapshot; a failure is recorded and shown, the connection stays
    except Exception:
        pass
    return password if new else None


def disconnect() -> None:
    """Stops the uploads on this machine. What is already in the cloud stays there."""
    _forget()
    with db.tx() as c:
        c.execute("DELETE FROM settings WHERE key IN ('cloud_status', 'cloud_last_ok', 'cloud_last_try')")


def _record(state: str, error: str = "") -> None:
    with db.tx() as c:
        if state == "ok":
            db.put_setting(c, "cloud_last_ok", datetime.now(config.TZ).replace(tzinfo=None).isoformat(timespec="seconds"))
        db.put_setting(c, "cloud_status", json.dumps({
            "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"), "state": state, "error": error[:300]}))


def status() -> dict | None:
    """Provider and the last snapshot (with its local time), or None when the cloud is not set up."""
    if not connected():
        return None
    out = {"provider": PROVIDERS.get((_info() or {}).get("provider", ""), "cloud"), "state": None, "when": None, "error": ""}
    try:
        s = json.loads(db.setting("cloud_status") or "null")
        if s:
            out.update(state=s["state"], error=s.get("error", ""),
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


def run_backup(now: datetime | None = None) -> None:
    """Tonight's snapshot (or one asked for in the admin page)."""
    if not _running.acquire(blocking=False):
        raise CloudError("Ένα ανέβασμα τρέχει ήδη.")
    try:
        _backup()
    finally:
        _running.release()


def _backup() -> None:
    """A snapshot, then the old ones are thinned out (30 daily, 24 monthly, yearly for good). The caller holds
    _running."""
    folder = os.path.join(data_dir(), "cloud-snapshot")
    try:
        os.makedirs(folder, exist_ok=True)
        snapshot(os.path.join(folder, "karta.db"))
        _run("restic", "unlock", timeout=300)                  # a lock left by an interrupted run
        _run("restic", "backup", "--quiet", "--host", "karta", "--tag", "karta", "karta.db", cwd=folder)
        _run("restic", "forget", "--quiet", "--host", "karta", *KEEP, "--prune")
        _record("ok")
        log.info("Cloud backup done")
    except Exception as e:
        _record("fail", str(e))
        log.warning("Cloud backup failed: %s", e)
        raise
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def list_backups() -> list[dict]:
    """The snapshots in the cloud, newest first: [{id, time (local, ISO), kind}]."""
    raw = _run("restic", "snapshots", "--json", "--host", "karta", timeout=300)
    out = []
    for s in json.loads(raw or "[]") or []:
        try:
            t = datetime.fromisoformat(s["time"][:19]).replace(tzinfo=timezone.utc).astimezone(config.TZ).replace(tzinfo=None)
        except (KeyError, ValueError):
            continue
        out.append({"id": s.get("short_id") or s["id"][:8], "time": t.isoformat(timespec="minutes")})
    out.sort(key=lambda x: x["time"], reverse=True)
    return out


def download(snapshot_id: str, dest: str) -> None:
    if not SNAPSHOT_ID.match(snapshot_id or ""):
        raise CloudError("Μη έγκυρο αντίγραφο.")
    with open(dest, "wb") as f:
        _run("restic", "dump", snapshot_id, FILE_IN_SNAPSHOT, stdout=f)


def due(now: datetime) -> bool:
    """Tonight's snapshot is due after 23:40 once a day; any time when the last good one is over 36 hours old
    (the machine was off at night). After an attempt, wait an hour before the next."""
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
