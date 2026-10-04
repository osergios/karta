"""Schedules and worked-time calculations (shared by the monitor and the monthly report)."""
import re
from datetime import date, datetime, time, timedelta
from typing import NamedTuple

from . import config, db

WEEKDAYS = ["Δευ", "Τρι", "Τετ", "Πεμ", "Παρ", "Σαβ", "Κυρ"]
_SEG = re.compile(r"^\s*(\d{1,2}):(\d{2})\s*[-–]\s*(\d{1,2}):(\d{2})\s*$")
_BRK = re.compile(r"/\s*(\+?)\s*(\d{1,3})\s*[′']?\s*$")   # "/30" = break inside the hours, "/+30" = outside (after the end)
BREAK_AFTER_SECONDS = 4 * 3600   # a break is due once the working day goes beyond 4 hours
MAX_SEGMENTS = 3


class Span(NamedTuple):
    start: str                 # first start 'HH:MM'
    end: str                   # last end 'HH:MM'
    break_min: int
    segments: tuple            # (('10:00','14:00'), ('17:00','21:00')); one item for a continuous day
    break_out: bool = False    # break «εκτός ωραρίου» (Ergani): not inside the declared hours, the day ends break_min later

    @property
    def text(self) -> str:
        return "+".join(f"{a}-{b}" for a, b in self.segments) + (
            f"/{'+' if self.break_out else ''}{self.break_min}" if self.break_min else "")

    @property
    def split(self) -> bool:
        return len(self.segments) > 1


def parse_span(text: str):
    """'10:00-21:00/30' -> Span('10:00','21:00',30,(('10:00','21:00'),));
    split shift: '10:00-14:00+17:00-21:00/20' (segments joined with + or ,); '' -> None.
    Raises ValueError if malformed, overlapping or out of order."""
    if not text or not text.strip():
        return None
    t = text.strip()
    brk, brk_out = 0, False
    m = _BRK.search(t)
    if m:
        brk_out, brk = m.group(1) == "+", int(m.group(2))
        t = t[:m.start()]
    parts = [x for x in re.split(r"\s*[+,]\s*", t.strip())]
    if not parts or len(parts) > MAX_SEGMENTS:
        raise ValueError(text)
    segs, prev_end, work = [], -1, 0
    for part in parts:
        sm = _SEG.match(part)
        if not sm:
            raise ValueError(text)
        h1, m1, h2, m2 = map(int, sm.groups())
        if not (0 <= h1 < 24 and 0 <= h2 < 24 and m1 < 60 and m2 < 60) or (h2, m2) <= (h1, m1):
            raise ValueError(text)
        a, b = h1 * 60 + m1, h2 * 60 + m2
        if a <= prev_end:            # segments must be in order with a real gap between them
            raise ValueError(text)
        prev_end, work = b, work + (b - a)
        segs.append((f"{h1:02d}:{m1:02d}", f"{h2:02d}:{m2:02d}"))
    if brk > 120 or (brk >= work and not brk_out):
        raise ValueError(text)
    return Span(segs[0][0], segs[-1][1], brk, tuple(segs), bool(brk and brk_out))


def net_seconds(gross: float, break_min: int) -> float:
    """Working time excluding the (flexible) break, which only applies once the day passes 4 hours."""
    return gross - min(break_min * 60, max(0.0, gross - BREAK_AFTER_SECONDS))


def _t(hm: str) -> time:
    h, m = map(int, hm.split(":"))
    return time(h, m)


