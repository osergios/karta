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
    pin_enc         TEXT,                     -- PIN sealed with PIN_KEY (admin can view it), or NULL
    qr_hash         TEXT,                     -- personal QR card: hash of its code
    qr_enc          TEXT,                     -- ... and the code sealed with PIN_KEY
    qr_issued_at    TEXT,
    flex_arrival    INTEGER NOT NULL DEFAULT 0,   -- «ευέλικτη προσέλευση» in minutes (0 = none, up to 120)
    active          INTEGER NOT NULL DEFAULT 1,
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until    TEXT,
    created_at      TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS employees_qr ON employees(qr_hash) WHERE qr_hash IS NOT NULL;
CREATE TABLE IF NOT EXISTS devices (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    token_hash  TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL,
    last_seen   TEXT,
    revoked     INTEGER NOT NULL DEFAULT 0,
    hidden      INTEGER NOT NULL DEFAULT 0      -- «Διαγραφή» from the list
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
    submitted_at       TEXT,
    auth_method        TEXT,                   -- 'pin' / 'qr' (NULL = entered by the admin)
    note               TEXT                    -- admin note (e.g. why a shift was closed in karta only)
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
    kiosk_message TEXT,                      -- neutral text shown on the shop screen (NULL = admin only)
    created_at    TEXT NOT NULL,             -- Europe/Athens local
    resolved_at   TEXT,
    cleared       INTEGER NOT NULL DEFAULT 0 -- «Εκκαθάριση» of the admin list
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
    created_by  TEXT,
    kind        TEXT NOT NULL DEFAULT 'regular' -- regular = κανονική, sick = ασθενείας, special = ειδικού σκοπού
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
    valid_from  TEXT NOT NULL,                     -- YYYY-MM-DD
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
    flex_arrival  TEXT,
    fetched_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ergani_week (          -- the hours last declared in Ergani's digital organisation (EX_BASE_08)
    employee_id   INTEGER PRIMARY KEY REFERENCES employees(id),
    declared_week TEXT NOT NULL,                  -- JSON {"proposal": {weekday: "HH:MM-HH:MM+…"}, "from": date, "to": date}
    fetched_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ergani_month (         -- «Έλεγχος μήνα με ΕΡΓΑΝΗ»: what Ergani gave for a closed month
    month       TEXT PRIMARY KEY,                 -- YYYY-MM
    fetched_at  TEXT NOT NULL,
    declared    TEXT NOT NULL,                    -- JSON {date: [{afm, type, start, end, break_min, break_in}]} (EX_BASE_08)
    actual      TEXT NOT NULL                     -- JSON {date: [{afm, start, end, next_day}]} (EX_BASE_07)
);
"""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


# Changes to the schema of databases made by an earlier version, in order: step N brings a database to version N
# (PRAGMA user_version). To change the schema, add the column to SCHEMA above (new databases) AND a step at the end
# of this list (existing ones), idempotent: e.g. `if not _has_column(c, "employees", "x"): c.execute("ALTER TABLE
# employees ADD COLUMN x TEXT")`. Only add: an older version must still run on the database after going back.
# Never edit or reorder an existing step: databases out there have already run it.
def _v1(c) -> None:
    """The schema of Karta 1.4: nothing to change, it only gets a version number. (An older installation may still
    hold the unused «schedules» table: it stays as it is.)"""


MIGRATIONS = [_v1]


def _has_column(c, table: str, column: str) -> bool:
    return any(r[1] == column for r in c.execute(f"PRAGMA table_info({table})"))


def migrate(c, steps=None) -> int:
    """Applies the steps above the database's version in one transaction; returns the version."""
    steps = MIGRATIONS if steps is None else steps
    version = c.execute("PRAGMA user_version").fetchone()[0]
    if version >= len(steps):            # up to date (or made by a newer version: leave it)
        return version
    c.execute("BEGIN IMMEDIATE")
    try:
        for step in steps[version:]:
            step(c)
        c.execute(f"PRAGMA user_version={len(steps)}")
        c.execute("COMMIT")
    except BaseException:
        c.execute("ROLLBACK")
        raise
    return len(steps)


def init() -> None:
    global _conn
    _conn = sqlite3.connect(config.DB_PATH, check_same_thread=False, isolation_level=None)
    _conn.row_factory = sqlite3.Row
    _conn.execute("PRAGMA journal_mode=WAL")
    _conn.execute("PRAGMA foreign_keys=ON")
    _conn.execute("PRAGMA busy_timeout=5000")
    _conn.executescript(SCHEMA)
    migrate(_conn)


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
