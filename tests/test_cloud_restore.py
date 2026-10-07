"""Cloud backups (real rclone against a local folder, when rclone is installed) and restore from the admin page."""
import base64
import os
import signal
import subprocess
import time
from datetime import datetime, timedelta

import pytest
from conftest import add_employee

from app import cloud, config, db, main, restore, security

needs_rclone = pytest.mark.skipif(not cloud.available(), reason="rclone / restic are not installed")


@pytest.fixture
def store(tmp_path):
    yield tmp_path / "store"
    cloud._forget()


def cloud_job(client, path, body):
    """A slow step with the cloud: started in the background, then asked until it is over (as the page does)."""
    r = client.post(path, json=body)
    assert r.status_code == 200 and r.json()["state"] == "running", r.text
    deadline = time.time() + 60
    while time.time() < deadline:
        st = client.get(path).json()
        if st["state"] != "running":
            return st
        time.sleep(0.1)
    raise AssertionError(f"{path} did not finish")


def fetch_from_cloud(client, snapshot_id):
    """«Έλεγχος αντιγράφου»: download and check in the background."""
    return cloud_job(client, "/admin/api/restore/cloud", {"id": snapshot_id})


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
        # last night's upload failed (a slow cloud): try again an hour later, not 36 hours after the last good one
        night = evening + timedelta(days=1)
        with db.tx() as c:
            db.put_setting(c, "cloud_last_try", night.isoformat())
            db.put_setting(c, "cloud_status", '{"at": "2026-10-07T20:45:00", "state": "fail", "error": "x"}')
        assert not cloud.due(night + timedelta(minutes=30))
        assert cloud.due(night + timedelta(hours=1, minutes=1))
        with db.tx() as c:
            db.put_setting(c, "cloud_status", '{"at": "2026-10-07T21:46:00", "state": "ok", "error": ""}')
            db.put_setting(c, "cloud_last_ok", (night + timedelta(hours=1)).isoformat())
        assert not cloud.due(night + timedelta(hours=3))         # it worked: back to the nightly upload
    finally:
        cloud.connected = orig


def test_cloud_connect_checks_the_code(client, admin):
    r = client.post("/admin/api/cloud/connect", json={"provider": "drive", "token": "not json"})
    assert r.status_code == 400 and "{" in r.json()["detail"]


@needs_rclone
def test_cloud_backup_is_encrypted_deduplicated_and_can_be_restored(client, admin, employee, store):
    with db.tx() as c:          # ~4 MB of history (~2 MB compressed): restic cuts files into ~1 MB pieces and re-uploads only changed ones
        c.executemany("INSERT INTO audit(at, actor, action, detail) VALUES (?,?,?,?)",
                      [(db.utc_now_iso(), "admin", "test", os.urandom(250).hex()) for _ in range(8000)])
    password = cloud.connect("local", local_path=str(store))
    assert password and len(password) == 24 and cloud.connected()
    cloud.run_backup(datetime(2026, 10, 6, 23, 40))
    size1 = sum(p.stat().st_size for p in store.rglob("*") if p.is_file())
    cloud.run_backup(datetime(2026, 10, 7, 23, 40))
    size2 = sum(p.stat().st_size for p in store.rglob("*") if p.is_file())
    assert size1 > 1_500_000 and size2 - size1 < size1 / 2               # the second snapshot stores only changes
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
    st = fetch_from_cloud(client, cloud.list_backups()[0]["id"])
    assert st["state"] == "done" and st["result"]["employees"] == 1, st
    r = client.post("/admin/api/restore/apply", json={"confirm": True})
    assert db.one("SELECT COUNT(*) n FROM employees")["n"] == 1
    os.remove(os.path.join(os.path.dirname(config.DB_PATH), r.json()["kept"]))
    assert client.post("/admin/api/restore/cloud", json={"id": "../etc/passwd"}).status_code == 400


@needs_rclone
def test_connecting_takes_the_first_backup_right_away(client, admin, employee, store):
    password = cloud.connect("local", local_path=str(store))
    assert password and len(cloud.list_backups()) == 1                 # no race with the nightly worker
    assert cloud.status()["state"] == "ok" and not cloud.due(datetime.now())
    cloud._forget()
    assert cloud.connect("local", local_path=str(store), password=password) is None
    assert len(cloud.list_backups()) == 2                               # existing backups: one more snapshot


