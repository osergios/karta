"""Builds Ergani work-card payloads and submits them (or records them in dry_run)."""
import json
import logging
import threading
from datetime import datetime, timedelta, timezone

import requests.sessions
from ergani.client import ErganiClient
from ergani.exceptions import APIError, AuthenticationError
from ergani.models import CompanyWorkCard, WorkCard

from . import config, db
from .timeutil import now_local

log = logging.getLogger("workcard.submitter")

# The SDK calls requests without a timeout; a hung connection would block the
# queue forever. Give every request made in this process a sane default.
_orig_session_request = requests.sessions.Session.request


def _session_request_with_timeout(self, method, url, *args, **kwargs):
    if kwargs.get("timeout") is None:
        kwargs["timeout"] = (10, 30)
    return _orig_session_request(self, method, url, *args, **kwargs)


requests.sessions.Session.request = _session_request_with_timeout

_submit_lock = threading.Lock()
_client: ErganiClient | None = None


def reset_client() -> None:
    """Forget the Ergani client after the user, password or mode changed in the admin page."""
    global _client
    with _submit_lock:
        _client = None


def _get_client() -> ErganiClient:
    global _client
    if _client is None:
        _client = ErganiClient(config.ERGANI_USERNAME, config.ERGANI_PASSWORD,
                               base_url=config.ERGANI_BASE_URL)
    return _client


def build_payload(row, late_justification: str | None) -> list[CompanyWorkCard]:
    movement_dt = datetime.fromisoformat(row["movement_at"])
    card = WorkCard(
        employee_tax_identification_number=row["afm"],
        employee_last_name=row["last_name"],
        employee_first_name=row["first_name"],
        work_card_movement_type=row["type"],
        work_card_submission_date=movement_dt.date(),
        work_card_movement_datetime=movement_dt,
        late_declaration_justification=late_justification,
    )
    return [CompanyWorkCard(
        employer_tax_identification_number=config.EMPLOYER_AFM or "000000000",
        business_branch_number=config.BRANCH_NUMBER,
        card_details=[card],
    )]


def _retry_delay(attempts: int) -> int:
    return min(60 * attempts, 900)


