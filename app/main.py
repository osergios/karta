"""Karta: digital work card (ψηφιακή κάρτα εργασίας) service."""
import json
import os
import secrets
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, Response as RawResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import (appconfig, archive, brand, cloud, config, db, erganicheck, erganiread, hours, monitor, onboarding, report,
               restore, security, submitter, updates)
from .timeutil import now_local

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("workcard")

STATIC = Path(__file__).parent / "static"
_stop = threading.Event()
_executor = ThreadPoolExecutor(max_workers=4)

# Simple in-memory throttle for enrollment attempts (single process).
_enroll_fails: list[datetime] = []
_enroll_lock = threading.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    _prepare_db()
    threading.Thread(target=submitter.worker, args=(_stop,), daemon=True).start()
    threading.Thread(target=monitor.worker, args=(_stop,), daemon=True).start()
    threading.Thread(target=cloud.worker, args=(_stop,), daemon=True).start()
    log.info("Started in ERGANI_MODE=%s host=%s branch=%s", config.ERGANI_MODE, config.ERGANI_HOST or "-", config.BRANCH_NUMBER)
    yield
    _stop.set()


def _prepare_db():
    """Everything that follows opening the database: at start-up, and again after a restore."""
    appconfig.load()
    for problem in config.problems():
        log.error("Settings: %s (complete it in the admin page, «Ρυθμίσεις»)", problem)


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
       "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")


@app.middleware("http")
async def guard(request: Request, call_next):
    # CSRF: state-changing requests must come from our own origin.
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        if request.headers.get("origin", "").rstrip("/") != config.PUBLIC_ORIGIN:
            return JSONResponse({"detail": "Bad origin"}, status_code=403)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = CSP
    # the kiosk may use the camera (QR cards) on this origin only; nothing else
    response.headers["Permissions-Policy"] = "camera=(self), microphone=(), geolocation=(), payment=(), usb=()"
    # a private tool: no search engine / AI crawler may index, cache or preview anything here
    response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive, nosnippet, noimageindex, notranslate"
    return response


def client_ip(request: Request) -> str:
    """The device's address, kept with each punch. Cloudflare (always in front: Access protects /admin) writes
    CF-Connecting-IP itself and overwrites whatever the browser sent; X-Real-IP passes the tunnel unchanged, so it is
    only a fallback for a reverse proxy that sets it without Cloudflare."""
    h = request.headers
    return h.get("cf-connecting-ip") or h.get("x-real-ip") or (request.client.host if request.client else "")


