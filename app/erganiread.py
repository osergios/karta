"""Read-only Ergani queries (employer, branches, current workforce) for the admin import.

Data minimisation: EX_BASE_05 returns the full employee record (ID documents, pay,
family details...). Only the fields below are ever kept, returned or stored; the raw
payload is discarded here and never logged."""
import json
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

from ergani.client import ErganiClient
from ergani.exceptions import APIError, AuthenticationError

from . import config, db
from .timeutil import now_local


class ErganiReadError(Exception):
    pass


# Cloudflare drops a request after 100 seconds (error 524). Reads from Ergani give up well
# before that, so the admin always gets a clear answer instead.
READ_DEADLINE = 60
_reader = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ergani-read")
SLOW = ("Το ΕΡΓΑΝΗ δεν απάντησε μέσα σε {s} δευτερόλεπτα. Συμβαίνει όταν είναι φορτωμένο· "
        "δοκίμασε ξανά σε λίγα λεπτά.")


def _within_deadline(fn):
    fut = _reader.submit(fn)
    try:
        return fut.result(timeout=READ_DEADLINE)
    except FutureTimeout:
        raise ErganiReadError(SLOW.format(s=READ_DEADLINE))


def _client() -> ErganiClient:
    if not (config.ERGANI_USERNAME and config.ERGANI_PASSWORD and config.ERGANI_BASE_URL):
        raise ErganiReadError("Λείπουν ERGANI_USERNAME / ERGANI_PASSWORD / ERGANI_BASE_URL στο .env.")
    return ErganiClient(config.ERGANI_USERNAME, config.ERGANI_PASSWORD, base_url=config.ERGANI_BASE_URL)


def _txt(v):
    if v is None:
        return None
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    s = str(v).strip()
    return s or None


def suggest_display_name(first_name: str) -> str:
    """ΠΟΛΥΞΕΝΗ -> Πολυξενη (accents can't be recovered; the admin edits it)."""
    word = (first_name or "").strip().split()[0] if (first_name or "").strip() else ""
    return word[:1] + word[1:].lower()


def _norm(s: str | None) -> str:
    """Compare names ignoring case, accents and extra spaces."""
    s = unicodedata.normalize("NFD", (s or "").strip().upper())
    return " ".join("".join(ch for ch in s if unicodedata.category(ch) != "Mn").split())


def fetch() -> dict:
    """Everything the admin needs to review, with Ergani's personal data reduced to the minimum."""
    def read():
        c = _client()
        return c.get_employer_details(), c.get_branch_details(), c.get_current_workforce()

    try:
        emp, branches, workforce = _within_deadline(read)
    except ErganiReadError:
        raise
    except AuthenticationError as e:
        raise ErganiReadError(f"Το ΕΡΓΑΝΗ απέρριψε τα στοιχεία σύνδεσης ({e}). "
                              "Έλεγξε όνομα χρήστη/κωδικό και ότι είναι για το σωστό περιβάλλον (παραγωγή ή trial).")
    except APIError as e:
        raise ErganiReadError(f"Σφάλμα ΕΡΓΑΝΗ: {e}")
    except Exception as e:  # network, timeouts, unexpected payloads
        raise ErganiReadError(f"Δεν ήταν δυνατή η επικοινωνία με το ΕΡΓΑΝΗ ({type(e).__name__}: {e})")

    # keep the employer's official name for the monthly report (reference only)
    name = _txt(emp.name) or _txt(emp.distinctive_title)
    if name and (emp.employer_tax_identification_number or "") == config.EMPLOYER_AFM:
        try:
            with db.tx() as tx:
                db.put_setting(tx, "employer_name", name)
        except Exception:
            pass
    people = []
    for w in workforce:
        afm = _txt(w.employee_tax_identification_number)
        if not afm:
            continue
        people.append({
            "afm": afm,
            "last_name": _txt(w.employee_last_name) or "",
            "first_name": _txt(w.employee_first_name) or "",
            "branch": w.branch_number,
            "schedule": _txt(w.working_schedule),
            "weekly_hours": _txt(w.weekly_hours),
            "break_minutes": w.break_minutes,
            "break_within": _txt(w.break_within_schedule),
            "working_card": _txt(w.working_card),
            "week_days": _txt(w.weekly_workdays),
            "employment": _txt(w.employment_status),
            "arrangement": _txt(w.working_time_arrangement),
            "digital_org": _txt(w.working_time_digital_organization),
            "flex_arrival": _txt(w.flexible_working_hours),     # «EueliktoWrario», shown for reference only
        })
    return {
        "employer": {
            "name": _txt(emp.name) or _txt(emp.distinctive_title),
            "afm_matches": (emp.employer_tax_identification_number or "") == config.EMPLOYER_AFM,
            "in_card_sector": emp.is_in_card_sector,
        },
        "branches": [{"number": b.branch_number, "address": _txt(b.address), "status": _txt(b.status_description)}
                     for b in branches],
        "configured_branch": config.BRANCH_NUMBER,
        "people": people,
    }


