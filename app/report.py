"""Monthly Excel for the accountant.

Concise by design: official names (as in Ergani), hours per day against the declared schedule rounded to the
quarter hour, and only the deviations that need a decision (extra/less hours, work outside the declared hours,
forgotten punches, days without punches, anything not yet in Ergani). Exact punch times are not listed on
normal days; on a day that deviates the actual hours are shown (to 5 minutes) so the accountant can file the
retrospective declaration (απολογιστική δήλωση) or pay the extra hours.
"""
import io
import re
from calendar import monthrange
from datetime import date, datetime, timedelta

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from . import config, db, hours, onboarding
from .timeutil import now_local

MONTHS = ["Ιανουάριος", "Φεβρουάριος", "Μάρτιος", "Απρίλιος", "Μάιος", "Ιούνιος", "Ιούλιος", "Αύγουστος",
          "Σεπτέμβριος", "Οκτώβριος", "Νοέμβριος", "Δεκέμβριος"]

TEAL = "16897B"
HEAD = Font(bold=True, color="FFFFFF")
HEAD_FILL = PatternFill("solid", fgColor=TEAL)
WARN_FILL = PatternFill("solid", fgColor="FBEEDD")
INFO_FILL = PatternFill("solid", fgColor="EEF6F4")
OFF_FONT = Font(color="8A8A8A")
TITLE = Font(bold=True, size=14)
BOLD = Font(bold=True)
THIN = Border(bottom=Side(style="thin", color="D9D2C5"))
H_FMT = '0.00;-0.00;""'          # hours; zero shows empty

STATUS = {"submitted": "Υποβλήθηκε", "dry_run": "Δοκιμή", "pending": "σε αναμονή αποστολής", "failed": "απέτυχε η αποστολή",
          "uncertain": "προς έλεγχο", "local": "μόνο στην κάρτα",
          "onboarding": "δοκιμή"}
LATE = {"POWER_OUTAGE": "001 Διακοπή ρεύματος",
        "EMPLOYER_SYSTEMS_UNAVAILABLE": "002 Πρόβλημα στα συστήματα του εργοδότη",
        "ERGANI_SYSTEMS_UNAVAILABLE": "003 Πρόβλημα στα συστήματα του ΕΡΓΑΝΗ"}

_BAD_TITLE = re.compile(r"[\[\]:*?/\\]")


def _sheet_title(name: str, used: set) -> str:
    r"""Excel sheet names: max 31 chars, none of []:*?/\, not starting/ending with ', unique (case-insensitive)."""
    base = _BAD_TITLE.sub("-", name or "").strip().strip("'").strip() or "Εργαζόμενος"
    base = base[:28]
    title, n = base, 2
    while title.casefold() in used:
        suffix = f" {n}"
        title = base[:31 - len(suffix)] + suffix
        n += 1
    used.add(title.casefold())
    return title


PREP_MIN = 10   # «χρόνος προετοιμασίας» (εγκύκλιος 26606/13-10-2025 §3): up to 10′ after the end, not working time


def _m(t: datetime) -> datetime:
    return t.replace(second=0, microsecond=0)


def _matches(eff, ints) -> bool:
    """Do the punched intervals match the declared (flexible-arrival moved) schedule exactly, to the minute?"""
    segs = eff.segments
    return len(ints) == len(segs) and all(
        a == s0 and s1 <= b <= (eff.leave_by if k == len(segs) - 1 else s1)
        for k, ((a, b), (s0, s1)) in enumerate(zip(ints, segs)))


def _hm(m: float) -> str:
    m = int(round(abs(m)))
    return f"{m // 60}:{m % 60:02d}"


def _sched_text(sched) -> str:
    if not sched:
        return "Ρεπό"
    t = " + ".join(f"{a:%H:%M}–{b:%H:%M}" for a, b in sched.segments)
    return t + ((f" · διάλ. {sched.break_min}′ εκτός (έως {sched.leave_by:%H:%M})" if sched.break_out
                 else f" · διάλ. {sched.break_min}′") if sched.break_min else "") + (
        f" · ευέλικτη προσέλευση {sched.flex}′" if sched.flex else "")


def _official(e) -> str:
    return f"{e['last_name']} {e['first_name']}".strip()


def _employer_line() -> str:
    name = db.setting("employer_name") or ""
    parts = [name, f"ΑΦΜ {config.EMPLOYER_AFM}", f"Παράρτημα {config.BRANCH_NUMBER}"]
    return "Εργοδότης: " + " · ".join(p for p in parts if p)