def utc_plus(minutes: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S")


# ------------------------------------------------------------------ devices
def current_device(request: Request):
    token = request.cookies.get(config.DEVICE_COOKIE)
    if not token:
        return None
    return db.one("SELECT * FROM devices WHERE token_hash=? AND revoked=0", (security.sha256(token),))


def require_device(request: Request):
    dev = current_device(request)
    if dev is None:
        raise HTTPException(status_code=401, detail="device_not_enrolled")
    now = db.utc_now_iso()
    if not dev["last_seen"] or dev["last_seen"][:16] != now[:16]:
        with db.tx() as c:
            c.execute("UPDATE devices SET last_seen=? WHERE id=?", (now, dev["id"]))
    return dev


# ------------------------------------------------------------------ helpers
def employee_state(employee_id: int) -> dict:
    # Only movements of the current ERGANI_MODE count: a dry-run/trial arrival must never make the
    # first real punch a DEPARTURE (each mode is its own world, see hours.last_movement).
    last = hours.last_movement(employee_id)
    today = now_local().date().isoformat()
    inside = bool(last and last["type"] == "ARRIVAL" and last["movement_at"][:10] == today)
    open_previous = bool(last and last["type"] == "ARRIVAL" and last["movement_at"][:10] != today)
    return {
        "inside": inside,
        "next_action": "DEPARTURE" if inside else "ARRIVAL",
        "last_movement_at": last["movement_at"] if last else None,
        "last_type": last["type"] if last else None,
        "last_status": last["status"] if last else None,     # 'onboarding' = recorded in karta only (admin «Αποχώρηση…»)
        "open_previous_day": open_previous,
        # not punched in for the part of today's schedule that is ending / has ended: the kiosk asks first,
        # so that someone leaving doesn't record an ARRIVAL at the time they go home
        "leaving_unpunched": None if inside else leaving_without_arrival(employee_id),
        # before the declared start: the arrival is refused (working before the declared hours is a mismatch in Ergani)
        "early": None if inside else early_arrival(employee_id),
        # holiday / shop closure: the arrival is refused unless a one-day change with working hours was entered
        "closed": None if inside else closed_today(employee_id),
    }


def closed_today(employee_id: int):
    """{'label'} when the shop is closed today (holiday or closure) and this person has no declared hours for today."""
    off = hours.day_off(employee_id, now_local().date())
    return {"label": off["label"]} if off and off["kind"] in ("holiday", "closure") else None


def notify_closed(emp, closed) -> None:
    """Phone alert (once a day per person) when someone tries to punch in on a day the shop is closed."""
    if not closed:
        return
    now = now_local()
    try:
        monitor.raise_alert("closed_punch", emp["id"], now.date(), "warning",
                            f"{emp['display_name']}: προσπάθησε να χτυπήσει προσέλευση στις {now:%H:%M}, ενώ σήμερα "
                            f"{closed['label'][0].lower() + closed['label'][1:]}. Δεν καταγράφηκε. Αν πρέπει να δουλέψει, "
                            "δήλωσε ΠΡΩΤΑ ωράριο για σήμερα στο ΕΡΓΑΝΗ και μετά πέρασέ το στη διαχείριση "
                            "(«Υπερωρία / αλλαγή ημέρας…»).", None, now)
    except Exception:
        log.exception("closed_punch alert failed")


def early_arrival(employee_id: int):
    """{'start'} when an arrival now would be earlier than the declared start of the next part of today's schedule
    (by more than «early_minutes»), unless the admin allowed an earlier start for today; else None."""
    now = now_local()
    today = now.date()
    sched = hours.schedule_for(employee_id, today)
    if sched is None or hours.day_off(employee_id, today):
        return None
    if db.setting(f"allow_early:{employee_id}") == today.isoformat():
        return None
    allowed = timedelta(minutes=monitor.get_settings()["early_minutes"])
    for a, b in sched.segments:
        if a <= now < b:
            return None                      # inside a part of the schedule: not early
        if now < a:
            return {"start": f"{a:%H:%M}"} if now < a - allowed else None
    return None                              # after the day's schedule (the «Φεύγω» guard handles that)


def notify_early(emp, early) -> None:
    """Phone alert (once a day per person) when someone tries to punch in before the declared start."""
    if not early:
        return
    now = now_local()
    try:
        monitor.raise_alert("early_punch", emp["id"], now.date(), "warning",
                            f"{emp['display_name']}: προσπάθησε να χτυπήσει προσέλευση στις {now:%H:%M}, πριν από την έναρξη "
                            f"του ωραρίου ({early['start']}). Δεν καταγράφηκε. Αν πρέπει να ξεκινήσει νωρίτερα, δήλωσε ΠΡΩΤΑ "
                            "αλλαγή ωραρίου στο ΕΡΓΑΝΗ και μετά πάτα «Νωρίτερη προσέλευση σήμερα» στη διαχείριση.", None, now)
    except Exception:
        log.exception("early_punch alert failed")


def leaving_without_arrival(employee_id: int):
    """{'start','end'} of today's schedule part if it is ending (last hour, or its second half if shorter) or over,
    and there was no arrival for it; else None."""
    now = now_local()
    today = now.date()
    sched = hours.schedule_for(employee_id, today)
    if sched is None or hours.day_off(employee_id, today):
        return None
    i = hours.segment_index(sched, now)
    a, b = sched.segments[i][0], sched.part_end(i)
    if now < a or now < b - min(timedelta(minutes=60), (b - a) / 2):
        return None
    if hours.arrived_for_segment(employee_id, sched, i, now):
        return None
    return {"start": f"{a:%H:%M}", "end": f"{b:%H:%M}"}


OPEN_LOOKBACK_DAYS = 62


def omissions_month(employee_id: int) -> int:
    """Punches that never reached Ergani this month because they were forgotten (entered in karta only)."""
    first = now_local().date().replace(day=1).isoformat()
    return db.one("SELECT COUNT(*) n FROM movements WHERE employee_id=? AND mode=? AND status='local' AND movement_at>=?",
                  (employee_id, config.ERGANI_MODE, first))["n"]


def open_arrivals(employee_id: int) -> list[dict]:
    """Arrivals that were never closed by a departure (forgotten punch-outs), newest first.
    The arrival of a shift that is running today is not included (that one is 'inside')."""
    since = (now_local() - timedelta(days=OPEN_LOOKBACK_DAYS)).isoformat(timespec="seconds")
    rows = db.all_rows("SELECT id, type, movement_at, status FROM movements WHERE employee_id=? AND mode=? "
                       "AND movement_at>=? ORDER BY movement_at, id", (employee_id, config.ERGANI_MODE, since))
    today = now_local().date().isoformat()
    out, arrival = [], None
    for r in rows:
        if r["type"] == "ARRIVAL":
            if arrival is not None:            # a second arrival while the first is still open
                out.append({"id": arrival["id"], "movement_at": arrival["movement_at"], "until": r["movement_at"],
                            "status": arrival["status"]})
            arrival = r
        else:
            arrival = None
    if arrival is not None and arrival["movement_at"][:10] != today:
        out.append({"id": arrival["id"], "movement_at": arrival["movement_at"], "until": None, "status": arrival["status"]})
    return list(reversed(out))


def check_pin(employee_id: int, pin: str):
    emp = db.one("SELECT * FROM employees WHERE id=? AND active=1", (employee_id,))
    if emp is None:
        raise HTTPException(status_code=404, detail="Δεν βρέθηκε ο εργαζόμενος")
    now = db.utc_now_iso()
    if emp["locked_until"] and emp["locked_until"] > now:
        raise HTTPException(status_code=423, detail="Πολλές λάθος προσπάθειες. Δοκιμάστε ξανά σε λίγα λεπτά.")
    if not security.valid_pin_format(pin) or not security.verify_pin(emp["pin_hash"], pin):
        fails = emp["failed_attempts"] + 1
        locked = None
        if fails >= config.PIN_MAX_FAILS:
            locked, fails = utc_plus(config.PIN_LOCK_MINUTES), 0
        with db.tx() as c:
            c.execute("UPDATE employees SET failed_attempts=?, locked_until=? WHERE id=?",
                      (fails, locked, employee_id))
        if locked:
            db.audit("kiosk", "pin_lockout", f"employee={employee_id}")
            raise HTTPException(status_code=423, detail="Πολλές λάθος προσπάθειες. Δοκιμάστε ξανά σε λίγα λεπτά.")
        raise HTTPException(status_code=401, detail="Λάθος PIN")
    if emp["failed_attempts"] or emp["locked_until"]:
        with db.tx() as c:
            c.execute("UPDATE employees SET failed_attempts=0, locked_until=NULL WHERE id=?", (employee_id,))
    return emp


def movement_public(row) -> dict:
    return {
        "id": row["id"], "type": row["type"], "movement_at": row["movement_at"],
        "status": row["status"], "protocol": row["protocol"], "mode": row["mode"],
    }


# ------------------------------------------------------------------ pages
@app.get("/healthz")
def healthz():
    db.one("SELECT 1")
    return {"ok": True, "mode": config.ERGANI_MODE}


@app.get("/robots.txt", response_class=RawResponse)
def robots_txt():
    return RawResponse("User-agent: *\nDisallow: /\n", media_type="text/plain")


def _page(path: Path) -> RawResponse:
    """An HTML page with the business name filled in (see brand.render)."""
    return RawResponse(brand.render(path.read_text(encoding="utf-8")), media_type="text/html; charset=utf-8")


@app.get("/")
def kiosk_page():
    return _page(STATIC / "public" / "kiosk.html")


@app.get("/brand.css")
def brand_css():
    return RawResponse(brand.css(), media_type="text/css")


@app.get("/brand/logo")
def brand_logo():
    lg = brand.logo()
    if lg is None:
        raise HTTPException(status_code=404)
    return RawResponse(lg[0], media_type=lg[1])


@app.get("/c/{token}")
def card_page(token: str):
    """Personal QR card page for the employee's phone (public; the token is the key, checked by /api/card)."""
    resp = _page(STATIC / "public" / "card.html")
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["X-Robots-Tag"] = "noindex, nofollow"
    return resp


@app.get("/enroll")
def enroll_page():
    return _page(STATIC / "public" / "enroll.html")


# PWA: the manifest and the service worker must live at the root so the SW can control "/".
@app.get("/manifest.webmanifest")
def manifest():
    return RawResponse(brand.manifest((STATIC / "public" / "manifest.webmanifest").read_text(encoding="utf-8")),
                       media_type="application/manifest+json")


@app.get("/sw.js")
def service_worker():
    return FileResponse(STATIC / "public" / "sw.js", media_type="application/javascript")


@app.get("/favicon.ico")
def favicon():
    return FileResponse(STATIC / "public" / "brand" / "icons" / "favicon-32.png", media_type="image/png")


app.mount("/static", StaticFiles(directory=STATIC / "public"), name="static")


# ------------------------------------------------------------------ kiosk API
class PinIn(BaseModel):
    employee_id: int
    pin: str = Field(max_length=6)


class PunchIn(PinIn):
    action: str = Field(pattern="^(ARRIVAL|DEPARTURE)$")


def kiosk_labels(rows) -> dict[int, str]:
    """First name only; if several active employees share it, add the shortest
    last-name prefix that tells them apart (e.g. "Μαρία Π." / "Μαρία Κ.")."""
    groups: dict[str, list] = {}
    for r in rows:
        groups.setdefault(r["display_name"].strip().casefold(), []).append(r)
    labels = {}
    for group in groups.values():
        if len(group) == 1:
            labels[group[0]["id"]] = group[0]["display_name"].strip()
            continue
        longest = max(len(r["last_name"]) for r in group)
        n = 1
        while n < longest and len({r["last_name"][:n].casefold() for r in group}) < len(group):
            n += 1
        for r in group:
            prefix = r["last_name"][:n]
            prefix = prefix[:1].upper() + prefix[1:].lower()
            labels[r["id"]] = f'{r["display_name"].strip()} {prefix}.'
    return labels


@app.get("/api/kiosk/employees")
def kiosk_employees(request: Request):
    require_device(request)
    rows = db.all_rows("SELECT id, display_name, last_name FROM employees WHERE active=1")
    labels = kiosk_labels(rows)
    people = sorted(({"id": r["id"], "name": labels[r["id"]], "short": r["display_name"].strip()} for r in rows),
                    key=lambda e: e["name"].casefold())
    return {"mode": config.ERGANI_MODE, "employees": people, **shop_day()}


PREVIEW_THEME = {"christmas": "christmas", "newyear": "christmas", "theophany": "christmas", "easter": "easter",
                 "good_friday": "easter", "mar25": "flag", "oct28": "flag", "clean_monday": "kites", "may1": "may"}


@app.get("/api/kiosk/preview")
def kiosk_preview(key: str):
    """Sample closed-day screen for the admin «Προεπισκόπηση» (no data, nothing recorded)."""
    if key == "closure":
        title, sub = "Σήμερα είμαστε κλειστά", "Ανακαίνιση"
    elif key in hours.GREETINGS:
        title, sub = hours.GREETINGS[key]
    else:
        raise HTTPException(status_code=404)
    reopen = hours.reopen_day(now_local().date())
    return {"closed": {"kind": "closure" if key == "closure" else "holiday", "key": key, "title": title, "sub": sub,
                       "reason": sub, "reopen": reopen.isoformat() if reopen else None, "works": False},
            "festive": PREVIEW_THEME.get(key)}


def shop_day() -> dict:
    """What the shop screen shows today besides the punches: closed-day greeting and the decoration theme."""
    today = now_local().date()
    return {"closed": hours.closed_info(today),
            "festive": hours.festive_season(today) if monitor.get_settings()["festive"] else None}


@app.post("/api/kiosk/state")
def kiosk_state(body: PinIn, request: Request):
    require_device(request)
    emp = check_pin(body.employee_id, body.pin)
    st = employee_state(emp["id"])
    notify_early(emp, st.get("early"))
    notify_closed(emp, st.get("closed"))
    return {"name": emp["display_name"], **st}


@app.post("/api/kiosk/punch")
def kiosk_punch(body: PunchIn, request: Request):
    dev = require_device(request)
    emp = check_pin(body.employee_id, body.pin)
    return record_punch(emp, body.action, dev, request, "pin")


# ---- personal QR card: the card alone identifies and authorises (no PIN)
class QrIn(BaseModel):
    code: str = Field(max_length=256)   # our card "CK1:…" or Ergani's own employee QR


class QrPunchIn(QrIn):
    action: str = Field(pattern="^(ARRIVAL|DEPARTURE)$")


_qr_fails: list[datetime] = []
_qr_lock = threading.Lock()


def check_qr(code: str):
    """(employee, auth_method) for a scanned QR: our personal card ('qr') or Ergani's employee QR ('qr_ergani').
    Ergani's QR carries no secret, so it is matched on ΑΦΜ + surname (+ employer id when configured)."""
    now = datetime.now(timezone.utc)
    with _qr_lock:
        _qr_fails[:] = [t for t in _qr_fails if now - t < timedelta(minutes=10)]
        if len(_qr_fails) >= 20:
            raise HTTPException(status_code=429, detail="Πολλές άκυρες κάρτες. Δοκιμάστε σε λίγα λεπτά ή χρησιμοποιήστε PIN.")
    emp, method, why = None, "qr", "Άγνωστη ή ακυρωμένη κάρτα QR. Χρησιμοποίησε το PIN σου."
    norm = security.normalize_qr(code)
    if norm:
        emp = db.one("SELECT * FROM employees WHERE qr_hash=?", (security.sha256(norm),))
    else:
        eq = security.parse_ergani_qr(code)
        if eq:
            method = "qr_ergani"
            if config.ERGANI_EMPLOYER_ID and eq["id"] != config.ERGANI_EMPLOYER_ID:
                why = "Αυτό το QR του ΕΡΓΑΝΗ είναι από άλλον εργοδότη. Χρησιμοποίησε το PIN σου."
            else:
                cand = db.one("SELECT * FROM employees WHERE afm=?", (eq["afm"],))
                if cand is not None and security.name_key(cand["last_name"]) == security.name_key(eq["ln"]):
                    emp = cand
                else:
                    why = "Αυτό το QR του ΕΡΓΑΝΗ δεν αντιστοιχεί σε εργαζόμενο του καταστήματος. Χρησιμοποίησε το PIN σου."
        else:
            why = "Αυτό δεν είναι κάρτα του καταστήματος ούτε QR του ΕΡΓΑΝΗ. Χρησιμοποίησε το PIN σου."
    if emp is None or not emp["active"]:
        with _qr_lock:
            _qr_fails.append(now)
        if emp is not None:
            raise HTTPException(status_code=403, detail="Η κάρτα ανήκει σε ανενεργό εργαζόμενο.")
        raise HTTPException(status_code=404, detail=why)
    return emp, method


@app.post("/api/kiosk/qr/state")
def kiosk_qr_state(body: QrIn, request: Request):
    require_device(request)
    emp, _ = check_qr(body.code)
    label = kiosk_labels(db.all_rows("SELECT id, display_name, last_name FROM employees WHERE active=1")).get(emp["id"])
    st = employee_state(emp["id"])
    notify_early(emp, st.get("early"))
    notify_closed(emp, st.get("closed"))
    return {"employee_id": emp["id"], "name": emp["display_name"], "label": label or emp["display_name"], **st}


@app.post("/api/kiosk/qr/punch")
def kiosk_qr_punch(body: QrPunchIn, request: Request):
    dev = require_device(request)
    emp, method = check_qr(body.code)
    return record_punch(emp, body.action, dev, request, method)


def record_punch(emp, action: str, dev, request: Request, method: str) -> dict:
    # State check, debounce and insert happen in ONE write transaction (BEGIN IMMEDIATE + the db lock),
    # so two simultaneous requests (network retry, double scan, two kiosks) can't both record a punch.
    with db.tx() as c:
        state = employee_state(emp["id"])
        if action != state["next_action"]:
            raise HTTPException(status_code=409, detail="Η κίνηση δεν ταιριάζει με την τρέχουσα κατάσταση. Ξεκινήστε ξανά.")
        if action == "ARRIVAL" and state.get("early"):
            raise HTTPException(status_code=409, detail=f"Είναι νωρίς: το ωράριό σου ξεκινά στις {state['early']['start']}. "
                                                        "Χτύπα κάρτα τότε.")
        if action == "ARRIVAL" and state.get("closed"):
            raise HTTPException(status_code=409, detail=f"Σήμερα δεν υπάρχει δηλωμένο ωράριο ({state['closed']['label']}). "
                                                        "Η διαχείριση ενημερώθηκε.")

        now = now_local()
        if state["last_movement_at"]:
            since = (now - datetime.fromisoformat(state["last_movement_at"])).total_seconds()
            if 0 <= since < config.DEBOUNCE_SECONDS:
                raise HTTPException(status_code=429, detail="Μόλις καταχωρήθηκε κίνηση. Περιμένετε ένα λεπτό.")

        # onboarding period: recorded here, never sent (a departure follows the arrival it closes)
        status = onboarding.status_for(action, hours.last_movement(emp["id"]) if action == "DEPARTURE" else None) or "pending"
        cur = c.execute(
            """INSERT INTO movements(employee_id, type, movement_at, created_at, device_id, client_ip,
                                     mode, status, next_attempt_at, auth_method)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (emp["id"], action, now.isoformat(timespec="seconds"), db.utc_now_iso(),
             dev["id"], client_ip(request), config.ERGANI_MODE, status, db.utc_now_iso(), method))
        movement_id = cur.lastrowid

    try:  # live checks; never allowed to break a punch
        if action == "ARRIVAL":
            monitor.on_arrival(emp["id"], emp["display_name"], now)
        else:
            monitor.resolve_employee(emp["id"], now)
            monitor.on_departure(emp["id"], emp["display_name"], now)
    except Exception:
        log.exception("monitor hook failed")

    if status == onboarding.STATUS:
        return {"name": emp["display_name"],
                "movement": movement_public(db.one("SELECT * FROM movements WHERE id=?", (movement_id,)))}
    fut = _executor.submit(submitter.process, movement_id, True)
    try:
        row = fut.result(timeout=15)
    except FutureTimeout:
        row = db.one("SELECT * FROM movements WHERE id=?", (movement_id,))
    except Exception:
        log.exception("Immediate submission crashed; the worker will retry")
        row = db.one("SELECT * FROM movements WHERE id=?", (movement_id,))
    return {"name": emp["display_name"], "movement": movement_public(row)}


class LeavingIn(BaseModel):
    employee_id: int | None = None
    pin: str | None = Field(default=None, max_length=6)
    code: str | None = Field(default=None, max_length=256)


@app.post("/api/kiosk/leaving-unpunched")
def kiosk_leaving_unpunched(body: LeavingIn, request: Request):
    """«Φεύγω»: someone who never punched in today is leaving. Nothing is recorded or sent to Ergani (an arrival
    at going-home time would be false); you get a phone alert so you can enter the shift in karta only."""
    dev = require_device(request)
    if body.code:
        emp, _ = check_qr(body.code)
    elif body.employee_id is not None and body.pin:
        emp = check_pin(body.employee_id, body.pin)
    else:
        raise HTTPException(status_code=400, detail="Χρειάζεται PIN ή κάρτα QR.")
    now = now_local()
    part = leaving_without_arrival(emp["id"])
    when = f" (ωράριο {part['start']}–{part['end']})" if part else ""
    try:
        monitor.resolve_employee(emp["id"], now)     # the «δεν χτύπησε προσέλευση» banners: you are told now
        monitor.raise_alert("left_unpunched", emp["id"], now.date(), "warning",
                            f"{emp['display_name']}: φεύγει στις {now:%H:%M} χωρίς να έχει χτυπήσει προσέλευση σήμερα{when}. "
                            "Δεν καταγράφηκε και δεν στάλθηκε τίποτα στο ΕΡΓΑΝΗ. Αν δούλεψε, πέρασε τη βάρδια "
                            "«μόνο στην κάρτα» από τη διαχείριση («Ξεχασμένη βάρδια…»).", None, now)
    except Exception:
        log.exception("left_unpunched alert failed")
    db.audit(f"kiosk:{dev['id']}", "left_unpunched", f"employee={emp['id']} at={now:%Y-%m-%d %H:%M}")
    return {"ok": True, "name": emp["display_name"]}


@app.get("/api/kiosk/reminders")
def kiosk_reminders(request: Request, rv: str | None = None):
    """Who should punch in/out now. The shop screen shows them and repeats a sound every 30″.
    rv = the reload request the screen was loaded after (admin «Ανανέωση οθόνης καταστήματος»)."""
    require_device(request)
    reload_at = db.setting("kiosk_reload_at")
    if rv and reload_at and rv == reload_at and db.setting("kiosk_reload_ack") != rv:
        with db.tx() as c:
            db.put_setting(c, "kiosk_reload_ack", rv)
    closed = hours.closure_on(now_local().date())
    screen = {"closed_today": closed["label"] if closed else None, "reload_at": reload_at, **shop_day()}
    if not monitor.get_settings()["kiosk_reminders"]:
        return {"enabled": False, "reminders": [], **screen}
    rows = db.all_rows("SELECT id, display_name, last_name FROM employees WHERE active=1")
    labels = kiosk_labels(rows)
    short = {r["id"]: r["display_name"].strip() for r in rows}
    now = now_local()
    gone = {r["employee_id"] for r in db.all_rows(   # said «Φεύγω» without a punch-in today: stop the ding-dong
        "SELECT employee_id FROM alerts WHERE kind='left_unpunched' AND key LIKE ?", (f"%:{now.date().isoformat()}",))}
    nxt = hours.next_reminder_in(now)
    return {"enabled": True, **screen, "next_in": round(nxt, 1) if nxt is not None else None,
            "reminders": [{**r, "name": labels.get(r["employee_id"], ""), "short": short.get(r["employee_id"], "")}
                          for r in hours.reminders(now) if r["employee_id"] not in gone]}


@app.get("/api/kiosk/alerts")
def kiosk_alerts(request: Request):
    require_device(request)
    # one line per person on the shop screen: the most serious, newest alert
    rank = {"urgent": 3, "warning": 2, "info": 1}
    best: dict = {}
    for a in monitor.active_alerts(for_kiosk=True):
        cur = best.get(a["employee_id"])
        if cur is None or (rank[a["level"]], a["id"]) > (rank[cur["level"]], cur["id"]):
            best[a["employee_id"]] = a
    ordered = sorted(best.values(), key=lambda a: (-rank[a["level"]], -a["id"]))
    return {"alerts": [{"id": a["id"], "key": a["key"], "level": a["level"], "text": a["kiosk_message"]} for a in ordered]}


# ------------------------------------------------------------------ enrollment
class EnrollIn(BaseModel):
    code: str = Field(max_length=32)


@app.post("/api/enroll")
def enroll(body: EnrollIn, request: Request, response: Response):
    now = datetime.now(timezone.utc)
    with _enroll_lock:
        _enroll_fails[:] = [t for t in _enroll_fails if now - t < timedelta(minutes=10)]
        if len(_enroll_fails) >= 10:
            raise HTTPException(status_code=429, detail="Πάρα πολλές προσπάθειες. Δοκιμάστε σε 10 λεπτά.")

    code = security.normalize_enroll_code(body.code)
    row = db.one("SELECT * FROM enroll_codes WHERE code_hash=?", (security.sha256(code),))
    if row is None or row["used"] or row["expires_at"] < db.utc_now_iso():
        with _enroll_lock:
            _enroll_fails.append(now)
        raise HTTPException(status_code=400, detail="Ο κωδικός δεν είναι έγκυρος ή έληξε.")

    token = security.new_device_token()
    with db.tx() as c:
        c.execute("UPDATE enroll_codes SET used=1 WHERE code_hash=?", (row["code_hash"],))
        c.execute("INSERT INTO devices(name, token_hash, created_at) VALUES (?,?,?)",
                  (row["device_name"], security.sha256(token), db.utc_now_iso()))
    db.audit("kiosk", "device_enrolled", f"name={row['device_name']} ip={client_ip(request)}")
    response.set_cookie(config.DEVICE_COOKIE, token, max_age=config.DEVICE_COOKIE_MAX_AGE,
                        httponly=True, secure=True, samesite="strict", path="/")
    return {"ok": True, "device": row["device_name"]}


# ------------------------------------------------------------------ admin (behind Cloudflare Access)
@app.get("/admin")
@app.get("/admin/")
def admin_page(admin: str = Depends(security.require_admin)):
    return _page(STATIC / "admin" / "admin.html")


@app.get("/admin/assets/{name}")
def admin_asset(name: str, admin: str = Depends(security.require_admin)):
    allowed = {"admin.js": "application/javascript", "admin.css": "text/css"}
    if name not in allowed:
        raise HTTPException(status_code=404)
    return FileResponse(STATIC / "admin" / name, media_type=allowed[name])


# ---- «Πρώτα βήματα»: a checklist for a new installation, ticked off from what is already in place
FIRST_STEPS_MANUAL = ("holidays", "notify", "backup", "training")     # «Έγινε» / «Παράλειψη» marks them (a test punch ticks "training")


def first_steps():
    """Steps of a new installation and whether each is done; None once hidden (or everything is done and hidden)."""
    if db.setting("first_steps_hidden") == "1":
        return None
    marked = set(filter(None, (db.setting("first_steps_marked") or "").split(",")))
    active = db.all_rows("SELECT id FROM employees WHERE active=1")
    with_schedule = {r["employee_id"] for r in db.all_rows("SELECT employee_id, days FROM schedule_versions")
                     if r["days"] not in ("", "{}")}
    steps = [
        ("ergani", "Σύνδεση με το ΕΡΓΑΝΗ", "ΑΦΜ, αριθμός παραρτήματος και ο χρήστης web services του ΕΡΓΑΝΗ, με «Δοκιμή σύνδεσης».",
         bool(config.EMPLOYER_AFM and config.VALUES.get("ERGANI_USERNAME") and config.VALUES.get("ERGANI_PASSWORD")),
         {"tab": "settings", "target": "cfgBox"}),
        ("brand", "Στοιχεία επιχείρησης", "Όνομα, χρώμα και λογότυπο για την οθόνη του καταστήματος.",
         bool(db.setting("brand_name")), {"tab": "settings", "target": "brandBox"}),
        ("staff", "Προσωπικό από το ΕΡΓΑΝΗ", "«Έλεγχος ΕΡΓΑΝΗ» και εισαγωγή των εργαζομένων. Δώστε σε καθέναν το PIN του.",
         bool(active), {"tab": "settings", "target": "erganiCheck"}),
        ("schedules", "Ωράρια", "Το ΕΡΓΑΝΗ δίνει συνήθως μόνο τις ώρες την εβδομάδα: γράψτε το ωράριο κάθε ημέρας από "
         "το πρόγραμμα που σας δίνει ο λογιστής. Η Karta ελέγχει ότι οι ώρες ταιριάζουν.",
         bool(active) and all(r["id"] in with_schedule for r in active), {"tab": "sched", "target": "scheds"}),
        ("holidays", "Αργίες της περιοχής", "Προσθέστε τοπικές αργίες (π.χ. του πολιούχου) ή κλεισίματα, αν υπάρχουν.",
         bool(db.setting("local_holidays")) or "holidays" in marked, {"tab": "sched", "target": "offdays"}),
        ("device", "Οθόνη καταστήματος", "«Δημιουργία κωδικού εγγραφής» και άνοιγμα του /enroll στη συσκευή του καταστήματος.",
         db.one("SELECT 1 FROM devices WHERE revoked=0") is not None, {"tab": "settings", "target": "addDev"}),
        ("notify", "Ειδοποιήσεις στο κινητό", "Προαιρετικά: εφαρμογή ntfy στο κινητό και ρύθμιση εδώ, στις «Ρυθμίσεις».",
         bool(config.NTFY_URL and config.NTFY_TOPIC) or "notify" in marked,
         {"tab": "settings", "target": "cfgNtfy", "test": bool(config.NTFY_URL and config.NTFY_TOPIC)}),
        ("backup", "Αντίγραφα ασφαλείας", "Τα χτυπήματα φυλάσσονται για χρόνια: αντίγραφο εκτός μηχανήματος, "
         "κρυπτογραφημένο στο cloud (Google Drive, Dropbox, Backblaze B2) ή σε USB (./setup.sh usb).",
         _offsite_ok() or "backup" in marked, {"tab": "settings", "target": "backupBox"}),
        ("training", "Δοκιμή με το προσωπικό", "Στη «Δοκιμαστική» λειτουργία όλοι δοκιμάζουν να χτυπήσουν· τίποτα δεν "
         "στέλνεται στο ΕΡΓΑΝΗ. Μετά: «Κινήσεις» → «Διαγραφή δοκιμαστικών κινήσεων».",
         db.one("SELECT 1 FROM movements WHERE mode<>'production' LIMIT 1") is not None or "training" in marked,
         {"tab": "settings", "target": "cfgBox"}),
        ("live", "Έναρξη στο ΕΡΓΑΝΗ", "«Περίοδος προσαρμογής» μέχρι να γίνει υποχρεωτική η κάρτα, ή «Κανονική λειτουργία» "
         "(«Ρυθμίσεις» → «Επιχείρηση και σύνδεση με το ΕΡΓΑΝΗ» → «Λειτουργία»).",
         config.ERGANI_MODE == "production" or onboarding.until() is not None, {"tab": "settings", "target": "cfgBox"}),
    ]
    return [{"key": k, "title": t, "text": x, "done": bool(d), "manual": k in FIRST_STEPS_MANUAL, "marked": k in marked, **link}
            for k, t, x, d, link in steps]


def _offsite_ok() -> bool:
    b, c = monitor.backup_status(), cloud.status()
    return bool((b and b.get("usb") == "ok") or (c and c.get("state") == "ok"))


def backup_info() -> dict:
    """The nightly copy on the machine (and USB) made by backup.sh, and the cloud upload made by Karta."""
    b, c = monitor.backup_status(), cloud.status()
    old = lambda w: w is not None and (now_local() - w).total_seconds() > 50 * 3600     # noqa: E731
    return {
        "host": None if b is None else {"when": b["when"].isoformat(timespec="minutes"), "local": b.get("local"),
                                        "usb": b.get("usb"), "old": old(b["when"])},
        "cloud": None if c is None else {"provider": c["provider"], "state": c["state"], "error": c["error"],
                                         "when": c["when"].isoformat(timespec="minutes") if c["when"] else None,
                                         "old": old(c["when"]), "seconds": c.get("seconds")},
        "cloud_available": cloud.available(),
        "restore_pending": os.path.exists(restore.staged_path()),
    }


class FirstStepIn(BaseModel):
    step: str | None = Field(default=None, pattern="^(holidays|notify|backup|training)$")
    done: bool = True
    hide: bool = False


@app.post("/admin/api/first-steps")
def admin_first_steps(body: FirstStepIn, admin: str = Depends(security.require_admin)):
    with db.tx() as c:
        if body.hide:
            db.put_setting(c, "first_steps_hidden", "1")
        if body.step:
            marked = set(filter(None, (db.setting("first_steps_marked") or "").split(",")))
            (marked.add if body.done else marked.discard)(body.step)
            db.put_setting(c, "first_steps_marked", ",".join(sorted(marked)))
    return {"ok": True, "first_steps": first_steps()}


@app.post("/admin/api/ntfy/test")
def admin_ntfy_test(admin: str = Depends(security.require_admin)):
    """Sends a test phone notification right away and says whether ntfy accepted it."""
    if not (config.NTFY_URL and config.NTFY_TOPIC):
        raise HTTPException(status_code=409, detail="Οι ειδοποιήσεις κινητού δεν είναι ρυθμισμένες: συμπλήρωσε server και θέμα στις «Ρυθμίσεις».")
    try:
        monitor.ntfy_post("Κάρτα: δοκιμή", "Δοκιμαστική ειδοποίηση από τη σελίδα διαχείρισης. Αν τη βλέπετε, όλα είναι σωστά.", "info")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Ο server ειδοποιήσεων δεν τη δέχτηκε: {type(e).__name__}")
    return {"ok": True}


# ---- settings changed from the admin page (business, Ergani users, mode, phone alerts)
class ConfigIn(BaseModel):
    group: str = Field(pattern="^(company|business|ergani|trial|ntfy)$")
    values: dict[str, str | None] = Field(max_length=10)


class LoginTestIn(BaseModel):
    target: str = Field(pattern="^(production|trial)$")
    username: str | None = Field(default=None, max_length=100)
    password: str | None = Field(default=None, max_length=200)     # None: the saved one
    user_type: str | None = Field(default=None, pattern="^(01|02)$")


class ModeIn(BaseModel):
    mode: str = Field(pattern="^(dry_run|trial|production)$")
    afm: str = Field(default="", max_length=9)
    # production only: «Περίοδος προσαρμογής» until this date (the first mandatory day); without it, production means
    # «Κανονική λειτουργία» and an onboarding period still running ends now
    onboarding_until: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


@app.get("/admin/api/config")
def admin_config(admin: str = Depends(security.require_admin)):
    return appconfig.view()


@app.post("/admin/api/config")
def admin_config_save(body: ConfigIn, admin: str = Depends(security.require_admin)):
    try:
        appconfig.save(body.group, body.values, admin)
    except appconfig.ConfigError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return appconfig.view()


@app.post("/admin/api/config/adopt-env")
def admin_config_adopt_env(admin: str = Depends(security.require_admin)):
    """«Να μπουν στα αντίγραφα»: the settings that exist only in .env are copied into the database."""
    try:
        names = appconfig.adopt_env(admin)
    except appconfig.ConfigError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"saved": names, "config": appconfig.view()}


@app.post("/admin/api/config/login-test")
def admin_config_login_test(body: LoginTestIn, admin: str = Depends(security.require_admin)):
    """Tries to log in to Ergani (read-only: nothing is submitted) with what is typed, or with what is saved."""
    user, pwd, utype, url = appconfig.creds_for(body.target)
    if body.target == "trial" and body.username is not None and not config.VALUES.get("ERGANI_TRIAL_USERNAME"):
        pwd = ""                                  # typing a trial user: don't fall back to the production password
    user = body.username if body.username is not None else user
    pwd = body.password if body.password is not None else pwd
    utype = body.user_type or utype
    ok, msg = appconfig.login_test(user.strip(), pwd, utype, url)
    return {"ok": ok, "message": msg}


@app.post("/admin/api/mode")
def admin_mode(body: ModeIn, admin: str = Depends(security.require_admin)):
    """«Λειτουργία»: Δοκιμαστική (dry_run), Περίοδος προσαρμογής (production + a date), Κανονική λειτουργία
    (production), or, for the advanced, δοκιμαστικό ΕΡΓΑΝΗ (trial)."""
    today = now_local().date()
    until = None
    if body.onboarding_until:
        if body.mode != "production":
            raise HTTPException(status_code=400, detail="Η περίοδος προσαρμογής είναι μέρος της κανονικής λειτουργίας.")
        until = _onboarding_date(body.onboarding_until, today)
    before = (db.setting("onboarding_until"), db.setting("onboarding_since"))
    if until:      # the period starts BEFORE the switch: not a single punch reaches Ergani in between
        # moving the date of a running period keeps its start; a date left over in «Δοκιμαστική» (a restored
        # database) is not a running period: it starts today
        running = onboarding.active(today) and config.ERGANI_MODE == "production"
        onboarding.set_period(onboarding.since() if running else today, until)
    try:
        appconfig.set_mode(body.mode, body.afm, admin)
    except appconfig.ConfigError as e:
        if until:  # the switch failed: the period goes back to what it was
            with db.tx() as c:
                for k, v in zip(("onboarding_until", "onboarding_since"), before):
                    if v is None:
                        c.execute("DELETE FROM settings WHERE key=?", (k,))
                    else:
                        db.put_setting(c, k, v)
        raise HTTPException(status_code=400, detail=str(e))
    if until:
        db.audit(admin, "onboarding_set", f"until={until}")
    elif onboarding.active(today):      # «Κανονική» or «Δοκιμαστική»: the onboarding period ends now
        onboarding.set_period(None, None)
        db.audit(admin, "onboarding_end", today.isoformat())
    return appconfig.view()


@app.get("/admin/api/overview")
def admin_overview(admin: str = Depends(security.require_admin)):
    emps = db.all_rows("SELECT * FROM employees ORDER BY active DESC, display_name")
    devices = db.all_rows("SELECT id, name, created_at, last_seen, revoked FROM devices WHERE hidden=0 ORDER BY id DESC")
    movements = db.all_rows(
        """SELECT m.*, e.display_name FROM movements m JOIN employees e ON e.id=m.employee_id
           ORDER BY m.id DESC LIMIT 300""")
    # the editor shows each employee's latest saved schedule (possibly starting in the future) and its history
    today_iso = now_local().date().isoformat()
    schedules: dict = {}
    sched_meta: dict = {}
    for r in db.all_rows("SELECT employee_id, valid_from, days FROM schedule_versions ORDER BY employee_id, valid_from"):
        k = str(r["employee_id"])
        schedules[k] = json.loads(r["days"])
        m = sched_meta.setdefault(k, {"versions": []})
        m["versions"].append(r["valid_from"])
        m["latest_from"] = r["valid_from"]
        if r["valid_from"] <= today_iso:
            m["current_from"] = r["valid_from"]
    alerts = db.all_rows("SELECT a.*, e.display_name FROM alerts a LEFT JOIN employees e ON e.id=a.employee_id "
                         "WHERE a.cleared=0 ORDER BY a.id DESC LIMIT 60")
    salon = db.setting("salon_hours")
    einfo = {str(r["employee_id"]): erganiread.facts(dict(r)) for r in db.all_rows(
        "SELECT i.*, w.declared_week FROM ergani_info i LEFT JOIN ergani_week w ON w.employee_id=i.employee_id")}
    return {
        "salon_hours": json.loads(salon) if salon else {},
        "ergani_info": einfo,
        "ergani_configured": bool(config.ERGANI_USERNAME and config.ERGANI_PASSWORD),
        "pin_view": bool(config.PIN_KEY),
        "alerts": [{"id": a["id"], "kind": a["kind"], "level": a["level"], "message": a["message"],
                    "created_at": a["created_at"], "resolved_at": a["resolved_at"]} for a in alerts],
        "schedules": schedules,
        "schedule_meta": sched_meta,
        "settings": monitor.get_settings(),
        "retro": config.RETRO,                    # the business declares changes and overtime afterwards
        "ntfy": bool(config.NTFY_URL and config.NTFY_TOPIC),
        "config_problems": config.problems(),
        "config": appconfig.view(),
        "backup": backup_info(),
        "update": updates.info(),
        "first_steps": first_steps(),
        "admin": admin,
        "mode": config.ERGANI_MODE,
        "ergani_host": config.ERGANI_HOST,
        "test_movements": db.one("SELECT COUNT(*) n FROM movements WHERE mode<>'production'")["n"],
        "onboarding": onboarding.info(),
        "onboarding_until": (lambda u: u.isoformat() if u else None)(onboarding.until()),
        "onboarding_since": (lambda u: u.isoformat() if u else None)(onboarding.since()),
        "onboarding_progress": onboarding_review(),
        "onboarding_count": db.one("SELECT COUNT(*) n FROM movements WHERE status=? AND mode=?",
                                   (onboarding.STATUS, config.ERGANI_MODE))["n"],
        "held": db.one("SELECT COUNT(*) n FROM movements WHERE status='pending' AND mode=?", (config.ERGANI_MODE,))["n"],
        "uncertain": db.one("SELECT COUNT(*) n FROM movements WHERE status='uncertain' AND mode=?",
                            (config.ERGANI_MODE,))["n"],
        # punches of the other modes, which «Σήμερα» and the reports leave out (each mode is its own world): in
        # «Δοκιμαστική» after a restore, the real ones are all there but not counted
        "other_mode": {"today": db.one("SELECT COUNT(*) n FROM movements WHERE mode<>? AND movement_at>=?",
                                       (config.ERGANI_MODE, now_local().date().isoformat()))["n"],
                       "total": db.one("SELECT COUNT(*) n FROM movements WHERE mode<>?", (config.ERGANI_MODE,))["n"]},
        "stuck_other_mode": db.one("SELECT COUNT(*) n FROM movements WHERE status='pending' AND mode<>?",
                                   (config.ERGANI_MODE,))["n"],
        "branch": config.BRANCH_NUMBER,
        "closures": [dict(r) for r in db.all_rows(
            "SELECT id, start_date, end_date, reason FROM closures WHERE end_date>=? ORDER BY start_date",
            ((now_local().date() - timedelta(days=OPEN_LOOKBACK_DAYS)).isoformat(),))],
        "holidays": [{**h, "date": h["date"].isoformat()} for y in (now_local().year, now_local().year + 1)
                     for h in hours.holidays(y)],
        "local_holidays": hours.local_holidays(),
        "brand": brand.get(),
        "kiosk_reload": {"at": db.setting("kiosk_reload_at"), "done": bool(db.setting("kiosk_reload_at"))
                         and db.setting("kiosk_reload_ack") == db.setting("kiosk_reload_at")},
        "festive_today": hours.festive_season(now_local().date()),
        "closed_today": (lambda c: c["label"] if c else None)(hours.closure_on(now_local().date())),
        "employees": [{
            "id": e["id"], "afm": e["afm"], "last_name": e["last_name"], "first_name": e["first_name"],
            "display_name": e["display_name"], "active": bool(e["active"]),
            "locked": bool(e["locked_until"] and e["locked_until"] > db.utc_now_iso()),
            "pin_viewable": bool(config.PIN_KEY and e["pin_enc"]),
            "qr": bool(e["qr_hash"]), "qr_issued_at": e["qr_issued_at"],
            "qr_viewable": bool(config.PIN_KEY and e["qr_enc"]),
            "link": live_link(e["id"], e["qr_hash"]),
            "open_arrivals": open_arrivals(e["id"]),
            "omissions_month": omissions_month(e["id"]),
            "early_allowed_today": bool(db.one("SELECT 1 FROM settings WHERE key=? AND value=?",
                                               (f"allow_early:{e['id']}", now_local().date().isoformat()))),
            "leaves": [{**dict(l), "label": hours.leave_label(l)} for l in db.all_rows(
                "SELECT id, start_date, end_date, note, kind FROM leaves WHERE employee_id=? AND end_date>=? ORDER BY start_date",
                (e["id"], now_local().date().isoformat()))],
            "on_leave": bool(hours.on_leave(e["id"], now_local().date())),
            "off_today": (lambda o: o["label"] if o else None)(hours.day_off(e["id"], now_local().date())),
            "day_changes": [dict(r) for r in db.all_rows(
                "SELECT day, kind, text, note FROM day_changes WHERE employee_id=? AND day>=? ORDER BY day",
                (e["id"], now_local().date().isoformat()))],
            "today": today_info(e["id"]),
            "flex_arrival": hours.flex_minutes(e["id"]),
            "quiet_today": hours.arrival_quiet(e["id"], now_local().date()),
            "early_leaves": [dict(r) for r in db.all_rows(
                "SELECT day, reason, note FROM early_leaves WHERE employee_id=? AND day>=? ORDER BY day DESC",
                (e["id"], (now_local().date() - timedelta(days=OPEN_LOOKBACK_DAYS)).isoformat()))],
            **employee_state(e["id"]),
        } for e in emps],
        "devices": [dict(d) for d in devices],
        "movements": [{
            "id": m["id"], "name": m["display_name"], "type": m["type"], "movement_at": m["movement_at"],
            "mode": m["mode"], "status": m["status"], "attempts": m["attempts"],
            "late_justification": m["late_justification"], "protocol": m["protocol"],
            "last_error": m["last_error"], "auth_method": m["auth_method"], "payload": m["response_json"] if m["status"] == "dry_run" else None,
            "note": m["note"],
        } for m in movements],
    }


def today_info(employee_id: int):
    """Today's declared hours for the admin list, with the deadline to declare overtime in Ergani."""
    now = now_local()
    if hours.day_off(employee_id, now.date()):
        return None
    declared = hours.schedule_for(employee_id, now.date())
    if declared is None:
        return None
    sched = hours.effective_schedule(employee_id, declared)   # flexible arrival: the end follows the arrival
    ch = hours.day_change(employee_id, now.date())
    # retrospective system (config.RETRO): overtime is declared afterwards, so there is no deadline today
    by = None if config.RETRO else sched.leave_by - timedelta(minutes=monitor.get_settings()["ot_deadline_minutes"])
    moved = int((sched.start - declared.start).total_seconds() // 60)
    return {"label": declared.label(), "end": f"{sched.leave_by:%H:%M}", "ot_by": f"{by:%H:%M}" if by else None,
            "ot_passed": by is not None and now >= by, "over": now >= sched.leave_by, "change": ch["kind"] if ch else None,
            "flex": declared.flex, "arrive_by": f"{declared.arrive_by:%H:%M}" if declared.flex else None,
            "moved": moved, "declared_end": f"{declared.leave_by:%H:%M}", "left": left_early_today(employee_id, now.date())}


def left_early_today(employee_id: int, day):
    """{'at','end','minutes','reason'} when the person left well before the end today (admin «Σήμερα»), else None."""
    e = hours.early_departure(employee_id, day)
    if e is None:
        return None
    m = hours.early_leave_mark(employee_id, day)
    return {**e, "reason": m["reason"] if m else None, "note": m["note"] if m else None}


class AdminPinIn(BaseModel):
    pin: str | None = None   # omitted -> the system generates one


@app.post("/admin/api/employees/{employee_id}/pin")
def admin_new_pin(employee_id: int, body: AdminPinIn | None = None, admin: str = Depends(security.require_admin)):
    emp = db.one("SELECT display_name FROM employees WHERE id=?", (employee_id,))
    if emp is None:
        raise HTTPException(status_code=404)
    custom = body.pin.strip() if body and body.pin else None
    if custom is not None:
        if not security.valid_pin_format(custom):
            raise HTTPException(status_code=400, detail="Το PIN πρέπει να είναι ακριβώς 6 ψηφία")
        if security.weak_pin(custom):
            raise HTTPException(status_code=400, detail="Πολύ εύκολο PIN. Απόφυγε επαναλήψεις και σειρές όπως 123456.")
    pin = custom or security.generate_pin()
    with db.tx() as c:
        c.execute("UPDATE employees SET pin_hash=?, pin_enc=?, failed_attempts=0, locked_until=NULL WHERE id=?",
                  (security.hash_pin(pin), security.seal_pin(pin), employee_id))
    db.audit(admin, "pin_set_custom" if custom else "pin_reset", f"employee={employee_id}")
    return {"ok": True, "name": emp["display_name"], "pin": pin}


@app.get("/admin/api/employees/{employee_id}/pin")
def admin_show_pin(employee_id: int, admin: str = Depends(security.require_admin)):
    emp = db.one("SELECT display_name, pin_enc FROM employees WHERE id=?", (employee_id,))
    if emp is None:
        raise HTTPException(status_code=404)
    if not config.PIN_KEY:
        raise HTTPException(status_code=409, detail="Η προβολή PIN δεν είναι ενεργή: λείπει το PIN_KEY από το .env.")
    pin = security.open_pin(emp["pin_enc"])
    if pin is None:
        raise HTTPException(status_code=409, detail=f"Το PIN του/της {emp['display_name']} ορίστηκε πριν ενεργοποιηθεί η προβολή "
                                                    "και δεν μπορεί να εμφανιστεί. Πάτα «Νέο PIN» ή «Ορισμός PIN» μία φορά.")
    db.audit(admin, "pin_viewed", f"employee={employee_id}")
    return {"name": emp["display_name"], "pin": pin}


@app.post("/admin/api/employees/{employee_id}/qr")
def admin_issue_qr(employee_id: int, admin: str = Depends(security.require_admin)):
    """New personal QR card; the previous one (if any) stops working immediately."""
    emp = db.one("SELECT display_name, qr_hash FROM employees WHERE id=?", (employee_id,))
    if emp is None:
        raise HTTPException(status_code=404)
    code = security.new_qr_code()
    with db.tx() as c:
        c.execute("UPDATE employees SET qr_hash=?, qr_enc=?, qr_issued_at=? WHERE id=?",
                  (security.sha256(code), security.seal_pin(code, security.QR_AAD), db.utc_now_iso(), employee_id))
    db.audit(admin, "qr_reissued" if emp["qr_hash"] else "qr_issued", f"employee={employee_id}")
    return {"name": emp["display_name"], "code": code, "svg": security.qr_svg(code), "viewable": bool(config.PIN_KEY)}


# ---- onboarding period («Περίοδος προσαρμογής»): real use of the card, nothing sent to Ergani until a date
ONBOARDING_REVIEW_DAYS = 31     # the «how is it going» table stays visible this long after the card became mandatory


def onboarding_review():
    u = onboarding.until()
    if u is None or (now_local().date() - u).days > ONBOARDING_REVIEW_DAYS:
        return None
    return onboarding.progress()


def _onboarding_date(raw: str, today) -> date:
    try:
        until = datetime.fromisoformat(raw).date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Μη έγκυρη ημερομηνία.")
    if until <= today:
        raise HTTPException(status_code=400, detail="Η ημερομηνία υποχρεωτικής χρήσης πρέπει να είναι από αύριο και μετά.")
    if until > today + timedelta(days=366):
        raise HTTPException(status_code=400, detail="Έως ένα έτος από σήμερα.")
    return until


class OnboardingIn(BaseModel):
    until: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")   # first mandatory day; None = end now


@app.post("/admin/api/onboarding")
def admin_onboarding(body: OnboardingIn, admin: str = Depends(security.require_admin)):
    """Start / move / end the onboarding period. While it runs, punches are recorded as usual but not sent;
    from the «until» date (the day the card becomes mandatory) every new punch is sent."""
    today = now_local().date()
    if body.until is None:
        if not onboarding.active(today):
            raise HTTPException(status_code=409, detail="Δεν υπάρχει περίοδος προσαρμογής σε εξέλιξη.")
        onboarding.set_period(None, None)
        db.audit(admin, "onboarding_end", today.isoformat())
        return {"ok": True, "onboarding": onboarding.info(today)}
    until = _onboarding_date(body.until, today)
    start = onboarding.since() if onboarding.active(today) else today   # moving the date keeps the start
    onboarding.set_period(start, until)
    db.audit(admin, "onboarding_set", f"since={start} until={until}")
    return {"ok": True, "onboarding": onboarding.info(today)}


# ---- admin correction: punch someone out (forgotten departure / arrival by mistake)
class DepartIn(BaseModel):
    arrival_id: int | None = None   # which open arrival to close; None = the current (latest) one
    at: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")   # HH:MM on the day of the arrival; None = now
    justification: str | None = Field(default=None, pattern="^(POWER_OUTAGE|EMPLOYER_SYSTEMS_UNAVAILABLE|ERGANI_SYSTEMS_UNAVAILABLE)$")
    note: str = Field(default="", max_length=200)
    # True = «Ξέχασε να χτυπήσει»: close the shift in karta only (report, reminders). NOTHING goes to Ergani:
    # a forgotten punch is not a technical fault, so no late-declaration code applies; Ergani keeps the omission.
    local: bool = False


@app.post("/admin/api/employees/{employee_id}/depart")
def admin_depart(employee_id: int, body: DepartIn, admin: str = Depends(security.require_admin)):
    emp = db.one("SELECT * FROM employees WHERE id=?", (employee_id,))
    if emp is None:
        raise HTTPException(status_code=404)
    now = now_local()
    with db.tx() as c:   # decide and insert atomically (no double departure from two clicks)
        last = hours.last_movement(employee_id)
        if body.arrival_id is None:
            if not last or last["type"] != "ARRIVAL":
                raise HTTPException(status_code=409, detail=f"{emp['display_name']} δεν είναι σε βάρδια — δεν χρειάζεται αποχώρηση.")
            target, until = last, None
        else:
            match = next((o for o in open_arrivals(employee_id) if o["id"] == body.arrival_id), None)
            if match is None and not (last and last["id"] == body.arrival_id and last["type"] == "ARRIVAL"):
                raise HTTPException(status_code=409, detail="Αυτή η προσέλευση έχει ήδη κλείσει με αποχώρηση.")
            target = db.one("SELECT * FROM movements WHERE id=?", (body.arrival_id,))
            until = match["until"] if match else None
        is_current = bool(last and last["id"] == target["id"])
        arrived = datetime.fromisoformat(target["movement_at"])
        limit = min(now, datetime.fromisoformat(until)) if until else now
        past_day = arrived.date() != now.date()
        if past_day and not body.at:
            # "now" would mean a shift running across midnight(s) up to today
            raise HTTPException(status_code=400, detail=f"Η προσέλευση είναι της {arrived:%d/%m}: γράψε την ώρα που "
                                                        f"έφυγε εκείνη την ημέρα.")
        if body.at:
            h, m = map(int, body.at.split(":"))
            when = arrived.replace(hour=h, minute=m, second=0)
            if not (arrived < when <= limit) or (until and when >= datetime.fromisoformat(until)):
                end_txt = f"την επόμενη προσέλευση ({datetime.fromisoformat(until):%d/%m %H:%M})" if until else "τώρα"
                raise HTTPException(status_code=400, detail=f"Η ώρα αποχώρησης πρέπει να είναι μετά την προσέλευση "
                                                            f"({arrived:%d/%m %H:%M}) και πριν από {end_txt}.")
        else:
            when = now
        note = body.note.strip()
        # the shift was punched in during the onboarding period: its departure is recorded in karta only too,
        # never sent, so no Ergani late-declaration code applies
        onb = target["status"] == onboarding.STATUS
        if body.local:
            if not body.at:
                raise HTTPException(status_code=400, detail="Γράψε την ώρα που έφυγε.")
            if not note:
                raise HTTPException(status_code=400, detail="Γράψε μια σημείωση (π.χ. «ξέχασε να χτυπήσει αποχώρηση»).")
            cur = c.execute(
                """INSERT INTO movements(employee_id, type, movement_at, created_at, device_id, client_ip,
                                         mode, status, next_attempt_at, auth_method, note)
                   VALUES (?, 'DEPARTURE', ?, ?, NULL, NULL, ?, 'local', ?, 'admin', ?)""",
                (employee_id, when.isoformat(timespec="seconds"), db.utc_now_iso(), config.ERGANI_MODE,
                 db.utc_now_iso(), note))
            movement_id = cur.lastrowid
        late = (now - when).total_seconds() > config.LATE_THRESHOLD_SECONDS
        if not body.local and not onb and late and not body.justification:
            raise HTTPException(status_code=400, detail="Αποχώρηση σε προηγούμενη ώρα = εκπρόθεσμη δήλωση: διάλεξε αιτιολογία ΕΡΓΑΝΗ "
                                                        "(μόνο αν υπήρξε πραγματικό τεχνικό πρόβλημα) ή «Ξέχασε να χτυπήσει».")
        if not body.local:
            cur = c.execute(
                """INSERT INTO movements(employee_id, type, movement_at, created_at, device_id, client_ip,
                                         mode, status, next_attempt_at, auth_method, late_justification, pending_reason, note)
                   VALUES (?, 'DEPARTURE', ?, ?, NULL, NULL, ?, ?, ?, 'admin', ?, ?, ?)""",
                (employee_id, when.isoformat(timespec="seconds"), db.utc_now_iso(), config.ERGANI_MODE,
                 onboarding.STATUS if onb else "pending", db.utc_now_iso(),
                 body.justification if late and not onb else None, body.justification if late and not onb else None,
                 note or None))
            movement_id = cur.lastrowid
    db.audit(admin, "admin_departure_local" if body.local else "admin_departure",
             f"employee={employee_id} arrival={target['id']} at={when:%Y-%m-%d %H:%M} late={late} "
             f"code={'-' if body.local or onb else (body.justification or '-')} onboarding={onb} note={note[:200]}")
    if is_current:   # closing an old forgotten shift must not clear today's banners
        try:
            monitor.resolve_employee(employee_id, now)
            monitor.on_departure(employee_id, emp["display_name"], when)
        except Exception:
            log.exception("monitor hook failed")
    if body.local or onb:
        return {"name": emp["display_name"], "movement": movement_public(db.one("SELECT * FROM movements WHERE id=?", (movement_id,)))}
    fut = _executor.submit(submitter.process, movement_id, True)
    try:
        row = fut.result(timeout=15)
    except Exception:
        row = db.one("SELECT * FROM movements WHERE id=?", (movement_id,))
    return {"name": emp["display_name"], "movement": movement_public(row)}


# ---- «Νωρίτερη προσέλευση σήμερα»: after declaring an earlier start in Ergani, let today's arrival through
@app.post("/admin/api/employees/{employee_id}/allow-early")
def admin_allow_early(employee_id: int, admin: str = Depends(security.require_admin)):
    emp = db.one("SELECT display_name FROM employees WHERE id=?", (employee_id,))
    if emp is None:
        raise HTTPException(status_code=404)
    today = now_local().date().isoformat()
    with db.tx() as c:
        db.put_setting(c, f"allow_early:{employee_id}", today)
    db.audit(admin, "allow_early", f"employee={employee_id} day={today}")
    return {"ok": True, "name": emp["display_name"]}


# ---- «Ευέλικτη προσέλευση»: the minutes agreed in writing and declared in Ergani (0 = none, up to 120).
# Arriving within that window after the declared start is not late; the day's end moves by the same amount.
class FlexIn(BaseModel):
    minutes: int


@app.post("/admin/api/employees/{employee_id}/flex")
def admin_flex(employee_id: int, body: FlexIn, admin: str = Depends(security.require_admin)):
    emp = db.one("SELECT display_name FROM employees WHERE id=?", (employee_id,))
    if emp is None:
        raise HTTPException(status_code=404)
    if not 0 <= body.minutes <= hours.FLEX_MAX:
        raise HTTPException(status_code=400, detail=f"Η ευέλικτη προσέλευση είναι από 0 έως {hours.FLEX_MAX} λεπτά.")
    with db.tx() as c:
        c.execute("UPDATE employees SET flex_arrival=? WHERE id=?", (body.minutes, employee_id))
    db.audit(admin, "flex_arrival", f"employee={employee_id} minutes={body.minutes}")
    return {"ok": True, "name": emp["display_name"], "minutes": body.minutes}


# ---- «Έφυγε νωρίτερα»: why someone left before the end (sickness...). The report then shows the hours to declare
# afterwards in Ergani (απολογιστική δήλωση ωραρίου). Nothing is sent from here.
class EarlyLeaveIn(BaseModel):
    day: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    reason: str = Field(pattern=r"^(sick|personal|other)$")
    note: str = Field(default="", max_length=200)


@app.post("/admin/api/employees/{employee_id}/early-leave")
def admin_early_leave(employee_id: int, body: EarlyLeaveIn, admin: str = Depends(security.require_admin)):
    from datetime import date as _date
    emp = db.one("SELECT display_name FROM employees WHERE id=?", (employee_id,))
    if emp is None:
        raise HTTPException(status_code=404)
    d = _date.fromisoformat(body.day)
    now = now_local()
    if not (now.date() - timedelta(days=OPEN_LOOKBACK_DAYS) <= d <= now.date()):
        raise HTTPException(status_code=400, detail="Η ημερομηνία είναι πολύ μακριά.")
    if not db.one("SELECT 1 FROM movements WHERE employee_id=? AND mode=? AND type='DEPARTURE' AND movement_at>=? "
                  "AND movement_at<? LIMIT 1", (employee_id, config.ERGANI_MODE, d.isoformat(),
                                                (d + timedelta(days=1)).isoformat())):
        raise HTTPException(status_code=400, detail=f"{emp['display_name']} δεν έχει αποχώρηση στις {d:%d/%m}.")
    with db.tx() as c:
        c.execute("INSERT INTO early_leaves(employee_id, day, reason, note, created_at, created_by) VALUES (?,?,?,?,?,?) "
                  "ON CONFLICT(employee_id, day) DO UPDATE SET reason=excluded.reason, note=excluded.note, "
                  "created_at=excluded.created_at, created_by=excluded.created_by",
                  (employee_id, d.isoformat(), body.reason, body.note.strip() or None, db.utc_now_iso(), admin))
        c.execute("UPDATE alerts SET resolved_at=? WHERE employee_id=? AND kind='early_leave' AND resolved_at IS NULL "
                  "AND key LIKE ?", (now.isoformat(timespec="seconds"), employee_id, f"%:{d.isoformat()}"))
    db.audit(admin, "early_leave", f"employee={employee_id} {d} {body.reason}")
    return {"ok": True, "name": emp["display_name"], "early": hours.early_departure(employee_id, d)}


@app.post("/admin/api/employees/{employee_id}/early-leave/{day}/delete")
def admin_early_leave_delete(employee_id: int, day: str, admin: str = Depends(security.require_admin)):
    with db.tx() as c:
        n = c.execute("DELETE FROM early_leaves WHERE employee_id=? AND day=?", (employee_id, day)).rowcount
    if not n:
        raise HTTPException(status_code=404)
    db.audit(admin, "early_leave_deleted", f"employee={employee_id} {day}")
    return {"ok": True}


# ---- «Θα αργήσει σήμερα»: mute today's punch-in reminder and «δεν χτύπησε» alert for one person
class QuietIn(BaseModel):
    on: bool


@app.post("/admin/api/employees/{employee_id}/quiet")
def admin_quiet(employee_id: int, body: QuietIn, admin: str = Depends(security.require_admin)):
    emp = db.one("SELECT display_name FROM employees WHERE id=?", (employee_id,))
    if emp is None:
        raise HTTPException(status_code=404)
    now = now_local()
    today = now.date().isoformat()
    with db.tx() as c:
        db.put_setting(c, f"quiet_in:{employee_id}", today if body.on else "")
        if body.on:   # an alert already sent for today is done too
            c.execute("UPDATE alerts SET resolved_at=? WHERE employee_id=? AND kind LIKE 'missed_in%' "
                      "AND resolved_at IS NULL AND created_at>=?", (now.isoformat(timespec="seconds"), employee_id, today))
    db.audit(admin, "quiet_in" if body.on else "quiet_in_off", f"employee={employee_id} day={today}")
    return {"ok": True, "name": emp["display_name"]}


# ---- «Ξεχασμένη βάρδια»: a whole shift nobody punched (no arrival, no departure), entered in karta only.
# Keeps the report / pay right. NOTHING goes to Ergani (not a technical fault: Ergani keeps the omission).
class LocalShiftIn(BaseModel):
    day: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    start: str = Field(pattern=r"^\d{2}:\d{2}$")
    end: str = Field(pattern=r"^\d{2}:\d{2}$")
    note: str = Field(min_length=1, max_length=200)


@app.post("/admin/api/employees/{employee_id}/local-shift")
def admin_local_shift(employee_id: int, body: LocalShiftIn, admin: str = Depends(security.require_admin)):
    emp = db.one("SELECT * FROM employees WHERE id=?", (employee_id,))
    if emp is None:
        raise HTTPException(status_code=404)
    note = body.note.strip()
    if not note:
        raise HTTPException(status_code=400, detail="Γράψε μια σημείωση.")
    try:
        day = datetime.fromisoformat(body.day).date()
        a = datetime.fromisoformat(f"{body.day}T{body.start}:00")
        b = datetime.fromisoformat(f"{body.day}T{body.end}:00")
    except ValueError:
        raise HTTPException(status_code=400, detail="Μη έγκυρη ημερομηνία ή ώρα.")
    now = now_local()
    if not a < b:
        raise HTTPException(status_code=400, detail="Η λήξη πρέπει να είναι μετά την έναρξη.")
    if b > now:
        raise HTTPException(status_code=400, detail="Η βάρδια πρέπει να έχει τελειώσει (όχι μελλοντική ώρα).")
    if (now.date() - day).days > OPEN_LOOKBACK_DAYS:
        raise HTTPException(status_code=400, detail=f"Μόνο για τις τελευταίες {OPEN_LOOKBACK_DAYS} ημέρες.")
    with db.tx() as c:
        rows = hours.day_movements(employee_id, day)
        for s_, e_ in hours.intervals(rows, None):
            if e_ is None or (s_ < b and a < e_):
                raise HTTPException(status_code=409, detail="Εκείνη την ημέρα υπάρχει ήδη κίνηση σε αυτές τις ώρες "
                                                            "(ή ανοιχτή προσέλευση). Κλείσε πρώτα εκείνη.")
        for r in rows:
            if a <= datetime.fromisoformat(r["movement_at"]) <= b:
                raise HTTPException(status_code=409, detail="Εκείνη την ημέρα υπάρχει ήδη κίνηση σε αυτές τις ώρες.")
        for typ, t in (("ARRIVAL", a), ("DEPARTURE", b)):
            c.execute("""INSERT INTO movements(employee_id, type, movement_at, created_at, device_id, client_ip,
                                                mode, status, next_attempt_at, auth_method, note)
                         VALUES (?, ?, ?, ?, NULL, NULL, ?, 'local', ?, 'admin', ?)""",
                      (employee_id, typ, t.isoformat(timespec="seconds"), db.utc_now_iso(), config.ERGANI_MODE,
                       db.utc_now_iso(), note))
    db.audit(admin, "admin_local_shift", f"employee={employee_id} {body.day} {body.start}-{body.end} note={note[:200]}")
    if day == now.date():
        try:
            monitor.resolve_employee(employee_id, now)
        except Exception:
            log.exception("monitor hook failed")
    return {"ok": True, "name": emp["display_name"]}


@app.post("/admin/api/movements/purge-tests")
def admin_purge_test_movements(admin: str = Depends(security.require_admin)):
    """Remove test punches (dry run + Ergani test server). Real (production) movements are never touched."""
    with db.tx() as c:
        n = c.execute("DELETE FROM movements WHERE mode IN ('dry_run','trial')").rowcount
    db.audit(admin, "test_movements_purged", f"count={n}")
    return {"ok": True, "deleted": n}


@app.get("/admin/api/employees/{employee_id}/qr")
def admin_show_qr(employee_id: int, admin: str = Depends(security.require_admin)):
    emp = db.one("SELECT display_name, qr_hash, qr_enc FROM employees WHERE id=?", (employee_id,))
    if emp is None or not emp["qr_hash"]:
        raise HTTPException(status_code=404, detail="Δεν έχει εκδοθεί κάρτα QR.")
    code = security.open_pin(emp["qr_enc"], security.QR_AAD)
    if code is None:
        raise HTTPException(status_code=409, detail="Η κάρτα δεν μπορεί να ξαναεμφανιστεί (λείπει το PIN_KEY). Έκδωσε νέα.")
    db.audit(admin, "qr_viewed", f"employee={employee_id}")
    return {"name": emp["display_name"], "code": code, "svg": security.qr_svg(code), "viewable": True}


@app.post("/admin/api/employees/{employee_id}/qr/revoke")
def admin_revoke_qr(employee_id: int, admin: str = Depends(security.require_admin)):
    with db.tx() as c:
        n = c.execute("UPDATE employees SET qr_hash=NULL, qr_enc=NULL, qr_issued_at=NULL WHERE id=? AND qr_hash IS NOT NULL",
                      (employee_id,)).rowcount
    if n:
        db.audit(admin, "qr_revoked", f"employee={employee_id}")
    return {"ok": True, "revoked": bool(n)}


# ---- personal link: the employee opens it on the phone and saves the card image
LINK_HOURS = 24
LINK_MAX_OPENS = 10
_link_fails: list[datetime] = []


@app.post("/admin/api/employees/{employee_id}/qr/link")
def admin_card_link(employee_id: int, admin: str = Depends(security.require_admin)):
    emp = db.one("SELECT display_name, qr_hash, qr_enc FROM employees WHERE id=? AND active=1", (employee_id,))
    if emp is None:
        raise HTTPException(status_code=404)
    if not emp["qr_hash"]:
        raise HTTPException(status_code=409, detail="Έκδωσε πρώτα κάρτα QR.")
    if not config.PIN_KEY or security.open_pin(emp["qr_enc"], security.QR_AAD) is None:
        raise HTTPException(status_code=409, detail="Ο σύνδεσμος χρειάζεται το PIN_KEY στο .env (και νέα κάρτα QR μετά).")
    token = secrets.token_urlsafe(24)
    expires = utc_plus(LINK_HOURS * 60)
    with db.tx() as c:
        c.execute("UPDATE card_links SET revoked=1 WHERE employee_id=? AND revoked=0", (employee_id,))   # one live link per person
        c.execute("INSERT INTO card_links(token_hash, employee_id, qr_hash, created_at, expires_at) VALUES (?,?,?,?,?)",
                  (security.sha256(token), employee_id, emp["qr_hash"], db.utc_now_iso(), expires))
    db.audit(admin, "card_link_created", f"employee={employee_id} hours={LINK_HOURS}")
    return {"url": f"{config.PUBLIC_ORIGIN}/c/{token}", "expires_at": expires, "name": emp["display_name"],
            "max_opens": LINK_MAX_OPENS}


@app.post("/admin/api/employees/{employee_id}/qr/link/revoke")
def admin_card_link_revoke(employee_id: int, admin: str = Depends(security.require_admin)):
    with db.tx() as c:
        n = c.execute("UPDATE card_links SET revoked=1 WHERE employee_id=? AND revoked=0", (employee_id,)).rowcount
    if n:
        db.audit(admin, "card_link_revoked", f"employee={employee_id}")
    return {"ok": True}


def live_link(employee_id: int, qr_hash: str | None):
    if not qr_hash:
        return None
    r = db.one("SELECT expires_at, first_opened_at, opens FROM card_links WHERE employee_id=? AND revoked=0 AND qr_hash=? "
               "AND expires_at>? AND opens<? ORDER BY created_at DESC LIMIT 1",
               (employee_id, qr_hash, db.utc_now_iso(), LINK_MAX_OPENS))
    return dict(r) if r else None


@app.get("/api/card/{token}")
def public_card(token: str, request: Request):
    now = datetime.now(timezone.utc)
    with _qr_lock:
        _link_fails[:] = [t for t in _link_fails if now - t < timedelta(minutes=10)]
        if len(_link_fails) >= 30:
            raise HTTPException(status_code=429, detail="Πολλές προσπάθειες. Δοκίμασε σε λίγα λεπτά.")
    gone = HTTPException(status_code=404, detail="Ο σύνδεσμος έληξε ή δεν ισχύει πια. Ζήτα νέο από το κατάστημα.")
    row = db.one("SELECT * FROM card_links WHERE token_hash=?", (security.sha256(token[:64]),)) if len(token) <= 64 else None
    if row is None:
        with _qr_lock:
            _link_fails.append(now)
        raise gone
    emp = db.one("SELECT id, display_name, qr_hash, qr_enc, active FROM employees WHERE id=?", (row["employee_id"],))
    if (row["revoked"] or row["expires_at"] <= db.utc_now_iso() or row["opens"] >= LINK_MAX_OPENS
            or emp is None or not emp["active"] or emp["qr_hash"] != row["qr_hash"]):
        raise gone
    code = security.open_pin(emp["qr_enc"], security.QR_AAD)
    if code is None:
        raise gone
    with db.tx() as c:
        c.execute("UPDATE card_links SET opens=opens+1, first_opened_at=COALESCE(first_opened_at, ?) WHERE token_hash=?",
                  (db.utc_now_iso(), row["token_hash"]))
    if not row["first_opened_at"]:
        db.audit("employee", "card_link_opened", f"employee={emp['id']} ip={client_ip(request)}")
    return {"name": emp["display_name"], "svg": security.qr_svg(code), "expires_at": row["expires_at"],
            "opens_left": LINK_MAX_OPENS - row["opens"] - 1}


class LeaveIn(BaseModel):
    start: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    end: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")      # last day off (inclusive)
    note: str = Field(default="", max_length=120)
    kind: str = Field(default="regular", pattern=r"^(regular|sick|special)$")


@app.post("/admin/api/employees/{employee_id}/leaves")
def admin_add_leave(employee_id: int, body: LeaveIn, admin: str = Depends(security.require_admin)):
    from datetime import date as _date
    emp = db.one("SELECT display_name FROM employees WHERE id=?", (employee_id,))
    if emp is None:
        raise HTTPException(status_code=404)
    try:
        a, b = _date.fromisoformat(body.start), _date.fromisoformat(body.end)
    except ValueError:
        raise HTTPException(status_code=400, detail="Μη έγκυρη ημερομηνία")
    if b < a:
        raise HTTPException(status_code=400, detail="Η επιστροφή πρέπει να είναι μετά την έναρξη της άδειας.")
    if (b - a).days > 366:
        raise HTTPException(status_code=400, detail="Η άδεια δεν μπορεί να ξεπερνά τον έναν χρόνο.")
    with db.tx() as c:
        c.execute("INSERT INTO leaves(employee_id, start_date, end_date, note, kind, created_at, created_by) "
                  "VALUES (?,?,?,?,?,?,?)",
                  (employee_id, a.isoformat(), b.isoformat(), body.note.strip() or None, body.kind, db.utc_now_iso(), admin))
    db.audit(admin, "leave_added", f"employee={employee_id} {a}..{b} {body.kind}")
    return {"ok": True}


@app.post("/admin/api/leaves/{leave_id}/delete")
def admin_delete_leave(leave_id: int, admin: str = Depends(security.require_admin)):
    with db.tx() as c:
        n = c.execute("DELETE FROM leaves WHERE id=?", (leave_id,)).rowcount
    if not n:
        raise HTTPException(status_code=404)
    db.audit(admin, "leave_deleted", f"leave={leave_id}")
    return {"ok": True}


# ------------------------------------------------------------------ holidays, shop closures, one-day changes
def _dates(a: str, b: str):
    from datetime import date as _date
    try:
        x, y = _date.fromisoformat(a), _date.fromisoformat(b)
    except ValueError:
        raise HTTPException(status_code=400, detail="Μη έγκυρη ημερομηνία")
    if y < x:
        raise HTTPException(status_code=400, detail="Η τελευταία ημέρα πρέπει να είναι μετά την πρώτη.")
    if (y - x).days > 366:
        raise HTTPException(status_code=400, detail="Το διάστημα δεν μπορεί να ξεπερνά τον έναν χρόνο.")
    return x, y


class ClosureIn(BaseModel):
    start: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    end: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")      # last closed day (inclusive)
    reason: str = Field(min_length=2, max_length=80)


@app.post("/admin/api/closures")
def admin_add_closure(body: ClosureIn, admin: str = Depends(security.require_admin)):
    a, b = _dates(body.start, body.end)
    with db.tx() as c:
        c.execute("INSERT INTO closures(start_date, end_date, reason, created_at, created_by) VALUES (?,?,?,?,?)",
                  (a.isoformat(), b.isoformat(), body.reason.strip(), db.utc_now_iso(), admin))
    db.audit(admin, "closure_added", f"{a}..{b} {body.reason.strip()}")
    return {"ok": True}


@app.post("/admin/api/closures/{closure_id}/delete")
def admin_delete_closure(closure_id: int, admin: str = Depends(security.require_admin)):
    with db.tx() as c:
        n = c.execute("DELETE FROM closures WHERE id=?", (closure_id,)).rowcount
    if not n:
        raise HTTPException(status_code=404)
    db.audit(admin, "closure_deleted", f"closure={closure_id}")
    return {"ok": True}


class HolidayIn(BaseModel):
    day: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    closed: bool


@app.post("/admin/api/holidays")
def admin_holiday(body: HolidayIn, admin: str = Depends(security.require_admin)):
    """Open or closed on a public/local holiday (default: closed, except Μεγάλη Παρασκευή)."""
    from datetime import date as _date
    d = _date.fromisoformat(body.day)
    h = next((h for h in hours.holidays(d.year) if h["date"] == d), None)
    if h is None:
        raise HTTPException(status_code=404, detail="Δεν είναι αργία.")
    state = hours.holiday_state()
    if body.closed == h["default_closed"]:
        state.pop(body.day, None)
    else:
        state[body.day] = "closed" if body.closed else "open"
    state = {k: v for k, v in state.items() if k >= f"{now_local().year - 1}-01-01"}   # keep it small
    with db.tx() as c:
        db.put_setting(c, "holiday_state", json.dumps(state))
    db.audit(admin, "holiday", f"{body.day} {'closed' if body.closed else 'open'}")
    return {"ok": True}


class LocalHolidaysIn(BaseModel):
    items: list[dict] = Field(max_length=6)


@app.post("/admin/api/local-holidays")
def admin_local_holidays(body: LocalHolidaysIn, admin: str = Depends(security.require_admin)):
    """Local holidays that repeat every year on the same date (e.g. the city's patron saint)."""
    from datetime import date as _date
    out = []
    for it in body.items:
        md, name = str(it.get("md", "")).strip(), str(it.get("name", "")).strip()[:60]
        try:
            _date.fromisoformat(f"2024-{md}")          # leap year: 02-29 allowed
        except ValueError:
            raise HTTPException(status_code=400, detail="Γράψε την ημερομηνία ως ημέρα/μήνα.")
        if len(name) < 2:
            raise HTTPException(status_code=400, detail="Γράψε όνομα για την τοπική αργία.")
        out.append({"md": md, "name": name})
    with db.tx() as c:
        db.put_setting(c, "local_holidays", json.dumps(out, ensure_ascii=False))
    db.audit(admin, "local_holidays", ", ".join(f"{x['md']} {x['name']}" for x in out))
    return {"ok": True}


class DayChangeIn(BaseModel):
    day: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    kind: str = Field(pattern=r"^(overtime|change|off)$")
    text: str = Field(default="", max_length=60)
    note: str = Field(default="", max_length=120)


@app.post("/admin/api/employees/{employee_id}/day-change")
def admin_day_change(employee_id: int, body: DayChangeIn, admin: str = Depends(security.require_admin)):
    """One-day change of the declared schedule (overtime, other hours, or no work), AFTER it was declared in Ergani.
    Reminders, alerts, the early-arrival/closed-day refusal and the report follow it for that day."""
    from datetime import date as _date
    if db.one("SELECT 1 FROM employees WHERE id=?", (employee_id,)) is None:
        raise HTTPException(status_code=404)
    d = _date.fromisoformat(body.day)
    today = now_local().date()
    if not (today - timedelta(days=OPEN_LOOKBACK_DAYS) <= d <= today + timedelta(days=366)):
        raise HTTPException(status_code=400, detail="Η ημερομηνία είναι πολύ μακριά.")
    if body.kind == "off":
        text = ""
    else:
        try:
            sp = hours.parse_span(body.text)
        except ValueError:
            sp = None
        if sp is None:
            raise HTTPException(status_code=400, detail="Γράψε το ωράριο της ημέρας, π.χ. 10:00-18:30/+30 ή 10:00-19:00/30.")
        text = sp.text
    with db.tx() as c:
        c.execute("INSERT INTO day_changes(employee_id, day, kind, text, note, created_at, created_by) VALUES (?,?,?,?,?,?,?) "
                  "ON CONFLICT(employee_id, day) DO UPDATE SET kind=excluded.kind, text=excluded.text, note=excluded.note, "
                  "created_at=excluded.created_at, created_by=excluded.created_by",
                  (employee_id, d.isoformat(), body.kind, text, body.note.strip() or None, db.utc_now_iso(), admin))
    db.audit(admin, "day_change", f"employee={employee_id} {d} {body.kind} {text}")
    # the deadline to declare it in Ergani, measured on the usual schedule of that day
    # (the first moment the new hours go beyond the usual ones: an earlier start, or a later end)
    late = None
    reg = hours.effective_schedule(employee_id, hours.schedule_for(employee_id, d, regular=True))
    new = hours.effective_schedule(employee_id, hours.schedule_for(employee_id, d))
    if d == today and new is not None and not config.RETRO:
        ref = (new.start if reg is None or new.start < reg.start else
               reg.leave_by if new.leave_by > reg.leave_by else None)
        by = ref - timedelta(minutes=monitor.get_settings()["ot_deadline_minutes"]) if ref else None
        if by and now_local() > by:
            late = f"{by:%H:%M}"
    return {"ok": True, "text": text, "late_after": late}


@app.post("/admin/api/employees/{employee_id}/day-change/{day}/delete")
def admin_day_change_delete(employee_id: int, day: str, admin: str = Depends(security.require_admin)):
    with db.tx() as c:
        n = c.execute("DELETE FROM day_changes WHERE employee_id=? AND day=?", (employee_id, day)).rowcount
    if not n:
        raise HTTPException(status_code=404)
    db.audit(admin, "day_change_deleted", f"employee={employee_id} {day}")
    return {"ok": True}


# ------------------------------------------------------------------ restart the shop screen from here
@app.post("/admin/api/update")
def admin_update(admin: str = Depends(security.require_admin)):
    """«Ενημέρωση τώρα»: leaves the request for update.sh on the host, which pulls the new version and restarts."""
    u = updates.info()
    if not u["updater"]:
        raise HTTPException(status_code=409, detail="Η αυτόματη ενημέρωση δεν είναι ρυθμισμένη σε αυτό το μηχάνημα: "
                                                    "τρέξτε μία φορά  cd ~/karta && ./setup.sh update")
    updates.request()
    db.audit(admin, "update_request", f"{u['version']} -> {u['latest'] or '?'}")
    return {"ok": True}


@app.post("/admin/api/update/check")
def admin_update_check(admin: str = Depends(security.require_admin)):
    """«Έλεγχος τώρα»: looks for a newer release right away (otherwise every few hours)."""
    updates.check_now()
    return updates.info()


@app.post("/admin/api/kiosk/reload")
def admin_kiosk_reload(admin: str = Depends(security.require_admin)):
    """The shop screen reloads itself within ~30″ (it waits if someone is in the middle of punching)."""
    stamp = now_local().isoformat(timespec="seconds")
    with db.tx() as c:
        db.put_setting(c, "kiosk_reload_at", stamp)
    db.audit(admin, "kiosk_reload", stamp)
    return {"ok": True, "at": stamp}


# ------------------------------------------------------------------ business details («Στοιχεία επιχείρησης»)
_OPT_COLOR = r"^(#[0-9a-fA-F]{6})?$"      # empty = the theme's default


class BrandIn(BaseModel):
    name: str = Field(default="", max_length=80)
    short: str = Field(default="", max_length=30)
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    # optional: left out = unchanged
    theme: str | None = Field(default=None, pattern=r"^[a-z]{0,20}$")
    bg: str | None = Field(default=None, pattern=_OPT_COLOR)
    side: str | None = Field(default=None, pattern=_OPT_COLOR)
    ink: str | None = Field(default=None, pattern=_OPT_COLOR)
    in_color: str | None = Field(default=None, pattern=_OPT_COLOR)
    out_color: str | None = Field(default=None, pattern=_OPT_COLOR)
    dark_kiosk: bool | None = None
    dark_admin: bool | None = None


@app.post("/admin/api/brand")
def admin_brand(body: BrandIn, admin: str = Depends(security.require_admin)):
    colors = {k: v for k, v in (("theme", body.theme), ("bg", body.bg), ("side", body.side), ("ink", body.ink),
                                ("in", body.in_color), ("out", body.out_color), ("dark_kiosk", body.dark_kiosk),
                                ("dark_admin", body.dark_admin)) if v is not None}
    brand.set_info(body.name, body.short, body.color, colors)
    db.audit(admin, "brand", f"{body.name} / {body.short} / {body.color}" + (f" / {colors}" if colors else ""))
    return {"ok": True}


class LogoIn(BaseModel):
    data: str = Field(max_length=1_400_000)       # base64 of a PNG / JPEG / WebP up to 1 MB


@app.post("/admin/api/brand/logo")
def admin_brand_logo(body: LogoIn, admin: str = Depends(security.require_admin)):
    import base64
    import binascii
    try:
        raw = base64.b64decode(body.data.split(",", 1)[-1], validate=True)
        brand.set_logo(raw)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="Το λογότυπο πρέπει να είναι PNG, JPG ή WebP έως 1 MB.")
    db.audit(admin, "brand_logo", f"{len(raw)} bytes")
    return {"ok": True}


@app.post("/admin/api/brand/logo/delete")
def admin_brand_logo_delete(admin: str = Depends(security.require_admin)):
    brand.set_logo(None)
    db.audit(admin, "brand_logo", "removed")
    return {"ok": True}


class DisplayNameIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=40)


@app.post("/admin/api/employees/{employee_id}/name")
def admin_set_display_name(employee_id: int, body: DisplayNameIn, admin: str = Depends(security.require_admin)):
    name = body.display_name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Το όνομα δεν μπορεί να είναι κενό")
    with db.tx() as c:
        n = c.execute("UPDATE employees SET display_name=? WHERE id=?", (name, employee_id)).rowcount
    if not n:
        raise HTTPException(status_code=404)
    db.audit(admin, "display_name", f"employee={employee_id} name={name}")
    return {"ok": True}


@app.post("/admin/api/employees/{employee_id}/delete")
def admin_delete_employee(employee_id: int, admin: str = Depends(security.require_admin)):
    """Hard delete — only for people without real card records (tests, entries made by mistake).
    Punches sent or queued for Ergani are legal working-time records and must be kept."""
    emp = db.one("SELECT id, afm, display_name FROM employees WHERE id=?", (employee_id,))
    if emp is None:
        raise HTTPException(status_code=404)
    real = db.one("SELECT COUNT(*) n FROM movements WHERE employee_id=? AND mode='production'", (employee_id,))["n"]
    if real:
        raise HTTPException(status_code=409, detail=(
            f"{emp['display_name']}: υπάρχουν {real} πραγματικές κινήσεις κάρτας (ΕΡΓΑΝΗ παραγωγής). "
            "Το αρχείο χρόνου εργασίας πρέπει να διατηρείται, οπότε δεν διαγράφεται — χρησιμοποίησε «Απενεργοποίηση»."))
    with db.tx() as c:
        tests = c.execute("DELETE FROM movements WHERE employee_id=?", (employee_id,)).rowcount
        for table in ("alerts", "schedule_versions", "ergani_info", "ergani_week", "card_links", "leaves", "day_changes"):
            c.execute(f"DELETE FROM {table} WHERE employee_id=?", (employee_id,))
        c.execute("DELETE FROM employees WHERE id=?", (employee_id,))
    db.audit(admin, "employee_deleted", f"name={emp['display_name']} afm=***{emp['afm'][-3:]} test_movements={tests}")
    return {"ok": True, "test_movements": tests}


class ActiveIn(BaseModel):
    active: bool


@app.post("/admin/api/employees/{employee_id}/active")
def admin_set_active(employee_id: int, body: ActiveIn, admin: str = Depends(security.require_admin)):
    with db.tx() as c:
        n = c.execute("UPDATE employees SET active=? WHERE id=?", (int(body.active), employee_id)).rowcount
    if not n:
        raise HTTPException(status_code=404)
    db.audit(admin, "employee_active", f"employee={employee_id} active={body.active}")
    return {"ok": True}


class EnrollCodeIn(BaseModel):
    device_name: str = Field(min_length=1, max_length=40)


@app.post("/admin/api/enroll-codes")
def admin_enroll_code(body: EnrollCodeIn, admin: str = Depends(security.require_admin)):
    code = security.new_enroll_code()
    with db.tx() as c:
        c.execute("INSERT INTO enroll_codes(code_hash, device_name, expires_at, created_by) VALUES (?,?,?,?)",
                  (security.sha256(code), body.device_name.strip(), utc_plus(config.ENROLL_CODE_MINUTES), admin))
    db.audit(admin, "enroll_code_created", f"device={body.device_name.strip()}")
    return {"code": f"{code[:4]}-{code[4:]}", "expires_minutes": config.ENROLL_CODE_MINUTES}


@app.post("/admin/api/devices/{device_id}/revoke")
def admin_revoke_device(device_id: int, admin: str = Depends(security.require_admin)):
    with db.tx() as c:
        n = c.execute("UPDATE devices SET revoked=1 WHERE id=?", (device_id,)).rowcount
    if not n:
        raise HTTPException(status_code=404)
    db.audit(admin, "device_revoked", f"device={device_id}")
    return {"ok": True}


@app.post("/admin/api/devices/{device_id}/delete")
def admin_delete_device(device_id: int, admin: str = Depends(security.require_admin)):
    """Remove a device from the list. It is revoked too; the row stays hidden so old punches keep their device."""
    dev = db.one("SELECT name FROM devices WHERE id=?", (device_id,))
    if dev is None:
        raise HTTPException(status_code=404)
    with db.tx() as c:
        c.execute("UPDATE devices SET revoked=1, hidden=1 WHERE id=?", (device_id,))
    db.audit(admin, "device_deleted", f"device={device_id} name={dev['name']}")
    return {"ok": True}


@app.post("/admin/api/alerts/clear")
def admin_clear_alerts(admin: str = Depends(security.require_admin)):
    """Empty the admin list: open alerts are marked done, all are hidden (the monthly report still counts them)."""
    now = now_local().isoformat(timespec="seconds")
    with db.tx() as c:
        c.execute("UPDATE alerts SET resolved_at=? WHERE resolved_at IS NULL", (now,))
        n = c.execute("UPDATE alerts SET cleared=1 WHERE cleared=0").rowcount
    db.audit(admin, "alerts_cleared", f"count={n}")
    return {"ok": True, "cleared": n}


@app.post("/admin/api/movements/{movement_id}/retry")
def admin_retry(movement_id: int, admin: str = Depends(security.require_admin)):
    with db.tx() as c:
        n = c.execute(
            "UPDATE movements SET status='pending', attempts=0, next_attempt_at=? WHERE id=? AND status='failed'",
            (db.utc_now_iso(), movement_id)).rowcount
    if not n:
        raise HTTPException(status_code=409, detail="Μόνο αποτυχημένες κινήσεις ξαναστέλνονται")
    db.audit(admin, "movement_retry", f"movement={movement_id}")
    return {"ok": True}


class UncertainIn(BaseModel):
    sent: bool                                            # True = it IS in Ergani; False = it is not, send it
    protocol: str = Field(default="", max_length=40)      # the protocol number seen in Ergani, if any


@app.post("/admin/api/movements/{movement_id}/uncertain")
def admin_resolve_uncertain(movement_id: int, body: UncertainIn, admin: str = Depends(security.require_admin)):
    """A submission whose outcome is unknown (timeout after sending). The admin checked Ergani:
    either mark it as submitted, or queue it again (it goes out as a late declaration)."""
    with db.tx() as c:
        if body.sent:
            n = c.execute("UPDATE movements SET status='submitted', protocol=?, submitted_at=?, last_error=NULL, "
                          "response_json=? WHERE id=? AND status='uncertain'",
                          (body.protocol.strip() or None, db.utc_now_iso(),
                           json.dumps({"confirmed_by_admin": admin}), movement_id)).rowcount
        else:
            n = c.execute("UPDATE movements SET status='pending', next_attempt_at=? WHERE id=? AND status='uncertain'",
                          (db.utc_now_iso(), movement_id)).rowcount
    if not n:
        raise HTTPException(status_code=409, detail="Η κίνηση δεν περιμένει έλεγχο.")
    db.audit(admin, "movement_confirmed_in_ergani" if body.sent else "movement_resend_after_check",
             f"movement={movement_id} protocol={body.protocol.strip() or '-'}")
    # The admin has checked Ergani and decided: the alert(s) for this movement are done either way.
    # If the new attempt is uncertain again, it raises a new alert (one per attempt).
    prefix = submitter.uncertain_alert_prefix(movement_id)
    old = f"ergani_uncertain#{movement_id}:"          # key format of the first release of this feature
    with db.tx() as c:
        c.execute("UPDATE alerts SET resolved_at=? WHERE (substr(key, 1, ?)=? OR substr(key, 1, ?)=?) AND resolved_at IS NULL",
                  (now_local().isoformat(timespec="seconds"), len(prefix), prefix, len(old), old))
    if not body.sent:
        _executor.submit(submitter.process, movement_id, True)
    return {"ok": True}


# ------------------------------------------------------------------ schedules, limits, alerts, report
class ScheduleIn(BaseModel):
    days: dict[str, str]          # {"0": "09:00-17:00", ...}; Monday = 0; "" = day off
    valid_from: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")   # default: today


@app.post("/admin/api/schedules/{employee_id}")
def admin_set_schedule(employee_id: int, body: ScheduleIn, admin: str = Depends(security.require_admin)):
    if db.one("SELECT 1 FROM employees WHERE id=?", (employee_id,)) is None:
        raise HTTPException(status_code=404)
    parsed = {}
    for wd, text in body.days.items():
        if wd not in {str(i) for i in range(7)}:
            raise HTTPException(status_code=400, detail="Μη έγκυρη ημέρα")
        try:
            span = hours.parse_span(text)
        except ValueError:
            raise HTTPException(status_code=400,
                                detail=f"{hours.WEEKDAYS[int(wd)]}: γράψε το ωράριο ως 10:00-18:00 ή 10:00-18:30/30 "
                                       f"(διάλειμμα σε λεπτά), σπαστό ως 10:00-14:00+17:00-21:00, ή άφησέ το κενό")
        if span:
            parsed[int(wd)] = span
    today = now_local().date()
    try:
        vf = datetime.fromisoformat(body.valid_from).date() if body.valid_from else today
    except ValueError:
        raise HTTPException(status_code=400, detail="Μη έγκυρη ημερομηνία «Ισχύει από».")
    if not (today - timedelta(days=OPEN_LOOKBACK_DAYS) <= vf <= today + timedelta(days=366)):
        raise HTTPException(status_code=400, detail="Η ημερομηνία «Ισχύει από» είναι πολύ μακριά.")
    days_json = json.dumps({str(wd): sp.text for wd, sp in sorted(parsed.items())})
    with db.tx() as c:
        # history: this schedule applies from vf on (earlier days keep the version that was in force then)
        c.execute("INSERT INTO schedule_versions(employee_id, valid_from, days, created_at, created_by) VALUES (?,?,?,?,?) "
                  "ON CONFLICT(employee_id, valid_from) DO UPDATE SET days=excluded.days, created_at=excluded.created_at, "
                  "created_by=excluded.created_by", (employee_id, vf.isoformat(), days_json, db.utc_now_iso(), admin))
    db.audit(admin, "schedule_set", f"employee={employee_id} days={len(parsed)} valid_from={vf}")
    return {"ok": True, "valid_from": vf.isoformat()}


class SettingsIn(BaseModel):
    values: dict[str, float]


LIMITS = {"pre_end_minutes": (0, 120),   # pre_end_minutes: no longer used (kept so an old admin page can still save)
           "grace_minutes": (0, 60), "escalate_minutes": (5, 240), "kiosk_reminders": (0, 1),
          "early_minutes": (0, 60), "ot_deadline_minutes": (0, 240), "ot_notice_minutes": (0, 120), "festive": (0, 1),
          "daily_max_hours": (1, 16), "weekly_max_hours": (1, 80), "weekly_legal_hours": (1, 80),
          "min_rest_hours": (0, 24)}


@app.post("/admin/api/settings")
def admin_settings(body: SettingsIn, admin: str = Depends(security.require_admin)):
    for k, v in body.values.items():
        if k not in LIMITS or not (LIMITS[k][0] <= v <= LIMITS[k][1]):
            raise HTTPException(status_code=400, detail=f"Μη έγκυρη τιμή: {k}")
    with db.tx() as c:
        for k, v in body.values.items():
            db.put_setting(c, k, str(v))
    db.audit(admin, "settings", ", ".join(f"{k}={v:g}" for k, v in body.values.items()))
    return {"ok": True}


@app.post("/admin/api/alerts/{alert_id}/resolve")
def admin_resolve_alert(alert_id: int, admin: str = Depends(security.require_admin)):
    with db.tx() as c:
        c.execute("UPDATE alerts SET resolved_at=? WHERE id=? AND resolved_at IS NULL",
                  (now_local().isoformat(timespec="seconds"), alert_id))
    return {"ok": True}


@app.get("/admin/api/report.xlsx")
def admin_report(month: str, admin: str = Depends(security.require_admin)):
    try:
        year, mon = map(int, month.split("-"))
        assert 2020 <= year <= 2100 and 1 <= mon <= 12
    except Exception:
        raise HTTPException(status_code=400, detail="month=YYYY-MM")
    db.audit(admin, "report", month)
    return RawResponse(report.build(year, mon),
                       media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       headers={"Content-Disposition": f'attachment; filename="karta-{year:04d}-{mon:02d}.xlsx"'})


@app.get("/admin/api/report-year.xlsx")
def admin_report_year(year: int, admin: str = Depends(security.require_admin)):
    if not 2020 <= year <= 2100:
        raise HTTPException(status_code=400, detail="year=YYYY")
    db.audit(admin, "report_year", str(year))
    return RawResponse(report.build_year(year),
                       media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       headers={"Content-Disposition": f'attachment; filename="karta-{year:04d}.xlsx"'})


@app.get("/admin/api/punches.xlsx")
def admin_punch_archive(year: int, admin: str = Depends(security.require_admin)):
    """«Αρχείο χτυπημάτων ΕΕΕΕ»: every punch of the year, for the archive (kept for years) and for an inspection."""
    if not 2020 <= year <= 2100:
        raise HTTPException(status_code=400, detail="year=YYYY")
    db.audit(admin, "punch_archive", str(year))
    return RawResponse(archive.build(year),
                       media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       headers={"Content-Disposition": f'attachment; filename="karta-xtypimata-{year:04d}.xlsx"'})


@app.get("/admin/api/backup.db")
def admin_backup_download(admin: str = Depends(security.require_admin)):
    """A consistent copy of the whole database, taken while Karta runs (SQLite online backup)."""
    import sqlite3
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        path = f"{tmp}/karta.db"
        dst = sqlite3.connect(path)
        try:
            with db._lock:
                db._conn.backup(dst)
        finally:
            dst.close()
        data = open(path, "rb").read()
    db.audit(admin, "backup_download", f"{len(data)} bytes")
    return RawResponse(data, media_type="application/vnd.sqlite3",
                       headers={"Content-Disposition": f'attachment; filename="karta-{now_local():%Y-%m-%d}.db"'})


# ---- cloud backups and restore («Ρυθμίσεις» → «Αντίγραφα ασφαλείας»)
class CloudIn(BaseModel):
    provider: str = Field(pattern="^(drive|dropbox|b2)$")
    token: str = Field(default="", max_length=8000)
    account: str = Field(default="", max_length=200)
    key: str = Field(default="", max_length=200)
    bucket: str = Field(default="", max_length=60)
    password: str | None = Field(default=None, max_length=200)   # the password of existing backups (restore)


class CloudJob:
    """One slow step with the cloud (or Ergani), run in the background: POST starts it (start), GET reports how it is going
    (view): {state: running | done | fail | idle, seconds, result, error}. Asking again for the same thing while it
    runs (a reloaded page) keeps waiting for it; something else is refused until it ends. idle = never started, or
    Karta restarted meanwhile."""

    def __init__(self, busy: str):
        self.busy = busy
        self.lock = threading.Lock()
        self.st = {"state": "idle", "key": None, "error": "", "result": None, "started": None}

    def start(self, key, fn) -> dict:
        with self.lock:
            if self.st["state"] == "running":
                if self.st["key"] == key:
                    return {"state": "running"}
                raise HTTPException(status_code=409, detail=self.busy)
            self.st.update(state="running", key=key, error="", result=None, started=time.monotonic())

        def run():
            try:
                self.st.update(state="done", result=fn())
            except (cloud.CloudError, restore.RestoreError, erganiread.ErganiReadError) as e:
                self.st.update(state="fail", error=str(e))
            except Exception as e:
                log.exception("cloud job failed")
                self.st.update(state="fail", error=f"Απρόσμενο σφάλμα: {e}")
        threading.Thread(target=run, daemon=True).start()
        return {"state": "running"}

    def view(self, once: bool = False) -> dict:
        """once: the result is handed over a single time (the new encryption password), then forgotten."""
        with self.lock:
            st = {k: v for k, v in self.st.items() if k not in ("key", "started")}
            st["seconds"] = int(time.monotonic() - self.st["started"]) if self.st["started"] else 0
            if once and st["state"] in ("done", "fail"):
                self.st.update(state="idle", key=None, error="", result=None, started=None)
        return st


def _connect(body: "CloudIn", admin: str) -> dict:
    pw = cloud.connect(body.provider, token=body.token.strip(), account=body.account, key=body.key,
                       bucket=body.bucket.strip(), password=(body.password or "").strip() or None)
    db.audit(admin, "cloud_connect", body.provider + (" (existing backups)" if pw is None else ""))
    st = cloud.status() or {}
    return {"password": pw, "first_backup": st.get("state"), "error": st.get("error", ""), "empty": cloud.empty()}


_connect_job = CloudJob("Μια σύνδεση με το cloud γίνεται ήδη· περιμένετε να τελειώσει.")
_list_job = CloudJob("Η λίστα των αντιγράφων φορτώνει ήδη.")


@app.post("/admin/api/cloud/connect")
def admin_cloud_connect(body: CloudIn, admin: str = Depends(security.require_admin)):
    """Connecting (a new repository, or the existing backups on a new machine) in the background: GET tells how it
    went, and hands over the new encryption password once."""
    if body.provider in ("drive", "dropbox"):              # a malformed access code is refused right away
        try:
            tok = json.loads(body.token.strip())
            assert isinstance(tok, dict) and (tok.get("access_token") or tok.get("refresh_token"))
        except (ValueError, AssertionError):
            raise HTTPException(status_code=400, detail="Ο κωδικός πρόσβασης δεν μοιάζει σωστός: αντιγράψτε όλο το κείμενο από το { έως το }.")
    return _connect_job.start(body.provider, lambda: _connect(body, admin))


@app.get("/admin/api/cloud/connect")
def admin_cloud_connect_state(admin: str = Depends(security.require_admin)):
    return _connect_job.view(once=True)


@app.post("/admin/api/cloud/password")
def admin_cloud_password(admin: str = Depends(security.require_admin)):
    """Shows the encryption password again while this machine works. Not a new risk: an admin can already download
    the whole database; the cloud copy is what protects it when the machine is gone."""
    pw = cloud.password()
    if pw is None:
        raise HTTPException(status_code=409, detail="Το cloud δεν έχει ρυθμιστεί.")
    db.audit(admin, "cloud_password_viewed")
    return {"password": pw}


@app.post("/admin/api/cloud/disconnect")
def admin_cloud_disconnect(admin: str = Depends(security.require_admin)):
    cloud.disconnect()
    db.audit(admin, "cloud_disconnect")
    return {"ok": True}


@app.post("/admin/api/cloud/run")
def admin_cloud_run(admin: str = Depends(security.require_admin)):
    """Uploads a copy now, in the background (the page shows the result when it is done)."""
    if not cloud.connected():
        raise HTTPException(status_code=409, detail="Το cloud δεν έχει ρυθμιστεί.")

    def run():
        try:
            cloud.run_backup()
        except Exception:
            pass
    threading.Thread(target=run, daemon=True).start()
    db.audit(admin, "cloud_run")
    return {"ok": True}


@app.post("/admin/api/cloud/backups")
def admin_cloud_backups(admin: str = Depends(security.require_admin)):
    """The list of backups in the cloud, in the background: GET returns it (result) when it is ready."""
    return _list_job.start("list", cloud.list_backups)


@app.get("/admin/api/cloud/backups")
def admin_cloud_backups_state(admin: str = Depends(security.require_admin)):
    return _list_job.view()


MAX_RESTORE_BYTES = 500_000_000


@app.post("/admin/api/restore/upload")
async def admin_restore_upload(request: Request, admin: str = Depends(security.require_admin)):
    """Step 1 (from a file): the backup is kept aside and checked; nothing is replaced yet."""
    tmp = restore.staged_path() + ".part"
    size = 0
    try:
        with open(tmp, "wb") as f:
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_RESTORE_BYTES:
                    raise HTTPException(status_code=413, detail="Το αρχείο είναι πολύ μεγάλο για αντίγραφο της Karta.")
                f.write(chunk)
        restore.stage_key(None)                           # a file brings no key of its own
        info = restore.stage_file(tmp)
    except restore.RestoreError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    db.audit(admin, "restore_staged", f"upload {size} bytes")
    return info


class RestoreCloudIn(BaseModel):
    id: str = Field(max_length=64)


# Step 1 (from the cloud) runs in the background, like every slow step with the cloud (connecting, the list of backups):
# reaching Google Drive can take longer than a page request may last (Cloudflare gives up after 100 seconds), so the
# page starts it and asks how it is going every few seconds.
def _fetch_from_cloud(snapshot_id: str, admin: str) -> dict:
    tmp = restore.staged_path() + ".part"
    try:
        key = cloud.download(snapshot_id, tmp)
        restore.stage_key(key)                              # before the check: it reports whether the key fits
        info = restore.stage_file(tmp)
        db.audit(admin, "restore_staged", f"cloud {snapshot_id}")
        return info
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


_fetch_job = CloudJob("Ένα άλλο αντίγραφο κατεβαίνει ήδη· περιμένετε να τελειώσει.")


@app.post("/admin/api/restore/cloud")
def admin_restore_cloud(body: RestoreCloudIn, admin: str = Depends(security.require_admin)):
    """Step 1 (from the cloud): starts downloading the chosen copy; GET says when it is downloaded and checked."""
    if not cloud.SNAPSHOT_ID.match(body.id or ""):
        raise HTTPException(status_code=400, detail="Μη έγκυρο αντίγραφο.")
    return _fetch_job.start(body.id, lambda: _fetch_from_cloud(body.id, admin))


@app.get("/admin/api/restore/cloud")
def admin_restore_cloud_state(admin: str = Depends(security.require_admin)):
    return _fetch_job.view()


@app.get("/admin/api/restore/pending")
def admin_restore_pending(admin: str = Depends(security.require_admin)):
    try:
        return restore.inspect()
    except restore.RestoreError as e:
        raise HTTPException(status_code=404, detail=str(e))


class RestoreApplyIn(BaseModel):
    confirm: bool = False


@app.post("/admin/api/restore/apply")
def admin_restore_apply(body: RestoreApplyIn, admin: str = Depends(security.require_admin)):
    """Step 2: the current database is kept as before-restore-….db, and the backup takes its place."""
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Χρειάζεται επιβεβαίωση.")

    try:
        kept = restore.apply(_prepare_db)
    except restore.RestoreError as e:
        raise HTTPException(status_code=400, detail=str(e))
    db.audit(admin, "restore", f"previous database kept as {kept}")
    log.warning("Database restored from a backup by %s (previous one kept as %s)", admin, kept)
    return {"ok": True, "kept": kept}


@app.post("/admin/api/restore/discard")
def admin_restore_discard(admin: str = Depends(security.require_admin)):
    restore.discard()
    return {"ok": True}


@app.post("/admin/api/salon-hours")
def admin_salon_hours(body: ScheduleIn, admin: str = Depends(security.require_admin)):
    """Opening hours of the shop: a reference/template for employee schedules (not sent to Ergani)."""
    clean = {}
    for wd, text in body.days.items():
        if wd not in {str(i) for i in range(7)}:
            raise HTTPException(status_code=400, detail="Μη έγκυρη ημέρα")
        try:
            span = hours.parse_span(text)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"{hours.WEEKDAYS[int(wd)]}: γράψε π.χ. 10:00-21:00 ή κενό αν είναι κλειστά")
        if span:
            clean[wd] = "+".join(f"{a}-{b}" for a, b in span.segments)
    with db.tx() as c:
        db.put_setting(c, "salon_hours", json.dumps(clean))
    db.audit(admin, "salon_hours", json.dumps(clean))
    return {"ok": True}


