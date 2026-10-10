"""«Έλεγχος μήνα με ΕΡΓΑΝΗ»: compares a closed month in Karta with what Ergani itself holds.

Ergani gives, per branch and date and only for the previous month and earlier:
  EX_BASE_08 — the declared digital organisation (hours, break, leave) of every employee;
  EX_BASE_07 — the actual work it recorded from the card punches.
The month is read in the background (two calls per day, about a minute), stored in `ergani_month` and compared with
Karta: the declared hours against Karta's schedule, leave against Karta's leave, and every punch Karta sent against
Ergani's record. Nothing is ever sent to Ergani from here. The result shows in «Αναφορές» and as the sheet
«Έλεγχος ΕΡΓΑΝΗ» of the monthly report.
"""
import json
import logging
import threading
from datetime import date, datetime, timedelta

from . import config, db, erganiread, hours
from .timeutil import now_local

log = logging.getLogger("karta.erganicheck")

_lock = threading.Lock()
_state: dict = {}          # the running / last check: {month, state, done, total, error, started}


def month_days(month: str) -> list[date]:
    y, m = map(int, month.split("-"))
    first = date(y, m, 1)
    nxt = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
    return [first + timedelta(days=k) for k in range((nxt - first).days)]


def can_check(month: str, today: date) -> str | None:
    """None if Ergani gives this month today, else why not (in Greek)."""
    days = month_days(month)
    if days[-1] > erganiread.readable_until(today):
        return erganiread.NOT_YET.format(m=f"{days[0]:%m/%Y}", d=f"{erganiread.first_available(days[-1]):%d/%m/%Y}")
    return None


def status() -> dict:
    with _lock:
        return dict(_state)


def start(month: str, admin: str) -> dict:
    """Read `month` from Ergani in the background. One check at a time."""
    why = can_check(month, now_local().date())
    if why:
        raise erganiread.ErganiReadError(why)
    with _lock:
        if _state.get("state") == "running":
            raise erganiread.ErganiReadError(f"Τρέχει ήδη έλεγχος για {_state['month']} — περίμενε να τελειώσει.")
        days = month_days(month)
        _state.clear()
        _state.update(month=month, state="running", done=0, total=len(days), error=None,
                      started=now_local().isoformat(timespec="seconds"))
    db.audit(admin, "ergani_month_check", month)
    threading.Thread(target=_run, args=(month,), daemon=True, name="ergani-month").start()
    return status()


def _run(month: str) -> None:
    declared, actual = {}, {}
    try:
        for d in month_days(month):
            declared[d.isoformat()] = erganiread.declared_day(d)
            actual[d.isoformat()] = erganiread.actual_day(d)
            with _lock:
                _state["done"] += 1
        with db.tx() as c:
            c.execute("INSERT INTO ergani_month(month, fetched_at, declared, actual) VALUES (?,?,?,?) "
                      "ON CONFLICT(month) DO UPDATE SET fetched_at=excluded.fetched_at, declared=excluded.declared, "
                      "actual=excluded.actual",
                      (month, now_local().isoformat(timespec="seconds"),
                       json.dumps(declared, ensure_ascii=False), json.dumps(actual, ensure_ascii=False)))
        with _lock:
            _state["state"] = "done"
    except Exception as e:      # ErganiReadError carries a readable Greek message; anything else is unexpected
        if not isinstance(e, erganiread.ErganiReadError):
            log.exception("ergani month check failed")
        with _lock:
            _state.update(state="error", error=str(e))


def stored(month: str):
    """{fetched_at, declared, actual} for a month already read, or None."""
    r = db.one("SELECT * FROM ergani_month WHERE month=?", (month,))
    if r is None:
        return None
    return {"fetched_at": r["fetched_at"], "declared": json.loads(r["declared"]), "actual": json.loads(r["actual"])}


