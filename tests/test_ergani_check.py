"""EX_BASE_07 / EX_BASE_08 (actual work log, declared digital organisation) and «Έλεγχος μήνα με ΕΡΓΑΝΗ».

The payloads below have the exact shape a production Ergani account returned (30/09/2026), with made-up ΑΦΜ.
Nothing here talks to Ergani: the client is replaced by a fake that answers from these payloads.
"""
import json
import time
from datetime import date

import pytest
from ergani.exceptions import APIError

from app import db, erganicheck, erganiread, report
from conftest import add_employee, set_schedule

EMP_A, EMP_B, EMP_C, STRANGER = "900000307", "900000123", "900000900", "900000555"

SERVICES = [  # GET /WebServices/ServicesList, shortened: 7 services, the last three with parameters
    {"name": "EX_BASE_01", "description": "ΣΤΟΙΧΕΙΑ ΕΡΓΟΔΟΤΗ", "instructions": "", "parameters": []},
    {"name": "EX_BASE_02", "description": "ΣΤΟΙΧΕΙΑ ΠΑΡΑΡΤΗΜΑΤΩΝ", "instructions": "", "parameters": []},
    {"name": "EX_BASE_03", "description": "ΣΤΟΙΧΕΙΑ ΠΑΡΑΜΕΤΡΙΚΩΝ", "instructions": "",
     "parameters": [{"name": "Parameter", "description": None, "isRequired": True, "type": "String", "maxLength": 0}]},
    {"name": "EX_BASE_05", "description": "ΣΤΟΙΧΕΙΑ ΤΡΕΧΟΥΣΑΣ ΚΑΤΑΣΤΑΣΗΣ ΔΥΝΑΜΙΚΟΥ", "instructions": "",
     "parameters": [{"name": "afm", "description": None, "isRequired": False, "type": "String", "maxLength": 9}]},
    {"name": "EX_BASE_06", "description": "ΣΤΟΙΧΕΙΑ ΚΑΤΑΣΤΑΣΗΣ ΑΠΟΔΟΧΗΣ ΟΥΣΙΩΔΩΝ ΟΡΩΝ", "instructions": "",
     "parameters": [{"name": "afm"}, {"name": "protocol"}, {"name": "date"}]},
    {"name": "EX_BASE_07", "description": "ΣΤΟΙΧΕΙΑ ΗΜΕΡΟΛΟΓΙΟΥ ΠΡΑΓΜΑΤΙΚΗΣ ΑΠΑΣΧΟΛΗΣΗΣ", "instructions": "",
     "parameters": [{"name": "PararthmaAa", "type": "Int"}, {"name": "Date", "type": "Date"}]},
    {"name": "EX_BASE_08", "description": "ΣΤΟΙΧΕΙΑ ΤΡΕΧΟΥΣΑΣ ΚΑΤΑΣΤΑΣΗΣ ΨΗΦΙΑΚΗΣ ΟΡΓΑΝΩΣΗΣ ΧΡΟΝΟΥ ΕΡΓΑΣΙΑΣ",
     "instructions": "", "parameters": [{"name": "PararthmaAa", "type": "Int"}, {"name": "Date", "type": "Date"}]},
]


def w(afm, day, typ="ΕΡΓ", a="11:00", b="19:00", brk="20", inwork="0"):
    return {"aa": "0", "Afm": afm, "Date": day, "Type": typ, "HourFrom": f"{a}:00" if a else None,
            "HourTo": f"{b}:00" if b else None, "Extra": None, "BreakMinutes": brk, "BreakInWork": inwork}


DECL_30_09 = {"EX_BASE_08": {"Working": [      # Wednesday 30/09/2026, exactly as Ergani answered
    w(EMP_A, "30/09/2026"),
    w(EMP_B, "30/09/2026", a="10:00", b="14:00"), w(EMP_B, "30/09/2026", a="17:00", b="21:00"),
    w(EMP_C, "30/09/2026", brk="30"),
]}}


class Resp:
    def __init__(self, payload):
        self.payload, self.status_code = payload, 200
        self.text = json.dumps(payload)

    def json(self):
        return self.payload