class Sched(NamedTuple):
    start: datetime            # first start of the day
    end: datetime              # last end of the day (the declared end)
    break_min: int
    segments: tuple            # ((start, end), ...) as datetimes; one item unless it is a split shift
    break_out: bool = False    # break «εκτός ωραρίου»: the punch-out may come up to break_min after the declared end
    flex: int = 0              # «ευέλικτη προσέλευση» in minutes (written agreement, declared in Ergani; up to 120)

    @property
    def split(self) -> bool:
        return len(self.segments) > 1

    @property
    def leave_by(self) -> datetime:
        """Latest punch-out that still matches the declared schedule."""
        return self.end + timedelta(minutes=self.break_min) if self.break_out else self.end

    def part_end(self, i: int) -> datetime:
        """When part i is over for reminders/alerts (the last part ends at leave_by)."""
        return self.leave_by if i == len(self.segments) - 1 else self.segments[i][1]

    @property
    def arrive_by(self) -> datetime:
        """End of the flexible-arrival window (= the start without flexible arrival)."""
        return self.start + timedelta(minutes=self.flex)

    def shifted(self, delta: timedelta) -> "Sched":
        """The same day moved by delta: with flexible arrival the whole day follows the actual arrival."""
        segs = tuple((a + delta, b + delta) for a, b in self.segments)
        return self._replace(start=self.start + delta, end=self.end + delta, segments=segs)

    def label(self) -> str:
        return " + ".join(f"{a:%H:%M}–{b:%H:%M}" for a, b in self.segments) + (
            f" /{'+' if self.break_out else ''}{self.break_min}′" if self.break_min else "")


def day_change(employee_id: int, day: date):
    """The one-day change of the declared schedule (overtime / other hours / no work) for that date, or None."""
    return db.one("SELECT * FROM day_changes WHERE employee_id=? AND day=?", (employee_id, day.isoformat()))


def schedule_text_for(employee_id: int, day: date, regular: bool = False):
    """The schedule text ('10:00-17:00/30') that applies on that date: a one-day change if there is one (unless
    regular=True), otherwise the weekly schedule version in force then."""
    import json
    if not regular:
        ch = day_change(employee_id, day)
        if ch is not None:
            return ch["text"] or None
    r = db.one("SELECT days FROM schedule_versions WHERE employee_id=? AND valid_from<=? ORDER BY valid_from DESC LIMIT 1",
               (employee_id, day.isoformat()))
    return (json.loads(r["days"]).get(str(day.weekday())) or None) if r else None     # none before the first version


def schedule_for(employee_id: int, day: date, regular: bool = False):
    """Sched(start, end, break_min, segments) for that date (a one-day change, else the schedule version in force
    then), or None. regular=True ignores the one-day change (the usual weekly schedule)."""
    text = schedule_text_for(employee_id, day, regular)
    if not text:
        return None
    try:
        sp = parse_span(text)
    except ValueError:
        return None
    if sp is None:
        return None
    segs = tuple((datetime.combine(day, _t(a)), datetime.combine(day, _t(b))) for a, b in sp.segments)
    return Sched(segs[0][0], segs[-1][1], int(sp.break_min), segs, sp.break_out, flex_minutes(employee_id))


FLEX_MAX = 120     # law 5239/2025 (ΠΔ 80/2022 άρθρο 580 παρ. 2Α): up to 120′ a day, by written agreement


def flex_minutes(employee_id: int) -> int:
    """The employee's agreed «ευέλικτη προσέλευση» (0 = none)."""
    r = db.one("SELECT flex_arrival FROM employees WHERE id=?", (employee_id,))
    return max(0, min(int(r["flex_arrival"] or 0), FLEX_MAX)) if r else 0


def first_arrival(employee_id: int, sched) -> datetime | None:
    """The day's first arrival (current mode), counted from 3 hours before the declared start."""
    day = sched.start.date()
    r = db.one("SELECT movement_at FROM movements WHERE employee_id=? AND mode=? AND type='ARRIVAL' AND movement_at>=? "
               "AND movement_at<? ORDER BY movement_at LIMIT 1",
               (employee_id, config.ERGANI_MODE, max(sched.start - timedelta(hours=3), datetime.combine(day, time())).isoformat(timespec="seconds"),
                datetime.combine(day + timedelta(days=1), time()).isoformat(timespec="seconds")))
    return datetime.fromisoformat(r["movement_at"]) if r else None