def review() -> dict:
    """Ergani data compared with the app's employees."""
    data = fetch()
    app = {r["afm"]: r for r in db.all_rows("SELECT id, afm, last_name, first_name, display_name, active FROM employees")}
    ergani_afms = set()
    for p in data["people"]:
        ergani_afms.add(p["afm"])
        p["in_branch"] = p["branch"] == config.BRANCH_NUMBER
        p["facts"] = facts(p)
        a = app.get(p["afm"])
        if a is None:
            p["status"] = "new"
            p["suggested_name"] = suggest_display_name(p["first_name"])
        else:
            p["employee_id"] = a["id"]
            p["display_name"] = a["display_name"]
            p["active"] = bool(a["active"])
            p["status"] = "match" if (a["last_name"], a["first_name"]) == (p["last_name"], p["first_name"]) else "name_differs"
            p["app_name"] = f'{a["last_name"]} {a["first_name"]}'
            p["close_match"] = _norm(p["app_name"]) == _norm(f'{p["last_name"]} {p["first_name"]}')
    data["not_in_ergani"] = [
        {"employee_id": a["id"], "display_name": a["display_name"], "afm_tail": a["afm"][-3:],
         "is_employer": a["afm"] == config.EMPLOYER_AFM}
        for afm, a in app.items() if a["active"] and afm not in ergani_afms]
    return data


def apply(selected: list[dict], admin: str) -> list[dict]:
    """Create new employees / align names with Ergani. Names always come from Ergani itself,
    never from the browser. Returns one-time PINs for created employees."""
    from . import security
    data = fetch()
    by_afm = {p["afm"]: p for p in data["people"]}
    now = now_local().isoformat(timespec="seconds")
    created, updated = [], []
    for item in selected:
        p = by_afm.get(str(item.get("afm", "")))
        if p is None:
            raise ErganiReadError("Ένας εργαζόμενος δεν βρέθηκε πια στο ΕΡΓΑΝΗ — ξανακάνε έλεγχο.")
        existing = db.one("SELECT id FROM employees WHERE afm=?", (p["afm"],))
        with db.tx() as c:
            if existing is None:
                display = (str(item.get("display_name") or "").strip() or suggest_display_name(p["first_name"]))[:40]
                pin = security.generate_pin()
                cur = c.execute(
                    "INSERT INTO employees(afm, last_name, first_name, display_name, pin_hash, pin_enc, created_at) VALUES (?,?,?,?,?,?,?)",
                    (p["afm"], p["last_name"], p["first_name"], display, security.hash_pin(pin), security.seal_pin(pin), db.utc_now_iso()))
                eid = cur.lastrowid
                created.append({"name": display, "pin": pin})
            else:
                eid = existing["id"]
                c.execute("UPDATE employees SET last_name=?, first_name=? WHERE id=?", (p["last_name"], p["first_name"], eid))
                updated.append(eid)
            store_info(c, eid, p, now)
    db.audit(admin, "ergani_import", f"created={len(created)} updated={len(updated)}")
    return created


INFO_COLS = ("schedule", "weekly_hours", "break_minutes", "break_within", "working_card",
             "week_days", "employment", "arrangement", "digital_org", "flex_arrival")