# ------------------------------------------------------------------ Ergani import (read-only queries)
# «Έλεγχος ΕΡΓΑΝΗ» in the background: the staff list and up to 14 days of the declared digital organisation
# (EX_BASE_08) can take longer than a page request may last. It also updates the stored schedule facts.
_review_job = CloudJob("Ο έλεγχος ΕΡΓΑΝΗ τρέχει ήδη.")


@app.post("/admin/api/ergani/review")
def admin_ergani_review(admin: str = Depends(security.require_admin)):
    return _review_job.start("review", lambda: {**erganiread.review(admin), "mode": config.ERGANI_MODE})


@app.get("/admin/api/ergani/review")
def admin_ergani_review_state(admin: str = Depends(security.require_admin)):
    return _review_job.view()


class ImportItem(BaseModel):
    afm: str = Field(max_length=9)
    display_name: str = Field(default="", max_length=40)


class ImportIn(BaseModel):
    people: list[ImportItem] = Field(max_length=100)


@app.post("/admin/api/ergani/import")
def admin_ergani_import(body: ImportIn, admin: str = Depends(security.require_admin)):
    try:
        created = erganiread.apply([i.model_dump() for i in body.people], admin)
    except erganiread.ErganiReadError as e:
        log.warning("Ergani read failed: %s", e)
        raise HTTPException(status_code=424, detail=str(e))
    return {"ok": True, "created": created}


