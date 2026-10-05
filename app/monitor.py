"""Live checks on who is working: shift ending, shift over, daily/weekly limits, rest, off-schedule work.
Runs every minute. Each alert is raised once per employee/day/kind and goes to:
  - the admin page and your phone (ntfy), with full detail;
  - the shop screen (banner + system notification) — only the neutral 'please punch out' kinds."""
import json
import logging
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from . import config, db, hours
from .timeutil import now_local

log = logging.getLogger("workcard.monitor")

DEFAULTS = {
    "grace_minutes": 5,         # flexibility: arrival/departure this many minutes off the schedule is fine;
                                #   beyond it you get a phone alert (not punched in / still in)
    "escalate_minutes": 30,     # still in this long after that -> urgent
    "daily_max_hours": 9.0,     # legal daily max, 5-day week (8h normal + 1h υπερεργασία); beyond = υπερωρία
    "weekly_max_hours": 40.0,   # contractual week; beyond = υπερεργασία
    "weekly_legal_hours": 45.0, # legal week, 5-day (48 for 6-day); beyond = υπερωρία
    "min_rest_hours": 11.0,     # daily rest between two shifts
    "kiosk_reminders": 1.0,     # 1 = the shop screen reminds people to punch in/out (repeats every 30″)
    "early_minutes": 0.0,       # an arrival punch is refused if it is more than this before the declared start
    "ot_deadline_minutes": 60.0,  # overtime / a later end must be declared in Ergani this long before the declared end
    "ot_notice_minutes": 0.0,     # phone reminder this long before that deadline, for whoever is at work (0 = off)
    "festive": 1.0,             # 1 = festive decorations on the shop screen (Christmas, Easter, national days...)
}
LEVEL_PRIORITY = {"info": 3, "warning": 4, "urgent": 5}
_lock = threading.Lock()


def get_settings() -> dict:
    s = dict(DEFAULTS)
    for r in db.all_rows("SELECT key, value FROM settings"):
        if r["key"] in s:
            s[r["key"]] = float(r["value"])
    return s


# Phone alerts go out on a background thread: a slow or unreachable ntfy server must never delay a
# punch (raise_alert runs inside the kiosk request) or the monitor loop. One worker keeps them in order.
_ntfy_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ntfy")


def _ntfy(title: str, message: str, level: str) -> None:
    if not (config.NTFY_URL and config.NTFY_TOPIC):
        return
    _ntfy_pool.submit(_ntfy_send, title, message, level)