def store_info(c, employee_id: int, p: dict, now: str) -> None:
    cols = ", ".join(INFO_COLS)
    c.execute(f"INSERT INTO ergani_info(employee_id, {cols}, fetched_at) VALUES (?{', ?' * len(INFO_COLS)}, ?) "
              f"ON CONFLICT(employee_id) DO UPDATE SET " + ", ".join(f"{k}=excluded.{k}" for k in INFO_COLS) +
              ", fetched_at=excluded.fetched_at",
              (employee_id, *[p.get(k) for k in INFO_COLS], now))


def refresh_info(admin: str) -> int:
    """Re-read Ergani and update the stored schedule facts of employees already in the app, with the hours last
    declared in the digital organisation (EX_BASE_08) when Ergani gives them."""
    data = fetch()
    weeks = declared_recent_weeks()
    now = now_local().isoformat(timespec="seconds")
    n = 0
    with db.tx() as c:
        for p in data["people"]:
            row = c.execute("SELECT id FROM employees WHERE afm=?", (p["afm"],)).fetchone()
            if row:
                store_info(c, row["id"], p, now); n += 1
                w = weeks.get(p["afm"])
                if w:
                    c.execute("INSERT INTO ergani_week(employee_id, declared_week, fetched_at) VALUES (?,?,?) "
                              "ON CONFLICT(employee_id) DO UPDATE SET declared_week=excluded.declared_week, "
                              "fetched_at=excluded.fetched_at", (row["id"], json.dumps(w, ensure_ascii=False), now))
    db.audit(admin, "ergani_refresh", f"employees={n}")
    return n


# ---------- turning Ergani's schedule facts into something the admin can use ----------
_DAYS = [("ΔΕΥ", 0), ("ΤΡΙ", 1), ("ΤΕΤ", 2), ("ΠΕΜ", 3), ("ΠΑΡ", 4), ("ΣΑΒ", 5), ("ΚΥΡ", 6)]


def _yes(v) -> bool | None:
    t = _norm(v)
    if t.startswith("ΝΑΙ"):
        return True
    if t.startswith("ΟΧΙ"):
        return False
    return None


def _int_prefix(v) -> int | None:
    import re
    m = re.match(r"\s*(\d+)", str(v or ""))
    return int(m.group(1)) if m else None


def _day_set(spec: str) -> set[int] | None:
    """'ΔΕΥ-ΠΑΡ', 'ΔΕΥΤΕΡΑ ΕΩΣ ΠΑΡΑΣΚΕΥΗ', 'ΤΡΙ, ΠΕΜ & ΣΑΒ' -> weekday numbers (Monday=0)."""
    import re
    t = _norm(spec)
    hits = [(m.start(), d) for key, d in _DAYS for m in re.finditer(key, t)]
    hits.sort()
    if not hits:
        return None
    days: set[int] = set()
    for i, (pos, d) in enumerate(hits):
        days.add(d)
        if i + 1 < len(hits):
            between = t[pos:hits[i + 1][0]]
            if re.search(r"-|–|ΕΩΣ|ΜΕΧΡΙ", between[3:]):
                a, b = d, hits[i + 1][1]
                days.update(range(a, b + 1) if a <= b else list(range(a, 7)) + list(range(0, b + 1)))
    return days


def parse_schedule_text(text: str | None) -> dict | None:
    """Best effort for employers whose Ergani schedule is free text (not the digital organisation).
    Returns {weekday: 'HH:MM-HH:MM'} or None when it can't be read unambiguously."""
    import re
    if not text or "ΨΗΦΙΑΚΗ" in _norm(text):
        return None
    t = _norm(text)
    rx = re.compile(r"(\d{1,2})[:.](\d{2})\s*(?:-|–|ΕΩΣ|ΜΕΧΡΙ)\s*(\d{1,2})[:.](\d{2})")
    out: dict[int, str] = {}
    prev_end = 0
    for m in rx.finditer(t):
        days = _day_set(t[prev_end:m.start()])
        prev_end = m.end()
        h1, m1, h2, m2 = map(int, m.groups())
        if not days or not (h1 < 24 and h2 < 24 and m1 < 60 and m2 < 60) or (h2, m2) <= (h1, m1):
            return None
        for d in days:
            seg = f"{h1:02d}:{m1:02d}-{h2:02d}:{m2:02d}"
            out[d] = f"{out[d]}+{seg}" if d in out else seg   # second block the same day = split shift
    from .hours import parse_span
    try:
        for v in out.values():
            parse_span(v)    # ordered, non-overlapping, at most 3 parts
    except ValueError:
        return None
    return {str(k): v for k, v in sorted(out.items())} or None


