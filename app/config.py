"""Configuration from environment. Fails fast on anything missing or unsafe."""
import os
import re
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Athens")


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _require(name: str) -> str:
    value = _get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


# Where card movements go is decided by ERGANI_MODE alone:
#   dry_run    -> nothing is ever sent (the Ergani *read* services use production, read-only)
#   trial      -> Ergani II test environment: submissions are stamped «ΑΚΥΡΟ», no legal effect
#   production -> the real thing
MODES = ("dry_run", "trial", "production")
ERGANI_URLS = {
    "trial": "https://trialv2eservices.yeka.gr/WebServicesAPI/api",
    "production": "https://eservices.yeka.gr/WebServicesAPI/api",
}

# The settings below can also be changed from the admin page («Ρυθμίσεις»). Those values are kept in the
# database (app/appconfig.py) and take precedence over .env; apply() recomputes everything derived.
EDITABLE = ("ERGANI_MODE", "EMPLOYER_AFM", "BRANCH_NUMBER", "ERGANI_EMPLOYER_ID", "TIME_DECLARATION",
            "ERGANI_USERNAME", "ERGANI_PASSWORD", "ERGANI_USER_TYPE",
            "ERGANI_TRIAL_USERNAME", "ERGANI_TRIAL_PASSWORD", "ERGANI_TRIAL_USER_TYPE",
            "NTFY_URL", "NTFY_TOPIC", "NTFY_TOKEN")
ENV_VALUES = {k: _get(k) for k in EDITABLE}
VALUES: dict = {}          # the effective raw values (.env overridden by the admin page)


def apply(overrides: dict | None = None) -> None:
    """Sets the module-level settings from .env, overridden by the values saved in the admin page."""
    global ERGANI_MODE, ERGANI_BASE_URL, ERGANI_HOST, ERGANI_USERNAME, ERGANI_PASSWORD, ERGANI_USER_TYPE
    global EMPLOYER_AFM, ERGANI_EMPLOYER_ID, BRANCH_NUMBER, NTFY_URL, NTFY_TOPIC, NTFY_TOKEN, RETRO
    v = {**ENV_VALUES, **(overrides or {})}
    VALUES.clear()
    VALUES.update(v)
    ERGANI_MODE = v["ERGANI_MODE"] or "dry_run"
    if ERGANI_MODE not in MODES:
        raise RuntimeError("ERGANI_MODE must be one of: dry_run, trial, production")
    ERGANI_BASE_URL = ERGANI_URLS["trial" if ERGANI_MODE == "trial" else "production"]
    ERGANI_HOST = ERGANI_BASE_URL.split("/")[2]
    # The test environment has its own users (created in trialv2eservices.yeka.gr with TaxisNet).
    # Login type sent to /Authentication: 01 = external/API user, 02 = «ΕΡΓΑΝΗ» branch user
    # (created under «Εξωτερικοί Χρήστες Παραρτημάτων»; the usual kind in the test environment).
    if ERGANI_MODE == "trial" and v["ERGANI_TRIAL_USERNAME"]:
        ERGANI_USERNAME, ERGANI_PASSWORD = v["ERGANI_TRIAL_USERNAME"], v["ERGANI_TRIAL_PASSWORD"]
        ERGANI_USER_TYPE = v["ERGANI_TRIAL_USER_TYPE"] or "02"
    else:
        ERGANI_USERNAME, ERGANI_PASSWORD = v["ERGANI_USERNAME"], v["ERGANI_PASSWORD"]
        ERGANI_USER_TYPE = v["ERGANI_USER_TYPE"] or "01"
    if ERGANI_USER_TYPE not in ("01", "02"):
        raise RuntimeError("ERGANI_USER_TYPE / ERGANI_TRIAL_USER_TYPE must be 01 (API user) or 02 (ΕΡΓΑΝΗ branch user)")
    os.environ["ERGANI_USER_TYPE"] = ERGANI_USER_TYPE   # read by the (patched) SDK at login
    EMPLOYER_AFM = v["EMPLOYER_AFM"]
    # Optional: the employer's system id in Ergani (the "id:" in Ergani's employee QR). When set, an Ergani QR
    # from another employer is refused at the kiosk.
    ERGANI_EMPLOYER_ID = v["ERGANI_EMPLOYER_ID"]
    BRANCH_NUMBER = int(v["BRANCH_NUMBER"] or "0")
    # How the business declares schedule changes and overtime in Ergani (its own choice there; the retrospective system exists since 1/7/2024):
    # "advance" (προαναγγελία, the default) before they happen, or "retro" (απολογιστικό σύστημα, businesses on the
    # digital card) afterwards, by the end of the next month, from the card's punches. It changes Karta's alerts.
    RETRO = v["TIME_DECLARATION"] == "retro"
    # Phone alerts (optional), through an ntfy server and topic.
    NTFY_URL = v["NTFY_URL"].rstrip("/")
    NTFY_TOPIC = v["NTFY_TOPIC"]
    NTFY_TOKEN = v["NTFY_TOKEN"]


