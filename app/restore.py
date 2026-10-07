"""Restore from a backup, from the admin page («Ρυθμίσεις» → «Αντίγραφα ασφαλείας» → «Επαναφορά»).

Two steps, so nothing is replaced by surprise: stage() keeps the uploaded (or downloaded) file aside and says what
is in it; apply() keeps a copy of the current database, then puts the staged one in its place while Karta runs.

A cloud backup also carries the PIN_KEY its secrets were sealed with (cloud.py). Restored on a new machine whose
.env has another key, that key is kept next to the database and used from then on (config.restored_pin_key_path),
so the Ergani password, the ntfy token, the PINs and the QR cards open as before, with nothing to type.
"""
import os
import sqlite3
from datetime import datetime

from . import config, db, security

HEADER = b"SQLite format 3\x00"
NEEDED = {"employees", "movements", "settings"}


class RestoreError(Exception):
    pass


def staged_path() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(config.DB_PATH)), "restore-pending.db")


def staged_key_path() -> str:
    """The PIN_KEY that came with a staged cloud backup."""
    return staged_path() + ".key"


def stage_key(key: str | None) -> None:
    _remove(staged_key_path())
    if key:
        fd = os.open(staged_key_path(), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(key.strip())


def _staged_key() -> str | None:
    try:
        with open(staged_key_path(), encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


def _pin_key_matches(c, key: str | None = None) -> bool | None:
    """Can this installation's PIN_KEY (or `key`) open what the backup sealed? None when there is nothing sealed."""
    sealed = [(r[0], b"workcard-pin") for r in c.execute(
        "SELECT pin_enc FROM employees WHERE pin_enc IS NOT NULL LIMIT 3")]
    sealed += [(r[1], f"karta-cfg-{r[0][4:]}".encode()) for r in c.execute(
        "SELECT key, value FROM settings WHERE key IN ('cfg.ERGANI_PASSWORD','cfg.ERGANI_TRIAL_PASSWORD','cfg.NTFY_TOKEN') "
        "AND value <> ''")]
    if not sealed:
        return None
    if not (key or config.PIN_KEY):
        return False
    return any(security.open_pin(v, aad, key) is not None for v, aad in sealed)


def inspect(path: str | None = None) -> dict:
    """What a backup holds, after checking that it is a sound Karta database."""
    path = path or staged_path()
    try:
        with open(path, "rb") as f:
            if f.read(16) != HEADER:
                raise RestoreError("Το αρχείο δεν είναι αντίγραφο της Karta (δεν είναι βάση SQLite).")
    except FileNotFoundError:
        raise RestoreError("Δεν υπάρχει αρχείο για επαναφορά: ανεβάστε ή διαλέξτε πρώτα ένα αντίγραφο.")
    try:
        c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error as e:
        raise RestoreError(f"Το αρχείο δεν ανοίγει ({e}).")
    try:
        if c.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise RestoreError("Το αρχείο είναι χαλασμένο: διαλέξτε άλλο αντίγραφο.")
        tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not NEEDED <= tables:
            raise RestoreError("Το αρχείο δεν είναι αντίγραφο της Karta.")
        last = c.execute("SELECT MAX(movement_at) FROM movements WHERE mode='production'").fetchone()[0]
        any_last = c.execute("SELECT MAX(movement_at) FROM movements").fetchone()[0]
        name = c.execute("SELECT value FROM settings WHERE key='brand_name'").fetchone()
        return {
            "business": name[0] if name else "",
            "employees": c.execute("SELECT COUNT(*) FROM employees WHERE active=1").fetchone()[0],
            "punches": c.execute("SELECT COUNT(*) FROM movements WHERE mode='production'").fetchone()[0],
            "test_punches": c.execute("SELECT COUNT(*) FROM movements WHERE mode<>'production'").fetchone()[0],
            "last_punch": last or any_last,
            "pin_key_ok": _pin_key_matches(c),
            "pin_key_restored": _adoptable(c),
            "size": os.path.getsize(path),
        }
    except sqlite3.DatabaseError as e:
        raise RestoreError(f"Το αρχείο δεν διαβάζεται ({e}).")
    finally:
        c.close()


def stage_file(src_path: str) -> dict:
    """Takes a file already written next to the database (upload or cloud download) as the one to restore."""
    os.replace(src_path, staged_path())
    try:
        return inspect()
    except RestoreError:
        discard()
        raise


def _remove(*paths: str) -> None:
    for p in paths:
        try:
            os.remove(p)
        except FileNotFoundError:
            pass


def discard() -> None:
    p = staged_path()
    _remove(p, p + "-wal", p + "-shm", staged_key_path())


def _adoptable(c) -> bool:
    """The backup's own PIN_KEY came with it, this installation's doesn't open the backup, and that one does."""
    key = _staged_key()
    return bool(key) and key != config.PIN_KEY and _pin_key_matches(c) is False and _pin_key_matches(c, key) is True


def _key_to_adopt() -> str | None:
    """The staged backup's own PIN_KEY, when that is the key that opens it (and this installation's isn't)."""
    try:
        c = sqlite3.connect(f"file:{staged_path()}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    try:
        return _staged_key() if _adoptable(c) else None
    finally:
        c.close()


def _use_key(key: str) -> None:
    fd = os.open(config.restored_pin_key_path(), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(key)
    config.PIN_KEY = key


def apply(after) -> str:
    """Replaces the database with the staged backup. Returns the name of the copy kept of the current one.
    `after` runs once the new database is open (migrations, settings), still holding the lock."""
    inspect()
    data = os.path.dirname(os.path.abspath(config.DB_PATH))
    keep = os.path.join(data, f"before-restore-{datetime.now():%Y%m%d-%H%M%S}.db")
    dst = sqlite3.connect(keep)
    try:
        with db._lock:
            db._conn.backup(dst)
    finally:
        dst.close()
    new_key = _key_to_adopt()
    with db._lock:
        db._conn.close()                       # the last connection: SQLite folds the WAL back into the file
        _remove(config.DB_PATH + "-wal", config.DB_PATH + "-shm")
        try:
            os.replace(staged_path(), config.DB_PATH)
            _remove(staged_path() + "-wal", staged_path() + "-shm")   # left by the read-only check
            if new_key:                        # before the settings are read: they open with this key
                _use_key(new_key)
        finally:
            _remove(staged_key_path())
            db.init()                          # the restored database, or the old one if the swap failed
        after()
    return os.path.basename(keep)