def effective_schedule(employee_id: int, sched):
    """The declared schedule as it applies after the actual arrival. With flexible arrival (ευέλικτη προσέλευση),
    arriving within the window after the declared start moves the whole day by the same amount (the hours are
    completed later: circular 26606/13-10-2025 §2); a later arrival moves it by the full window only (the rest is
    lateness). Arriving before the declared start never moves it (not allowed). Without an arrival: as declared."""
    if not sched or not sched.flex:
        return sched
    a = first_arrival(employee_id, sched)
    if a is None or a <= sched.start or a >= sched.segments[0][1]:
        return sched
    last = datetime.combine(sched.start.date(), time(23, 59))      # a working day never moves past midnight
    late = timedelta(minutes=int((a - sched.start).total_seconds() // 60))   # whole minutes, as Ergani counts
    return sched.shifted(max(timedelta(0), min(late, timedelta(minutes=sched.flex), last - sched.leave_by)))


def scheduled_seconds(sched) -> float:
    """Paid hours of the declared schedule: the declared hours minus a break inside them; a break «εκτός ωραρίου»
    is already outside the declared hours."""
    if not sched:
        return 0.0
    gross = sum((b - a).total_seconds() for a, b in sched.segments)
    return gross if sched.break_out else net_seconds(gross, sched.break_min)


def net_worked(gross: float, sched) -> float:
    """Working time from punched time. Break inside the hours: deducted (after 4h). Break «εκτός ωραρίου»: the time
    beyond the declared hours up to the break length counts as break (not work), so leaving anywhere between the
    declared end and end + break gives exactly the declared hours."""
    if sched and sched.break_out:
        declared = sum((b - a).total_seconds() for a, b in sched.segments)
        return max(gross - sched.break_min * 60, min(gross, declared))
    return net_seconds(gross, sched.break_min if sched else 0)


def segment_index(sched, when: datetime) -> int:
    """Which part of the day `when` belongs to: the last segment that has started (0 before the first)."""
    idx = 0
    for i, (a, _) in enumerate(sched.segments):
        if a <= when:
            idx = i
    return idx


def arrival_segment(sched, when: datetime) -> int:
    """For an arrival: the first segment that has not ended yet (the one they are coming in for)."""
    for i, (_, b) in enumerate(sched.segments):
        if when < b:
            return i
    return len(sched.segments) - 1


def last_movement(employee_id: int):
    """Latest movement of the current ERGANI_MODE. Movements made in another mode (dry run / Ergani
    test server) are ignored everywhere: state, alerts, rest checks and the report."""
    return db.one("SELECT * FROM movements WHERE employee_id=? AND mode=? ORDER BY movement_at DESC, id DESC LIMIT 1",
                  (employee_id, config.ERGANI_MODE))


def on_leave(employee_id: int, day: date):
    """The leave row covering that day, or None."""
    return db.one("SELECT * FROM leaves WHERE employee_id=? AND start_date<=? AND end_date>=? ORDER BY id LIMIT 1",
                  (employee_id, day.isoformat(), day.isoformat()))


LEAVE_KINDS = {"regular": "Κανονική άδεια", "sick": "Άδεια ασθενείας", "special": "Άδεια ειδικού σκοπού"}


def leave_label(row) -> str:
    kind = row["kind"] if "kind" in row.keys() else "regular"
    return LEAVE_KINDS.get(kind, "Άδεια") + (f" ({row['note']})" if row["note"] else "")


# ---- public holidays and shop closures
def orthodox_easter(year: int) -> date:
    """Orthodox Easter Sunday (Meeus, Julian calendar + 13 days: valid 1900-2099)."""
    a, b, c = year % 4, year % 7, year % 19
    d = (19 * c + 15) % 30
    e = (2 * a + 4 * b - d + 34) % 7
    m, dd = divmod(d + e + 114, 31)
    return date(year, m, dd + 1) + timedelta(days=13)


DEFAULT_LOCAL_HOLIDAYS: list[dict] = []   # none preset: each shop adds its own (e.g. the city's patron saint)


def local_holidays() -> list[dict]:
    import json
    raw = db.setting("local_holidays")
    try:
        return json.loads(raw) if raw else list(DEFAULT_LOCAL_HOLIDAYS)
    except ValueError:
        return list(DEFAULT_LOCAL_HOLIDAYS)


def holiday_state() -> dict:
    """Your choice per holiday date: {'2026-04-10': 'closed' | 'open'} (default: closed, open for Μεγάλη Παρασκευή)."""
    import json
    raw = db.setting("holiday_state")
    try:
        return json.loads(raw) if raw else {}
    except ValueError:
        return {}


def holidays(year: int) -> list[dict]:
    """Public holidays of Greece + the local ones, each {'date','name','kind','default_closed','closed'}."""
    E = orthodox_easter(year)
    rows = [
        (date(year, 1, 1), "Πρωτοχρονιά", True, "newyear"),
        (date(year, 1, 6), "Θεοφάνεια", True, "theophany"),
        (E - timedelta(days=48), "Καθαρά Δευτέρα", True, "clean_monday"),
        (date(year, 3, 25), "Εθνική Επέτειος 25ης Μαρτίου", True, "mar25"),
        (E - timedelta(days=2), "Μεγάλη Παρασκευή", False, "good_friday"),
        (E, "Κυριακή του Πάσχα", True, "easter"),
        (E + timedelta(days=1), "Δευτέρα του Πάσχα", True, "easter"),
        (date(year, 5, 1), "Πρωτομαγιά", True, "may1"),
        (E + timedelta(days=50), "Αγίου Πνεύματος", True, "whit_monday"),
        (date(year, 8, 15), "Κοίμηση της Θεοτόκου", True, "aug15"),
        (date(year, 10, 28), "Επέτειος του «Όχι»", True, "oct28"),
        (date(year, 12, 25), "Χριστούγεννα", True, "christmas"),
        (date(year, 12, 26), "Σύναξη της Θεοτόκου", True, "christmas"),
    ]
    out = [{"date": d, "name": n, "kind": "national", "default_closed": c, "key": k} for d, n, c, k in rows]
    for h in local_holidays():
        try:
            mm, dd = map(int, h["md"].split("-"))
            out.append({"date": date(year, mm, dd), "name": h["name"], "kind": "local", "default_closed": True,
                        "key": "local"})
        except (ValueError, KeyError):
            continue
    state = holiday_state()
    for h in out:
        s = state.get(h["date"].isoformat())
        h["closed"] = h["default_closed"] if s is None else s == "closed"
    return sorted(out, key=lambda h: h["date"])


def closure_on(day: date):
    """Why the shop is closed that day ({'kind': 'holiday'|'closure', 'label', 'reason'}), or None."""
    r = db.one("SELECT * FROM closures WHERE start_date<=? AND end_date>=? ORDER BY id LIMIT 1",
               (day.isoformat(), day.isoformat()))
    if r is not None:
        return {"kind": "closure", "label": f"Κατάστημα κλειστό: {r['reason']}", "reason": r["reason"], "id": r["id"]}
    for h in holidays(day.year):
        if h["date"] == day and h["closed"]:
            return {"kind": "holiday", "label": f"Αργία: {h['name']}", "reason": h["name"], "key": h["key"]}
    return None


# what the shop screen says on a closed day: holiday key -> (greeting, line under it)
GREETINGS = {
    "newyear": ("Καλή Χρονιά!", "Πρωτοχρονιά · Χρόνια πολλά"),
    "theophany": ("Καλά Φώτα!", "Θεοφάνεια · Χρόνια πολλά"),
    "clean_monday": ("Καλή Σαρακοστή!", "Καθαρά Δευτέρα"),
    "mar25": ("Χρόνια πολλά!", "25η Μαρτίου · Εθνική Επέτειος και Ευαγγελισμός της Θεοτόκου"),
    "good_friday": ("Καλή Ανάσταση!", "Μεγάλη Παρασκευή"),
    "easter": ("Χριστός Ανέστη!", "Καλό Πάσχα · Χρόνια πολλά"),
    "may1": ("Καλή Πρωτομαγιά!", "Εργατική Πρωτομαγιά"),
    "whit_monday": ("Χρόνια πολλά!", "Αγίου Πνεύματος"),
    "aug15": ("Χρόνια πολλά!", "Κοίμηση της Θεοτόκου"),
    "oct28": ("Χρόνια πολλά!", "28η Οκτωβρίου · Εθνική Επέτειος του «Όχι»"),
    "christmas": ("Καλά Χριστούγεννα!", "Χρόνια πολλά"),
}


def reopen_day(day: date):
    """The next day the shop is open after a closed day: not closed, and with opening hours that weekday
    (the shop's hours if saved, otherwise anyone's usual schedule). None if not found within 60 days."""
    import json
    raw = db.setting("salon_hours")
    try:
        salon = json.loads(raw) if raw else {}
    except ValueError:
        salon = {}
    emps = [e["id"] for e in db.all_rows("SELECT id FROM employees WHERE active=1")]
    for k in range(1, 61):
        d = day + timedelta(days=k)
        if closure_on(d):
            continue
        if any(v.strip() for v in salon.values()):
            if (salon.get(str(d.weekday())) or "").strip():
                return d
        elif any(schedule_for(e, d, regular=True) for e in emps):
            return d
    return None


def closed_info(day: date):
    """For the shop screen on a closed day: {'kind','key','title','sub','reason','reopen','works'}, or None.
    works = someone has declared working hours that day (then the screen still takes their punches)."""
    c = closure_on(day)
    if c is None:
        return None
    if c["kind"] == "holiday":
        title, sub = GREETINGS.get(c.get("key"), ("Χρόνια πολλά!", c["reason"]))
        if c.get("key") == "local":
            sub = c["reason"]
    else:
        title, sub = "Σήμερα είμαστε κλειστά", c["reason"]
    works = any(r["text"] for r in db.all_rows(
        "SELECT dc.text FROM day_changes dc JOIN employees e ON e.id=dc.employee_id WHERE e.active=1 AND dc.day=?",
        (day.isoformat(),)))
    ro = reopen_day(day)
    return {"kind": c["kind"], "key": c.get("key") or "closure", "title": title, "sub": sub, "reason": c["reason"],
            "reopen": ro.isoformat() if ro else None, "works": works}


def festive_season(day: date):
    """Decoration theme for the shop screen on that date, or None."""
    E = orthodox_easter(day.year)
    md = (day.month, day.day)
    if E - timedelta(days=7) <= day <= E + timedelta(days=1):
        return "easter"                    # Κυριακή των Βαΐων .. Δευτέρα του Πάσχα
    if E - timedelta(days=51) <= day <= E - timedelta(days=48):
        return "kites"                     # the long weekend of Καθαρά Δευτέρα
    if md >= (12, 1) or md <= (1, 6):
        return "christmas"                 # 1 December .. Θεοφάνεια
    if (3, 24) <= md <= (3, 25) or (10, 27) <= md <= (10, 28):
        return "flag"
    if (4, 29) <= md <= (5, 1):
        return "may"
    return None


def day_off(employee_id: int, day: date):
    """Nobody should expect this person at work that day: {'kind': 'holiday'|'closure'|'leave', 'label', ...}, or None.
    A one-day change with working hours wins (work on a holiday / during a closure, declared in Ergani)."""
    ch = day_change(employee_id, day)
    if ch is not None and ch["text"]:
        return None
    c = closure_on(day)
    if c:
        return c
    lv = on_leave(employee_id, day)
    if lv:
        kind = lv["kind"] if "kind" in lv.keys() else "regular"
        return {"kind": "leave", "leave_kind": kind, "label": leave_label(lv), "row": lv}
    return None


def arrival_quiet(employee_id: int, day: date) -> bool:
    """«Θα αργήσει σήμερα»: the admin muted today's punch-in reminder (shop screen) and «δεν χτύπησε» alert (phone)
    for this person, e.g. after they called to say they'll be late. Only that day; punch-out notices are unaffected."""
    return db.setting(f"quiet_in:{employee_id}") == day.isoformat()


def arrived_for_segment(employee_id: int, sched, i: int, now: datetime) -> bool:
    """Has there been an arrival (current mode) for part i of today's schedule? Counts from the end of the
    previous part (or 3 hours before the start for the first part), so an early arrival counts too."""
    start = sched.segments[i][0]
    lo = sched.segments[i - 1][1] if i > 0 else start - timedelta(hours=3)
    return db.one("SELECT 1 FROM movements WHERE employee_id=? AND mode=? AND type='ARRIVAL' AND movement_at>=? "
                  "AND movement_at<=? LIMIT 1", (employee_id, config.ERGANI_MODE, lo.isoformat(timespec="seconds"),
                                                   now.isoformat(timespec="seconds"))) is not None


EARLY_LEAVE_MIN = 1    # no tolerance: leaving even a minute before the end of the (moved) day is «έφυγε νωρίτερα»
EARLY_REASONS = {"sick": "ασθένεια", "personal": "προσωπικός λόγος", "other": "άλλος λόγος"}


def early_departure(employee_id: int, day: date):
    """{'at','end','minutes'} when the person punched out before the end of that part of the day (to the minute)
    (flexible arrival included; a break «εκτός ωραρίου» does not count) and did not come back; else None."""
    declared = schedule_for(employee_id, day)
    rows = day_movements(employee_id, day)
    if declared is None or not rows or rows[-1]["type"] != "DEPARTURE":
        return None
    sched = effective_schedule(employee_id, declared)
    found = None
    for k, r in enumerate(rows):
        if r["type"] != "DEPARTURE":
            continue
        t = datetime.fromisoformat(r["movement_at"]).replace(second=0)
        i = segment_index(sched, t)
        pe = sched.end if i == len(sched.segments) - 1 else sched.segments[i][1]
        back = any(x["type"] == "ARRIVAL" and t < datetime.fromisoformat(x["movement_at"]) < pe for x in rows[k + 1:])
        if pe - t >= timedelta(minutes=EARLY_LEAVE_MIN) and not back:
            found = {"at": f"{t:%H:%M}", "end": f"{pe:%H:%M}", "minutes": int((pe - t).total_seconds() // 60)}
    return found


def early_leave_mark(employee_id: int, day: date):
    """The «Έφυγε νωρίτερα» note the admin entered for that day, or None."""
    return db.one("SELECT * FROM early_leaves WHERE employee_id=? AND day=?", (employee_id, day.isoformat()))


SOON_SECONDS = 120   # the shop screen counts down the last 2 minutes before a punch-out is due


def reminders(now: datetime) -> list[dict]:
    """Who should punch right now (shop-screen reminders):
    'in'       = the part of the schedule has started and no arrival yet (from the exact start time);
    'out_soon' = inside, the part ends within 2 minutes ('in_s' = seconds left);
    'out'      = still in at/after the end of the current part (the end already includes the break).
    People on leave, holidays and shop closures are skipped."""
    today = now.date()
    out = []
    for e in db.all_rows("SELECT id, display_name FROM employees WHERE active=1"):
        sched = schedule_for(e["id"], today)
        if sched is None or day_off(e["id"], today):
            continue
        last = last_movement(e["id"])
        inside = bool(last and last["type"] == "ARRIVAL" and last["movement_at"][:10] == today.isoformat())
        if inside:
            sched = effective_schedule(e["id"], sched)        # flexible arrival: the end follows the arrival
            i = segment_index(sched, now)
            end = sched.part_end(i)
            if now >= end:
                out.append({"employee_id": e["id"], "kind": "out", "at": f"{end:%H:%M}"})
            elif (end - now).total_seconds() <= SOON_SECONDS:
                out.append({"employee_id": e["id"], "kind": "out_soon", "at": f"{end:%H:%M}",
                            "in_s": int((end - now).total_seconds())})
        elif not arrival_quiet(e["id"], today):              # «Θα αργήσει»: no punch-in reminder today
            for i, (start, end) in enumerate(sched.segments):
                if start <= now < end and not arrived_for_segment(e["id"], sched, i, now):
                    out.append({"employee_id": e["id"], "kind": "in", "at": f"{start:%H:%M}"})
                    break
    return out


def next_reminder_in(now: datetime):
    """Seconds until the next moment the reminders change (a start, 2′ and 1′ before an end, an end), so the
    shop screen can wake up exactly then instead of waiting for its 30″ poll. None if nothing is left today."""
    today = now.date()
    best = None
    for e in db.all_rows("SELECT id FROM employees WHERE active=1"):
        declared = schedule_for(e["id"], today)
        if declared is None or day_off(e["id"], today):
            continue
        sched = effective_schedule(e["id"], declared)
        for i in range(len(sched.segments)):
            b = sched.part_end(i)
            for t in (declared.segments[i][0], b - timedelta(seconds=SOON_SECONDS), b - timedelta(seconds=60), b):
                d = (t - now).total_seconds()
                if d > 0 and (best is None or d < best):
                    best = d
    return best


def day_movements(employee_id: int, day: date):
    lo = datetime.combine(day, time()).isoformat(timespec="seconds")
    hi = datetime.combine(day + timedelta(days=1), time()).isoformat(timespec="seconds")
    return db.all_rows(
        "SELECT id, type, movement_at, status, late_justification, note, protocol FROM movements "
        "WHERE employee_id=? AND mode=? AND movement_at>=? AND movement_at<? ORDER BY movement_at, id",
        (employee_id, config.ERGANI_MODE, lo, hi))


def intervals(rows, until: datetime | None = None):
    """Pair ARRIVAL -> DEPARTURE. An open arrival runs to `until` (or stays open: end=None)."""
    out, start = [], None
    for r in rows:
        t = datetime.fromisoformat(r["movement_at"])
        if r["type"] == "ARRIVAL":
            if start is None:
                start = t
        elif start is not None:
            out.append((start, t))
            start = None
    if start is not None:
        out.append((start, until))
    return out


def gross_seconds(employee_id: int, day: date, now: datetime | None = None) -> float:
    return sum((b - a).total_seconds() for a, b in intervals(day_movements(employee_id, day), now) if b)


def worked_seconds(employee_id: int, day: date, now: datetime | None = None) -> float:
    """Net working time that day: punched time minus that day's scheduled break."""
    sched = schedule_for(employee_id, day)
    return net_worked(gross_seconds(employee_id, day, now), sched)


def week_seconds(employee_id: int, day: date, now: datetime | None = None) -> float:
    monday = day - timedelta(days=day.weekday())
    total = 0.0
    for i in range((day - monday).days + 1):
        d = monday + timedelta(days=i)
        total += worked_seconds(employee_id, d, now if d == day else None)
    return total


def last_departure_before(employee_id: int, when: datetime):
    r = db.one("SELECT movement_at FROM movements WHERE employee_id=? AND mode=? AND type='DEPARTURE' AND movement_at<? "
               "ORDER BY movement_at DESC LIMIT 1", (employee_id, config.ERGANI_MODE, when.isoformat(timespec="seconds")))
    return datetime.fromisoformat(r["movement_at"]) if r else None


def hm(seconds: float) -> str:
    m = int(round(seconds / 60))
    return f"{m // 60}ω {m % 60:02d}λ"
