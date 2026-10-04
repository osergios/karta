"""Records the result of the nightly backup (backup.sh on the host runs this inside the container).

    python -m app.backupmark <local> <usb> <cloud>      each one: ok / fail / -  (- = not set up)

Uses sqlite3 only (no app settings needed). The admin page shows the result, and the monitor raises an
alert when the last backup is old or a copy failed.
"""
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

STATES = ("ok", "fail", "-")


def main(argv: list[str]) -> int:
    if len(argv) != 3 or any(a not in STATES for a in argv):
        print(__doc__)
        return 2
    local, usb, cloud = argv
    value = json.dumps({"at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
                        "local": local, "usb": usb, "cloud": cloud})
    c = sqlite3.connect(os.environ.get("DB_PATH", "/data/workcard.db"), timeout=10)
    try:
        with c:
            c.execute("INSERT INTO settings(key, value) VALUES ('backup_status', ?) "
                      "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (value,))
    finally:
        c.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