class FakeErgani:
    """Answers EX_BASE_07/08 from {(code, 'DD/MM/YYYY'): payload}; anything else: null. Records the calls."""

    def __init__(self, answers=None, criteria_error=False):
        self.answers, self.calls, self.criteria_error = answers or {}, [], criteria_error

    def _execute_service(self, code, params):
        self.calls.append((code, dict(params)))
        if self.criteria_error:
            raise APIError("Error message: Criteria doesn't meet requirements")
        return Resp(self.answers.get((code, params["Date"])))

    def get_services_list(self):
        return Resp(SERVICES)


@pytest.fixture
def fake(monkeypatch):
    f = FakeErgani({("EX_BASE_08", "30/09/2026"): DECL_30_09})
    monkeypatch.setattr(erganiread, "_client", lambda: f)
    return f


def test_the_services_list_counts_only_services(fake):
    got = erganiread.services()
    assert [s["code"] for s in got] == [s["name"] for s in SERVICES]          # 7, not 7 + one row per parameter
    assert got[-1]["parameters"] == ["PararthmaAa", "Date"]


def test_declared_day_reads_the_real_reply(fake, clock):
    rows = erganiread.declared_day(date(2026, 9, 30))
    assert fake.calls[-1] == ("EX_BASE_08", {"PararthmaAa": "0", "Date": "30/09/2026"})
    assert len(rows) == 4
    emp_b = [r for r in rows if r["afm"] == EMP_B]
    assert [(r["start"], r["end"]) for r in emp_b] == [("10:00", "14:00"), ("17:00", "21:00")]   # split shift
    emp_c = next(r for r in rows if r["afm"] == EMP_C)
    assert emp_c == {"afm": EMP_C, "type": "ΕΡΓ", "start": "11:00", "end": "19:00", "break_min": 30, "break_in": False}
    assert erganiread.declared_day(date(2026, 9, 29)) == []                   # null: nothing that day


def test_actual_day_reads_the_documented_fields(monkeypatch, clock):
    f = FakeErgani({("EX_BASE_07", "29/09/2026"): {"EX_BASE_07": {"RealWorking": [
        {"Aa": "0", "Afm": EMP_B, "Date": "29/09/2026", "HourFrom": "10:02:41", "HourTo": "17:00:05",
         "IsEndDateDifferentThanDate": "0"}]}}})
    monkeypatch.setattr(erganiread, "_client", lambda: f)
    assert erganiread.actual_day(date(2026, 9, 29)) == [{"afm": EMP_B, "start": "10:02", "end": "17:00", "next_day": False}]
    assert erganiread.actual_day(date(2026, 9, 30)) == []


def test_the_current_month_is_refused_with_a_clear_reason(fake, clock):
    with pytest.raises(erganiread.ErganiReadError, match="01/11/2026"):
        erganiread.declared_day(date(2026, 10, 1))           # «today» is 6/10: October is not «the previous month» yet
    assert not fake.calls                                     # refused before asking Ergani


def test_ergani_criteria_error_becomes_the_same_message(monkeypatch, clock):
    monkeypatch.setattr(erganiread, "_client", lambda: FakeErgani(criteria_error=True))
    with pytest.raises(erganiread.ErganiReadError, match="προηγούμενο μήνα"):
        erganiread.declared_day(date(2026, 9, 30))


def test_the_last_declared_week_becomes_a_schedule_proposal():
    leave = {"afm": EMP_A, "type": "ΑΔΚΑΝ", "start": None, "end": None, "break_min": None, "break_in": None}
    work = lambda afm, a, b: {"afm": afm, "type": "ΕΡΓ", "start": a, "end": b, "break_min": 20, "break_in": False}
    rest = {"afm": EMP_A, "type": "ΑΝ", "start": None, "end": None, "break_min": None, "break_in": None}
    days = {
        date(2026, 9, 30): [leave, work(EMP_B, "10:00", "14:00"), work(EMP_B, "17:00", "21:00")],   # Wed
        date(2026, 9, 28): [rest],                                                                   # Mon
        date(2026, 9, 23): [work(EMP_A, "11:00", "19:00")],                                         # previous Wed
    }
    weeks = erganiread.week_from_declared(days)
    assert weeks[EMP_B]["proposal"] == {"2": "10:00-14:00+17:00-21:00"}
    # the first one was on leave on 30/09: her Wednesday comes from 23/09; Monday is «ρεπό»
    assert weeks[EMP_A]["proposal"] == {"2": "11:00-19:00", "0": ""}
    assert weeks[EMP_A]["from"] == "2026-09-23" and weeks[EMP_A]["to"] == "2026-09-28"