def _week(info: dict) -> dict:
    try:
        w = json.loads(info.get("declared_week") or "null")
    except ValueError:
        return {}
    return w if isinstance(w, dict) and isinstance(w.get("proposal"), dict) else {}


def facts(info: dict) -> dict:
    """Normalised, UI-ready view of what Ergani says for one employee."""
    return {
        "weekly_hours": float(str(info.get("weekly_hours")).replace(",", ".")) if info.get("weekly_hours") not in (None, "") else None,
        "week_days": _int_prefix(info.get("week_days")),
        "full_time": (lambda v: None if not v else "ΠΛΗΡ" in _norm(v))(info.get("employment")),
        "break_minutes": info.get("break_minutes"),
        "break_within": _yes(info.get("break_within")),
        "arrangement": _yes(info.get("arrangement")),
        "digital": _yes(info.get("digital_org")) is True or "ΨΗΦΙΑΚΗ" in _norm(info.get("schedule")),
        "proposal": parse_schedule_text(info.get("schedule")) or _week(info).get("proposal"),
        # where the hours came from when they are the digital schedule last declared (EX_BASE_08)
        "proposal_week": (lambda w: {"from": w["from"], "to": w["to"]} if w.get("proposal") and not
                          parse_schedule_text(info.get("schedule")) else None)(_week(info)),
        # what Ergani reports as flexible hours (minutes when it is a plain number); set in the app by hand
        "flex_text": info.get("flex_arrival"),
        "flex": (lambda n: n if n is not None and 0 <= n <= 120 and str(info.get("flex_arrival")).strip().isdigit()
                 else None)(_int_prefix(info.get("flex_arrival"))),
        "schedule_text": info.get("schedule"),
        "fetched_at": info.get("fetched_at"),
    }


def services() -> list[dict]:
    """The services Ergani offers this employer (metadata only, no personal data)."""
    try:
        resp = _within_deadline(lambda: _client().get_services_list())
        payload = resp.json() if resp is not None else []
    except ErganiReadError:
        raise
    except AuthenticationError as e:
        raise ErganiReadError(f"Το ΕΡΓΑΝΗ απέρριψε τα στοιχεία σύνδεσης ({e}).")
    except Exception as e:
        raise ErganiReadError(f"Δεν ήταν δυνατή η ανάγνωση της λίστας υπηρεσιών ({type(e).__name__}: {e})")
    found: list[dict] = []

    def walk(x):
        if isinstance(x, dict):
            keys = {k.lower(): k for k in x}
            code = next((x[keys[k]] for k in keys if "code" in k or k in ("name", "servicename")), None)
            desc = next((x[keys[k]] for k in keys if "descr" in k or "title" in k or "perigrafi" in k), None)
            if isinstance(code, str) and code.strip():
                params = next((x[keys[k]] for k in keys if "param" in k), None)
                names = []
                if isinstance(params, list):
                    for pr in params:
                        if isinstance(pr, dict):
                            names.append(str(next(iter(pr.values()), "")))
                found.append({"code": code.strip(), "description": str(desc or "").strip(), "parameters": names[:10]})
                return          # a service: its parameters ({"name": "afm", …}) are not services themselves
            for v in x.values():
                if isinstance(v, (dict, list)):
                    walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(payload)
    seen, unique = set(), []
    for f in found:
        if f["code"] not in seen:
            seen.add(f["code"]); unique.append(f)
    return unique[:300]


