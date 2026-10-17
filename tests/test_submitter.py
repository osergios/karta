"""Sending punches while Ergani itself is down (found on a Saturday maintenance, 17/10/2026)."""
from datetime import datetime

import pytest
from ergani.exceptions import AuthenticationError
from requests.structures import CaseInsensitiveDict

from app import config, db, submitter

PAGE = ("<!DOCTYPE html><html><h1>ΠΣ ΕΡΓΑΝΗ — Προσωρινή συντήρηση</h1>"
        "ERGANI is temporarily unavailable due to scheduled maintenance.</html>")


class Resp:
    def __init__(self, status, text, ctype="text/html"):
        self.status_code, self.text = status, text
        self.headers = CaseInsensitiveDict({"Content-Type": ctype})
        self.ok = status < 400

    def __bool__(self):          # like requests.Response: an error reply is falsy
        return self.ok

    def json(self):
        raise ValueError("not json")


@pytest.fixture
def production(monkeypatch):
    monkeypatch.setattr(config, "ERGANI_MODE", "production")
    monkeypatch.setattr(config, "problems", lambda: [])
    monkeypatch.setattr(submitter, "_client", None)


def _pending(employee):
    with db.tx() as c:
        return c.execute("INSERT INTO movements(employee_id, type, movement_at, created_at, mode, status, next_attempt_at) "
                         "VALUES (?,?,?,?,?,?,?)", (employee, "ARRIVAL", "2026-10-06T10:00:00", db.utc_now_iso(),
                                                    "production", "pending", "2000-01-01T00:00:00")).lastrowid


def _login_fails(monkeypatch, resp):
    def boom():
        raise AuthenticationError(message="", response=resp)
    monkeypatch.setattr(submitter, "_get_client", boom)


def test_a_maintenance_is_ergani_down_not_a_wrong_password(client, admin, clock, employee, production, monkeypatch):
    """The login fails with Ergani's maintenance page: the reason is «003 Πρόβλημα στα συστήματα του ΕΡΓΑΝΗ» (it is the
    late justification Ergani gets later), the alert says Ergani is down, and the punch never gives up."""
    _login_fails(monkeypatch, Resp(503, PAGE))
    mid = _pending(employee)
    for _ in range(config.MAX_SUBMIT_ATTEMPTS + 3):
        submitter.process(mid, force=True)
    row = db.one("SELECT * FROM movements WHERE id=?", (mid,))
    assert row["status"] == "pending"                                   # still tried, every 15 minutes
    assert row["pending_reason"] == "ERGANI_SYSTEMS_UNAVAILABLE"
    assert "συντήρηση" in row["last_error"]
    kinds = {r["kind"] for r in db.all_rows("SELECT kind FROM alerts")}
    assert "ergani_down" in kinds and "ergani_auth" not in kinds


def test_a_wrong_password_is_still_a_login_problem(client, admin, clock, employee, production, monkeypatch):
    _login_fails(monkeypatch, Resp(401, "{}", "application/json"))
    mid = _pending(employee)
    submitter.process(mid, force=True)
    row = db.one("SELECT * FROM movements WHERE id=?", (mid,))
    assert row["pending_reason"] == "EMPLOYER_SYSTEMS_UNAVAILABLE" and "HTTP 401" in row["last_error"]
    assert db.one("SELECT 1 FROM alerts WHERE kind='ergani_auth'") is not None


def test_a_reason_recorded_by_the_old_classification_is_corrected(client, admin, clock, employee, production, monkeypatch):
    """Punches queued during the maintenance by 1.9.1 were recorded as a login problem (002): the next failure, now
    known to be Ergani's side, corrects it to 003 before anything is sent."""
    mid = _pending(employee)
    with db.tx() as c:
        c.execute("UPDATE movements SET pending_reason='EMPLOYER_SYSTEMS_UNAVAILABLE', "
                  "last_error='AuthenticationError: Error message: ' WHERE id=?", (mid,))
    _login_fails(monkeypatch, Resp(503, PAGE))
    submitter.process(mid, force=True)
    assert db.one("SELECT pending_reason FROM movements WHERE id=?", (mid,))["pending_reason"] == "ERGANI_SYSTEMS_UNAVAILABLE"