# ---------------------------------------------------------------- the comparison
def _karta_day(eid: int, d: date) -> dict:
    """What Karta has for one person and day: {blocks, break_min, break_out, leave, closed}."""
    off = hours.day_off(eid, d)
    sched = hours.schedule_for(eid, d)
    blocks = [(f"{a:%H:%M}", f"{b:%H:%M}") for a, b in sched.segments] if sched else []
    return {"blocks": blocks, "break_min": sched.break_min if sched else 0, "break_out": bool(sched and sched.break_out),
            "leave": off["label"] if off and off["kind"] == "leave" else None,
            "closed": off["label"] if off and off["kind"] in ("holiday", "closure") else None}


def _fmt_blocks(blocks, break_min, break_out) -> str:
    if not blocks:
        return "ρεπό"
    t = " + ".join(f"{a}–{b}" for a, b in blocks)
    return t + (f" · διάλ. {break_min}′ {'εκτός' if break_out else 'εντός'}" if break_min else "")


def _sent_pairs(eid: int, d: date) -> list[tuple]:
    """The arrival–departure pairs Karta sent to Ergani that day (punches kept only in Karta are not compared)."""
    rows = [r for r in hours.day_movements(eid, d) if r["status"] == "submitted"]
    out = []
    for a, b in hours.intervals(rows):
        out.append((f"{a:%H:%M}", f"{b:%H:%M}" if b else None))
    return out


def compare(month: str, data: dict | None = None) -> list[dict]:
    """Differences between Karta and Ergani for a month already read: [{date, afm, employee_id, name, what, karta,
    ergani}], in date order. `what` is one of: schedule, leave, punch_missing, punch_extra, unknown_person."""
    data = data or stored(month)
    if data is None:
        return []
    emps = {e["afm"]: e for e in db.all_rows("SELECT id, afm, last_name, first_name, created_at FROM employees")}
    out: list[dict] = []
    unknown: set = set()

    def add(d, e, afm, what, karta, ergani):
        out.append({"date": d.isoformat(), "afm": afm, "employee_id": e["id"] if e else None,
                    "name": f"{e['last_name']} {e['first_name']}" if e else f"ΑΦΜ …{afm[-3:]}",
                    "what": what, "karta": karta, "ergani": ergani})

    for d in month_days(month):
        drows = data["declared"].get(d.isoformat()) or []
        arows = data["actual"].get(d.isoformat()) or []
        by_afm: dict = {}
        for r in drows:
            by_afm.setdefault(r["afm"], {"decl": [], "act": []})["decl"].append(r)
        for r in arows:
            by_afm.setdefault(r["afm"], {"decl": [], "act": []})["act"].append(r)
        for e in emps.values():         # people in Karta with punches that day but nothing in Ergani
            if e["afm"] not in by_afm and _sent_pairs(e["id"], d):
                by_afm[e["afm"]] = {"decl": [], "act": []}
        if drows:                        # Ergani has the day's organisation: Karta hours with nothing declared?
            for e in emps.values():
                if e["afm"] in by_afm or e["afm"] == config.EMPLOYER_AFM or d.isoformat() < (e["created_at"] or "")[:10]:
                    continue
                k = _karta_day(e["id"], d)
                if k["blocks"] and not k["leave"] and not k["closed"]:
                    add(d, e, e["afm"], "schedule", _fmt_blocks(k["blocks"], k["break_min"], k["break_out"]),
                        "τίποτα δηλωμένο")
        for afm, g in sorted(by_afm.items()):
            e = emps.get(afm)
            if e is None:
                if afm != config.EMPLOYER_AFM and afm not in unknown:
                    unknown.add(afm)
                    add(d, None, afm, "unknown_person", "δεν υπάρχει στην Karta", "υπάρχει στο ΕΡΓΑΝΗ")
                continue
            if d.isoformat() < (e["created_at"] or "")[:10]:
                continue
            k = _karta_day(e["id"], d)
            decl = g["decl"]
            # --- declared hours / break
            if decl:
                types = {r["type"] for r in decl}
                work = sorted((r["start"], r["end"]) for r in decl if r["type"] in erganiread.WORK_TYPES and r["start"])
                leave_t = next((t for t in types if erganiread.is_leave(t)), None)
                if leave_t and not k["leave"]:
                    add(d, e, afm, "leave", k["closed"] or _fmt_blocks(k["blocks"], k["break_min"], k["break_out"]),
                        erganiread.type_name(leave_t))
                elif k["leave"] and not leave_t:
                    add(d, e, afm, "leave", k["leave"],
                        _fmt_blocks(work, decl[0]["break_min"], decl[0]["break_in"] is False) if work
                        else erganiread.type_name(next(iter(types))))
                elif not leave_t and not k["leave"]:
                    kb = [] if k["closed"] else k["blocks"]
                    ebreak = next((r["break_min"] for r in decl if r["type"] in erganiread.WORK_TYPES), None) or 0
                    eout = next((r["break_in"] is False for r in decl if r["type"] in erganiread.WORK_TYPES), False)
                    same_blocks = [tuple(b) for b in kb] == [tuple(b) for b in work]
                    same_break = not work or (ebreak == (k["break_min"] or 0) and (not ebreak or eout == k["break_out"]))
                    if not (same_blocks and same_break):
                        add(d, e, afm, "schedule",
                            k["closed"] or _fmt_blocks(kb, k["break_min"], k["break_out"]),
                            _fmt_blocks(work, ebreak, eout) if work else erganiread.type_name(next(iter(types))))
            # --- punches: what Karta sent vs what Ergani recorded
            sent = _sent_pairs(e["id"], d)
            rec = [(r["start"], r["end"]) for r in g["act"] if r["start"]]
            for p in sent:
                if p not in rec:
                    add(d, e, afm, "punch_missing", f"{p[0]}–{p[1] or '…'}",
                        ", ".join(f"{a}–{b or '…'}" for a, b in rec) or "τίποτα")
            for p in rec:
                if p not in sent:
                    add(d, e, afm, "punch_extra", ", ".join(f"{a}–{b or '…'}" for a, b in sent) or "τίποτα",
                        f"{p[0]}–{p[1] or '…'}")
    return out


