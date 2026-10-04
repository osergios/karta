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


ERGANI_MODE = _get("ERGANI_MODE", "dry_run")
if ERGANI_MODE not in ("dry_run", "trial", "production"):
    raise RuntimeError("ERGANI_MODE must be one of: dry_run, trial, production")

# Where card movements go is decided by ERGANI_MODE alone:
#   dry_run    -> nothing is ever sent (the Ergani *read* services use production, read-only)
#   trial      -> Ergani II test environment: submissions are stamped «ΑΚΥΡΟ», no legal effect
#   production -> the real thing
ERGANI_URLS = {
    "trial": "https://trialv2eservices.yeka.gr/WebServicesAPI/api",
    "production": "https://eservices.yeka.gr/WebServicesAPI/api",
}
_url_env = _get("ERGANI_BASE_URL").rstrip("/")
ERGANI_BASE_URL = ERGANI_URLS["trial" if ERGANI_MODE == "trial" else "production"]
if _url_env and _url_env.lower() != ERGANI_BASE_URL.lower() and ERGANI_MODE != "dry_run":
    raise RuntimeError(f"ERGANI_BASE_URL={_url_env} does not match ERGANI_MODE={ERGANI_MODE} "
                       f"(expected {ERGANI_BASE_URL}). Remove the ERGANI_BASE_URL line: the mode picks the URL.")
ERGANI_HOST = ERGANI_BASE_URL.split("/")[2]

# The test environment has its own users (created in trialv2eservices.yeka.gr with TaxisNet).
# Login type sent to /Authentication: 01 = external/API user, 02 = «ΕΡΓΑΝΗ» branch user
# (created under «Εξωτερικοί Χρήστες Παραρτημάτων»; the usual kind in the test environment).
if ERGANI_MODE == "trial" and _get("ERGANI_TRIAL_USERNAME"):
    ERGANI_USERNAME, ERGANI_PASSWORD = _get("ERGANI_TRIAL_USERNAME"), _get("ERGANI_TRIAL_PASSWORD")
    ERGANI_USER_TYPE = _get("ERGANI_TRIAL_USER_TYPE", "02")
else:
    ERGANI_USERNAME, ERGANI_PASSWORD = _get("ERGANI_USERNAME"), _get("ERGANI_PASSWORD")
    ERGANI_USER_TYPE = _get("ERGANI_USER_TYPE", "01")
if ERGANI_USER_TYPE not in ("01", "02"):
    raise RuntimeError("ERGANI_USER_TYPE / ERGANI_TRIAL_USER_TYPE must be 01 (API user) or 02 (ΕΡΓΑΝΗ branch user)")
os.environ["ERGANI_USER_TYPE"] = ERGANI_USER_TYPE   # read by the (patched) SDK at login
EMPLOYER_AFM = _get("EMPLOYER_AFM")
# Optional: the employer's system id in Ergani (the "id:" in Ergani's employee QR). When set, an Ergani QR
# from another employer is refused at the kiosk.
ERGANI_EMPLOYER_ID = os.environ.get("ERGANI_EMPLOYER_ID", "").strip()
BRANCH_NUMBER = int(_get("BRANCH_NUMBER", "0") or "0")

if ERGANI_MODE != "dry_run":
    for _n, _v in (("ERGANI_USERNAME", ERGANI_USERNAME), ("ERGANI_PASSWORD", ERGANI_PASSWORD), ("EMPLOYER_AFM", EMPLOYER_AFM)):
        if not _v:
            raise RuntimeError(f"Missing required environment variable: {_n}"
                               + (" (or ERGANI_TRIAL_*)" if ERGANI_MODE == "trial" and _n != "EMPLOYER_AFM" else ""))
    if not re.fullmatch(r"\d{9}", EMPLOYER_AFM):
        raise RuntimeError("EMPLOYER_AFM must be exactly 9 digits")

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

# Optional: lets the admin view current PINs. 32-byte key, urlsafe base64, kept ONLY in .env
# (which the DR backup stores encrypted). Without it PINs are hash-only and cannot be shown.
PIN_KEY = _get("PIN_KEY")

# Phone alerts (optional) — same ntfy server/topic as the DR backup alerts.
NTFY_URL = _get("NTFY_URL").rstrip("/")
NTFY_TOPIC = _get("NTFY_TOPIC")
NTFY_TOKEN = _get("NTFY_TOKEN")