def process(movement_id: int, force: bool = False):
    """Submit one pending movement. Safe to call concurrently (serialized)."""
    with _submit_lock:
        row = db.one(
            """SELECT m.*, e.afm, e.first_name, e.last_name, e.display_name
               FROM movements m JOIN employees e ON e.id = m.employee_id
               WHERE m.id = ?""", (movement_id,))
        if row is None or row["status"] != "pending":
            return row
        # A movement is only ever sent to the environment it was made in: a trial punch must never
        # reach production (and a real punch must never be "used up" on the test server).
        if row["mode"] != config.ERGANI_MODE:
            log.warning("Movement %s was made in %s mode; not sending it in %s mode", movement_id, row["mode"], config.ERGANI_MODE)
            return row
        if not force and row["next_attempt_at"] > db.utc_now_iso():
            return row
        # Missing user, password or ΑΦΜ: hold the queue (attempts are not used up) until it is completed
        # in the admin page. The page shows what is missing.
        if config.ERGANI_MODE != "dry_run" and config.problems():
            return row

        # A movement that could not be sent in (near) real time is declared late.
        late = row["late_justification"]
        age = (now_local() - datetime.fromisoformat(row["movement_at"])).total_seconds()
        if late is None and age > config.LATE_THRESHOLD_SECONDS:
            late = row["pending_reason"] or "EMPLOYER_SYSTEMS_UNAVAILABLE"

        payload = build_payload(row, late)
        wire = json.dumps([p.serialize() for p in payload], ensure_ascii=False, default=str)
        attempts = row["attempts"] + 1

        if config.ERGANI_MODE == "dry_run":
            with db.tx() as c:
                c.execute(
                    """UPDATE movements SET status='dry_run', attempts=?, late_justification=?,
                       response_json=?, submitted_at=?, last_error=NULL WHERE id=?""",
                    (attempts, late, wire, db.utc_now_iso(), movement_id))
            log.info("DRY RUN movement %s: %s", movement_id, wire)
            return db.one("SELECT * FROM movements WHERE id=?", (movement_id,))

        reason = None
        error = None
        result = None
        kind = None      # for the alert: rejected (Ergani said no) / auth / down
        try:
            result = _get_client().submit_work_card(company_work_cards=payload)
        except AuthenticationError as e:
            reason, error, kind = "EMPLOYER_SYSTEMS_UNAVAILABLE", f"AuthenticationError: {e}", "auth"
        except APIError as e:
            code = getattr(getattr(e, "response", None), "status_code", None)
            # the SDK drops the status code from the text of error responses (a Response is falsy on 4xx/5xx)
            reason, error = "ERGANI_SYSTEMS_UNAVAILABLE", f"APIError (HTTP {code}): {e}"
            kind = "down" if code is not None and code >= 500 else "rejected"
            if code == 504:          # gateway gave up waiting: Ergani may still have stored it
                kind = "uncertain"
        except Exception as e:  # network errors, timeouts, parsing
            reason, error, kind = "ERGANI_SYSTEMS_UNAVAILABLE", f"{type(e).__name__}: {e}", "down"
            if _maybe_delivered(e):
                kind = "uncertain"

        if error is None:
            first = result[0] if result else {}
            with db.tx() as c:
                c.execute(
                    """UPDATE movements SET status='submitted', attempts=?, late_justification=?,
                       protocol=?, submission_id=?, response_json=?, submitted_at=?,
                       last_error=NULL WHERE id=?""",
                    (attempts, late, str(first.get("protocol", "")), str(first.get("submission_id", "")),
                     json.dumps(result, ensure_ascii=False, default=str), db.utc_now_iso(), movement_id))
            log.info("Submitted movement %s protocol=%s", movement_id, first.get("protocol"))
        elif kind == "uncertain":
            # The card may already be in Ergani: sending it again would create a duplicate movement.
            # Hold it until the admin checks Ergani and chooses «Υπάρχει στο ΕΡΓΑΝΗ» or «Νέα αποστολή».
            with db.tx() as c:
                c.execute(
                    """UPDATE movements SET status='uncertain', attempts=?, late_justification=?,
                       pending_reason=COALESCE(pending_reason, ?), last_error=? WHERE id=?""",
                    (attempts, late, reason, error[:1000], movement_id))
            log.warning("Movement %s: outcome unknown (%s); held for admin check", movement_id, error)
            try:
                _alert_failure(row, kind, error, attempts)
            except Exception:
                log.exception("failure alert failed")
        else:
            status = "failed" if attempts >= config.MAX_SUBMIT_ATTEMPTS else "pending"
            next_at = (datetime.now(timezone.utc) + timedelta(seconds=_retry_delay(attempts))
                       ).strftime("%Y-%m-%dT%H:%M:%S")
            with db.tx() as c:
                c.execute(
                    """UPDATE movements SET status=?, attempts=?, next_attempt_at=?,
                       pending_reason=COALESCE(pending_reason, ?), last_error=? WHERE id=?""",
                    (status, attempts, next_at, reason, error[:1000], movement_id))
            log.warning("Movement %s attempt %s failed: %s", movement_id, attempts, error)
            try:
                _alert_failure(row, kind, error, attempts)
            except Exception:
                log.exception("failure alert failed")
        return db.one("SELECT * FROM movements WHERE id=?", (movement_id,))


def _maybe_delivered(e: Exception) -> bool:
    """True when the submission request itself may have reached Ergani before failing (the answer
    timed out, the connection dropped mid-response, or Ergani answered 2xx with something we could
    not read). Failures of the login call, or before any connection was made, are safe to retry."""
    import requests
    if isinstance(e, requests.exceptions.JSONDecodeError) or not isinstance(e, requests.exceptions.RequestException):
        # The SDK only parses the answer of a successful (2xx) submission — login errors are raised as
        # AuthenticationError — so a parsing failure (HTML page, unexpected fields/date format) means
        # Ergani accepted the request and we just can't read the protocol number.
        return True
    if isinstance(e, (requests.exceptions.ConnectTimeout, requests.exceptions.SSLError, requests.exceptions.ProxyError)):
        return False
    if not isinstance(e, (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError,
                          requests.exceptions.ChunkedEncodingError)):
        return False
    req = getattr(e, "request", None)
    url = (getattr(req, "url", None) or "").lower()
    if url.endswith("/authentication"):
        return False                        # the login failed; nothing was submitted
    text = str(e)
    if isinstance(e, requests.exceptions.ConnectionError) and not isinstance(e, requests.exceptions.ReadTimeout):
        # refused / DNS (also temporary) / no route: the request never left
        import urllib3
        cause = getattr(e.args[0], "reason", None) if e.args else None
        if isinstance(cause, urllib3.exceptions.NewConnectionError):   # NameResolutionError is a subclass
            return False
        if any(k in text for k in ("NewConnectionError", "Failed to establish", "Name or service not known",
                                   "Temporary failure in name resolution", "NameResolutionError",
                                   "nodename nor servname", "Connection refused", "getaddrinfo")):
            return False
    return True


