"""Shared fixtures. The app reads its settings at import time, so the environment is set first.

Everything runs in ERGANI_MODE=dry_run against a throwaway database: nothing is ever sent to Ergani.
"""
import os
import tempfile
from datetime import datetime, timedelta

_TMP = tempfile.mkdtemp(prefix="karta-tests-")
os.environ.update(
    ERGANI_MODE="dry_run",
    EMPLOYER_AFM="123456789",
    CF_ACCESS_TEAM_DOMAIN="test.cloudflareaccess.com",
    CF_ACCESS_AUD="test-aud",
    ADMIN_EMAILS="admin@example.com",
    PUBLIC_ORIGIN="http://testserver",
    DB_PATH=os.path.join(_TMP, "workcard.db"),
    NTFY_URL="",
    NTFY_TOPIC="",
    PIN_KEY="",
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import appconfig, db, main, security, updates  # noqa: E402

updates._latest["at"] = float("inf")      # never ask GitHub for the latest release during the tests

ORIGIN = {"origin": "http://testserver"}
DEVICE_TOKEN = "test-device-token"
PIN = "482916"
# An ordinary working day: Tuesday 6 October 2026 (not a Greek public holiday)
TUESDAY = datetime(2026, 10, 6, 10, 0, 0)

_TABLES = ("movements", "alerts", "card_links", "leaves", "day_changes", "early_leaves", "ergani_week", "ergani_month", "ergani_info",
           "schedule_versions", "closures", "enroll_codes", "devices", "employees", "audit", "settings")


class Clock:
    """A controllable replacement for timeutil.now_local (Europe/Athens wall time, naive)."""

    def __init__(self, start: datetime):
        self.now = start

    def __call__(self) -> datetime:
        return self.now.replace(microsecond=0)

    def set(self, when: datetime) -> None:
        self.now = when

    def advance(self, **kw) -> None:
        self.now += timedelta(**kw)


@pytest.fixture(scope="session")
def client():
    with TestClient(main.app, headers=ORIGIN) as c:
        yield c


@pytest.fixture(autouse=True)
def clean(client):
    """Each test starts with an empty database and no leftover in-memory state."""
    with db.tx() as c:
        for t in _TABLES:
            c.execute(f"DELETE FROM {t}")
    appconfig.load()                   # settings saved from the admin page are gone with the table
    main._enroll_fails.clear()
    main._qr_fails.clear()
    client.cookies.clear()
    main.app.dependency_overrides.clear()
    yield
    main.app.dependency_overrides.clear()


@pytest.fixture
def clock(monkeypatch):
    """Freeze 'now' for every module that imported now_local."""
    from app import erganiread, monitor, onboarding, report, submitter, timeutil
    clk = Clock(TUESDAY)
    for mod in (timeutil, main, monitor, onboarding, report, submitter, erganiread):
        monkeypatch.setattr(mod, "now_local", clk)
    return clk


@pytest.fixture
def admin():
    """Act as a logged-in admin (stands in for the Cloudflare Access check)."""
    main.app.dependency_overrides[security.require_admin] = lambda: "admin@example.com"


@pytest.fixture
def kiosk(client):
    """A registered shop device: the client carries its cookie."""
    with db.tx() as c:
        c.execute("INSERT INTO devices(name, token_hash, created_at) VALUES (?,?,?)",
                  ("Ταμείο", security.sha256(DEVICE_TOKEN), db.utc_now_iso()))
    client.cookies.set("wc_device", DEVICE_TOKEN)
    return client


def add_employee(afm="900000001", last="Παπαδοπούλου", first="Μαρία", display="Μαρία", pin=PIN) -> int:
    with db.tx() as c:
        cur = c.execute(
            "INSERT INTO employees(afm, last_name, first_name, display_name, pin_hash, created_at) VALUES (?,?,?,?,?,?)",
            # a fixed date before every test day: with the real date, days earlier than the day the tests run were
            # «before the employee existed» and the reports of those days came out empty
            (afm, last, first, display, security.hash_pin(pin), "2026-09-01T00:00:00"))
        return cur.lastrowid


@pytest.fixture
def employee():
    return add_employee()


def set_schedule(client, employee_id: int, days: dict, valid_from: str = "2026-09-01"):
    r = client.post(f"/admin/api/schedules/{employee_id}", json={"days": days, "valid_from": valid_from})
    assert r.status_code == 200, r.text
    return r
