"""Settings changed from the admin page: business, Ergani users, phone alerts and the mode switch."""
import base64
import os

import pytest

from app import appconfig, config, db, submitter

KEY = base64.urlsafe_b64encode(os.urandom(32)).decode()


@pytest.fixture
def pin_key(monkeypatch):
    monkeypatch.setattr(config, "PIN_KEY", KEY)


@pytest.fixture
def logins(monkeypatch):
    """Ergani logins succeed unless the password is 'wrong'; records what was tried."""
    tried = []

    def fake(username, password, user_type, url):
        tried.append((username, password, user_type, url))
        return (password != "wrong", "ok" if password != "wrong" else "λάθος κωδικός")
    monkeypatch.setattr(appconfig, "login_test", fake)
    return tried


def save(client, group, **values):
    return client.post("/admin/api/config", json={"group": group, "values": values})


def test_env_values_are_shown_with_their_source(client, admin):
    v = client.get("/admin/api/config").json()
    assert v["business"]["EMPLOYER_AFM"] == {"value": "123456789", "source": "env"}
    assert v["mode"]["value"] == "dry_run"
    assert v["ergani"]["ERGANI_PASSWORD"] == {"set": False, "source": ""}


def test_business_details_are_checked_and_override_env(client, admin):
    assert save(client, "business", EMPLOYER_AFM="123456788", BRANCH_NUMBER="0").status_code == 400   # bad check digit
    r = save(client, "business", EMPLOYER_AFM="090000045", BRANCH_NUMBER="2", ERGANI_EMPLOYER_ID="")
    assert r.status_code == 200, r.text
    assert r.json()["business"]["EMPLOYER_AFM"] == {"value": "090000045", "source": "gui"}
    assert (config.EMPLOYER_AFM, config.BRANCH_NUMBER) == ("090000045", 2)


def test_passwords_need_pin_key_and_are_stored_encrypted(client, admin, monkeypatch):
    r = save(client, "ergani", ERGANI_USERNAME="user1", ERGANI_PASSWORD="secret-pass", ERGANI_USER_TYPE="01")
    assert r.status_code == 400 and "PIN_KEY" in r.json()["detail"]
    monkeypatch.setattr(config, "PIN_KEY", KEY)
    r = save(client, "ergani", ERGANI_USERNAME="user1", ERGANI_PASSWORD="secret-pass", ERGANI_USER_TYPE="01")
    assert r.status_code == 200, r.text
    assert r.json()["ergani"]["ERGANI_PASSWORD"] == {"set": True, "source": "gui"}
    assert "secret-pass" not in db.setting("cfg.ERGANI_PASSWORD")
    assert (config.ERGANI_USERNAME, config.ERGANI_PASSWORD) == ("user1", "secret-pass")
    # leaving the password out keeps it
    save(client, "ergani", ERGANI_USERNAME="user2", ERGANI_USER_TYPE="02")
    assert (config.ERGANI_USERNAME, config.ERGANI_PASSWORD, config.ERGANI_USER_TYPE) == ("user2", "secret-pass", "02")


def test_ntfy_needs_server_and_topic_together(client, admin):
    assert save(client, "ntfy", NTFY_URL="https://ntfy.sh", NTFY_TOPIC="").status_code == 400
    assert save(client, "ntfy", NTFY_URL="ftp://x", NTFY_TOPIC="karta-abc123").status_code == 400
    assert save(client, "ntfy", NTFY_URL="https://ntfy.sh/", NTFY_TOPIC="karta-abc123").status_code == 200
    assert (config.NTFY_URL, config.NTFY_TOPIC) == ("https://ntfy.sh", "karta-abc123")
    assert client.get("/admin/api/overview").json()["ntfy"] is True


def test_login_test_uses_what_is_typed(client, admin, pin_key, logins):
    save(client, "ergani", ERGANI_USERNAME="saved", ERGANI_PASSWORD="saved-pass", ERGANI_USER_TYPE="01")
    r = client.post("/admin/api/config/login-test", json={"target": "production", "username": "typed", "password": "wrong"})
    assert r.json() == {"ok": False, "message": "λάθος κωδικός"}
    client.post("/admin/api/config/login-test", json={"target": "production"})
    assert logins[-1][:2] == ("saved", "saved-pass") and "eservices.yeka.gr" in logins[-1][3]
    # a typed trial user never borrows the production password
    client.post("/admin/api/config/login-test", json={"target": "trial", "username": "trialuser"})
    assert logins[-1][:2] == ("trialuser", "") and "trialv2" in logins[-1][3]


