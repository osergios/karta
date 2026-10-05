"""Schema migrations (PRAGMA user_version): an existing database is brought up to date at start-up."""
import sqlite3

from app import config, db


def old_database(path) -> sqlite3.Connection:
    """A database as Karta 1.4 made it: today's schema, user_version 0."""
    c = sqlite3.connect(path, isolation_level=None)
    c.executescript(db.SCHEMA)
    assert c.execute("PRAGMA user_version").fetchone()[0] == 0
    return c


def test_an_existing_database_gets_version_1_at_start_up(tmp_path, monkeypatch):
    path = str(tmp_path / "old.db")
    c = old_database(path)
    c.execute("CREATE TABLE schedules (id INTEGER PRIMARY KEY)")         # left over by an older version: kept
    c.close()
    live = db._conn
    monkeypatch.setattr(config, "DB_PATH", path)
    try:
        db.init()
        assert db.one("PRAGMA user_version")[0] == 1
        assert db.one("SELECT COUNT(*) n FROM employees")["n"] == 0      # the app works on it
        assert db.one("SELECT name FROM sqlite_master WHERE name='schedules'")
        db._conn.close()
    finally:
        db._conn = live


def test_a_step_runs_once(tmp_path):
    c = old_database(str(tmp_path / "old.db"))
    runs = []

    def add_note(c):
        runs.append(1)
        if not db._has_column(c, "employees", "note"):
            c.execute("ALTER TABLE employees ADD COLUMN note TEXT")
    steps = db.MIGRATIONS + [add_note]
    assert db.migrate(c, steps) == 2 and db._has_column(c, "employees", "note")
    assert db.migrate(c, steps) == 2 and runs == [1]                      # next start: skipped
    assert c.execute("PRAGMA user_version").fetchone()[0] == 2
    assert db.migrate(c) == 2                                             # an older Karta (one step) leaves it alone


def test_a_failing_step_changes_nothing(tmp_path):
    c = old_database(str(tmp_path / "old.db"))

    def broken(c):
        c.execute("ALTER TABLE employees ADD COLUMN half TEXT")
        raise RuntimeError("boom")
    try:
        db.migrate(c, db.MIGRATIONS + [broken])
    except RuntimeError:
        pass
    assert c.execute("PRAGMA user_version").fetchone()[0] == 0 and not db._has_column(c, "employees", "half")


def test_the_live_database_is_up_to_date():
    assert db.one("PRAGMA user_version")[0] == len(db.MIGRATIONS)
