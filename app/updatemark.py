"""The host side of «Ενημέρωση τώρα» (update.sh on the machine runs this inside the container, every minute).

    python -m app.updatemark poll           -> prints "update" when the admin asked for an update (and takes the
                                               request), otherwise nothing; records that the updater runs (at most
                                               every 30 minutes, so the poll is read-only almost every time)
    python -m app.updatemark done ok|fail   -> records the result (run by the new container after the update)

Uses sqlite3 only (no app settings needed), like app/backupmark.py.
"""
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _put(c, key: str, value: str) -> None:
    c.execute("INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
              (key, value))


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("poll", "done") or (argv[0] == "done" and argv[1:2] not in (["ok"], ["fail"])):
        print(__doc__)
        return 2
    c = sqlite3.connect(os.environ.get("DB_PATH", "/data/workcard.db"), timeout=10)
    try:
        with c:
            if argv[0] == "poll":
                seen = c.execute("SELECT value FROM settings WHERE key='updater_seen'").fetchone()
                try:
                    fresh = seen and datetime.now(timezone.utc) - datetime.fromisoformat(seen[0]).replace(
                        tzinfo=timezone.utc) < timedelta(minutes=30)
                except ValueError:
                    fresh = False
                if not fresh:
                    _put(c, "updater_seen", _now())
                row = c.execute("SELECT value FROM settings WHERE key='update_request'").fetchone()
                if row:
                    c.execute("DELETE FROM settings WHERE key='update_request'")
                    _put(c, "update_running", _now())
                    print("update")
            else:
                ok = argv[1] == "ok"
                _put(c, "update_result", json.dumps({"at": _now(), "state": argv[1],
                                                     "version": os.environ.get("KARTA_VERSION", "")}))
                c.execute("DELETE FROM settings WHERE key='update_running'")
                if ok:      # the shop screen reloads itself with the new version
                    _put(c, "kiosk_reload_at",
                         datetime.now(ZoneInfo("Europe/Athens")).replace(tzinfo=None).isoformat(timespec="seconds"))
    finally:
        c.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