# ---------- EX_BASE_08 (declared digital schedule) and EX_BASE_07 (actual work log) ----------
# Ergani answers both only for dates of the PREVIOUS month and earlier («Περιορισμός σε ημ/νιες προηγούμενου
# μήνα και πίσω»), one date and one branch per call. The reply shapes below are the real ones (production
# account, 30/09/2026), not the field names guessed in the unmerged SDK branches:
#   {"EX_BASE_08": {"Working": [{"aa": "0", "Afm": "…", "Date": "30/09/2026", "Type": "ΕΡΓ",
#                                "HourFrom": "10:00:00", "HourTo": "14:00:00", "Extra": null,
#                                "BreakMinutes": "20", "BreakInWork": "0"}, …]}}     (one row per block of a split shift)
#   {"EX_BASE_07": {"RealWorking": [{"Aa", "Afm", "Date", "HourFrom", "HourTo", "IsEndDateDifferentThanDate"}]}}
#   null when there is nothing for that date.
# Only these fields are kept (data minimisation), never names or anything else Ergani might add.
NOT_YET = ("Το ΕΡΓΑΝΗ δίνει αυτά τα στοιχεία μόνο για τον προηγούμενο μήνα και πιο πίσω — "
           "για {m} θα είναι διαθέσιμα από {d}.")
WORK_TYPES = {"ΕΡΓ", "ΤΗΛ"}          # working (in the shop / remote); everything else = no work that day
REST_TYPES = {"ΑΝ", "ΜΕ"}            # ανάπαυση/ρεπό, μη εργασία
TYPE_NAMES = {"ΕΡΓ": "Εργασία", "ΤΗΛ": "Τηλεργασία", "ΑΝ": "Ανάπαυση / ρεπό", "ΜΕ": "Μη εργασία",
              "ΑΔΚΑΝ": "Κανονική άδεια", "ΑΔΑΑ": "Άδεια άνευ αποδοχών", "ΑΔΓΑΜ": "Άδεια γάμου",
              "ΑΔΑΙΜ": "Αιμοδοτική άδεια", "ΑΔΕΞ": "Άδεια εξετάσεων", "ΑΔΜΗ": "Άδεια μητρότητας",
              "ΑΔΠΑ": "Άδεια πατρότητας", "ΑΔΦΠ": "Άδεια φροντίδας παιδιού", "ΑΔΓΟΝ": "Γονική άδεια",
              "ΑΔΦΡΟ": "Άδεια φροντιστή", "ΑΔΑΠΑΒ": "Απουσία λόγω ανωτέρας βίας"}


def type_name(code: str | None) -> str:
    c = (code or "").strip().upper()
    return TYPE_NAMES.get(c) or ("Άδεια" + (f" ({c})" if c else "") if c.startswith("ΑΔ") else (c or "—"))


def is_leave(code: str | None) -> bool:
    return (code or "").strip().upper().startswith("ΑΔ")


def first_available(day):
    """The first date on which Ergani answers for `day`: the 1st of the following month (from then on `day`'s month
    is «the previous month»)."""
    from datetime import date as _d
    y, m = (day.year + 1, 1) if day.month == 12 else (day.year, day.month + 1)
    return _d(y, m, 1)


def readable_until(today):
    """The last date Ergani gives these data for, today: the last day of the previous month."""
    from datetime import timedelta
    return today.replace(day=1) - timedelta(days=1)


def _rows(payload, key: str) -> list:
    """The list under `key` (any case, any depth); [] for null / nothing."""
    if isinstance(payload, dict):
        for k, v in payload.items():
            if k.lower() == key.lower() and isinstance(v, list):
                return v
        for v in payload.values():
            r = _rows(v, key)
            if r:
                return r
    elif isinstance(payload, list):
        for v in payload:
            r = _rows(v, key)
            if r:
                return r
    return []


def _hhmm(v) -> str | None:
    import re
    m = re.match(r"\s*(\d{1,2}):(\d{2})", str(v or ""))
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else None


