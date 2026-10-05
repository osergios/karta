"""Onboarding period («Περίοδος προσαρμογής»): the card is used exactly as in real life — punches are recorded,
reminders, alerts and reports work — but NOTHING is sent to Ergani until the date the card becomes mandatory.

For a business that has time to get used to the card before it is enforced: you see how everyone copes
(forgotten punches, days without punches…) without a single late or wrong declaration in Ergani.

Rules
  * An ARRIVAL made while the period runs is stored with status 'onboarding' (never sent).
  * A DEPARTURE follows the arrival it closes: if that arrival was 'onboarding', so is the departure (even if the
    period ended in between); if the arrival was sent, the departure is sent. Ergani therefore never receives a
    departure without its arrival, whatever the timing of the switch.
  * The period ends by itself on the «mandatory from» date (or with «Τέλος τώρα» in admin).
Settings: 'onboarding_until' = first mandatory day (ISO date, exclusive end), 'onboarding_since' = start day.
"""
from datetime import date, timedelta

from . import config, db
from .timeutil import now_local

STATUS = "onboarding"
KIOSK_METHODS = ("pin", "qr", "qr_ergani")


def _date(v):
    try:
        return date.fromisoformat(v) if v else None
    except ValueError:
        return None


def until() -> date | None:
    """The first day the card is mandatory (punches are sent from then on), whether the period is running or over."""
    return _date(db.setting("onboarding_until"))


def since() -> date | None:
    return _date(db.setting("onboarding_since"))


def active(today: date | None = None) -> bool:
    u = until()
    return bool(u and (today or now_local().date()) < u)


def info(today: date | None = None) -> dict | None:
    """What the kiosk and admin show. None when there is no onboarding period and it did not just end."""
    today = today or now_local().date()
    u = until()
    if u is None:
        return None
    if today < u:
        return {"active": True, "until": u.isoformat(), "last_day": (u - timedelta(days=1)).isoformat(),
                "days_left": (u - today).days, "since": (since() or today).isoformat()}
    if today == u:   # the first mandatory day: a friendly reminder on the shop screen
        return {"active": False, "golive_today": True, "until": u.isoformat(),
                "sending": config.ERGANI_MODE != "dry_run"}
    return None


def set_period(start: date | None, end: date | None) -> None:
    """end = first mandatory day; None = the period ends now (from today everything is sent)."""
    today = now_local().date()
    with db.tx() as c:
        if end is None:
            if active(today):
                c.execute("UPDATE settings SET value=? WHERE key='onboarding_until'", (today.isoformat(),))
            return
        for k, v in (("onboarding_until", end.isoformat()), ("onboarding_since", (start or today).isoformat())):
            db.put_setting(c, k, v)


def status_for(action: str, closing_arrival) -> str | None:
    """'onboarding' when this new movement must stay in karta only, else None (normal sending).
    closing_arrival = the open ARRIVAL row a DEPARTURE closes (None for an arrival)."""
    if action == "DEPARTURE":
        return STATUS if closing_arrival is not None and closing_arrival["status"] == STATUS else None
    return STATUS if active() else None


def check_alerts(now) -> None:
    """Phone/admin notices: the day before the card becomes mandatory, and on that day."""
    from . import monitor
    u = until()
    if u is None:
        return
    today = now.date()
    real = config.ERGANI_MODE == "production"
    if today == u - timedelta(days=1):
        monitor.raise_alert("onboarding_ending", None, today, "warning",
                            f"Σήμερα είναι η τελευταία ημέρα της περιόδου προσαρμογής. Από αύριο ({u:%d/%m}) η κάρτα "
                            "είναι υποχρεωτική και κάθε χτύπημα "
                            + ("στέλνεται στο ΕΡΓΑΝΗ. Υπενθύμισε στο προσωπικό ότι μετρά κανονικά."
                               if real else f"θα στελνόταν στο ΕΡΓΑΝΗ — αλλά η εφαρμογή είναι σε λειτουργία "
                                            f"{config.ERGANI_MODE}, οπότε τίποτα δεν θα πάει στο πραγματικό ΕΡΓΑΝΗ "
                                            "(«Ρυθμίσεις» → «Επιχείρηση και σύνδεση με το ΕΡΓΑΝΗ» → «Λειτουργία» → "
                                            "«Έναρξη κανονικής λειτουργίας»)."),
                            None, now)
    elif today == u:
        monitor.raise_alert("onboarding_ended", None, today, "info" if real else "urgent",
                            "Από σήμερα η κάρτα είναι υποχρεωτική: κάθε νέο χτύπημα στέλνεται στο ΕΡΓΑΝΗ."
                            if real else f"Η περίοδος προσαρμογής τελείωσε, αλλά η εφαρμογή είναι σε λειτουργία "
                                         f"{config.ERGANI_MODE}: τίποτα δεν πάει στο πραγματικό ΕΡΓΑΝΗ. «Ρυθμίσεις» → "
                                         "«Επιχείρηση και σύνδεση με το ΕΡΓΑΝΗ» → «Λειτουργία» → "
                                         "«Έναρξη κανονικής λειτουργίας».", None, now)


def progress() -> list[dict]:
    """How each active employee copes during the period (from its start until yesterday; punches include today)."""
    from . import report
    s, u = since(), until()
    if s is None or u is None:
        return []
    now = now_local()
    today = now.date()
    end = min(today, u)                      # completed days: start .. end-1
    out = []
    for e in db.all_rows("SELECT id, display_name, last_name, first_name, afm, created_at FROM employees "
                         "WHERE active=1 ORDER BY display_name"):
        if e["afm"] == config.EMPLOYER_AFM:
            continue
        first = max(s, _date((e["created_at"] or "")[:10]) or s)
        lo, hi = first.isoformat(), u.isoformat()
        rows = db.all_rows("SELECT type, status, auth_method FROM movements WHERE employee_id=? AND mode=? "
                           "AND movement_at>=? AND movement_at<?", (e["id"], config.ERGANI_MODE, lo, hi))
        kiosk = [r for r in rows if r["auth_method"] in KIOSK_METHODS]
        fixed = sum(1 for r in rows if r["auth_method"] == "admin")      # forgotten punches entered by you
        days = good = missing = 0
        d = first
        while d < end:
            x = report._day(e, d, today, now)
            if x["show"] and not x["leave"] and not x["shut"]:
                if x["rows"]:
                    days += 1
                    spans_ok = all(r["status"] != "local" for r in x["rows"]) and len(x["rows"]) % 2 == 0
                    if spans_ok and not db.one(
                            "SELECT 1 FROM movements WHERE employee_id=? AND mode=? AND auth_method='admin' "
                            "AND movement_at>=? AND movement_at<? LIMIT 1",
                            (e["id"], config.ERGANI_MODE, d.isoformat(), (d + timedelta(days=1)).isoformat())):
                        good += 1
                elif x["sched"] is not None:
                    missing += 1
            d += timedelta(days=1)
        out.append({"id": e["id"], "name": e["display_name"], "punches": len(kiosk),
                    "qr": sum(1 for r in kiosk if r["auth_method"] != "pin"),
                    "fixed": fixed, "days": days, "good_days": good, "missing_days": missing})
    return out
