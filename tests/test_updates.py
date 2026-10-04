"""«Ενημέρωση τώρα»: the request from the admin page and the host updater (update.sh -> app.updatemark)."""
import json

from app import db, updatemark, updates


def test_versions_compare():
    assert updates.newer("v1.3.0", "1.2.1") and updates.newer("1.10.0", "1.9.9")
    assert not updates.newer("v1.2.1", "1.2.1") and not updates.newer(None, "1.2.1") and not updates.newer("v2.0.0", "dev")


def test_update_needs_the_host_updater(client, admin):
    r = client.post("/admin/api/update")
    assert r.status_code == 409 and "setup.sh" in r.json()["detail"]


def test_update_request_is_carried_out_by_the_host(client, admin, capsys):
    updatemark.main(["poll"])                                  # update.sh runs: nothing asked yet
    assert capsys.readouterr().out == ""
    assert client.get("/admin/api/overview").json()["update"]["updater"]
    assert client.post("/admin/api/update").status_code == 200
    assert client.get("/admin/api/overview").json()["update"]["requested"]
    updatemark.main(["poll"])
    assert capsys.readouterr().out.strip() == "update"         # update.sh pulls the new version...
    u = client.get("/admin/api/overview").json()["update"]
    assert u["running"] and not u["requested"]
    updatemark.main(["poll"])
    assert capsys.readouterr().out == ""                       # ...only once
    updatemark.main(["done", "ok"])                            # the new container reports back
    u = client.get("/admin/api/overview").json()["update"]
    assert not u["running"] and u["result"]["state"] == "ok"
    assert db.setting("kiosk_reload_at")                       # and the shop screen reloads itself
    assert updatemark.main(["done", "maybe"]) == 2
    assert json.loads(db.setting("update_result"))["state"] == "ok"


def test_poll_is_read_only_most_of_the_time(capsys):
    from datetime import datetime, timedelta, timezone
    stamp = lambda m: (datetime.now(timezone.utc) - timedelta(minutes=m)).strftime("%Y-%m-%dT%H:%M:%S")   # noqa: E731
    with db.tx() as c:
        db.put_setting(c, "updater_seen", stamp(10))
    before = db.setting("updater_seen")
    updatemark.main(["poll"])
    assert db.setting("updater_seen") == before                # fresh enough: nothing written
    with db.tx() as c:
        db.put_setting(c, "updater_seen", stamp(40))
    updatemark.main(["poll"])
    assert db.setting("updater_seen") > stamp(1)               # refreshed