WHAT = {
    "schedule": ("Ωράριο διαφορετικό από το ΕΡΓΑΝΗ",
                 "Διόρθωσε το ωράριο στην Karta («Ωράρια») ή ζήτα από τον λογιστή να διορθώσει τη δήλωση στο ΕΡΓΑΝΗ."),
    "leave": ("Άδεια μόνο στη μία πλευρά",
              "Καταχώρησε την άδεια στην Karta («Άδεια…») ή ζήτα από τον λογιστή να τη δηλώσει / διορθώσει στο ΕΡΓΑΝΗ."),
    "punch_missing": ("Χτύπημα που στάλθηκε αλλά δεν υπάρχει στο ΕΡΓΑΝΗ",
                      "Έλεγξε την κίνηση στην Karta («Κινήσεις», πρωτόκολλο) και στο ΕΡΓΑΝΗ· αν λείπει, δήλωσέ την με τον λογιστή."),
    "punch_extra": ("Απασχόληση στο ΕΡΓΑΝΗ που δεν βγαίνει από την Karta",
                    "Ίσως χτύπημα από άλλη συσκευή/εφαρμογή ή διόρθωση στο ΕΡΓΑΝΗ — έλεγξέ το με τον λογιστή."),
    "unknown_person": ("Εργαζόμενος στο ΕΡΓΑΝΗ που δεν είναι στην Karta",
                       "«Ρυθμίσεις» → ΕΡΓΑΝΗ → «Έλεγχος ΕΡΓΑΝΗ» για εισαγωγή, αν δουλεύει στο κατάστημα."),
}


def summary(month: str) -> dict:
    """For the admin page: the stored check (if any), its differences and the running state."""
    data = stored(month)
    diffs = compare(month, data) if data else []
    today = now_local().date()
    return {"month": month, "checked_at": data["fetched_at"] if data else None,
            "available": can_check(month, today) is None, "why_not": can_check(month, today),
            "diffs": [{**x, "title": WHAT[x["what"]][0], "todo": WHAT[x["what"]][1]} for x in diffs],
            "running": status()}
