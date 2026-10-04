"""Encrypted backups to the cloud, made by Karta itself («Ρυθμίσεις» → «Αντίγραφα ασφαλείας»).

rclone (in the image) uploads a copy of the whole database every night to Google Drive, Dropbox or Backblaze B2,
through an rclone *crypt* remote: names and contents are encrypted on this machine with a password that is shown
to the admin once. The rclone configuration lives next to the database (/data/rclone.conf, mode 600).

In the cloud:  daily/karta-YYYY-MM-DD.db (30 days) · monthly/karta-YYYY-MM.db (24 months) · yearly/karta-YYYY.db
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

REMOTE = "karta-cloud:"
PROVIDERS = {"drive": "Google Drive", "dropbox": "Dropbox", "b2": "Backblaze B2"}
RUN_AT = (23, 40)                         # nightly upload, local time
BACKUP_NAME = re.compile(r"^(daily|monthly|yearly)/karta-\d{4}(-\d{2}){0,2}\.db$")
_running = threading.Lock()


class CloudError(Exception):
    pass


def data_dir() -> str:
    return os.path.dirname(os.path.abspath(config.DB_PATH))


def conf_path() -> str:
    return os.path.join(data_dir(), "rclone.conf")


def available() -> bool:
    return shutil.which("rclone") is not None


def _rclone(*args: str, stdin: str | None = None, timeout: int = 900) -> str:
    if not available():
        raise CloudError("Το rclone δεν υπάρχει σε αυτή την εγκατάσταση (χρειάζεται το image της Karta 1.2 ή νεότερο).")
    cache = os.path.join(data_dir(), ".rclone-cache")     # the app user has no home folder in the image
    env = {**os.environ, "RCLONE_CONFIG": conf_path(), "RCLONE_CACHE_DIR": cache, "XDG_CACHE_HOME": cache}
    try:
        r = subprocess.run(["rclone", *args], input=stdin, capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        raise CloudError("Το cloud δεν απάντησε εγκαίρως.")
    if r.returncode != 0:
        lines = [x for x in (r.stderr or "").strip().splitlines() if x.strip()]
        raise CloudError(lines[-1][-300:] if lines else f"rclone: κωδικός {r.returncode}")
    return r.stdout


def connected() -> bool:
    try:
        with open(conf_path(), encoding="utf-8") as f:
            return "[karta-cloud]" in f.read()
    except OSError:
        return False


def _forget() -> None:
    try:
        os.remove(conf_path())
    except FileNotFoundError:
        pass


def connect(provider: str, *, token: str = "", account: str = "", key: str = "", bucket: str = "",
            password: str | None = None, local_path: str = "") -> str | None:
    """Sets up the cloud. Without a password a new one is made and returned (show it once); with the password of
    existing backups (restore on a new machine) it checks that they can be read and returns None."""
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
        _rclone("config", "create", "karta-store", *store, "--non-interactive")
        _rclone("config", "create", "karta-cloud", "crypt", "remote", base, "password", password,
                "--obscure", "--non-interactive")
        os.chmod(conf_path(), 0o600)
        if new:
            _rclone("rcat", REMOTE + ".karta-test", stdin="ok")
            _rclone("deletefile", REMOTE + ".karta-test")
        elif not list_backups():
            raise CloudError("Δεν βρέθηκαν αντίγραφα με αυτόν τον κωδικό (λάθος κωδικός, ή άλλος λογαριασμός/φάκελος).")
    except Exception:
        _forget()
        raise
    with db.tx() as c:
        db.put_setting(c, "cloud_provider", provider)
    return password if new else None


def disconnect() -> None:
    """Stops the uploads on this machine. What is already in the cloud stays there."""
    _forget()
    with db.tx() as c:
        c.execute("DELETE FROM settings WHERE key IN ('cloud_provider', 'cloud_status', 'cloud_last_ok', 'cloud_last_try')")


def _record(state: str, error: str = "") -> None:
    with db.tx() as c:
        if state == "ok":
            db.put_setting(c, "cloud_last_ok", datetime.now(config.TZ).replace(tzinfo=None).isoformat(timespec="seconds"))
        db.put_setting(c, "cloud_status", json.dumps({
            "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"), "state": state, "error": error[:300]}))


def status() -> dict | None:
    """Provider and the last upload (with its local time), or None when the cloud is not set up."""
    if not connected():
        return None
    out = {"provider": PROVIDERS.get(db.setting("cloud_provider") or "", "cloud"), "state": None, "when": None, "error": ""}
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
    """Uploads tonight's copy (and refreshes this month's and this year's), then removes old ones."""
    if not _running.acquire(blocking=False):
        raise CloudError("Ένα ανέβασμα τρέχει ήδη.")
    tmp = os.path.join(data_dir(), "cloud-upload.db")
    try:
        now = now or datetime.now(config.TZ).replace(tzinfo=None)
        snapshot(tmp)
        _rclone("copyto", tmp, f"{REMOTE}daily/karta-{now:%Y-%m-%d}.db")
        _rclone("copyto", tmp, f"{REMOTE}monthly/karta-{now:%Y-%m}.db")
        _rclone("copyto", tmp, f"{REMOTE}yearly/karta-{now:%Y}.db")
        _rclone("delete", "--min-age", "31d", f"{REMOTE}daily")
        _rclone("delete", "--min-age", "731d", f"{REMOTE}monthly")
        _record("ok")
        log.info("Cloud backup uploaded")
    except Exception as e:
        _record("fail", str(e))
        log.warning("Cloud backup failed: %s", e)
        raise
    finally:
        _running.release()
        try:
            os.remove(tmp)
        except FileNotFoundError:
            pass


def list_backups() -> list[dict]:
    """The copies in the cloud, newest first: [{path, size, modified}]."""
    out = []
    raw = _rclone("lsjson", "--recursive", "--files-only", REMOTE, timeout=120)
    for f in json.loads(raw or "[]"):
        if BACKUP_NAME.match(f.get("Path", "")):
            out.append({"path": f["Path"], "size": f.get("Size", 0), "modified": f.get("ModTime", "")[:19]})
    order = {"daily": 0, "monthly": 1, "yearly": 2}
    out.sort(key=lambda x: x["path"], reverse=True)                   # newest first (dates in the names)
    out.sort(key=lambda x: order[x["path"].split("/")[0]])            # then daily, monthly, yearly (stable)
    return out


def download(path: str, dest: str) -> None:
    if not BACKUP_NAME.match(path or ""):
        raise CloudError("Μη έγκυρο αντίγραφο.")
    _rclone("copyto", REMOTE + path, dest)


def due(now: datetime) -> bool:
    """Tonight's upload is due after 23:40 once a day; any time when the last good one is over 36 hours old
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