def problems() -> list[str]:
    """What stops the current mode from working (empty in dry_run with nothing filled in)."""
    out = []
    if ERGANI_MODE != "dry_run":
        trial = " (ή ERGANI_TRIAL_*)" if ERGANI_MODE == "trial" else ""
        for n, val in (("ERGANI_USERNAME", ERGANI_USERNAME), ("ERGANI_PASSWORD", ERGANI_PASSWORD)):
            if not val:
                out.append(f"Λείπει το {n}{trial}")
        if not EMPLOYER_AFM:
            out.append("Λείπει το ΑΦΜ του εργοδότη (EMPLOYER_AFM)")
    if EMPLOYER_AFM and not re.fullmatch(r"\d{9}", EMPLOYER_AFM):
        out.append("Το ΑΦΜ του εργοδότη (EMPLOYER_AFM) πρέπει να έχει 9 ψηφία")
    return out


apply()
_url_env = _get("ERGANI_BASE_URL").rstrip("/")
if _url_env and _url_env.lower() != ERGANI_BASE_URL.lower() and ERGANI_MODE != "dry_run":
    raise RuntimeError(f"ERGANI_BASE_URL={_url_env} does not match ERGANI_MODE={ERGANI_MODE} "
                       f"(expected {ERGANI_BASE_URL}). Remove the ERGANI_BASE_URL line: the mode picks the URL.")

CF_ACCESS_TEAM_DOMAIN = _require("CF_ACCESS_TEAM_DOMAIN").removeprefix("https://").rstrip("/")
CF_ACCESS_AUD = _require("CF_ACCESS_AUD")
ADMIN_EMAILS = {e.strip().lower() for e in _require("ADMIN_EMAILS").split(",") if e.strip()}

PUBLIC_ORIGIN = _get("PUBLIC_ORIGIN", "http://localhost:8000").rstrip("/")
DB_PATH = _get("DB_PATH", "/data/workcard.db")
LATE_THRESHOLD_SECONDS = int(_get("LATE_THRESHOLD_SECONDS", "120"))
DEBOUNCE_SECONDS = int(_get("DEBOUNCE_SECONDS", "60"))

# Security knobs (not meant to be changed casually)
PIN_MAX_FAILS = 5
PIN_LOCK_MINUTES = 5
ENROLL_CODE_MINUTES = 10
DEVICE_COOKIE = "wc_device"
DEVICE_COOKIE_MAX_AGE = 400 * 24 * 3600  # browsers cap cookies at 400 days
MAX_SUBMIT_ATTEMPTS = 30

# Optional: lets the admin view current PINs. 32-byte key, urlsafe base64, in .env (and inside every cloud
# snapshot, see restored_pin_key_path). Without it PINs are hash-only and cannot be shown.
PIN_KEY = _get("PIN_KEY")


def restored_pin_key_path() -> str:
    """A backup restored from the cloud on a new machine brings the PIN_KEY its secrets were sealed with (restore.py).
    It is kept here, next to the database (not inside it), and used instead of the one in .env."""
    return os.path.join(os.path.dirname(os.path.abspath(DB_PATH)), "pin-key")


def _restored_pin_key() -> str | None:
    try:
        with open(restored_pin_key_path(), encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


PIN_KEY = _restored_pin_key() or PIN_KEY