def test_facts_offer_the_declared_week_for_a_digital_schedule():
    info = {"schedule": "ΨΗΦΙΑΚΗ ΟΡΓΑΝΩΣΗ", "digital_org": "ΝΑΙ",
            "declared_week": json.dumps({"proposal": {"1": "10:00-16:30"}, "from": "2026-09-24", "to": "2026-09-30"})}
    f = erganiread.facts(info)
    assert f["proposal"] == {"1": "10:00-16:30"}
    assert f["proposal_week"] == {"from": "2026-09-24", "to": "2026-09-30"}
    assert erganiread.facts({"schedule": "ΨΗΦΙΑΚΗ ΟΡΓΑΝΩΣΗ"})["proposal"] is None


def _sent(eid, day, hm_in, hm_out):
    with db.tx() as c:
        for typ, hm in (("ARRIVAL", hm_in), ("DEPARTURE", hm_out)):
            c.execute("INSERT INTO movements(employee_id, type, movement_at, created_at, mode, status, next_attempt_at) "
                      "VALUES (?,?,?,?,?,?,?)", (eid, typ, f"{day}T{hm}:00", "x", "dry_run", "submitted", "x"))


def _declared_30(rows):
    out = {d.isoformat(): [] for d in erganicheck.month_days("2026-09")}
    out["2026-09-30"] = rows
    return out


def test_compare_finds_every_kind_of_difference(client, admin, clock):
    a = add_employee(afm=EMP_A, last="Παπαδοπούλου", first="Μαρία", display="Μαρία")
    m = add_employee(afm=EMP_B, last="Νικολάου", first="Ελένη", display="Ελένη")
    e = add_employee(afm=EMP_C, last="Γεωργίου", first="Άννα", display="Άννα")
    set_schedule(client, a, {"2": "11:00-19:00/+30"})            # Ergani: 20′ → break differs
    set_schedule(client, m, {"2": "10:00-14:00+17:00-21:00/+20"})  # same as Ergani
    set_schedule(client, e, {"2": "11:00-19:00/+30"})            # same as Ergani, but on leave in Karta
    client.post(f"/admin/api/employees/{e}/leaves", json={"start": "2026-09-30", "end": "2026-09-30", "kind": "regular"})
    _sent(m, "2026-09-30", "10:01", "14:00")      # Ergani recorded it
    _sent(m, "2026-09-30", "17:00", "21:00")      # Ergani has nothing for this one
    declared = _declared_30([
        {"afm": EMP_A, "type": "ΕΡΓ", "start": "11:00", "end": "19:00", "break_min": 20, "break_in": False},
        {"afm": EMP_B, "type": "ΕΡΓ", "start": "10:00", "end": "14:00", "break_min": 20, "break_in": False},
        {"afm": EMP_B, "type": "ΕΡΓ", "start": "17:00", "end": "21:00", "break_min": 20, "break_in": False},
        {"afm": EMP_C, "type": "ΕΡΓ", "start": "11:00", "end": "19:00", "break_min": 30, "break_in": False},
        {"afm": STRANGER, "type": "ΕΡΓ", "start": "09:00", "end": "13:00", "break_min": 0, "break_in": None},
    ])
    actual = {d: [] for d in declared}
    actual["2026-09-30"] = [{"afm": EMP_B, "start": "10:01", "end": "14:00", "next_day": False},
                            {"afm": EMP_A, "start": "11:00", "end": "19:20", "next_day": False}]
    diffs = erganicheck.compare("2026-09", {"fetched_at": "2026-10-06T10:00:00", "declared": declared, "actual": actual})
    got = {(x["name"].split()[0] if x["employee_id"] else "?", x["what"]) for x in diffs}
    assert got == {("Παπαδοπούλου", "schedule"),        # 30′ in Karta, 20′ in Ergani
                   ("Παπαδοπούλου", "punch_extra"),     # Ergani has work Karta never sent
                   ("Γεωργίου", "leave"),          # leave in Karta, work declared in Ergani
                   ("Νικολάου", "punch_missing"),      # 17:00–21:00 sent, not in Ergani
                   ("?", "unknown_person")}
    sched = next(x for x in diffs if x["what"] == "schedule")
    assert "30′" in sched["karta"] and "20′" in sched["ergani"]


