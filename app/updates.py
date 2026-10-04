"""Which Karta version runs, whether a newer one is out, and «Ενημέρωση τώρα» (carried out by update.sh on the host:
the app never gets control of Docker itself)."""
import json
import os
import threading
import time
import urllib.request
from datetime import datetime, timedelta, timezone

from . import db

VERSION = os.environ.get("KARTA_VERSION", "").lstrip("v") or "dev"
RELEASES = "https://api.github.com/repos/osergios/karta/releases/latest"
CHECK_EVERY = 6 * 3600
_latest: dict = {"at": 0.0, "tag": None, "url": None}
_lock = threading.Lock()


def _parse(v: str):
    try:
        return tuple(int(x) for x in v.lstrip("v").split("."))
    except ValueError:
        return None


def newer(candidate: str | None, current: str = VERSION) -> bool:
    a, b = _parse(candidate or ""), _parse(current)
    return bool(a and b and a > b)


def _fetch() -> None:
    try:
        req = urllib.request.Request(RELEASES, headers={"User-Agent": "karta", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=8) as r:
            d = json.loads(r.read())
        with _lock:
            _latest.update(tag=d.get("tag_name"), url=d.get("html_url"))
    except Exception:
        pass


def latest() -> dict:
    """The newest release (cached; refreshed in the background every few hours)."""
    with _lock:
        stale = time.time() - _latest["at"] > CHECK_EVERY
        if stale:
            _latest["at"] = time.time()
    if stale:
        threading.Thread(target=_fetch, daemon=True).start()
    with _lock:
        return {"tag": _latest["tag"], "url": _latest["url"]}


def _utc(raw: str | None):
    try:
        return datetime.fromisoformat(raw).replace(tzinfo=timezone.utc) if raw else None
    except ValueError:
        return None


def info() -> dict:
    now = datetime.now(timezone.utc)
    seen = _utc(db.setting("updater_seen"))
    running = _utc(db.setting("update_running"))
    try:
        result = json.loads(db.setting("update_result") or "null")
    except ValueError:
        result = None
    lt = latest()
    return {
        "version": VERSION,
        "latest": lt["tag"].lstrip("v") if lt["tag"] else None,
        "latest_url": lt["url"],
        "available": newer(lt["tag"]),
        "updater": seen is not None and now - seen < timedelta(minutes=5),     # update.sh runs on the host
        "requested": db.setting("update_request") is not None,
        "running": running is not None and now - running < timedelta(minutes=15),
        "result": result,
    }


def request() -> None:
    with db.tx() as c:
        db.put_setting(c, "update_request", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"))