def _day(e, d: date, today: date, now: datetime) -> dict:
    """Everything the report needs about one employee-day."""
    rows = hours.day_movements(e["id"], d)
    reg = hours.schedule_for(e["id"], d, regular=True)     # the usual weekly schedule
    change = hours.day_change(e["id"], d)                  # one-day change declared in Ergani (overtime, other hours, off)
    sched = hours.schedule_for(e["id"], d)                 # what was declared for that day
    off = hours.day_off(e["id"], d)
    leave = off if off and off["kind"] == "leave" else None
    mark = hours.early_leave_mark(e["id"], d) if rows else None      # «Έφυγε νωρίτερα» (sickness...)
    leave_after = None
    if leave and mark:            # left sick and the leave was entered from that same day: a worked (part) day
        leave_after, leave = leave, None
    shut = off if off and off["kind"] in ("holiday", "closure") else None
    spans = [(_m(a), _m(b) if b else None) for a, b in hours.intervals(rows)]    # whole minutes, as Ergani counts
    closed = [(a, b) for a, b in spans if b]
    open_ = any(b is None for _, b in spans)
    work_min = hours.net_worked(sum((b - a).total_seconds() for a, b in closed), sched) / 60
    sched_min = 0.0 if (leave or shut) else hours.scheduled_seconds(sched) / 60
    reg_min = hours.scheduled_seconds(reg) / 60
    out = {"date": d, "sched": sched, "leave": leave, "mark": mark, "shut": shut if reg else None, "rows": rows,
           "sched_h": sched_min / 60, "work_h": None, "ot_h": 0.0, "change": change,
           "diff_h": 0.0, "actual": "", "notes": [], "issues": [], "worked": bool(rows),
           "show": bool(rows or (sched and not (shut and not reg)) or (change and reg))}
    running = open_ and d == today
    if not out["show"]:
        return out          # day off (a leave / holiday on a day off is not a leave / holiday day)
    if change is not None:
        was = f" (κανονικό: {_sched_text(reg)})" if reg else " (κανονικά ρεπό)"
        out["notes"].append({"overtime": "Δηλωμένη υπερωρία", "change": "Αλλαγή ωραρίου ημέρας",
                             "off": "Ρεπό (αλλαγή ημέρας)"}[change["kind"]] + was
                            + (f" — {change['note']}" if change["note"] else ""))
        holiday = hours.closure_on(d)
        if change["text"] and holiday:
            out["notes"].append(f"Εργασία σε ημέρα που το κατάστημα είναι κλειστό ({holiday['label']})")
            if holiday["kind"] == "holiday":
                out["issues"].append((f"Εργασία σε αργία ({holiday['reason']}), δηλωμένη",
                                      "Προσαύξηση εργασίας σε αργία — έλεγχος λογιστή"))
    if shut:
        out["notes"].append(shut["label"])
        if rows:
            out["issues"].append((f"Εργασία ενώ το κατάστημα ήταν κλειστό ({shut['label']}) χωρίς δηλωμένο ωράριο",
                                  "Εργασία χωρίς δηλωμένο ωράριο — έλεγχος λογιστή (δήλωση/πληρωμή)"))
    if leave_after:
        out["notes"].append(f"{leave_after['label']} μετά την αποχώρηση")
    if leave:
        out["notes"].append(leave["label"])
        if rows:
            out["issues"].append(("Εργασία σε ημέρα άδειας", "Έλεγχος: διόρθωση της άδειας ή του ωραρίου"))
    if running:
        out["notes"].append("Σε βάρδια τώρα")
        out["actual"] = " + ".join(f"{a:%H:%M}–{f'{b:%H:%M}' if b else '…'}" for a, b in spans)
    elif rows:
        actual = " + ".join(f"{a:%H:%M}–{f'{b:%H:%M}' if b else '…'}" for a, b in spans)
        if open_:
            out["issues"].append(("Προσέλευση χωρίς αποχώρηση",
                                  "Κλείσιμο στη διαχείριση («Ξέχασε να χτυπήσει» — μόνο στην κάρτα)"))
        if sched and not leave and not shut:
            first, last = spans[0][0], (closed[-1][1] if closed else None)
            # flexible arrival (ευέλικτη προσέλευση): arriving within the agreed window after the declared start
            # moves the whole day; the punches are compared with that moved day
            eff = hours.effective_schedule(e["id"], sched)
            if eff.start != sched.start:
                late = first - sched.arrive_by
                out["notes"].append(f"Ευέλικτη προσέλευση: {first:%H:%M} (+{_hm((eff.start - sched.start).total_seconds() / 60)}"
                                    f" από τις {sched.start:%H:%M}) → λήξη {eff.leave_by:%H:%M}"
                                    + (f" · καθυστέρηση {_hm(late.total_seconds() / 60)} μετά το τέλος του περιθωρίου"
                                       if late > timedelta(0) else ""))
            # punch-out up to 10′ after the limit: preparation time (changing etc.), not working time — the hours
            # stay as declared; it is shown, softly, because the punch should have been made at the end
            # punch-out up to 10′ after the limit = preparation time, not working time (εγκύκλιος 26606/2025 §3):
            # inside the limits, so the day counts as «όπως το ωράριο» and nothing is flagged
            if not open_ and last is not None and timedelta(0) < last - eff.leave_by <= timedelta(minutes=PREP_MIN):
                closed = closed[:-1] + [(closed[-1][0], eff.leave_by)]
                last = eff.leave_by
                work_min = hours.net_worked(sum((b - a).total_seconds() for a, b in closed), sched) / 60
            # no tolerance: «όπως το ωράριο» only when every punch is exactly inside the declared (moved) hours;
            # a break «εκτός ωραρίου» lets the punch-out fall anywhere between the end and end + break
            if not open_ and _matches(eff, closed):
                out["work_h"] = sched_min / 60
                out["actual"] = "όπως το ωράριο"
            else:
                out["work_h"] = round(work_min) / 60
                out["diff_h"] = 0.0 if open_ else (round(work_min) - round(sched_min)) / 60
                out["actual"] = actual
                if open_:
                    pass
                elif out["diff_h"] > 0:
                    out["issues"].append((f"Εργασία πέραν του δηλωμένου ωραρίου +{_hm(out['diff_h'] * 60)} ({actual})"
                                          + ("" if config.RETRO else ", χωρίς δήλωση υπερωρίας"),
                                          "Απολογιστική δήλωση έως το τέλος του επόμενου μήνα (φύλλο «Απολογιστικές "
                                          "δηλώσεις») και πληρωμή των ωρών — λογιστής" if config.RETRO else
                                          "Μη δηλωμένη υπερωρία: πληρωμή των ωρών — έλεγχος λογιστή"))
                elif out["diff_h"] < 0 and mark:
                    why = hours.EARLY_REASONS.get(mark["reason"], mark["reason"]) + (f": {mark['note']}" if mark["note"] else "")
                    out["issues"].append((f"Αποχώρηση νωρίτερα — {why} (−{_hm(-out['diff_h'] * 60)}, {actual})",
                                          "Απολογιστική δήλωση ωραρίου με τις πραγματικές ώρες (φύλλο «Απολογιστικές "
                                          "δηλώσεις») · πληρωμή της ημέρας: λογιστής"))
                elif out["diff_h"] < 0:
                    out["issues"].append((f"Λιγότερες ώρες −{_hm(-out['diff_h'] * 60)} ({actual})",
                                          "Ενημερωτικό (π.χ. αποχώρησε νωρίτερα ή ήρθε αργότερα). Αν έφυγε λόγω "
                                          "ασθένειας: «Έφυγε νωρίτερα…» στη διαχείριση"))
                elif first < eff.start or (last is not None and last > eff.leave_by):
                    out["issues"].append((f"Εργασία εκτός των δηλωμένων ωρών ({actual})",
                                          "Απολογιστική δήλωση έως το τέλος του επόμενου μήνα (φύλλο «Απολογιστικές "
                                          "δηλώσεις»)" if config.RETRO else
                                          "Εργασία εκτός δηλωμένου ωραρίου: η αλλαγή έπρεπε να δηλωθεί στο ΕΡΓΑΝΗ πριν — έλεγχος λογιστή"))
                else:
                    out["issues"].append((f"Καθυστέρηση ή νωρίτερη αποχώρηση ({actual})",
                                          "Ενημερωτικό (οι ώρες βγήκαν όσες το ωράριο)"))
        elif not leave:
            out["work_h"] = round(work_min) / 60
            out["diff_h"] = 0.0 if open_ else out["work_h"]
            out["actual"] = actual
            if not shut:
                out["issues"].append((f"Εργασία χωρίς δηλωμένο ωράριο ({actual})",
                                      "Εργασία χωρίς δηλωμένο ωράριο — έλεγχος λογιστή (δήλωση/πληρωμή)"))
    elif sched and not leave and not shut:
        if d < today or now >= sched.leave_by:
            out["work_h"] = 0.0
            out["diff_h"] = -sched_min / 60
            out["issues"].append(("Χωρίς κινήσεις ενώ είχε ωράριο",
                                  "Απουσία; δήλωση άδειας/ρεπό — έλεγχος λογιστή"))
    if change is not None and change["text"] and out["work_h"] is not None:
        # declared extra hours actually worked: beyond the usual schedule, up to what was declared for the day
        out["ot_h"] = max(0.0, min(out["work_h"], sched_min / 60) - reg_min / 60)
    for r in rows:
        t = r["movement_at"][11:16]
        what = "προσέλευση" if r["type"] == "ARRIVAL" else "αποχώρηση"
        if r["status"] == "local":
            out["issues"].append((f"Ξεχασμένη {what} {t} (καταχωρήθηκε μόνο στην κάρτα"
                                  + (f": {r['note']}" if r["note"] else "") + ")",
                                  "Παράλειψη στο ΕΡΓΑΝΗ — ενημερωτικό (ανεκτές έως 3 τον μήνα)"))
        elif r["status"] in ("pending", "failed", "uncertain"):
            out["issues"].append((f"{what.capitalize()} {t}: {STATUS[r['status']]} στο ΕΡΓΑΝΗ",
                                  "Έλεγχος στη διαχείριση («Κινήσεις»)"))
        if r["late_justification"]:
            code = LATE.get(r["late_justification"], r["late_justification"])
            if r["late_justification"] == "ERGANI_SYSTEMS_UNAVAILABLE":
                out["notes"].append(f"Εκπρόθεσμη {what} {t}: {code}")
            else:
                out["issues"].append((f"Εκπρόθεσμη {what} {t} ({code})",
                                      "Κράτα αποδεικτικά του προβλήματος και το email προς την Επιθεώρηση"))
    return out


