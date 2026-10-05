"""Punching at the shop screen, end to end, in dry_run (nothing leaves the machine)."""
import json
from datetime import datetime

from conftest import PIN, add_employee, set_schedule

from app import db, security

WORKDAYS = {str(d): "09:00-17:00/30" for d in range(6)}   # Monday-Saturday


def punch(client, employee_id, action, pin=PIN):
    return client.post("/api/kiosk/punch", json={"employee_id": employee_id, "pin": pin, "action": action})


def test_employee_list_on_the_kiosk(kiosk, clock):
    add_employee(afm="900000001", display="Μαρία", last="Παπαδοπούλου")
    add_employee(afm="900000002", display="Μαρία", last="Κωνσταντίνου")
    names = sorted(e["name"] for e in kiosk.get("/api/kiosk/employees").json()["employees"])
    assert names == ["Μαρία Κ.", "Μαρία Π."]                    # same first name: told apart by surname


def test_arrival_then_departure_in_dry_run(kiosk, admin, clock, employee):
    set_schedule(kiosk, employee, WORKDAYS)

    r = punch(kiosk, employee, "ARRIVAL")
    assert r.status_code == 200, r.text
    m = r.json()["movement"]
    assert (m["type"], m["status"], m["mode"]) == ("ARRIVAL", "dry_run", "dry_run")
    assert m["movement_at"] == "2026-10-06T10:00:00"

    stored = db.one("SELECT response_json FROM movements WHERE id=?", (m["id"],))["response_json"]
    payload = json.loads(stored)
    assert "123456789" in stored                                  # employer ΑΦΜ
    assert "900000001" in stored                                  # employee ΑΦΜ
    assert payload, "the exact payload that would be sent is kept"

    clock.advance(hours=7)
    r = punch(kiosk, employee, "DEPARTURE")
    assert r.status_code == 200, r.text
    assert r.json()["movement"]["type"] == "DEPARTURE"


def test_the_wrong_action_is_refused(kiosk, admin, clock, employee):
    set_schedule(kiosk, employee, WORKDAYS)
    assert punch(kiosk, employee, "DEPARTURE").status_code == 409   # not in yet


def test_double_punch_is_ignored(kiosk, admin, clock, employee):
    set_schedule(kiosk, employee, WORKDAYS)
    assert punch(kiosk, employee, "ARRIVAL").status_code == 200
    clock.advance(seconds=20)
    assert punch(kiosk, employee, "DEPARTURE").status_code == 429   # within DEBOUNCE_SECONDS


def test_arrival_before_the_declared_start_is_refused(kiosk, admin, clock, employee):
    set_schedule(kiosk, employee, WORKDAYS)
    clock.set(datetime(2026, 10, 6, 8, 30))
    r = punch(kiosk, employee, "ARRIVAL")
    assert r.status_code == 409
    assert "νωρίς" in r.json()["detail"]
    assert db.one("SELECT COUNT(*) n FROM movements")["n"] == 0


def test_arrival_on_a_public_holiday_is_refused(kiosk, admin, clock, employee):
    set_schedule(kiosk, employee, WORKDAYS)
    clock.set(datetime(2026, 10, 28, 10, 0))                       # 28 Οκτωβρίου, Wednesday
    r = punch(kiosk, employee, "ARRIVAL")
    assert r.status_code == 409
    assert db.one("SELECT COUNT(*) n FROM movements")["n"] == 0


def test_wrong_pin_locks_after_five_tries(kiosk, admin, clock, employee):
    set_schedule(kiosk, employee, WORKDAYS)
    codes = [punch(kiosk, employee, "ARRIVAL", pin="000001").status_code for _ in range(5)]
    assert codes == [401, 401, 401, 401, 423]
    assert punch(kiosk, employee, "ARRIVAL").status_code == 423     # even the right PIN, while locked


def test_punch_with_the_shop_qr_card(kiosk, admin, clock, employee):
    set_schedule(kiosk, employee, WORKDAYS)
    code = security.new_qr_code()
    with db.tx() as c:
        c.execute("UPDATE employees SET qr_hash=? WHERE id=?", (security.sha256(code), employee))
    r = kiosk.post("/api/kiosk/qr/punch", json={"code": code, "action": "ARRIVAL"})
    assert r.status_code == 200, r.text
    assert db.one("SELECT auth_method FROM movements")["auth_method"] == "qr"
    assert kiosk.post("/api/kiosk/qr/state", json={"code": security.new_qr_code()}).status_code == 404


def test_punch_with_the_ergani_qr(kiosk, admin, clock, employee):
    set_schedule(kiosk, employee, WORKDAYS)
    code = "﻿erg|nm:ΜΑΡΙΑ;ln:ΠΑΠΑΔΟΠΟΥΛΟΥ;afm:900000001;id:777"
    r = kiosk.post("/api/kiosk/qr/punch", json={"code": code, "action": "ARRIVAL"})
    assert r.status_code == 200, r.text
    assert db.one("SELECT auth_method FROM movements")["auth_method"] == "qr_ergani"


def test_ergani_qr_with_the_wrong_surname_is_refused(kiosk, admin, clock, employee):
    code = "﻿erg|nm:ΜΑΡΙΑ;ln:ΑΛΛΟΥ;afm:900000001;id:777"
    assert kiosk.post("/api/kiosk/qr/state", json={"code": code}).status_code == 404


def test_training_mode_is_gone(kiosk, admin, clock, employee):
    """Practice happens in «Δοκιμαστική»: there is no separate training switch any more."""
    assert kiosk.post("/admin/api/training", json={"on": True}).status_code in (404, 405)
    assert "training" not in kiosk.get("/api/kiosk/reminders").json()


def test_device_registration_with_a_one_time_code(client, admin, clock):
    code = client.post("/admin/api/enroll-codes", json={"device_name": "Ταμείο"}).json()["code"]
    r = client.post("/api/enroll", json={"code": code})
    assert r.status_code == 200
    assert r.json()["device"] == "Ταμείο"
    assert client.post("/api/enroll", json={"code": code}).status_code == 400   # used up


def test_the_punch_keeps_the_address_cloudflare_saw(kiosk, clock, employee):
    """X-Real-IP comes from the browser through the tunnel unchanged: Cloudflare's own header wins."""
    r = kiosk.post("/api/kiosk/punch", json={"employee_id": employee, "pin": PIN, "action": "ARRIVAL"},
                   headers={"CF-Connecting-IP": "203.0.113.7", "X-Real-IP": "198.51.100.66"})
    assert r.status_code == 200, r.text
    assert db.one("SELECT client_ip FROM movements WHERE id=?", (r.json()["movement"]["id"],))["client_ip"] == "203.0.113.7"
    clock.advance(hours=1)
    r = kiosk.post("/api/kiosk/punch", json={"employee_id": employee, "pin": PIN, "action": "DEPARTURE"},
                   headers={"X-Real-IP": "198.51.100.8"})          # a reverse proxy without Cloudflare
    assert db.one("SELECT client_ip FROM movements WHERE id=?", (r.json()["movement"]["id"],))["client_ip"] == "198.51.100.8"