def test_no_backup_while_connecting(store):
    assert cloud._running.acquire(blocking=False)                      # connect() holds it until its first snapshot
    try:
        with pytest.raises(cloud.CloudError):
            cloud.run_backup()
        with pytest.raises(cloud.CloudError):
            cloud.connect("local", local_path=str(store))
    finally:
        cloud._running.release()


def test_connect_reports_the_first_backup(client, admin, monkeypatch):
    """Connecting runs in the background; the result (and the new encryption password) is handed over once."""
    monkeypatch.setattr(cloud, "connect", lambda *a, **k: "secret-password-1234")
    monkeypatch.setattr(cloud, "status", lambda: {"state": "fail", "error": "δεν απαντά το cloud"})
    st = cloud_job(client, "/admin/api/cloud/connect", {"provider": "drive", "token": '{"access_token": "x"}'})
    assert st["state"] == "done" and st["result"] == {"password": "secret-password-1234", "first_backup": "fail",
                                                      "error": "δεν απαντά το cloud", "empty": True}
    assert client.get("/admin/api/cloud/connect").json()["state"] == "idle"        # the password: once only


def test_slow_cloud_steps_wait_for_each_other(client, admin, monkeypatch):
    """A reloaded page asking again for the same step keeps waiting for it; another one waits its turn; a failure
    comes back as a message."""
    import threading
    go = threading.Event()

    def slow_list():
        go.wait(10)
        return [{"id": "abcdef12", "time": "2026-10-07T13:32"}]
    monkeypatch.setattr(cloud, "list_backups", slow_list)
    assert client.post("/admin/api/cloud/backups", json={}).json()["state"] == "running"
    assert client.post("/admin/api/cloud/backups", json={}).json()["state"] == "running"       # the same: waits
    st = client.get("/admin/api/cloud/backups").json()
    assert st["state"] == "running" and st["seconds"] >= 0
    go.set()
    deadline = time.time() + 10
    while client.get("/admin/api/cloud/backups").json()["state"] == "running" and time.time() < deadline:
        time.sleep(0.05)
    assert client.get("/admin/api/cloud/backups").json()["result"][0]["id"] == "abcdef12"

    def broken():
        raise cloud.CloudError("Το cloud άργησε να απαντήσει")
    monkeypatch.setattr(cloud, "list_backups", broken)
    st = cloud_job(client, "/admin/api/cloud/backups", {})
    assert st["state"] == "fail" and "άργησε" in st["error"]


