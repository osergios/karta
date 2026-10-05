"""«Δήλωση αλλαγών ωραρίου και υπερωριών»: προαναγγελία (before) or απολογιστικό σύστημα (afterwards, by the end of
the next month). The business chooses it in Ergani; Karta's alerts and deadlines follow the setting."""
import io

import openpyxl
from conftest import PIN, set_schedule

from app import config, db, monitor

WORKDAYS = {str(d): "09:00-17:00/30" for d in range(6)}


def declaration(client, value):
    return client.post("/admin/api/config", json={"group": "business", "values": {
        "EMPLOYER_AFM": "", "BRANCH_NUMBER": "0", "ERGANI_EMPLOYER_ID": "", "TIME_DECLARATION": value}})


def still_inside_after_the_end(kiosk, clock, employee):
    """Arrived 10:00, schedule ends 17:00; it is now 17:30 and nobody punched out."""
    r = kiosk.post("/api/kiosk/punch", json={"employee_id": employee, "pin": PIN, "action": "ARRIVAL"})
    assert r.status_code == 200, r.text
    clock.advance(hours=7, minutes=30)
    monitor.check(clock())
    return db.one("SELECT message FROM alerts WHERE kind='overdue'")["message"]


def today(client):
    return client.get("/admin/api/overview").json()["employees"][0]["today"]


def test_advance_declaration_is_the_default(kiosk, admin, clock, employee):
    set_schedule(kiosk, employee, WORKDAYS)
    assert not config.RETRO and kiosk.get("/admin/api/overview").json()["retro"] is False
    assert today(kiosk)["ot_by"] == "16:00"                                # 60′ before the end
    assert "μη δηλωμένη υπερωρία" in still_inside_after_the_end(kiosk, clock, employee)


def test_retrospective_system_changes_the_alerts(kiosk, admin, clock, employee):
    set_schedule(kiosk, employee, WORKDAYS)
    assert declaration(kiosk, "retro").status_code == 200
    assert config.RETRO and kiosk.get("/admin/api/overview").json()["retro"] is True
    assert today(kiosk)["ot_by"] is None and today(kiosk)["ot_passed"] is False   # no deadline before
    with db.tx() as c:
        db.put_setting(c, "ot_notice_minutes", "30")
    msg = still_inside_after_the_end(kiosk, clock, employee)
    assert "απολογιστικά" in msg and "τέλος του επόμενου μήνα" in msg and "μη δηλωμένη" not in msg
    assert not db.one("SELECT 1 FROM alerts WHERE kind LIKE 'ot_notice%'")      # no «declare by …» reminder
    xlsx = kiosk.get("/admin/api/report.xlsx?month=2026-10").content
    note = " ".join(str(c.value) for row in openpyxl.load_workbook(io.BytesIO(xlsx))["Απολογιστικές δηλώσεις"].iter_rows()
                    for c in row if c.value)
    assert "έχει δηλώσει απολογιστικό σύστημα" in note
    assert declaration(kiosk, "advance").status_code == 200 and not config.RETRO


def test_only_the_two_systems_are_accepted(client, admin):
    r = declaration(client, "sometimes")
    assert r.status_code == 400 and "απολογιστικό" in r.json()["detail"]


def test_retro_keeps_the_break_outside_hours_and_the_flexible_arrival(kiosk, admin, clock, employee):
    """09:00–17:00 with a 30′ break «εκτός ωραρίου» (/+30) and up to 60′ flexible arrival: arriving 10:00 moves the
    end to 18:00, and the break to 18:30. No «έληξε» before that, in either system."""
    assert declaration(kiosk, "retro").status_code == 200
    set_schedule(kiosk, employee, {str(d): "09:00-17:00/+30" for d in range(6)})
    with db.tx() as c:
        c.execute("UPDATE employees SET flex_arrival=60 WHERE id=?", (employee,))
    assert kiosk.post("/api/kiosk/punch", json={"employee_id": employee, "pin": PIN, "action": "ARRIVAL"}).status_code == 200
    assert today(kiosk)["end"] == "18:30"                                  # 10:00 arrival + 8h + 30′ break
    clock.advance(hours=8, minutes=25)                                      # 18:25: still within the day
    monitor.check(clock())
    assert not db.one("SELECT 1 FROM alerts WHERE kind='overdue'")
    clock.advance(minutes=30)                                               # 18:55: past the end (and the grace)
    monitor.check(clock())
    assert "18:30" in db.one("SELECT message FROM alerts WHERE kind='overdue'")["message"]