def _ergani_text(error: str) -> str:
    t = error.split("Error message:", 1)[-1].replace("\\n", " ").replace("\n", " ")
    t = " ".join(t.split())
    if not t:   # Ergani sent no message (e.g. an HTML 504 page): show what we know instead of «»
        t = " ".join(error.split("Error message:", 1)[0].replace("\n", " ").split()).rstrip(":")
    return t[:400]


def uncertain_alert_prefix(movement_id: int) -> str:
    """Alert kind of an uncertain submission is '<prefix><attempt>' (the key adds ':<employee>:<day>')."""
    return f"ergani_uncertain#{movement_id}#"


def _alert_failure(row, kind: str | None, error: str, attempts: int) -> None:
    """Tell the admin (page + phone) as soon as Ergani refuses a punch, so it can be fixed the same day."""
    from . import monitor
    now = now_local()
    what = "προσέλευση" if row["type"] == "ARRIVAL" else "αποχώρηση"
    when = row["movement_at"][11:16]
    test = " [ΔΟΚΙΜΑΣΤΙΚΟ ΕΡΓΑΝΗ]" if row["mode"] == "trial" else ""
    if kind == "rejected":
        monitor.raise_alert("ergani_rejected", row["employee_id"], now.date(), "urgent",
                            f"{row['display_name']}: το ΕΡΓΑΝΗ απέρριψε την {what} {when}{test}: «{_ergani_text(error)}». "
                            "Η κίνηση κρατιέται και ξαναστέλνεται αυτόματα — διόρθωσε το στοιχείο στο ΕΡΓΑΝΗ (π.χ. μέσω λογιστή).",
                            None, now)
    elif kind == "auth":
        monitor.raise_alert("ergani_auth", None, now.date(), "urgent",
                            f"Το ΕΡΓΑΝΗ δεν δέχεται τα στοιχεία σύνδεσης{test}: «{_ergani_text(error)}». "
                            "Οι κινήσεις κρατιούνται και ξαναστέλνονται — έλεγξε χρήστη/κωδικό web services στο .env.", None, now)
    elif kind == "uncertain":
        # one alert per attempt: if a «Νέα αποστολή» times out again the same day, it must alert again
        monitor.raise_alert(f"{uncertain_alert_prefix(row['id'])}{attempts}", row["employee_id"], now.date(), "urgent",
                            f"{row['display_name']}: δεν ξέρουμε αν η {what} {when}{test} έφτασε στο ΕΡΓΑΝΗ "
                            f"(«{_ergani_text(error)[:160]}»). ΔΕΝ ξαναστέλνεται αυτόματα, για να μη γίνει διπλή κίνηση. "
                            "Έλεγξε στο ΕΡΓΑΝΗ και πάτα στη διαχείριση «Υπάρχει στο ΕΡΓΑΝΗ» ή «Νέα αποστολή».", None, now)
    elif kind == "down" and attempts == 3:
        monitor.raise_alert("ergani_down", None, now.date(), "warning",
                            f"Το ΕΡΓΑΝΗ δεν απαντά (3 προσπάθειες για {row['display_name']} {what} {when}){test}. "
                            "Οι κινήσεις κρατιούνται και θα σταλούν μόλις επανέλθει, με αιτιολογία εκπρόθεσμης υποβολής.", None, now)


def worker(stop: threading.Event) -> None:
    while not stop.wait(20):
        try:
            due = db.all_rows(
                "SELECT id FROM movements WHERE status='pending' AND mode=? AND next_attempt_at<=? ORDER BY id LIMIT 20",
                (config.ERGANI_MODE, db.utc_now_iso()))
            for r in due:
                process(r["id"])
        except Exception:
            log.exception("Worker loop error")