class MonthIn(BaseModel):
    month: str = Field(pattern=r"^20\d\d-(0[1-9]|1[0-2])$")


@app.get("/admin/api/ergani/month")
def admin_ergani_month(month: str, admin: str = Depends(security.require_admin)):
    """«Έλεγχος μήνα με ΕΡΓΑΝΗ»: the stored result for a month (differences) and the running check, if any."""
    import re
    if not re.fullmatch(r"20\d\d-(0[1-9]|1[0-2])", month or ""):
        raise HTTPException(status_code=400, detail="month=YYYY-MM")
    return erganicheck.summary(month)


@app.post("/admin/api/ergani/month")
def admin_ergani_month_start(body: MonthIn, admin: str = Depends(security.require_admin)):
    """Read the month's declared organisation (EX_BASE_08) and actual work (EX_BASE_07) from Ergani, in the
    background. Read-only: nothing is sent."""
    try:
        return erganicheck.start(body.month, admin)
    except erganiread.ErganiReadError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.get("/admin/api/ergani/services")
def admin_ergani_services(admin: str = Depends(security.require_admin)):
    try:
        return {"services": erganiread.services()}
    except erganiread.ErganiReadError as e:
        log.warning("Ergani read failed: %s", e)
        raise HTTPException(status_code=424, detail=str(e))
