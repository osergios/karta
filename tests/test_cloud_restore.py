"""Cloud backups (real rclone against a local folder, when rclone is installed) and restore from the admin page."""
import base64
import os
from datetime import datetime, timedelta

import pytest
from conftest import add_employee

from app import cloud, config, db, restore, security

needs_rclone = pytest.mark.skipif(not cloud.available(), reason="rclone / restic are not installed")


@pytest.fixture
def store(tmp_path):
    yield tmp_path / "store"
    cloud._forget()


def backup_bytes(client) -> bytes:
    r = client.get("/admin/api/backup.db")
    assert r.status_code == 200
    return r.content


# ---------- restore ----------
def test_restore_refuses_what_is_not_a_karta_backup(client, admin):
    r = client.post("/admin/api/restore/upload", content=b"hello, not a database")
    assert r.status_code == 400 and "SQLite" in r.json()["detail"]
    assert not os.path.exists(restore.staged_path())
    assert client.post("/admin/api/restore/apply", json={"confirm": True}).status_code == 400


def test_restore_puts_the_backup_back_and_keeps_the_current_database(client, admin, employee):
    saved = backup_bytes(client)                                     # one employee
    add_employee(afm="900000002", display="Γιώργος")                 # changes after the backup
    r = client.post("/admin/api/restore/upload", content=saved)
    assert r.status_code == 200, r.text
    assert r.json()["employees"] == 1 and r.json()["pin_key_ok"] is None
    assert client.get("/admin/api/overview").json()["backup"]["restore_pending"]
    assert db.one("SELECT COUNT(*) n FROM employees")["n"] == 2       # nothing replaced yet
    assert client.post("/admin/api/restore/apply", json={}).status_code == 400   # needs confirmation
    r = client.post("/admin/api/restore/apply", json={"confirm": True})
    assert r.status_code == 200, r.text
    assert db.one("SELECT COUNT(*) n FROM employees")["n"] == 1
    kept = os.path.join(os.path.dirname(config.DB_PATH), r.json()["kept"])
    assert os.path.exists(kept)
    assert client.get("/admin/api/overview").status_code == 200       # Karta keeps running on the restored database
    os.remove(kept)


def test_restore_warns_when_pin_key_differs(client, admin, monkeypatch):
    monkeypatch.setattr(config, "PIN_KEY", base64.urlsafe_b64encode(b"a" * 32).decode())
    eid = add_employee()
    with db.tx() as c:
        c.execute("UPDATE employees SET pin_enc=? WHERE id=?", (security.seal_pin("482916"), eid))
    saved = backup_bytes(client)
    monkeypatch.setattr(config, "PIN_KEY", base64.urlsafe_b64encode(b"b" * 32).decode())
    assert client.post("/admin/api/restore/upload", content=saved).json()["pin_key_ok"] is False
    monkeypatch.setattr(config, "PIN_KEY", base64.urlsafe_b64encode(b"a" * 32).decode())
    assert restore.inspect()["pin_key_ok"] is True
    client.post("/admin/api/restore/discard")
    assert not os.path.exists(restore.staged_path())


# ---------- cloud ----------
def test_cloud_schedule():
    evening = datetime(2026, 10, 6, 23, 45)
    noon = datetime(2026, 10, 6, 12, 0)
    orig = cloud.connected
    cloud.connected = lambda: True
    try:
        assert cloud.due(noon)                                   # never uploaded: right away
        with db.tx() as c:
            db.put_setting(c, "cloud_last_ok", (noon - timedelta(hours=2)).isoformat())
        assert not cloud.due(noon)
        assert cloud.due(evening)                                # tonight's upload
        with db.tx() as c:
            db.put_setting(c, "cloud_last_ok", evening.isoformat())
        assert not cloud.due(evening + timedelta(minutes=10))
        assert cloud.due(evening + timedelta(hours=37))          # the machine was off: catch up
        with db.tx() as c:
            db.put_setting(c, "cloud_last_try", (evening + timedelta(hours=36, minutes=40)).isoformat())
        assert not cloud.due(evening + timedelta(hours=37))      # tried 20′ ago: wait an hour
    finally:
        cloud.connected = orig


def test_cloud_connect_checks_the_code(client, admin):
    r = client.post("/admin/api/cloud/connect", json={"provider": "drive", "token": "not json"})
    assert r.status_code == 400 and "{" in r.json()["detail"]


@needs_rclone
def test_cloud_backup_is_encrypted_deduplicated_and_can_be_restored(client, admin, employee, store):
    password = cloud.connect("local", local_path=str(store))
    assert password and len(password) == 24 and cloud.connected()
    cloud.run_backup(datetime(2026, 10, 6, 23, 40))
    size1 = sum(p.stat().st_size for p in store.rglob("*") if p.is_file())
    cloud.run_backup(datetime(2026, 10, 7, 23, 40))
    size2 = sum(p.stat().st_size for p in store.rglob("*") if p.is_file())
    assert size2 - size1 < size1 / 3                                      # the second snapshot stores only changes
    raw = b"".join(p.read_bytes() for p in store.rglob("*") if p.is_file())
    assert "Παπαδοπούλου".encode() not in raw and b"SQLite format" not in raw   # encrypted
    snaps = cloud.list_backups()
    assert len(snaps) >= 1 and all(cloud.SNAPSHOT_ID.match(s["id"]) for s in snaps)
    assert client.get("/admin/api/overview").json()["backup"]["cloud"]["state"] == "ok"
    assert client.post("/admin/api/cloud/connect", json={"provider": "drive", "token": "{}"}).status_code == 400

    # a new machine: connect to the same backups with the password, then restore from the cloud
    cloud._forget()
    with pytest.raises(cloud.CloudError):
        cloud.connect("local", local_path=str(store), password="wrong-password-123")
    assert not cloud.connected()
    with pytest.raises(cloud.CloudError):
        cloud.connect("local", local_path=str(store))                    # a new repository over the old one: refused
    assert cloud.connect("local", local_path=str(store), password=password) is None
    add_employee(afm="900000002", display="Γιώργος")
    r = client.post("/admin/api/restore/cloud", json={"id": cloud.list_backups()[0]["id"]})
    assert r.status_code == 200 and r.json()["employees"] == 1, r.text
    r = client.post("/admin/api/restore/apply", json={"confirm": True})
    assert db.one("SELECT COUNT(*) n FROM employees")["n"] == 1
    os.remove(os.path.join(os.path.dirname(config.DB_PATH), r.json()["kept"]))
    assert client.post("/admin/api/restore/cloud", json={"id": "../etc/passwd"}).status_code == 400
