"""«Σήμερα» → «Κινήσεις»: the punches of the days picked in the calendar, which offers only days with something to see."""
from app import config, db
from conftest import add_employee, set_schedule

WEEK = {str(i): "09:00-17:00" for i in range(5)}                      # Monday to Friday
WEEK6 = {str(i): "09:00-17:00" for i in range(6)}                     # Monday to Saturday


def _punch(employee_id, at, kind="ARRIVAL", status=None, auth="qr", protocol=None):
    with db.tx() as c:
        return c.execute("INSERT INTO movements(employee_id, type, movement_at, created_at, mode, status, auth_method, protocol, "
                         "next_attempt_at) VALUES (?,?,?,?,?,?,?,?,?)", (employee_id, kind, at, db.utc_now_iso(), config.ERGANI_MODE,
                                                      status or ("submitted" if config.ERGANI_MODE == "production" else "dry_run"),
                                                      auth, protocol, at)).lastrowid


def _setup(client):
    maria = add_employee()
    giorgos = add_employee(afm="900000002", last="Νικολάου", first="Γιώργος", display="Γιώργος")
    set_schedule(client, maria, WEEK)
    set_schedule(client, giorgos, WEEK6)
    _punch(maria, "2026-09-29T09:01:00")
    _punch(maria, "2026-10-01T09:02:14", auth="pin")
    _punch(maria, "2026-10-01T17:01:00", "DEPARTURE")
    _punch(giorgos, "2026-10-02T10:00:00")                            # he came in on the closed day after all
    _punch(maria, "2026-10-05T09:00:00")
    assert client.post("/admin/api/closures", json={"start": "2026-10-02", "end": "2026-10-02", "reason": "Απογραφή"}).status_code == 200
    assert client.post(f"/admin/api/employees/{maria}/leaves",
                       json={"start": "2026-09-30", "end": "2026-09-30", "kind": "regular"}).status_code == 200
    return maria, giorgos


def _days(client, month, employee_id=None):
    q = f"?month={month}" + (f"&employee_id={employee_id}" if employee_id else "")
    r = client.get("/admin/api/movements/days" + q)
    assert r.status_code == 200, r.text
    return {d["date"]: d for d in r.json()["days"]}


def test_the_calendar_offers_only_days_with_something_to_see(client, admin, clock):
    maria, giorgos = _setup(client)
    m = _days(client, "2026-10", maria)
    assert m["2026-10-01"]["state"] == "open" and m["2026-10-01"]["punches"] == 2
    assert m["2026-10-02"]["state"] == "closed" and "Απογραφή" in m["2026-10-02"]["label"]
    assert m["2026-10-03"]["state"] == "closed" and m["2026-10-03"]["label"] == "Ρεπό"       # Saturday
    assert m["2026-10-05"]["punches"] == 1
    assert m["2026-10-06"]["state"] == "open"                                               # today
    assert m["2026-10-07"]["state"] == "future"
    sep = _days(client, "2026-09", maria)
    assert sep["2026-09-28"]["state"] == "none"                     # before the first punch: the card was not in use
    assert sep["2026-09-29"]["state"] == "open"
    assert sep["2026-09-30"]["state"] == "closed" and "άδεια" in sep["2026-09-30"]["label"].lower()
    everyone = _days(client, "2026-10")
    assert everyone["2026-10-02"]["state"] == "open"                # closed, but Γιώργος punched
    assert everyone["2026-10-03"]["state"] == "open"                # Saturday: Γιώργος works
    assert everyone["2026-10-04"]["state"] == "closed"              # Sunday: nobody


def test_the_punches_of_the_chosen_days(client, admin, clock):
    maria, giorgos = _setup(client)
    r = client.get("/admin/api/movements?start=2026-10-01&end=2026-10-09")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["end"] == "2026-10-06"                               # never past today
    days = {d["date"]: d for d in out["days"]}
    assert set(days) == {"2026-10-01", "2026-10-02", "2026-10-03", "2026-10-05", "2026-10-06"}
    assert out["skipped"] == 1                                      # Sunday
    first = {p["name"]: p for p in days["2026-10-01"]["people"]}
    assert [m["movement_at"][11:19] for m in first["Μαρία"]["movements"]] == ["09:02:14", "17:01:00"]
    assert first["Μαρία"]["movements"][0]["auth_method"] == "pin" and first["Μαρία"]["schedule"].startswith("09:00–17:00")
    assert first["Γιώργος"]["movements"] == [] and first["Γιώργος"]["late"]          # due, did not punch
    closed = days["2026-10-02"]
    assert "Απογραφή" in closed["closed"] and [p["name"] for p in closed["people"]] == ["Γιώργος"]
    today = {p["name"]: p for p in days["2026-10-06"]["people"]}
    assert today["Μαρία"]["late"]                                   # 10:00, due at 09:00
    only = client.get(f"/admin/api/movements?start=2026-09-28&end=2026-10-04&employee_id={maria}").json()
    assert [d["date"] for d in only["days"]] == ["2026-09-29", "2026-09-30", "2026-10-01", "2026-10-02"]
    leave = only["days"][1]["people"][0]                            # one person: a leave / closed shop is said as such
    assert leave["movements"] == [] and "άδεια" in leave["off"].lower() and not leave["late"]
    assert "Απογραφή" in only["days"][3]["people"][0]["off"]
    assert only["skipped"] == 3                                     # 28/9 (before the first punch) and the weekend


def test_what_needs_a_decision_is_always_listed_and_the_old_list_is_gone(client, admin, clock):
    maria = add_employee()
    _punch(maria, "2026-08-03T09:00:00", status="uncertain")
    _punch(maria, "2026-10-05T09:00:00", status="failed")
    _punch(maria, "2026-10-05T17:00:00", "DEPARTURE")
    d = client.get("/admin/api/overview").json()
    assert "movements" not in d and "onboarding_progress" not in d
    assert [m["status"] for m in d["attention"]] == ["failed", "uncertain"]


def test_a_range_is_limited(client, admin, clock):
    r = client.get("/admin/api/movements?start=2026-06-01&end=2026-10-06")
    assert r.status_code == 400
    assert client.get("/admin/api/movements/days?month=2026-13").status_code == 400
