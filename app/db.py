"""SQLite storage. Single process, serialized with one lock (tiny workload)."""
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

from . import config

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS employees (
    id              INTEGER PRIMARY KEY,
    afm             TEXT NOT NULL UNIQUE,
    last_name       TEXT NOT NULL,
    first_name      TEXT NOT NULL,
    display_name    TEXT NOT NULL,
    pin_hash        TEXT NOT NULL,
    active          INTEGER NOT NULL DEFAULT 1,
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until    TEXT,
    created_at      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS devices (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    token_hash  TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL,
    last_seen   TEXT,
    revoked     INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS enroll_codes (
    code_hash   TEXT PRIMARY KEY,
    device_name TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    used        INTEGER NOT NULL DEFAULT 0,
    created_by  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS movements (
    id                 INTEGER PRIMARY KEY,
    employee_id        INTEGER NOT NULL REFERENCES employees(id),
    type               TEXT NOT NULL CHECK (type IN ('ARRIVAL','DEPARTURE')),
    movement_at        TEXT NOT NULL,          -- Europe/Athens local, naive ISO, seconds
    created_at         TEXT NOT NULL,          -- UTC ISO
    device_id          INTEGER REFERENCES devices(id),
    client_ip          TEXT,
    mode               TEXT NOT NULL,          -- dry_run / trial / production at creation
    status             TEXT NOT NULL,          -- pending / submitted / dry_run / failed / uncertain /
                                               -- local (entered by admin in karta only: NEVER sent to Ergani) /
                                               -- onboarding (onboarding period: recorded, NEVER sent, see onboarding.py)
    attempts           INTEGER NOT NULL DEFAULT 0,
    next_attempt_at    TEXT NOT NULL,          -- UTC ISO
    pending_reason     TEXT,                   -- justification to use if it becomes late
    late_justification TEXT,
    last_error         TEXT,
    protocol           TEXT,
    submission_id      TEXT,
    response_json      TEXT,
    submitted_at       TEXT
);
CREATE INDEX IF NOT EXISTS ix_mov_emp ON movements(employee_id, movement_at);
CREATE INDEX IF NOT EXISTS ix_mov_status ON movements(status, next_attempt_at);
CREATE TABLE IF NOT EXISTS audit (
    id      INTEGER PRIMARY KEY,
    at      TEXT NOT NULL,
    actor   TEXT NOT NULL,
    action  TEXT NOT NULL,
    detail  TEXT
);
CREATE TABLE IF NOT EXISTS schedules (
    employee_id INTEGER NOT NULL REFERENCES employees(id),
    weekday     INTEGER NOT NULL CHECK (weekday BETWEEN 0 AND 6),   -- Monday = 0
    start       TEXT NOT NULL,                                       -- HH:MM
    "end"       TEXT NOT NULL,                                       -- HH:MM
    break_min   INTEGER NOT NULL DEFAULT 0,                          -- flexible break, taken as work allows
    segments    TEXT,                                                -- split shift: 'HH:MM-HH:MM,HH:MM-HH:MM'
    PRIMARY KEY (employee_id, weekday)
);
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS alerts (
    id            INTEGER PRIMARY KEY,
    key           TEXT NOT NULL UNIQUE,      -- dedupe: kind:employee:date
    employee_id   INTEGER REFERENCES employees(id),
    kind          TEXT NOT NULL,
    level         TEXT NOT NULL,             -- info / warning / urgent
    message       TEXT NOT NULL,             -- full text for admin + phone
    kiosk_message TEXT,                      -- neutral text shown on the shop laptop (NULL = admin only)
    created_at    TEXT NOT NULL,             -- Europe/Athens local
    resolved_at   TEXT
);
CREATE INDEX IF NOT EXISTS ix_alerts_open ON alerts(resolved_at, created_at);
CREATE TABLE IF NOT EXISTS card_links (             -- time-limited personal link to a QR card (sent by Viber/SMS)
    token_hash      TEXT PRIMARY KEY,
    employee_id     INTEGER NOT NULL REFERENCES employees(id),
    qr_hash         TEXT NOT NULL,                  -- the card it shows; a new/cancelled card kills the link
    created_at      TEXT NOT NULL,
    expires_at      TEXT NOT NULL,                  -- UTC ISO
    first_opened_at TEXT,
    opens           INTEGER NOT NULL DEFAULT 0,
    revoked         INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS leaves (                 -- time off: no reminders / alerts, «Άδεια» in the report
    id          INTEGER PRIMARY KEY,
    employee_id INTEGER NOT NULL REFERENCES employees(id),
    start_date  TEXT NOT NULL,                     -- YYYY-MM-DD, inclusive
    end_date    TEXT NOT NULL,                     -- YYYY-MM-DD, inclusive (last day off)
    note        TEXT,
    created_at  TEXT NOT NULL,
    created_by  TEXT
);
CREATE INDEX IF NOT EXISTS ix_leaves_emp ON leaves(employee_id, end_date);
CREATE TABLE IF NOT EXISTS closures (               -- shop closed (renovation, extra day off...): no one is expected
    id          INTEGER PRIMARY KEY,
    start_date  TEXT NOT NULL,                     -- YYYY-MM-DD, inclusive
    end_date    TEXT NOT NULL,                     -- YYYY-MM-DD, inclusive
    reason      TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    created_by  TEXT
);
CREATE TABLE IF NOT EXISTS day_changes (           -- one-day change of the declared schedule (declared in Ergani first)
    employee_id INTEGER NOT NULL REFERENCES employees(id),
    day         TEXT NOT NULL,                     -- YYYY-MM-DD
    kind        TEXT NOT NULL CHECK (kind IN ('overtime','change','off')),
    text        TEXT NOT NULL DEFAULT '',          -- schedule of that day ('10:00-18:30/+30'); '' = no work (kind 'off')
    note        TEXT,
    created_at  TEXT NOT NULL,
    created_by  TEXT,
    PRIMARY KEY (employee_id, day)
);
CREATE TABLE IF NOT EXISTS schedule_versions (      -- schedule history: each save applies from valid_from on
    employee_id INTEGER NOT NULL REFERENCES employees(id),
    valid_from  TEXT NOT NULL,                     -- YYYY-MM-DD (baseline of older installs: 2000-01-01)
    days        TEXT NOT NULL,                     -- JSON {"1": "10:00-17:00/30", ...}; Monday = 0; missing = day off
    created_at  TEXT NOT NULL,
    created_by  TEXT,
    PRIMARY KEY (employee_id, valid_from)
);
CREATE TABLE IF NOT EXISTS early_leaves (         -- «Έφυγε νωρίτερα»: why someone left before the end of the day
    employee_id INTEGER NOT NULL REFERENCES employees(id),
    day         TEXT NOT NULL,                     -- YYYY-MM-DD
    reason      TEXT NOT NULL CHECK (reason IN ('sick','personal','other')),
    note        TEXT,
    created_at  TEXT NOT NULL,
    created_by  TEXT,
    PRIMARY KEY (employee_id, day)
);
CREATE TABLE IF NOT EXISTS ergani_info (          -- what Ergani says (reference only)
    employee_id   INTEGER PRIMARY KEY REFERENCES employees(id),
    schedule      TEXT,
    weekly_hours  TEXT,
    break_minutes INTEGER,
    break_within  TEXT,
    working_card  TEXT,
    week_days     TEXT,
    employment    TEXT,
    arrangement   TEXT,
    digital_org   TEXT,
    fetched_at    TEXT NOT NULL
);
"""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def init() -> None:
    global _conn
    _conn = sqlite3.connect(config.DB_PATH, check_same_thread=False, isolation_level=None)
    _conn.row_factory = sqlite3.Row
    _conn.execute("PRAGMA journal_mode=WAL")
    _conn.execute("PRAGMA foreign_keys=ON")
    _conn.execute("PRAGMA busy_timeout=5000")
    _conn.executescript(SCHEMA)
    # migrations for databases created by earlier versions
    emcols = {r[1] for r in _conn.execute("PRAGMA table_info(employees)")}
    for col in ("pin_enc", "qr_hash", "qr_enc", "qr_issued_at"):   # qr_*: personal QR card (hash, sealed copy)
        if col not in emcols:
            _conn.execute(f"ALTER TABLE employees ADD COLUMN {col} TEXT")
    if "flex_arrival" not in emcols:   # «ευέλικτη προσέλευση» in minutes (0 = none, up to 120)
        _conn.execute("ALTER TABLE employees ADD COLUMN flex_arrival INTEGER NOT NULL DEFAULT 0")
    _conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS employees_qr ON employees(qr_hash) WHERE qr_hash IS NOT NULL")
    if "hidden" not in {r[1] for r in _conn.execute("PRAGMA table_info(devices)")}:
        _conn.execute("ALTER TABLE devices ADD COLUMN hidden INTEGER NOT NULL DEFAULT 0")   # «Διαγραφή» from the list
    if "cleared" not in {r[1] for r in _conn.execute("PRAGMA table_info(alerts)")}:
        _conn.execute("ALTER TABLE alerts ADD COLUMN cleared INTEGER NOT NULL DEFAULT 0")   # «Εκκαθάριση» of the admin list
    if "auth_method" not in {r[1] for r in _conn.execute("PRAGMA table_info(movements)")}:
        _conn.execute("ALTER TABLE movements ADD COLUMN auth_method TEXT")   # 'pin' / 'qr' (NULL = before QR existed)
    if "kind" not in {r[1] for r in _conn.execute("PRAGMA table_info(leaves)")}:
        # regular = κανονική άδεια, sick = άδεια ασθενείας, special = άδεια ειδικού σκοπού
        _conn.execute("ALTER TABLE leaves ADD COLUMN kind TEXT NOT NULL DEFAULT 'regular'")
    if "note" not in {r[1] for r in _conn.execute("PRAGMA table_info(movements)")}:
        _conn.execute("ALTER TABLE movements ADD COLUMN note TEXT")   # admin note (e.g. why a shift was closed in karta only)
    ecols = {r[1] for r in _conn.execute("PRAGMA table_info(ergani_info)")}
    for col in ("week_days", "employment", "arrangement", "digital_org", "flex_arrival"):
        if col not in ecols:
            _conn.execute(f"ALTER TABLE ergani_info ADD COLUMN {col} TEXT")
    cols = {r[1] for r in _conn.execute("PRAGMA table_info(schedules)")}
    if "break_min" not in cols:
        _conn.execute("ALTER TABLE schedules ADD COLUMN break_min INTEGER NOT NULL DEFAULT 0")
    if "segments" not in cols:
        _conn.execute("ALTER TABLE schedules ADD COLUMN segments TEXT")   # 'HH:MM-HH:MM,HH:MM-HH:MM' for split shifts


@contextmanager
def tx():
    with _lock:
        _conn.execute("BEGIN IMMEDIATE")
        try:
            yield _conn
            _conn.execute("COMMIT")
        except BaseException:
            _conn.execute("ROLLBACK")
            raise


def all_rows(sql: str, args=()) -> list[sqlite3.Row]:
    with _lock:
        return _conn.execute(sql, args).fetchall()


def one(sql: str, args=()) -> sqlite3.Row | None:
    with _lock:
        return _conn.execute(sql, args).fetchone()


def setting(key: str, default: str | None = None) -> str | None:
    """A value of the settings table (key/value), or default."""
    r = one("SELECT value FROM settings WHERE key=?", (key,))
    return r["value"] if r else default


def put_setting(c, key: str, value: str) -> None:
    """Insert or replace a setting inside an open transaction (c = the connection from tx())."""
    c.execute("INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
              (key, value))


def audit(actor: str, action: str, detail: str = "") -> None:
    with tx() as c:
        c.execute("INSERT INTO audit(at, actor, action, detail) VALUES (?,?,?,?)",
                  (utc_now_iso(), actor, action, detail))