def test_month_check_runs_in_the_background_and_lands_in_the_report(client, admin, clock, fake):
    add_employee(afm=EMP_A, last="Παπαδοπούλου", first="Μαρία", display="Μαρία")
    r = client.post("/admin/api/ergani/month", json={"month": "2026-10"})
    assert r.status_code == 409 and "01/11/2026" in r.json()["detail"]            # not available yet
    assert client.get("/admin/api/ergani/month?month=2026-10").json()["available"] is False
    assert client.post("/admin/api/ergani/month", json={"month": "2026-09"}).status_code == 200
    for _ in range(100):
        if erganicheck.status().get("state") != "running":
            break
        time.sleep(0.05)
    assert erganicheck.status()["state"] == "done"
    assert len(fake.calls) == 60                                   # 30 days × EX_BASE_07 and EX_BASE_08
    s = client.get("/admin/api/ergani/month?month=2026-09").json()
    assert s["checked_at"] and s["available"]
    assert any(x["what"] == "unknown_person" for x in s["diffs"])  # the other two are not in this Karta
    from openpyxl import load_workbook
    import io
    wb = load_workbook(io.BytesIO(report.build(2026, 9)))
    assert "Έλεγχος ΕΡΓΑΝΗ" in wb.sheetnames
    assert "Έλεγχος ΕΡΓΑΝΗ" not in load_workbook(io.BytesIO(report.build(2026, 8))).sheetnames   # not checked


def test_refresh_stores_the_declared_week_for_the_schedule_card(client, admin, clock, monkeypatch):
    a = add_employee(afm=EMP_A, last="Παπαδοπούλου", first="Μαρία", display="Μαρία")
    monkeypatch.setattr(erganiread, "fetch", lambda: {"people": [{"afm": EMP_A, "schedule": "ΨΗΦΙΑΚΗ ΟΡΓΑΝΩΣΗ",
                                                                  "digital_org": "ΝΑΙ", "break_minutes": 20}]})
    monkeypatch.setattr(erganiread, "declared_recent_weeks",
                        lambda: {EMP_A: {"proposal": {"2": "11:00-19:00"}, "from": "2026-09-24", "to": "2026-09-30"}})
    assert erganiread.refresh_info("admin@example.com") == 1
    ei = client.get("/admin/api/overview").json()["ergani_info"][str(a)]
    assert ei["proposal"] == {"2": "11:00-19:00"} and ei["proposal_week"]["to"] == "2026-09-30"


def test_the_refresh_runs_in_the_background(client, admin, monkeypatch):
    """«Ενημέρωση στοιχείων ωραρίου από ΕΡΓΑΝΗ» reads up to 14 more days now: it must not hang on the page request."""
    monkeypatch.setattr(erganiread, "refresh_info", lambda admin: 3)
    assert client.post("/admin/api/ergani/refresh").json()["state"] == "running"
    for _ in range(100):
        st = client.get("/admin/api/ergani/refresh").json()
        if st["state"] != "running":
            break
        time.sleep(0.05)
    assert st["state"] == "done" and st["result"] == {"updated": 3}

    def down(admin):
        raise erganiread.ErganiReadError("Το ΕΡΓΑΝΗ δεν απάντησε")
    monkeypatch.setattr(erganiread, "refresh_info", down)
    client.post("/admin/api/ergani/refresh")
    for _ in range(100):
        st = client.get("/admin/api/ergani/refresh").json()
        if st["state"] != "running":
            break
        time.sleep(0.05)
    assert st["state"] == "fail" and "δεν απάντησε" in st["error"]