def _info(ws, lines, ncols: int, widths):
    """Title/notes above a table: merged across the table width and wrapped, so they never widen the print."""
    total = sum(widths[:ncols])
    for i, t in enumerate(lines, 1):
        c = ws.cell(i, 1, t)
        c.font = TITLE if i == 1 else Font(color="555555", italic=i >= 4)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        ws.merge_cells(start_row=i, start_column=1, end_row=i, end_column=ncols)
        ws.row_dimensions[i].height = 20 if i == 1 else 15 * max(1, -(-len(t) // int(total * 1.1)))


def _table_header(ws, row: int, cols):
    for i, v in enumerate(cols, 1):
        c = ws.cell(row, i, v)
        c.font, c.fill = HEAD, HEAD_FILL
        c.alignment = Alignment(vertical="center", wrap_text=True)
    ws.row_dimensions[row].height = 30


def _widths(ws, widths):
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w


def _print_setup(ws, header_row: int):
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = f"{header_row}:{header_row}"
    ws.freeze_panes = ws.cell(header_row + 1, 1)


# per-employee counters (summary, yearly «Ανά μήνα»): headings and values in the same order
COUNT_HEADS = ["Ημέρες εργασίας", "Ώρες ωραρίου", "Ώρες εργασίας", "Δηλωμένες επιπλέον ώρες (υπερωρία)",
               "Επιπλέον ώρες χωρίς δήλωση", "Λιγότερες ώρες", "Κανονική άδεια (ημέρες)", "Άδεια ασθενείας (ημέρες)",
               "Άδεια ειδικού σκοπού (ημέρες)", "Αργίες / κλειστό (ημέρες)", "Ξεχασμένα χτυπήματα"]
H_COLS = (2, 3, 4, 5, 6)      # 1-based positions inside COUNT_HEADS that are hours
PLUS_COL = 5


def _zero() -> dict:
    return {"days": 0, "sched": 0.0, "work": 0.0, "ot": 0.0, "plus": 0.0, "minus": 0.0,
            "regular": 0, "sick": 0, "special": 0, "shut": 0, "omit": 0}


def _add(acc: dict, x: dict) -> None:
    acc["days"] += 1 if x["worked"] else 0
    acc["sched"] += x["sched_h"]
    acc["work"] += x["work_h"] or 0.0
    acc["ot"] += x["ot_h"]
    acc["plus"] += max(x["diff_h"], 0.0)
    acc["minus"] += max(-x["diff_h"], 0.0)
    if x["leave"]:
        acc[x["leave"]["leave_kind"] if x["leave"]["leave_kind"] in ("regular", "sick", "special") else "regular"] += 1
    acc["shut"] += 1 if x["shut"] else 0
    acc["omit"] += sum(1 for m in x["rows"] if m["status"] == "local")


def _counts(v: dict) -> list:
    return [v["days"], round(v["sched"], 2), round(v["work"], 2), round(v["ot"], 2), round(v["plus"], 2),
            round(v["minus"], 2), v["regular"], v["sick"], v["special"], v["shut"], v["omit"]]


def _end_of_next_month(d: date) -> date:
    y, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return date(y, m, monthrange(y, m)[1])


def _retro(e, x: dict, today: date, now: datetime):
    """A day whose punches do not match the declared schedule to the minute (the ministry gives no tolerance):
    what to declare afterwards in Ergani (απολογιστική δήλωση ωραρίου), or None when the day matches.
    Same rule as the ministry's example: 09:00–17:00, punched 08:13–16:19 → declare 08:13–16:13 (the declared
    length from the actual arrival); time beyond it is shown apart (υπερεργασία / υπερωρία: Ε8)."""
    rows = x["rows"]
    if not rows or all(r["status"] == onboarding.STATUS for r in rows):
        return None                                        # nothing reached Ergani (onboarding period)
    spans = hours.intervals(rows)
    if any(b is None for _, b in spans):
        return None                                        # forgotten punch-out: close it in admin first
    ints = [(_m(a), _m(b)) for a, b in spans]
    punched = " + ".join(f"{a:%H:%M}–{b:%H:%M}" for a, b in ints)
    d = x["date"]
    res = {"date": d, "punched": punched, "extra": "", "deadline": _end_of_next_month(d)}
    sched = None if (x["leave"] or x["shut"]) else x["sched"]
    if sched is None:
        why = ("Εργασία σε ημέρα άδειας" if x["leave"] else "Εργασία ενώ το κατάστημα ήταν κλειστό" if x["shut"]
               else "Εργασία χωρίς δηλωμένο ωράριο")
        return {**res, "declared": _declared(x), "declare": punched, "why": why}
    eff = hours.effective_schedule(e["id"], sched)
    if d == today and (sched.split and now < eff.leave_by):
        return None                                        # a split day still running
    segs = eff.segments
    prep = timedelta(0) < ints[-1][1] - eff.leave_by <= timedelta(minutes=PREP_MIN)
    if prep:   # punch-out within the 10′ preparation time: same hours as declared, nothing to declare for it
        ints = ints[:-1] + [(ints[-1][0], eff.leave_by)]
    if _matches(eff, ints):
        return None
    a0, bl = ints[0][0], ints[-1][1]
    why = []
    if a0 < sched.start:
        why.append(f"Προσέλευση πριν την έναρξη ({a0:%H:%M} αντί {sched.start:%H:%M})")
    elif a0 > eff.start:
        why.append(f"Προσέλευση μετά το περιθώριο ευέλικτης προσέλευσης ({a0:%H:%M}, έως {sched.arrive_by:%H:%M})"
                   if sched.flex else f"Καθυστέρηση ({a0:%H:%M} αντί {sched.start:%H:%M})")
    if bl < eff.end:
        m = x.get("mark")
        why.append(f"Αποχώρηση νωρίτερα ({bl:%H:%M} αντί {eff.end:%H:%M})"
                   + (f" — {hours.EARLY_REASONS.get(m['reason'], m['reason'])}" + (f": {m['note']}" if m["note"] else "")
                      if m else ""))
    elif bl > eff.leave_by:
        why.append(f"Αποχώρηση αργότερα ({bl:%H:%M}, έως {eff.leave_by:%H:%M})")
    if len(ints) != len(segs):
        why.append(f"{len(ints)} διαστήματα εργασίας αντί {len(segs)}")
    if not why:
        why.append("Οι ώρες των σκελών διαφέρουν από το ωράριο")
    brk, out_ = sched.break_min, sched.break_out
    btxt = lambda: f" · διάλ. {brk}′ {'εκτός' if out_ else 'εντός'} ωραρίου" if brk else ""
    if not sched.split and len(ints) == 1:
        span = eff.end - eff.start                         # declared length (a break «εκτός» is outside it)
        full_end = a0 + span
        if bl >= full_end:
            declare = f"{a0:%H:%M}–{full_end:%H:%M}" + btxt()
            over = bl - full_end - (timedelta(minutes=brk) if out_ else timedelta(0))
            if over > timedelta(minutes=PREP_MIN):    # up to 10′ = preparation time, not work (as the ministry's example)
                res["extra"] = f"+{_hm(over.total_seconds() / 60)} μετά τις {full_end + (timedelta(minutes=brk) if out_ else timedelta(0)):%H:%M}"
        else:
            worked = (bl - a0).total_seconds()
            keep = brk and not out_ and worked > hours.BREAK_AFTER_SECONDS and brk * 60 < worked
            declare = f"{a0:%H:%M}–{bl:%H:%M}" + (btxt() if keep else "")
    else:
        declare = punched + btxt()
    return {**res, "declared": _declared(x), "declare": declare, "why": "; ".join(why)}


def _declared(x: dict) -> str:
    """The «Δηλωμένο ωράριο» cell of a day."""
    if x["shut"]:
        return x["shut"]["label"]
    if x["leave"]:
        return x["leave"]["label"]
    ch = x["change"]
    if ch is not None:
        if not ch["text"]:
            return "Ρεπό (αλλαγή ημέρας)"
        return ("Υπερωρία: " if ch["kind"] == "overtime" else "Αλλαγή: ") + _sched_text(x["sched"])
    return _sched_text(x["sched"])


def build(year: int, month: int) -> bytes:
    """Monthly report."""
    return _build(date(year, month, 1), date(year, month, monthrange(year, month)[1]), f"{MONTHS[month - 1]} {year}", False)


def build_year(year: int) -> bytes:
    """Yearly report: the same sheets for the whole year, plus «Ανά μήνα» (each employee, month by month)."""
    return _build(date(year, 1, 1), date(year, 12, 31), f"Έτος {year}", True)


def _build(first: date, last_day: date, label: str, yearly: bool) -> bytes:
    now = now_local()
    today = now.date()
    days = [first + timedelta(days=k) for k in range((last_day - first).days + 1) if first + timedelta(days=k) <= today]
    period = f"{first:%d/%m/%Y} – {last_day:%d/%m/%Y}"
    if days and days[-1] < last_day:
        period += f" ({'έτος' if yearly else 'μήνας'} σε εξέλιξη: έως {days[-1]:%d/%m})"
    test = config.ERGANI_MODE != "production"
    first_iso, next_iso = first.isoformat(), (last_day + timedelta(days=1)).isoformat()
    emps = [e for e in db.all_rows("SELECT id, afm, last_name, first_name, active, created_at FROM employees "
                                   "ORDER BY last_name, first_name")
            if e["afm"] != config.EMPLOYER_AFM and (e["active"] or db.one(
                "SELECT 1 FROM movements WHERE employee_id=? AND mode=? AND movement_at>=? AND movement_at<? LIMIT 1",
                (e["id"], config.ERGANI_MODE, first_iso, next_iso)))]

    # the card counts from its first real movement (go-live): earlier days were tests, not "absences"
    g = db.one("SELECT MIN(movement_at) m FROM movements WHERE mode=?", (config.ERGANI_MODE,))
    golive = g["m"][:10] if g and g["m"] else (today + timedelta(days=1)).isoformat()

    wb = Workbook()
    summary = wb.active
    summary.title = "Σύνοψη"
    title = f"Κάρτα εργασίας — {label}" + (" — ΔΟΚΙΜΑΣΤΙΚΑ ΔΕΔΟΜΕΝΑ" if test else "")
    ob_s, ob_u = onboarding.since(), onboarding.until()
    ob = (f"Περίοδος προσαρμογής {ob_s:%d/%m/%Y} – {ob_u - timedelta(days=1):%d/%m/%Y}: «δοκιμή» = καταγράφηκε "
          f"στην κάρτα, δεν στάλθηκε στο ΕΡΓΑΝΗ (υποχρεωτική από {ob_u:%d/%m/%Y})."
          if ob_s and ob_u and ob_s <= last_day and ob_u > first and ob_s < ob_u else None)
    info = [title, _employer_line(), f"Περίοδος: {period}" + (f" · {ob}" if ob else ""),
            "Ώρες σε δεκαδικά (π.χ. 6,50 = 6 ώρες και 30′), ακριβείς στο λεπτό, μετά την αφαίρεση του διαλείμματος. "
            "Χωρίς ανοχή: «όπως το ωράριο» μόνο όταν τα χτυπήματα είναι ακριβώς μέσα στο δηλωμένο ωράριο (με την ευέλικτη "
            "προσέλευση και το διάλειμμα «εκτός ωραρίου»). Αποχώρηση έως 10′ μετά το όριο = χρόνος προετοιμασίας (όχι χρόνος "
            "εργασίας, εγκύκλιος 26606/2025): μετρά «όπως το ωράριο». Οι ακριβείς ώρες: φύλλο «Αναλυτικά».",
            f"Εκδόθηκε {now:%d/%m/%Y %H:%M} από την κάρτα εργασίας {config.PUBLIC_ORIGIN.split('://')[-1]}"]
    SUM_W = [20, 16, 12, 10, 10, 10, 11, 11, 10, 10, 10, 10, 10, 11, 11]
    NS = len(SUM_W)
    _info(summary, info, NS, SUM_W)

    SUM_ROW = len(info) + 2
    _table_header(summary, SUM_ROW, ["Επώνυμο", "Όνομα", "ΑΦΜ", *COUNT_HEADS, "Παρατηρήσεις (φύλλο «Αναλυτικά»)"])
    summary.row_dimensions[SUM_ROW].height = 45
    _widths(summary, SUM_W)

    retro = wb.create_sheet("Απολογιστικές δηλώσεις")
    RET_W = [24, 11, 30, 22, 30, 24, 46, 12]
    _info(retro, info[:3] + [
        "Ημέρες όπου τα χτυπήματα δεν ταιριάζουν ακριβώς (στο λεπτό) με το δηλωμένο ωράριο — το υπουργείο δεν δίνει ανοχή. "
        "Για καθεμία υποβάλλεται στο ΕΡΓΑΝΗ απολογιστική δήλωση ωραρίου με τις ώρες της στήλης «Δήλωση», έως την προθεσμία "
        "(τέλος του επόμενου μήνα). Όπως στο παράδειγμα του υπουργείου (37271/2024): ωράριο 09:00–17:00, χτυπήματα "
        "08:13–16:19 → δήλωση 08:13–16:13. Χρόνος πέραν αυτού («Επιπλέον») = υπερεργασία/υπερωρία: απολογιστικά και Ε8.",
        ("Η επιχείρηση έχει δηλώσει απολογιστικό σύστημα («Ρυθμίσεις» → «Επιχείρηση»). " if config.RETRO else
         "Η επιχείρηση δηλώνει με προαναγγελία («Ρυθμίσεις» → «Επιχείρηση»): οι αποκλίσεις εδώ έπρεπε να είχαν δηλωθεί "
         "πριν· δώσε τη λίστα στον λογιστή. ") +
        "Ευέλικτη προσέλευση μέσα στο περιθώριο, αποχώρηση μέσα στο διάλειμμα «εκτός ωραρίου» και έως 10′ μετά το όριο "
        "(χρόνος προετοιμασίας, όχι χρόνος εργασίας) δεν χρειάζονται δήλωση. "
        "Χτυπήματα της περιόδου προσαρμογής (δεν στάλθηκαν) δεν περιλαμβάνονται."], 8, RET_W)
    RR = 7
    _table_header(retro, RR, ["Εργαζόμενος", "Ημερομηνία", "Δηλωμένο ωράριο", "Χτυπήματα", "Δήλωση (απολογιστική)",
                              "Επιπλέον (Ε8;)", "Τι έγινε", "Προθεσμία"])
    _widths(retro, RET_W)
    retro_n = 0

    detail = wb.create_sheet("Αναλυτικά")
    DET_W = [24, 11, 12, 7, 24, 11, 15, 11, 15, 11, 11, 10, 58]
    _info(detail, info[:3] + ["Όλοι οι εργαζόμενοι, ανά ημέρα: οι ακριβείς ώρες προσέλευσης/αποχώρησης όπως στάλθηκαν στο ΕΡΓΑΝΗ, "
                              "με τον αριθμό πρωτοκόλλου. Μία γραμμή για κάθε ζεύγος προσέλευσης–αποχώρησης."], 13, DET_W)
    DR = 6
    _table_header(detail, DR, ["Εργαζόμενος", "ΑΦΜ", "Ημερομηνία", "Ημέρα", "Δηλωμένο ωράριο", "Προσέλευση",
                               "Πρωτόκολλο", "Αποχώρηση", "Πρωτόκολλο", "Ώρες ωραρίου", "Ώρες εργασίας", "Διαφορά",
                               "Παρατηρήσεις"])
    _widths(detail, DET_W)

    def proto(m):
        if m is None:
            return ""
        if m["status"] == "submitted":
            return m["protocol"] or "υποβλήθηκε"
        return {"local": "μόνο στην κάρτα", "onboarding": "δοκιμή", "pending": "σε αναμονή", "failed": "απέτυχε", "uncertain": "προς έλεγχο",
                "dry_run": "δοκιμή"}.get(m["status"], m["status"])

    def pairs(rows):
        out, cur = [], None
        for m in rows:
            if m["type"] == "ARRIVAL":
                if cur is not None:
                    out.append((cur, None))
                cur = m
            else:
                out.append((cur, m))
                cur = None
        if cur is not None:
            out.append((cur, None))
        return out or [(None, None)]

    per_month: dict = {}
    for e in emps:
        name = _official(e)
        tot = {**_zero(), "issues": 0}
        per_month[e["id"]] = {}
        since = max((e["created_at"] or "")[:10], golive)
        any_row = False
        for d in days:
            if d.isoformat() < since:
                continue    # before go-live or before the employee was added to the system
            x = _day(e, d, today, now)
            if not x["show"]:
                continue
            any_row = True
            notes = "; ".join(x["notes"] + [t for t, _ in x["issues"]])
            fill = WARN_FILL if x["issues"] else (INFO_FILL if (x["leave"] or x["shut"] or x["change"]) else None)
            for k, (a, b) in enumerate(pairs(x["rows"])):
                is1 = k == 0
                detail.append([name, e["afm"], d, hours.WEEKDAYS[d.weekday()],
                               _declared(x) if is1 else "",
                               a["movement_at"][11:19] if a else "", proto(a),
                               b["movement_at"][11:19] if b else "", proto(b),
                               (x["sched_h"] or None) if is1 else None, x["work_h"] if is1 else None,
                               (x["diff_h"] or None) if is1 else None, notes if is1 else ""])
                r = detail.max_row
                detail.cell(r, 3).number_format = "DD/MM/YYYY"
                for col in (10, 11, 12):
                    detail.cell(r, col).number_format = H_FMT
                for c in detail[r]:
                    c.border = THIN
                    c.alignment = Alignment(wrap_text=c.column == 13, vertical="top")
                    if fill:
                        c.fill = fill
            rt = _retro(e, x, today, now)
            if rt:
                retro_n += 1
                retro.append([name, d, rt["declared"], rt["punched"], rt["declare"], rt["extra"], rt["why"], rt["deadline"]])
                rr = retro.max_row
                retro.cell(rr, 2).number_format = retro.cell(rr, 8).number_format = "DD/MM/YYYY"
                for c in retro[rr]:
                    c.alignment = Alignment(wrap_text=True, vertical="top")
                    c.border = THIN
                if rt["extra"]:
                    retro.cell(rr, 6).fill = WARN_FILL
            pm = per_month[e["id"]].setdefault(d.month, _zero())
            for acc in (tot, pm):
                _add(acc, x)
            tot["issues"] += len(x["issues"])
        if any_row:   # subtotal per employee
            detail.append([f"Σύνολο {name}", "", "", "", "", "", "", "", "", round(tot["sched"], 2), round(tot["work"], 2),
                           round(tot["plus"] - tot["minus"], 2) or None,
                           (f"Δηλωμένες επιπλέον {tot['ot']:.2f} · Επιπλέον χωρίς δήλωση {tot['plus']:.2f} · "
                            f"Λιγότερες {tot['minus']:.2f}").replace(".", ",")])
            r = detail.max_row
            for c in detail[r]:
                c.font = BOLD
                c.fill = PatternFill("solid", fgColor="EFE9DF")
            for col in (10, 11, 12):
                detail.cell(r, col).number_format = H_FMT

        summary.append([e["last_name"], e["first_name"], e["afm"], *_counts(tot), tot["issues"]])
        sr = summary.max_row
        for col in H_COLS:
            summary.cell(sr, 3 + col).number_format = H_FMT
        for c in summary[sr]:
            c.border = THIN
        if tot["issues"]:
            summary.cell(sr, NS).fill = WARN_FILL
        if tot["plus"]:
            summary.cell(sr, 3 + PLUS_COL).fill = WARN_FILL
        if not yearly and tot["omit"] >= 3:
            summary.cell(sr, NS - 1).fill = WARN_FILL
    detail.auto_filter.ref = f"A{DR}:M{max(detail.max_row, DR + 1)}"
    _print_setup(detail, DR)

    if not retro_n:
        retro.cell(RR + 1, 1, "Καμία: όλες οι ημέρες ταιριάζουν ακριβώς με το δηλωμένο ωράριο.").font = OFF_FONT
    else:
        retro.auto_filter.ref = f"A{RR}:H{retro.max_row}"
    _print_setup(retro, RR)
    # ---- leave of the month, per employee (working days = days with a declared schedule)
    n = summary.max_row + 2
    summary.cell(n, 1, "Άδειες του έτους" if yearly else "Άδειες του μήνα").font = Font(bold=True, size=12)
    n += 1
    for i, v in enumerate(["Επώνυμο", "Όνομα", "Από", "Έως", "Εργάσιμες ημέρες", "Είδος άδειας", "Σημείωση"], 1):
        c = summary.cell(n, i, v)
        c.font, c.fill = HEAD, HEAD_FILL
    summary.merge_cells(start_row=n, start_column=7, end_row=n, end_column=NS)
    any_leave = False
    month_first, month_last = first, last_day
    for e in emps:
        rows_ = db.all_rows("SELECT start_date, end_date, note, kind FROM leaves WHERE employee_id=? AND start_date<=? "
                            "AND end_date>=? ORDER BY start_date", (e["id"], month_last.isoformat(), month_first.isoformat()))
        by_kind: dict = {}
        for lv in rows_:
            a = max(date.fromisoformat(lv["start_date"]), month_first)
            b = min(date.fromisoformat(lv["end_date"]), month_last)
            # working days: the usual schedule has hours and the shop is open (a holiday inside a leave is not leave)
            wd = sum(1 for k in range((b - a).days + 1)
                     if hours.schedule_for(e["id"], a + timedelta(days=k), regular=True)
                     and not hours.closure_on(a + timedelta(days=k)))
            kind = lv["kind"] or "regular"
            by_kind[kind] = by_kind.get(kind, 0) + wd
            n += 1
            any_leave = True
            summary.cell(n, 1, e["last_name"]); summary.cell(n, 2, e["first_name"])
            summary.cell(n, 3, a).number_format = "DD/MM/YYYY"
            summary.cell(n, 4, b).number_format = "DD/MM/YYYY"
            summary.cell(n, 5, wd)
            summary.cell(n, 6, hours.LEAVE_KINDS.get(kind, kind))
            summary.cell(n, 7, lv["note"] or "")
            summary.merge_cells(start_row=n, start_column=7, end_row=n, end_column=NS)
            for col in range(1, NS + 1):
                summary.cell(n, col).border = THIN
        if rows_:
            n += 1
            summary.cell(n, 1, f"Σύνολο {e['last_name']} {e['first_name']}").font = BOLD
            c = summary.cell(n, 5, sum(by_kind.values()))
            c.font = BOLD
            c = summary.cell(n, 6, " · ".join(f"{hours.LEAVE_KINDS[k]}: {by_kind[k]}" for k in hours.LEAVE_KINDS if k in by_kind))
            c.font = BOLD
            summary.merge_cells(start_row=n, start_column=6, end_row=n, end_column=NS)
            for col in range(1, NS + 1):
                summary.cell(n, col).fill = PatternFill("solid", fgColor="EFE9DF")
    if not any_leave:
        n += 1
        summary.cell(n, 1, "Καμία άδεια σε αυτή την περίοδο.").font = OFF_FONT
    # ---- holidays and shop closures of the period
    n += 2
    summary.cell(n, 1, "Αργίες και κλειστό κατάστημα").font = Font(bold=True, size=12)
    n += 1
    for i, v in enumerate(["Ημερομηνία", "Ημέρα", "Αιτία", "", "", "", "Αφορά (είχαν ωράριο εκείνη την ημέρα)"], 1):
        c = summary.cell(n, i, v)
        c.font, c.fill = HEAD, HEAD_FILL
    summary.merge_cells(start_row=n, start_column=3, end_row=n, end_column=6)
    summary.merge_cells(start_row=n, start_column=7, end_row=n, end_column=NS)
    shut_days = []
    for k in range((last_day - first).days + 1):
        d = first + timedelta(days=k)
        if d.isoformat() < golive or d > today:
            continue
        c = hours.closure_on(d)
        if not c:
            continue
        # only the days that matter for pay: someone had working hours in the usual schedule
        who = []
        for e in emps:
            reg = hours.schedule_for(e["id"], d, regular=True)
            if reg is None or d.isoformat() < (e["created_at"] or "")[:10]:
                continue
            ch = hours.day_change(e["id"], d)
            worked = " — δούλεψε με δηλωμένο ωράριο" if ch is not None and ch["text"] else ""
            who.append(f"{e['last_name']} {e['first_name']}{worked}")
        if who:
            shut_days.append((d, c, who))
    for d, c, who in shut_days:
        n += 1
        summary.cell(n, 1, d).number_format = "DD/MM/YYYY"
        summary.cell(n, 2, hours.WEEKDAYS[d.weekday()])
        summary.cell(n, 3, c["label"])
        summary.merge_cells(start_row=n, start_column=3, end_row=n, end_column=6)
        summary.cell(n, 7, ", ".join(who)).alignment = Alignment(wrap_text=True, vertical="top")
        summary.merge_cells(start_row=n, start_column=7, end_row=n, end_column=NS)
        for col in range(1, NS + 1):
            summary.cell(n, col).border = THIN
    if not shut_days:
        n += 1
        summary.cell(n, 1, "Καμία αργία ή κλείσιμο σε εργάσιμη ημέρα σε αυτή την περίοδο.").font = OFF_FONT
    n += 2
    for i, t in enumerate([
            "Δηλωμένες επιπλέον ώρες: ώρες πέραν του συνηθισμένου ωραρίου που δηλώθηκαν στο ΕΡΓΑΝΗ πριν γίνουν "
            "(υπερωρία / αλλαγή ωραρίου ημέρας) και δουλεύτηκαν. Επιπλέον ώρες χωρίς δήλωση: εργασία πέραν του "
            "δηλωμένου ωραρίου της ημέρας — προς πληρωμή και έλεγχο. Οι ώρες ωραρίου περιλαμβάνουν τις δηλωμένες αλλαγές.",
            "Άδειες και αργίες σε εργάσιμες ημέρες (ημέρες με ωράριο). Αργία μέσα σε άδεια μετρά ως αργία, όχι ως άδεια.",
            "Ξεχασμένα χτυπήματα: κινήσεις που δεν έγιναν στην κάρτα και καταχωρήθηκαν μόνο εσωτερικά (δεν στάλθηκαν "
            "στο ΕΡΓΑΝΗ). Ανεκτά έως 3 τον μήνα ανά εργαζόμενο.",
            "Αναλυτικά ανά ημέρα, για όλους μαζί, με ακριβείς ώρες και πρωτόκολλα ΕΡΓΑΝΗ: φύλλο «Αναλυτικά» (στη στήλη «Παρατηρήσεις» ό,τι θέλει προσοχή). Τι δηλώνεται εκ των υστέρων στο ΕΡΓΑΝΗ: φύλλο «Απολογιστικές δηλώσεις»."]):
        c = summary.cell(n + i, 1, t)
        c.font, c.alignment = Font(color="555555", italic=True), Alignment(wrap_text=True, vertical="top")
        summary.merge_cells(start_row=n + i, start_column=1, end_row=n + i, end_column=NS)
        summary.row_dimensions[n + i].height = 15 * max(1, -(-len(t) // int(sum(SUM_W) * 1.1)))
    _print_setup(summary, SUM_ROW)

    if yearly:
        pmw = wb.create_sheet("Ανά μήνα", 1)
        PM_W = [20, 16, 13, 10, 10, 10, 11, 11, 10, 10, 10, 10, 10, 11]
        NP = len(PM_W)
        _info(pmw, info[:3] + ["Κάθε εργαζόμενος μήνα προς μήνα. Ξεχασμένα χτυπήματα: ανεκτά έως 3 τον μήνα."], NP, PM_W)
        PR = 6
        _table_header(pmw, PR, ["Επώνυμο", "Όνομα", "Μήνας", *COUNT_HEADS])
        pmw.row_dimensions[PR].height = 45
        _widths(pmw, PM_W)
        for e in emps:
            months = per_month.get(e["id"], {})
            if not months:
                continue
            for m in sorted(months):
                v = months[m]
                pmw.append([e["last_name"], e["first_name"], MONTHS[m - 1], *_counts(v)])
                r = pmw.max_row
                for col in H_COLS:
                    pmw.cell(r, 3 + col).number_format = H_FMT
                for c in pmw[r]:
                    c.border = THIN
                if v["omit"] >= 3:
                    pmw.cell(r, NP).fill = WARN_FILL
            t = {k: sum(v[k] for v in months.values()) for k in _zero()}
            pmw.append([f"Σύνολο {e['last_name']} {e['first_name']}", "", "", *_counts(t)])
            r = pmw.max_row
            for c in pmw[r]:
                c.font = BOLD
                c.fill = PatternFill("solid", fgColor="EFE9DF")
            for col in H_COLS:
                pmw.cell(r, 3 + col).number_format = H_FMT
        pmw.auto_filter.ref = f"A{PR}:{get_column_letter(NP)}{max(pmw.max_row, PR + 1)}"
        _print_setup(pmw, PR)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