def ntfy_post(title: str, message: str, level: str) -> None:
    """Sends one phone notification now; raises if ntfy is unreachable or refuses it."""
    body = json.dumps({"topic": config.NTFY_TOPIC, "title": title, "message": message,
                       "priority": LEVEL_PRIORITY.get(level, 3), "tags": ["alarm_clock"]}).encode()
    req = urllib.request.Request(config.NTFY_URL, data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    if config.NTFY_TOKEN:
        req.add_header("Authorization", f"Bearer {config.NTFY_TOKEN}")
    urllib.request.urlopen(req, timeout=10).close()


def _ntfy_send(title: str, message: str, level: str) -> None:
    try:
        ntfy_post(title, message, level)
    except Exception as e:  # never let a phone alert break the monitor
        log.warning("ntfy failed: %s", e)


def raise_alert(kind: str, employee_id: int | None, day, level: str, message: str,
                kiosk_message: str | None, now: datetime, push: bool = True) -> bool:
    key = f"{kind}:{employee_id}:{day.isoformat()}"
    with db.tx() as c:
        created = c.execute(
            "INSERT OR IGNORE INTO alerts(key, employee_id, kind, level, message, kiosk_message, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (key, employee_id, kind, level, message, kiosk_message, now.isoformat(timespec="seconds"))).rowcount == 1
    if created:
        log.info("ALERT [%s] %s", level, message)
        if push:
            _ntfy("Κάρτα: " + {"info": "ενημέρωση", "warning": "προσοχή", "urgent": "ΕΠΕΙΓΟΝ"}[level], message, level)
    return created


def resolve_employee(employee_id: int, now: datetime) -> None:
    """On departure the 'please punch out' banners are done; history stays."""
    with db.tx() as c:
        c.execute("UPDATE alerts SET resolved_at=? WHERE employee_id=? AND resolved_at IS NULL "
                  "AND kind NOT LIKE 'ergani_%'",   # Ergani rejections stay until you mark them done
                  (now.isoformat(timespec="seconds"), employee_id))


def on_arrival(employee_id: int, name: str, when: datetime) -> None:
    """Checks that only make sense at the moment someone clocks in."""
    s = get_settings()
    day = when.date()
    sched = hours.schedule_for(employee_id, day)
    off = hours.day_off(employee_id, day)
    if off and off["kind"] == "leave":
        leave = off["row"]
        raise_alert("leave_punch", employee_id, day, "warning",
                    f"{name} χτύπησε προσέλευση {when:%H:%M} ενώ είναι σε άδεια ({off['label']}, "
                    f"{leave['start_date'][8:10]}/{leave['start_date'][5:7]}–{leave['end_date'][8:10]}/{leave['end_date'][5:7]}). "
                    f"Αν δουλεύει, ακύρωσε την άδεια στη διαχείριση και ενημέρωσε το ΕΡΓΑΝΗ.", None, when)
    elif off:
        raise_alert("closed_punch", employee_id, day, "warning",
                    f"{name} χτύπησε προσέλευση {when:%H:%M} ενώ σήμερα {off['label'][0].lower() + off['label'][1:]}. "
                    + ("Αν δουλεύει, η ημέρα δηλώνεται απολογιστικά στο ΕΡΓΑΝΗ έως το τέλος του επόμενου μήνα· πέρασέ τη και "
                       "στη διαχείριση («Υπερωρία / αλλαγή ημέρας…»)." if config.RETRO else
                       "Αν δουλεύει, δήλωσε ωράριο για σήμερα στο ΕΡΓΑΝΗ και πέρασέ το στη διαχείριση («Υπερωρία / αλλαγή ημέρας…»)."),
                    None, when)
    elif sched is None:
        raise_alert("unscheduled", employee_id, day, "warning",
                    f"{name} χτύπησε προσέλευση {when:%H:%M} χωρίς ωράριο για σήμερα. "
                    f"Αν δεν είναι δηλωμένο στο ΕΡΓΑΝΗ, η εργασία θεωρείται αδήλωτη.", None, when)
    else:
        i = hours.arrival_segment(sched, when)
        start = sched.segments[i][0]
        if when < start - timedelta(minutes=s["grace_minutes"]):
            raise_alert("early" + _suffix(i), employee_id, day, "warning",
                        f"{name} ήρθε {when:%H:%M}, το ωράριο ξεκινά {start:%H:%M}. "
                        f"Ο χρόνος πριν την έναρξη μετρά ως επιπλέον εργασία.", None, when)
    # daily rest is between working days: a return after a split-shift gap is not a new day
    first_today = db.one("SELECT 1 FROM movements WHERE employee_id=? AND mode=? AND type='ARRIVAL' AND movement_at>=? "
                         "AND movement_at<? LIMIT 1",
                         (employee_id, config.ERGANI_MODE, day.isoformat(), when.isoformat(timespec="seconds")))
    prev = None if first_today else hours.last_departure_before(employee_id, when)
    if prev is not None and when - prev < timedelta(hours=s["min_rest_hours"]):
        raise_alert("rest", employee_id, day, "urgent",
                    f"{name}: μόνο {hours.hm((when - prev).total_seconds())} ανάπαυση από την αποχώρηση "
                    f"{prev:%d/%m %H:%M} (ελάχιστο {s['min_rest_hours']:g} ώρες).", None, when)


def on_departure(employee_id: int, name: str, when: datetime) -> None:
    """Left well before the end of the day (e.g. got sick): a note in the admin list only — no phone alert."""
    e = hours.early_departure(employee_id, when.date())
    if e and not hours.early_leave_mark(employee_id, when.date()):
        raise_alert("early_leave", employee_id, when.date(), "info",
                    f"{name} αποχώρησε {e['at']}, {hours.hm(e['minutes'] * 60)} πριν τη λήξη ({e['end']}). Αν έφυγε λόγω "
                    "ασθένειας ή για άλλο λόγο, σημείωσέ το με «Έφυγε νωρίτερα…»: η αναφορά θα δείξει τις ώρες για την "
                    "απολογιστική δήλωση ωραρίου.", None, when, push=False)


def _suffix(i: int) -> str:
    """Alerts are once per kind/employee/day; each part of a split shift gets its own."""
    return "" if i == 0 else f"#{i + 1}"


def check(now: datetime | None = None) -> None:
    now = now or now_local()
    today = now.date()
    s = get_settings()
    try:
        from . import onboarding
        onboarding.check_alerts(now)      # the day before / the day the card becomes mandatory
    except Exception:
        log.exception("onboarding notice failed")
    try:
        _check_backup(now)
    except Exception:
        log.exception("backup check failed")
    with _lock:
        for emp in db.all_rows("SELECT id, display_name FROM employees WHERE active=1"):
            eid, name = emp["id"], emp["display_name"]
            last = hours.last_movement(eid)
            if not last or last["type"] != "ARRIVAL" or last["movement_at"][:10] != today.isoformat():
                _check_missed_arrival(eid, name, today, now, s)
                continue  # not working right now

            # flexible arrival (ευέλικτη προσέλευση): the end follows the actual arrival, within the agreed window
            sched = hours.effective_schedule(eid, hours.schedule_for(eid, today))
            if sched:
                i = hours.segment_index(sched, now)
                end, sfx = sched.part_end(i), _suffix(i)   # a break «εκτός ωραρίου» moves the last end by its length
                last_part = i == len(sched.segments) - 1
                what = "η βάρδια" if not sched.split else ("το πρωινό σκέλος" if i == 0 else
                                                           "το απογευματινό σκέλος" if last_part else f"το {i + 1}ο σκέλος")
                back = "" if last_part else f" Επιστροφή στις {sched.segments[i + 1][0]:%H:%M}."
                over = end + timedelta(minutes=s["grace_minutes"])
                if now >= over:
                    raise_alert("overdue" + sfx, eid, today, "warning",
                                f"{name} είναι ακόμα μέσα. {what[0].upper() + what[1:]} έληξε {end:%H:%M}: " + (
                                    "αν δουλεύει, οι επιπλέον ώρες δηλώνονται απολογιστικά στο ΕΡΓΑΝΗ έως το τέλος του "
                                    "επόμενου μήνα (η μηνιαία αναφορά τις δείχνει). Αν έφυγε, να χτυπήσει αποχώρηση ΤΩΡΑ, "
                                    "με την πραγματική ώρα" if config.RETRO else
                                    "ό,τι περισσότερο είναι εκτός δηλωμένου ωραρίου (μη δηλωμένη υπερωρία). Να χτυπήσει "
                                    "αποχώρηση ΤΩΡΑ, με την πραγματική ώρα") +
                                f" — ποτέ αποχώρηση και μετά συνέχεια της δουλειάς.{back}",
                                None, now)   # the shop screen shows the repeating reminder instead
                dl = sched.leave_by - timedelta(minutes=s["ot_deadline_minutes"])
                if (last_part and s["ot_notice_minutes"] > 0 and not config.RETRO     # retro: no deadline before
                        and dl - timedelta(minutes=s["ot_notice_minutes"]) <= now < dl):
                    _ot_notice(sched.leave_by, dl, today, now)
                if now >= over + timedelta(minutes=s["escalate_minutes"]):
                    raise_alert("overdue2" + sfx, eid, today, "urgent",
                                f"{name} δουλεύει {hours.hm((now - end).total_seconds())} μετά τη λήξη "
                                f"({what}, {end:%H:%M}) χωρίς αποχώρηση.",
                                None, now)

            worked = hours.worked_seconds(eid, today, now)
            daily = s["daily_max_hours"] * 3600
            if daily - 15 * 60 <= worked < daily:
                raise_alert("daily_near", eid, today, "warning",
                            f"{name}: {hours.hm(worked)} καθαρή εργασία σήμερα. Σε 15′ συμπληρώνει "
                            f"{s['daily_max_hours']:g} ώρες και ό,τι ακολουθεί είναι υπερωρία ("
                            + ("απολογιστική δήλωση στο ΕΡΓΑΝΗ έως το τέλος του επόμενου μήνα" if config.RETRO else
                               "δήλωση στο ΕΡΓΑΝΗ πριν ξεκινήσει") + ").",
                            None, now)
            if worked >= daily:
                raise_alert("daily_max", eid, today, "urgent",
                            f"{name}: {hours.hm(worked)} καθαρή εργασία σήμερα — πέρασε τις {s['daily_max_hours']:g} ώρες. "
                            + ("Από εδώ είναι υπερωρία: δηλώνεται απολογιστικά στο ΕΡΓΑΝΗ έως το τέλος του επόμενου μήνα, "
                               "μέσα στα νόμιμα όρια." if config.RETRO else
                               "Από εδώ είναι υπερωρία: μόνο αν έχει δηλωθεί στο ΕΡΓΑΝΗ."),
                            None, now)   # your call (declare or send home): phone/admin only, not the shop screen

            week = hours.week_seconds(eid, today, now)
            if week >= s["weekly_max_hours"] * 3600:
                raise_alert("weekly_max", eid, today, "warning",
                            f"{name}: {hours.hm(week)} αυτή την εβδομάδα — πέρασε τις {s['weekly_max_hours']:g} "
                            f"(ό,τι ακολουθεί είναι υπερεργασία, +20%).", None, now)
            if week >= s["weekly_legal_hours"] * 3600:
                raise_alert("weekly_legal", eid, today, "urgent",
                            f"{name}: {hours.hm(week)} αυτή την εβδομάδα — πέρασε το νόμιμο όριο των "
                            f"{s['weekly_legal_hours']:g} ωρών. Από εδώ μόνο δηλωμένη υπερωρία.", None, now)


def backup_status() -> dict | None:
    """The last nightly backup as recorded by backup.sh (app/backupmark.py), with its local time."""
    raw = db.setting("backup_status")
    try:
        b = json.loads(raw) if raw else None
        b["when"] = datetime.fromisoformat(b["at"]).replace(tzinfo=timezone.utc).astimezone(config.TZ).replace(tzinfo=None)
    except (ValueError, TypeError, KeyError):
        return None
    return b


def _resolve_backup_alerts(b: dict | None, c: dict | None, cloud_ok: datetime | None, now: datetime) -> None:
    """Backup alerts whose problem is gone close by themselves (like resolve_employee); the rows stay as history."""
    fresh = lambda t: t is not None and (now - t).total_seconds() <= 50 * 3600
    gone = [kind for kind, ok in (
        ("backup_none", b is not None or c is not None),
        ("backup_old", b is not None and fresh(b["when"])),
        ("backup_cloud_old", fresh(cloud_ok)),
        ("backup_failed", b is not None and "fail" not in (b.get("local"), b.get("usb"))),
    ) if ok]
    marks = ",".join("?" * len(gone))
    if gone and db.one(f"SELECT 1 FROM alerts WHERE resolved_at IS NULL AND kind IN ({marks}) LIMIT 1", gone):
        with db.tx() as tx:
            tx.execute(f"UPDATE alerts SET resolved_at=? WHERE resolved_at IS NULL AND kind IN ({marks})",
                       (now.isoformat(timespec="seconds"), *gone))


def _check_backup(now: datetime) -> None:
    """Once a day: backups stopped (or never ran although real punches exist), or a copy failed. Alerts whose problem
    is gone close at any hour."""
    from . import cloud
    b, c = backup_status(), cloud.status()
    today = now.date()
    raw_ok = db.setting("cloud_last_ok")
    cloud_ok = datetime.fromisoformat(raw_ok) if c and raw_ok else None
    _resolve_backup_alerts(b, c, cloud_ok, now)
    if now.hour < 9:          # backups run in the evening; look at them in the morning
        return
    if b is None and c is None:           # no backup of any kind is set up
        if db.one("SELECT 1 FROM movements WHERE mode='production' LIMIT 1") and today.weekday() == 0:
            raise_alert("backup_none", None, today, "warning",
                        "Δεν γίνεται αντίγραφο ασφαλείας. Τα χτυπήματα πρέπει να φυλάσσονται για χρόνια: «Ρυθμίσεις» → "
                        "«Αντίγραφα ασφαλείας» (cloud), ή ./setup.sh στο μηχάνημα της Karta.", None, now)
        return
    if b is not None and (now - b["when"]).total_seconds() > 50 * 3600:
        raise_alert("backup_old", None, today, "warning",
                    f"Το τελευταίο αντίγραφο στο μηχάνημα είναι από {b['when']:%d/%m %H:%M}. Ελέγξτε ότι το μηχάνημα "
                    "της Karta είναι ανοιχτό και ότι τρέχει το backup.sh κάθε βράδυ.", None, now)
    if c is not None and (cloud_ok is None or (now - cloud_ok).total_seconds() > 50 * 3600) and c.get("when"):
        raise_alert("backup_cloud_old", None, today, "warning",
                    (f"Το πρώτο αντίγραφο στο cloud δεν έγινε: {c.get('error') or 'άγνωστο σφάλμα'}"
                     if cloud_ok is None else           # it never worked: right after connecting, not «two days»
                     "Το αντίγραφο στο cloud δεν ανέβηκε τις τελευταίες δύο ημέρες"
                     + (f" ({c['error']})" if c.get("error") else ""))
                    + ". Δείτε «Ρυθμίσεις» → «Αντίγραφα ασφαλείας».", None, now)
    failed = [n for k, n in (("local", "στο μηχάνημα"), ("usb", "στο USB")) if b and b.get(k) == "fail"]
    if failed:
        raise_alert("backup_failed", None, today, "warning",
                    f"Το αντίγραφο ασφαλείας της {b['when']:%d/%m} απέτυχε {', '.join(failed)}. Δείτε «Ρυθμίσεις» → "
                    "«Αντίγραφα ασφαλείας».", None, now)


def _ot_notice(end: datetime, deadline: datetime, today, now: datetime) -> None:
    """One phone reminder per end time: who is at work and until when overtime can still be declared in Ergani."""
    names = []
    for e in db.all_rows("SELECT id, display_name FROM employees WHERE active=1"):
        last = hours.last_movement(e["id"])
        if not last or last["type"] != "ARRIVAL" or last["movement_at"][:10] != today.isoformat():
            continue
        sc = hours.effective_schedule(e["id"], hours.schedule_for(e["id"], today))
        if sc is not None and sc.leave_by == end:
            names.append(e["display_name"])
    if names:
        raise_alert(f"ot_notice@{end:%H%M}", None, today, "info",
                    f"Λήξη {end:%H:%M}: {', '.join(names)}. Αν χρειαστεί να μείνει κάποιος παραπάνω, η υπερωρία "
                    f"δηλώνεται στο ΕΡΓΑΝΗ έως τις {deadline:%H:%M} (και μετά «Υπερωρία / αλλαγή ημέρας…» στη διαχείριση).",
                    None, now)


def _check_missed_arrival(eid: int, name: str, today, now: datetime, s: dict) -> None:
    """Phone alert when a scheduled part of the day started more than the flexibility ago and nobody punched in."""
    sched = hours.schedule_for(eid, today)
    if sched is None or hours.day_off(eid, today):
        return
    if hours.arrival_quiet(eid, today):         # «Θα αργήσει σήμερα»: muted by the admin
        return
    flex = timedelta(minutes=s["grace_minutes"])
    for i, (start, end) in enumerate(sched.segments):
        if start + flex <= now < end and not hours.arrived_for_segment(eid, sched, i, now):
            raise_alert("missed_in" + _suffix(i), eid, today, "warning",
                        f"{name} δεν έχει χτυπήσει προσέλευση — το ωράριο ξεκίνησε {start:%H:%M} "
                        f"(πέρασαν τα {s['grace_minutes']:g}′ ευελιξίας). Αν λείπει, βάλε άδεια στη διαχείριση.", None, now)


def active_alerts(for_kiosk: bool, now: datetime | None = None):
    now = now or now_local()
    sql = "SELECT a.*, e.display_name FROM alerts a LEFT JOIN employees e ON e.id=a.employee_id " \
          "WHERE a.resolved_at IS NULL AND a.created_at>=?"
    if for_kiosk:
        sql += " AND a.kiosk_message IS NOT NULL"
    return db.all_rows(sql + " ORDER BY a.id DESC", (now.date().isoformat(),))


def worker(stop: threading.Event) -> None:
    while not stop.wait(15):     # every 15″, so phone alerts come right at their minute
        try:
            check()
        except Exception:
            log.exception("monitor check failed")