def test_mode_switch_needs_the_afm_and_a_working_login(client, admin, pin_key, logins):
    mode = lambda m, afm="": client.post("/admin/api/mode", json={"mode": m, "afm": afm})   # noqa: E731
    save(client, "ergani", ERGANI_USERNAME="user1", ERGANI_PASSWORD="wrong", ERGANI_USER_TYPE="01")
    assert mode("production").status_code == 400                       # ΑΦΜ not typed
    assert mode("production", "999999999").status_code == 400          # wrong ΑΦΜ
    r = mode("production", "123456789")                                # right ΑΦΜ, but the login fails
    assert r.status_code == 400 and "απέτυχε" in r.json()["detail"]
    assert config.ERGANI_MODE == "dry_run"
    save(client, "ergani", ERGANI_USERNAME="user1", ERGANI_PASSWORD="good", ERGANI_USER_TYPE="01")
    r = mode("trial", "123456789")
    assert r.status_code == 200 and r.json()["mode"] == {"value": "trial", "source": "gui"}
    assert config.ERGANI_HOST == "trialv2eservices.yeka.gr"
    assert mode("dry_run").status_code == 200                          # back to safety needs no confirmation
    assert config.ERGANI_MODE == "dry_run"


def test_queue_waits_while_the_ergani_user_is_missing(client, admin, monkeypatch, employee):
    monkeypatch.setattr(config, "ERGANI_MODE", "production")
    with db.tx() as c:
        mid = c.execute("INSERT INTO movements(employee_id, type, movement_at, created_at, mode, status, next_attempt_at) "
                        "VALUES (?,?,?,?,?,?,?)", (employee, "ARRIVAL", "2026-10-06T09:00:00", db.utc_now_iso(),
                                                   "production", "pending", db.utc_now_iso())).lastrowid
    assert config.problems()
    row = submitter.process(mid, force=True)
    assert row["status"] == "pending" and row["attempts"] == 0
    assert client.get("/admin/api/overview").json()["config_problems"]


def test_one_mode_control_with_the_onboarding_period(client, admin, pin_key, logins, clock):
    """«Λειτουργία»: Δοκιμαστική, Περίοδος προσαρμογής (production + date), Κανονική λειτουργία."""
    from app import onboarding
    mode = lambda m, afm="", until=None: client.post("/admin/api/mode", json={   # noqa: E731
        "mode": m, "afm": afm, "onboarding_until": until})
    save(client, "ergani", ERGANI_USERNAME="user1", ERGANI_PASSWORD="wrong", ERGANI_USER_TYPE="01")
    assert mode("production", "123456789", "2026-10-12").status_code == 400      # the login fails...
    assert config.ERGANI_MODE == "dry_run" and onboarding.until() is None          # ...and the period is undone
    assert mode("dry_run", until="2026-10-12").status_code == 400                  # a period belongs to production
    assert mode("production", "123456789", "2026-10-06").status_code == 400        # from tomorrow on
    save(client, "ergani", ERGANI_USERNAME="user1", ERGANI_PASSWORD="good", ERGANI_USER_TYPE="01")
    assert mode("production", "123456789", "2026-10-12").status_code == 200       # Περίοδος προσαρμογής
    assert config.ERGANI_MODE == "production" and onboarding.active() and str(onboarding.until()) == "2026-10-12"
    assert mode("production", until="2026-10-19").status_code == 200              # a new date: no ΑΦΜ needed
    assert str(onboarding.until()) == "2026-10-19" and str(onboarding.since()) == "2026-10-06"
    assert mode("production").status_code == 200                                  # Κανονική λειτουργία
    assert config.ERGANI_MODE == "production" and not onboarding.active()
    assert mode("production", until="2026-10-12").status_code == 200              # back to a period (not yet mandatory)
    assert mode("dry_run").status_code == 200                                      # Δοκιμαστική: the period ends
    assert config.ERGANI_MODE == "dry_run" and not onboarding.active()