def _day_query(code: str, key: str, day) -> list[dict]:
    """One EX_BASE_07/08 call for the configured branch and `day`; the raw rows (still unfiltered)."""
    if day > readable_until(now_local().date()):
        raise ErganiReadError(NOT_YET.format(m=f"{day:%m/%Y}", d=f"{first_available(day):%d/%m/%Y}"))
    try:
        resp = _within_deadline(lambda: _client()._execute_service(
            code, {"PararthmaAa": str(config.BRANCH_NUMBER), "Date": f"{day:%d/%m/%Y}"}))
        payload = resp.json() if resp is not None and (resp.text or "").strip() else None
    except ErganiReadError:
        raise
    except AuthenticationError as e:
        raise ErganiReadError(f"Το ΕΡΓΑΝΗ απέρριψε τα στοιχεία σύνδεσης ({e}).")
    except APIError as e:
        if "criteria" in str(e).lower():
            raise ErganiReadError(NOT_YET.format(m=f"{day:%m/%Y}", d=f"{first_available(day):%d/%m/%Y}"))
        raise ErganiReadError(f"Σφάλμα ΕΡΓΑΝΗ ({code}, {day:%d/%m/%Y}): {e}")
    except Exception as e:
        raise ErganiReadError(f"Δεν ήταν δυνατή η ανάγνωση {code} για {day:%d/%m/%Y} ({type(e).__name__}: {e})")
    return [r for r in _rows(payload, key) if isinstance(r, dict)]


def declared_day(day) -> list[dict]:
    """EX_BASE_08 for `day`: [{afm, type, start, end, break_min, break_in}] (one row per block)."""
    out = []
    for r in _day_query("EX_BASE_08", "Working", day):
        afm = str(r.get("Afm") or r.get("afm") or "").strip()
        if not afm:
            continue
        bm = _int_prefix(r.get("BreakMinutes"))
        bi = str(r.get("BreakInWork") if r.get("BreakInWork") is not None else "").strip()
        out.append({"afm": afm, "type": str(r.get("Type") or "").strip().upper(),
                    "start": _hhmm(r.get("HourFrom")), "end": _hhmm(r.get("HourTo")),
                    "break_min": bm, "break_in": True if bi == "1" else False if bi == "0" else None})
    return out


def actual_day(day) -> list[dict]:
    """EX_BASE_07 for `day`: [{afm, start, end, next_day}] — the work Ergani recorded from the card."""
    out = []
    for r in _day_query("EX_BASE_07", "RealWorking", day):
        afm = str(r.get("Afm") or r.get("afm") or "").strip()
        if not afm:
            continue
        out.append({"afm": afm, "start": _hhmm(r.get("HourFrom")), "end": _hhmm(r.get("HourTo")),
                    "next_day": str(r.get("IsEndDateDifferentThanDate") or "0").strip() == "1"})
    return out


def week_from_declared(days: dict) -> dict:
    """{afm: {"proposal": {weekday: 'HH:MM-HH:MM+…'}, "from": iso, "to": iso}} from EX_BASE_08 rows of several
    dates ({date: rows}). Per weekday the latest date where the person worked or was off wins; a leave day says
    nothing about the usual schedule and is skipped."""
    out: dict = {}
    for d in sorted(days, reverse=True):
        by_afm: dict = {}
        for r in days[d]:
            by_afm.setdefault(r["afm"], []).append(r)
        for afm, rows in by_afm.items():
            types = {r["type"] for r in rows}
            if any(is_leave(t) for t in types) or not types <= (WORK_TYPES | REST_TYPES):
                continue
            w = out.setdefault(afm, {"proposal": {}, "from": d.isoformat(), "to": d.isoformat()})
            key = str(d.weekday())
            if key in w["proposal"]:
                continue
            blocks = sorted((r["start"], r["end"]) for r in rows if r["type"] in WORK_TYPES and r["start"] and r["end"])
            w["proposal"][key] = "+".join(f"{a}-{b}" for a, b in blocks)
            w["from"] = min(w["from"], d.isoformat())
    return out


def declared_recent_weeks() -> dict:
    """The schedule last declared in Ergani's digital organisation, per employee (see week_from_declared), read from
    the last 14 days Ergani gives. {} when this account has no EX_BASE_08 or it fails: it is only a convenience."""
    import time
    from datetime import timedelta
    end = readable_until(now_local().date())
    days, t0 = {}, time.monotonic()
    for k in range(14):
        d = end - timedelta(days=k)
        if time.monotonic() - t0 > 150:     # runs in the background («Ενημέρωση…»); a slow Ergani still has an end
            break
        try:
            days[d] = declared_day(d)
        except ErganiReadError:
            return {}
    return week_from_declared(days)
