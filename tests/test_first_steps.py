"""«Πρώτα βήματα» checklist and the test phone notification."""
from conftest import set_schedule

from app import config, db, monitor


def steps(client):
    return {s["key"]: s for s in client.get("/admin/api/overview").json()["first_steps"]}


def test_a_new_installation_has_nothing_done(client, admin):
    s = steps(client)
    assert list(s) == ["ergani", "brand", "staff", "schedules", "holidays", "device", "notify", "backup", "training", "live"]
    assert not any(x["done"] for x in s.values())
    assert s["staff"]["tab"] == "settings" and s["staff"]["target"] == "erganiCheck"


def test_steps_tick_themselves_off(client, admin, clock, employee):
    client.post("/admin/api/brand", json={"name": "Demo Business", "short": "Demo", "color": "#16897b"})
    s = steps(client)
    assert s["brand"]["done"] and s["staff"]["done"]
    assert not s["schedules"]["done"]                                  # the employee has no schedule yet
    set_schedule(client, employee, {"1": "09:00-17:00/30"})
    client.post("/admin/api/enroll-codes", json={"device_name": "Ταμείο"})
    assert not steps(client)["device"]["done"]                         # a code alone is not a registered device
    with db.tx() as c:
        c.execute("INSERT INTO devices(name, token_hash, created_at) VALUES ('Ταμείο', 'x', ?)", (db.utc_now_iso(),))
    client.post("/admin/api/training", json={"on": True})
    client.post("/admin/api/training", json={"on": False})
    s = steps(client)
    assert s["schedules"]["done"] and s["device"]["done"] and s["training"]["done"]
    assert not s["live"]["done"]                                       # still dry_run


def test_manual_steps_can_be_marked_and_unmarked(client, admin):
    r = client.post("/admin/api/first-steps", json={"step": "holidays"})
    assert {x["key"]: x for x in r.json()["first_steps"]}["holidays"]["done"]
    client.post("/admin/api/first-steps", json={"step": "holidays", "done": False})
    assert not steps(client)["holidays"]["done"]
    assert client.post("/admin/api/first-steps", json={"step": "brand"}).status_code == 422   # automatic steps can't be faked


def test_onboarding_counts_as_going_live(client, admin, clock):
    client.post("/admin/api/onboarding", json={"until": "2026-11-02"})
    assert steps(client)["live"]["done"]


def test_the_checklist_can_be_hidden(client, admin):
    client.post("/admin/api/first-steps", json={"hide": True})
    assert client.get("/admin/api/overview").json()["first_steps"] is None


def test_first_steps_need_the_admin(client):
    assert client.post("/admin/api/first-steps", json={"hide": True}).status_code == 403


def test_test_notification_needs_ntfy(client, admin):
    r = client.post("/admin/api/ntfy/test")
    assert r.status_code == 409


def test_test_notification_is_sent(client, admin, monkeypatch):
    sent = []
    monkeypatch.setattr(config, "NTFY_URL", "https://ntfy.example")
    monkeypatch.setattr(config, "NTFY_TOPIC", "karta-test")

    class _R:
        def close(self): pass
    monkeypatch.setattr(monitor.urllib.request, "urlopen", lambda req, timeout=None: sent.append(req) or _R())
    assert client.post("/admin/api/ntfy/test").status_code == 200
    assert sent and b"karta-test" in sent[0].data
    s = steps(client)["notify"]
    assert s["done"] and s["test"]


def test_test_notification_reports_failure(client, admin, monkeypatch):
    monkeypatch.setattr(config, "NTFY_URL", "https://ntfy.example")
    monkeypatch.setattr(config, "NTFY_TOPIC", "karta-test")

    def boom(req, timeout=None):
        raise OSError("unreachable")
    monkeypatch.setattr(monitor.urllib.request, "urlopen", boom)
    assert client.post("/admin/api/ntfy/test").status_code == 502