@needs_rclone
def test_a_killed_backup_does_not_block_the_next_one(client, admin, employee, store):
    cloud.connect("local", local_path=str(store))
    big = store.parent / "big.bin"
    big.write_bytes(os.urandom(200_000_000))
    p = subprocess.Popen(["restic", "backup", "--quiet", str(big)], env=cloud._env(),
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + 30
    while not any((store / "locks").iterdir()) and time.time() < deadline:       # it holds its lock
        time.sleep(0.05)
    os.kill(p.pid, signal.SIGKILL)                                                # a power cut
    p.wait()
    assert any((store / "locks").iterdir())                                       # the lock stays behind
    cloud.run_backup()
    assert cloud.status()["state"] == "ok"
    big.unlink()


def test_a_night_is_one_restic_run_and_a_stale_lock_is_cleared(client, admin, employee, store, monkeypatch):
    """Each restic run reaches Google Drive afresh (~40″): a night is the backup alone. Only when a run cut short
    left the repository locked: unlock (stale locks only) and the same step once more."""
    calls = []
    locked = [True]

    def fake_run(tool, *args, **kw):
        calls.append(args[0])
        if args[0] == "backup" and locked[0]:
            locked[0] = False
            raise cloud.CloudError(cloud.LOCKED)
        return ""
    monkeypatch.setattr(cloud, "_run", fake_run)
    monkeypatch.setattr(cloud, "connected", lambda: True)
    with db.tx() as c:
        db.put_setting(c, "cloud_last_prune", datetime.now().strftime("%Y-%m-%dT%H:%M:%S"))
    cloud.run_backup()
    assert calls == ["backup", "unlock", "backup"] and cloud.status()["state"] == "ok"
    calls.clear()
    cloud.run_backup()
    assert calls == ["backup"]                                             # a normal night: one run


def _setup_files():
    out = []
    for p in (cloud.conf_path(), cloud._pw_path(), cloud._info_path()):
        with open(p, encoding="utf-8") as f:
            out.append(f.read())
    return out


@needs_rclone
def test_reconnecting_without_the_password_keeps_it(client, admin, employee, store):
    """An expired token, then «Σύνδεση» as if new: the backups and their password stay (it used to wipe both)."""
    password = cloud.connect("local", local_path=str(store))
    assert cloud.connect("local", local_path=str(store)) is None          # nothing new to write down
    with open(cloud._pw_path(), encoding="utf-8") as f:
        assert f.read() == password
    assert cloud.password() == password                                    # «Εμφάνιση κωδικού κρυπτογράφησης»
    assert len(cloud.list_backups()) == 2                                  # same backups, one more snapshot
    assert not os.path.exists(os.path.join(cloud.data_dir(), cloud.STAGE))


@needs_rclone
def test_a_failed_reconnect_leaves_the_working_setup(client, admin, employee, store, tmp_path):
    cloud.connect("local", local_path=str(store))
    before = _setup_files()
    with pytest.raises(cloud.CloudError):
        cloud.connect("local", local_path="/proc/karta-nowhere")         # the cloud can't be written
    assert _setup_files() == before and cloud.connected()
    assert len(cloud.list_backups()) == 1                                  # still works
    other = tmp_path / "other"                                             # backups made with another password
    subprocess.run(["restic", "init", "--repo", str(other)], check=True, capture_output=True,
                   env={**os.environ, "RESTIC_PASSWORD": "another-password-456", "RESTIC_CACHE_DIR": str(tmp_path / "c")})
    with pytest.raises(cloud.CloudError, match="άλλον κωδικό"):
        cloud.connect("local", local_path=str(other))
    with pytest.raises(cloud.CloudError):
        cloud.connect("local", local_path=str(store), password="wrong-password-123")
    assert _setup_files() == before
    assert not os.path.exists(os.path.join(cloud.data_dir(), cloud.STAGE))


@needs_rclone
def test_a_reconnect_to_an_empty_place_keeps_the_password(client, admin, employee, store, tmp_path):
    password = cloud.connect("local", local_path=str(store))
    assert cloud.connect("local", local_path=str(tmp_path / "new-place")) == password   # shown again: a new repository
    assert len(cloud.list_backups()) == 1


def test_the_encryption_password_can_be_shown_again(client, admin, monkeypatch):
    assert client.post("/admin/api/cloud/password").status_code == 409            # no cloud
    monkeypatch.setattr(cloud, "password", lambda: "Kq7mZp2xRt9bWn4cHs8vYd3F")
    r = client.post("/admin/api/cloud/password")
    assert r.json() == {"password": "Kq7mZp2xRt9bWn4cHs8vYd3F"}
    assert db.one("SELECT action FROM audit ORDER BY id DESC LIMIT 1")["action"] == "cloud_password_viewed"
    main.app.dependency_overrides.clear()
    assert client.post("/admin/api/cloud/password").status_code in (401, 403)     # admins only


@needs_rclone
def test_a_new_machine_never_uploads_its_empty_database(client, admin, store):
    """Disaster recovery: the new installation connects to the old backups before restoring them. Its empty
    database must not become the newest snapshot (the one «Επαναφορά» → «Από το cloud…» offers first)."""
    emp = add_employee()
    password = cloud.connect("local", local_path=str(store))
    assert len(cloud.list_backups()) == 1
    cloud._forget()
    with db.tx() as c:                                                     # the new machine: nothing yet
        c.execute("DELETE FROM employees WHERE id=?", (emp,))
    assert cloud.connect("local", local_path=str(store), password=password) is None
    assert len(cloud.list_backups()) == 1                                  # no empty snapshot on top
    cloud.run_backup()                                                     # nor at night
    assert len(cloud.list_backups()) == 1
    st = fetch_from_cloud(client, cloud.list_backups()[0]["id"])
    assert st["state"] == "done" and st["result"]["employees"] == 1, st  # the newest is the real one


@needs_rclone
def test_a_cloud_restore_on_a_new_machine_brings_its_pin_key(client, admin, store, monkeypatch, tmp_path):
    """The old machine's PIN_KEY travels inside the encrypted snapshot; the new machine (another key in its .env)
    takes it over on restore, so the Ergani password and the PINs open as before, with nothing to type."""
    old_key = base64.urlsafe_b64encode(os.urandom(32)).decode()
    new_key = base64.urlsafe_b64encode(os.urandom(32)).decode()
    monkeypatch.setattr(config, "PIN_KEY", old_key)
    add_employee()
    with db.tx() as c:
        db.put_setting(c, "cfg.ERGANI_PASSWORD", security.seal_pin("ergani-secret", b"karta-cfg-ERGANI_PASSWORD"))
    password = cloud.connect("local", local_path=str(store))
    snap = cloud.list_backups()[0]["id"]
    assert cloud.download(snap, str(tmp_path / "got.db")) == old_key     # the database and its key, in one run
    assert (tmp_path / "got.db").read_bytes()[:15] == b"SQLite format 3"

    # the old machine is gone; a new one, with its own key and an empty database
    cloud._forget()
    with db.tx() as c:
        for t in ("employees", "settings"):
            c.execute(f"DELETE FROM {t}")
    monkeypatch.setattr(config, "PIN_KEY", new_key)
    assert cloud.connect("local", local_path=str(store), password=password) is None
    key_file = config.restored_pin_key_path()
    try:
        st = fetch_from_cloud(client, snap)
        assert st["state"] == "done", st
        assert st["result"]["pin_key_ok"] is False and st["result"]["pin_key_restored"] is True
        r = client.post("/admin/api/restore/apply", json={"confirm": True})
        assert r.status_code == 200, r.text
        assert config.PIN_KEY == old_key                                   # used from now on
        with open(key_file, encoding="utf-8") as f:
            assert f.read() == old_key                                     # and after a restart
        assert oct(os.stat(key_file).st_mode & 0o777) == "0o600"
        sealed = db.setting("cfg.ERGANI_PASSWORD")
        assert security.open_pin(sealed, b"karta-cfg-ERGANI_PASSWORD") == "ergani-secret"
        assert config.VALUES.get("ERGANI_PASSWORD") == "ergani-secret"         # loaded, nothing to type again
        assert not os.path.exists(restore.staged_key_path())
        os.remove(os.path.join(os.path.dirname(config.DB_PATH), r.json()["kept"]))
    finally:
        if os.path.exists(key_file):
            os.remove(key_file)


def test_a_backup_without_a_key_restores_as_before(client, admin):
    """A file upload (or a snapshot made before 1.7.5) brings no key: nothing is taken over."""
    restore.stage_key(None)
    assert not os.path.exists(restore.staged_key_path())
    r = client.post("/admin/api/restore/upload", content=backup_bytes(client))
    assert r.status_code == 200, r.text
    assert r.json()["pin_key_restored"] is False
    client.post("/admin/api/restore/discard")
    assert not os.path.exists(config.restored_pin_key_path())


def test_old_snapshots_are_pruned_weekly_and_the_time_is_shown(client, admin, employee, monkeypatch):
    """Every night: the backup. Once a week: forget + prune (lists the whole repository, slow on Google Drive).
    Each result keeps how long it took."""
    calls = []

    def fake_run(tool, *args, **kw):
        calls.append(args)
        return ""
    monkeypatch.setattr(cloud, "_run", fake_run)
    monkeypatch.setattr(cloud, "connected", lambda: True)
    prunes = lambda: [a for a in calls if a[0] == "forget" and "--prune" in a]      # noqa: E731
    cloud.run_backup()
    assert len(prunes()) == 1                                        # never pruned: now
    cloud.run_backup()
    assert len(prunes()) == 1                                        # the next night: the backup only
    assert len([a for a in calls if a[0] == "forget"]) == 1
    with db.tx() as c:
        db.put_setting(c, "cloud_last_prune", "2026-01-01T00:00:00")
    cloud.run_backup()
    assert len(prunes()) == 2                                        # a week (or more) later: prune
    st = cloud.status()
    assert st["state"] == "ok" and isinstance(st["seconds"], int) and st["seconds"] >= 0
    assert client.get("/admin/api/overview").json()["backup"]["cloud"]["seconds"] == st["seconds"]


def test_google_drive_deletes_without_the_trash():
    assert cloud._env()["RCLONE_DRIVE_USE_TRASH"] == "false"
