"""update.sh (written by setup.sh): the newest version is tried, and Karta goes back to the previous one when it isn't
healthy. Runs the real script against a stand-in for `docker` that plays the container."""
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

FAKE_DOCKER = r'''#!PYTHON
import json, os, subprocess, sys
state_path = os.environ["FAKE_STATE"]
st = json.load(open(state_path))
a = sys.argv[1:]
def env_version():
    for line in open(".env"):
        if line.startswith("KARTA_VERSION="):
            v = line.strip().split("=", 1)[1]
    return locals().get("v", "latest")
def save():
    json.dump(st, open(state_path, "w"))
if a[:4] == ["compose", "exec", "-T", "karta"]:
    if st["running"] is None:
        sys.exit(1)
    cmd = a[4:]
    if cmd[0] == "printenv":
        print("v" + st["running"]); sys.exit(0)
    env = {**os.environ, "DB_PATH": os.environ["FAKE_DB"], "KARTA_VERSION": st["running"], "PYTHONPATH": os.environ["FAKE_ROOT"]}
    sys.exit(subprocess.run([sys.executable] + cmd[1:], env=env).returncode)
if a[:3] == ["compose", "config", "--images"]:
    print("ghcr.io/osergios/karta:" + env_version())
elif a[:2] == ["pull", "-q"]:
    sys.exit(1 if st.get("offline") else 0)
elif a[:2] == ["image", "inspect"]:
    print("PATH=/usr/bin\nKARTA_VERSION=v" + st["latest"])
elif a[:2] == ["compose", "pull"]:
    pass
elif a[:3] == ["compose", "up", "-d"]:
    st["running"] = env_version(); st["started"].append(st["running"]); save()
elif a[:3] == ["compose", "ps", "-q"]:
    print("cid")
elif a[:1] == ["inspect"]:
    print("unhealthy" if st["running"] in st["broken"] else "healthy")
else:
    sys.exit("fake docker: unexpected " + " ".join(a))
'''


def update_script() -> str:
    text = (ROOT / "setup.sh").read_text()
    return re.search(r"cat > update\.sh <<'SH'\n(.*?)\nSH\n", text, re.S).group(1) + "\n"


@pytest.fixture
def machine(tmp_path):
    """A Karta folder: update.sh, .env with KARTA_VERSION=1.4.1, a database, and the fake docker on PATH."""
    (tmp_path / "update.sh").write_text(update_script())
    (tmp_path / "update.sh").chmod(0o755)
    (tmp_path / ".env").write_text("PIN_KEY=x\nKARTA_VERSION=1.4.1\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "docker").write_text(FAKE_DOCKER.replace("PYTHON", sys.executable, 1))
    (bin_dir / "docker").chmod(0o755)
    db = tmp_path / "karta.db"
    with sqlite3.connect(db) as c:
        c.execute("CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT)")
    state = tmp_path / "state.json"

    def run(latest: str, broken=(), *args, offline=False):
        state.write_text(json.dumps({"running": "1.4.1", "latest": latest, "broken": list(broken), "started": [],
                                     "offline": offline}))
        env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "FAKE_STATE": str(state),
               "FAKE_DB": str(db), "FAKE_ROOT": str(ROOT)}
        r = subprocess.run(["sh", str(tmp_path / "update.sh"), *args], env=env, capture_output=True, text=True,
                           timeout=120)
        with sqlite3.connect(db) as c:
            result = c.execute("SELECT value FROM settings WHERE key='update_result'").fetchone()
        pinned = re.search(r"^KARTA_VERSION=(.*)$", (tmp_path / ".env").read_text(), re.M).group(1)
        return r, json.loads(state.read_text()), pinned, json.loads(result[0]) if result else None
    return run


def test_update_switches_to_the_newest_version(machine):
    r, st, pinned, result = machine("1.5.0", (), "now")
    assert r.returncode == 0, r.stdout + r.stderr
    assert pinned == "1.5.0" and st["running"] == "1.5.0"
    assert result["state"] == "ok" and result["version"] == "1.5.0"           # «ενημερώθηκε σε 1.5.0»


def test_a_broken_version_goes_back_to_the_previous_one(machine):
    r, st, pinned, result = machine("1.5.0", ["1.5.0"], "now")
    assert r.returncode == 1
    assert "back to 1.4.1" in r.stdout
    assert st["started"] == ["1.5.0", "1.4.1"] and st["running"] == "1.4.1" and pinned == "1.4.1"
    assert result["state"] == "fail" and result["version"] == "1.4.1"       # «απέτυχε — επέστρεψε στην 1.4.1»


def test_nothing_happens_without_a_request_or_a_network(machine):
    r, st, pinned, result = machine("1.5.0")                                 # from cron, nobody pressed the button
    assert r.returncode == 0 and st["started"] == [] and pinned == "1.4.1" and result is None
    r, st, pinned, result = machine("1.5.0", (), "now", offline=True)        # the newest version can't be fetched
    assert r.returncode == 1 and st["started"] == [] and pinned == "1.4.1" and result["state"] == "fail"


def test_setup_recognises_this_docker_compose_yml():
    """setup.sh replaces a docker-compose.yml only when it is an official one: list every new version there."""
    h = hashlib.sha256((ROOT / "docker-compose.yml").read_bytes()).hexdigest()
    old = re.search(r'OLD_COMPOSE="(.*?)"', (ROOT / "setup.sh").read_text(), re.S).group(1).split()
    assert h in old
