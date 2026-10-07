"""Settings the admin changes from the admin page («Ρυθμίσεις»): business, Ergani users, mode, phone alerts.

They are stored in the settings table as "cfg.<NAME>" and take precedence over .env (a saved empty value
clears what .env says). Passwords and the ntfy token are encrypted with PIN_KEY; without PIN_KEY they can
only be set in .env. Changing the mode needs the employer's ΑΦΜ typed again and, for trial/production, a
successful login to that Ergani environment first.
"""
import logging
import os
import re
from urllib.parse import urlparse

from . import config, db, security

log = logging.getLogger("workcard.appconfig")

PREFIX = "cfg."
SECRETS = ("ERGANI_PASSWORD", "ERGANI_TRIAL_PASSWORD", "NTFY_TOKEN")
GROUPS = {
    "business": ("EMPLOYER_AFM", "BRANCH_NUMBER", "ERGANI_EMPLOYER_ID", "TIME_DECLARATION"),
    "ergani": ("ERGANI_USERNAME", "ERGANI_PASSWORD", "ERGANI_USER_TYPE"),
    "trial": ("ERGANI_TRIAL_USERNAME", "ERGANI_TRIAL_PASSWORD", "ERGANI_TRIAL_USER_TYPE"),
    "ntfy": ("NTFY_URL", "NTFY_TOPIC", "NTFY_TOKEN"),
}
GROUPS["company"] = GROUPS["business"] + GROUPS["ergani"]      # «Επιχείρηση»: both, saved together


class ConfigError(ValueError):
    pass


def _aad(name: str) -> bytes:
    return f"karta-cfg-{name}".encode()


def saved() -> dict:
    """The values saved from the admin page (secrets decrypted). Unreadable secrets are skipped."""
    out = {}
    for r in db.all_rows("SELECT key, value FROM settings WHERE key LIKE 'cfg.%'"):
        name = r["key"][len(PREFIX):]
        if name not in config.EDITABLE:
            continue
        value = r["value"]
        if name in SECRETS and value:
            value = security.open_pin(value, _aad(name))
            if value is None:
                log.error("Cannot decrypt the saved %s (PIN_KEY changed?); using .env instead", name)
                continue
        out[name] = value
    return out


def load() -> None:
    """Applies the saved values on top of .env (at start-up and after every change)."""
    config.apply(saved())
    from . import submitter
    submitter.reset_client()


def source(name: str) -> str:
    return "gui" if db.setting(PREFIX + name) is not None else ("env" if config.ENV_VALUES.get(name) else "")


# ---------- validation ----------
def _afm(v: str) -> str:
    if v and not security.valid_afm(v):
        raise ConfigError("Το ΑΦΜ δεν είναι έγκυρο (9 ψηφία, με σωστό ψηφίο ελέγχου).")
    return v


def _branch(v: str) -> str:
    if not re.fullmatch(r"\d{1,4}", v or "0"):
        raise ConfigError("Ο αριθμός παραρτήματος είναι αριθμός, συνήθως 0.")
    return str(int(v or "0"))


def _user_type(v: str) -> str:
    if v not in ("", "01", "02"):
        raise ConfigError("Τύπος χρήστη: 01 (χρήστης API) ή 02 (χρήστης ΕΡΓΑΝΗ παραρτήματος).")
    return v


def _declaration(v: str) -> str:
    if v not in ("", "advance", "retro"):
        raise ConfigError("Σύστημα δήλωσης: προαναγγελία ή απολογιστικό.")
    return v


def _url(v: str) -> str:
    v = v.rstrip("/")
    if v and (urlparse(v).scheme not in ("http", "https") or not urlparse(v).netloc):
        raise ConfigError("Η διεύθυνση του server ntfy πρέπει να είναι π.χ. https://ntfy.sh")
    return v


def _topic(v: str) -> str:
    if v and not re.fullmatch(r"[A-Za-z0-9_-]{6,64}", v):
        raise ConfigError("Το θέμα (topic) έχει γράμματα, αριθμούς, - ή _ (6 έως 64).")
    return v


def _text(limit: int):
    def check(v: str) -> str:
        if len(v) > limit or any(ord(ch) < 32 for ch in v):
            raise ConfigError("Μη έγκυρη τιμή.")
        return v
    return check


CHECKS = {
    "EMPLOYER_AFM": _afm, "BRANCH_NUMBER": _branch, "ERGANI_EMPLOYER_ID": _text(40), "TIME_DECLARATION": _declaration,
    "ERGANI_USERNAME": _text(100), "ERGANI_PASSWORD": _text(200), "ERGANI_USER_TYPE": _user_type,
    "ERGANI_TRIAL_USERNAME": _text(100), "ERGANI_TRIAL_PASSWORD": _text(200), "ERGANI_TRIAL_USER_TYPE": _user_type,
    "NTFY_URL": _url, "NTFY_TOPIC": _topic, "NTFY_TOKEN": _text(200),
}


def save(group: str, values: dict, admin: str) -> None:
    """Saves one group of settings. A secret left as None keeps its current value."""
    names = GROUPS.get(group)
    if names is None:
        raise ConfigError("Άγνωστη ομάδα ρυθμίσεων.")
    clean = {}
    for name in names:
        v = values.get(name)
        if v is None and name in SECRETS:
            # "unchanged". A secret that exists only in .env goes into the database too (encrypted): only the
            # database is in the backups, so a new machine restored from them would not have it.
            if source(name) == "env" and config.PIN_KEY:
                clean[name] = config.ENV_VALUES[name]
            continue
        clean[name] = CHECKS[name](str(v or "").strip())
    if group == "ntfy" and bool(clean.get("NTFY_URL")) != bool(clean.get("NTFY_TOPIC")):
        raise ConfigError("Συμπλήρωσε και τον server και το θέμα, ή άφησέ τα και τα δύο κενά.")
    if "EMPLOYER_AFM" in names and config.ERGANI_MODE != "dry_run" and not clean.get("EMPLOYER_AFM"):
        raise ConfigError("Το ΑΦΜ χρειάζεται όσο η Karta στέλνει στο ΕΡΓΑΝΗ.")
    if any(clean.get(n) for n in SECRETS) and not config.PIN_KEY:
        raise ConfigError("Για να φυλαχτεί κωδικός από εδώ χρειάζεται PIN_KEY στο .env (το βάζει ο οδηγός ρύθμισης).")
    for users, mode in (("ergani", "production"), ("trial", "trial")):
        u, p = GROUPS[users][:2]
        if u in names and config.ERGANI_MODE == mode and (not clean.get(u) or not clean.get(p, "keep")):
            raise ConfigError("Η Karta στέλνει με αυτόν τον χρήστη: δεν μπορεί να μείνει κενός.")
    with db.tx() as c:
        for name, v in clean.items():
            db.put_setting(c, PREFIX + name, security.seal_pin(v, _aad(name)) if (name in SECRETS and v) else v)
    load()
    db.audit(admin, "config", f"{group}: " + ", ".join(n for n in clean if n not in SECRETS or clean[n]))


def env_only() -> list[str]:
    """Settings that exist only in .env: the backups (the database) don't have them."""
    return [n for n in config.EDITABLE if source(n) == "env"]


def adopt_env(admin: str) -> list[str]:
    """Copies the settings that exist only in .env into the database (secrets encrypted), so that they are in the
    backups too. They take effect as they are: same values."""
    names = env_only()
    if any(n in SECRETS for n in names) and not config.PIN_KEY:
        raise ConfigError("Για να φυλαχτούν κωδικοί στη βάση χρειάζεται PIN_KEY στο .env (το βάζει ο οδηγός ρύθμισης).")
    with db.tx() as c:
        for n in names:
            v = config.ENV_VALUES[n]
            db.put_setting(c, PREFIX + n, security.seal_pin(v, _aad(n)) if n in SECRETS else v)
    load()
    db.audit(admin, "config_adopt_env", ", ".join(names))
    return names


def view() -> dict:
    """What the admin page shows: values with their source; secrets only as set / not set."""
    out = {}
    for group, names in GROUPS.items():
        if group == "company":           # the same values as business + ergani
            continue
        out[group] = {}
        for n in names:
            v = config.VALUES.get(n, "")
            out[group][n] = {"set": bool(v), "source": source(n)} if n in SECRETS else {"value": v, "source": source(n)}
    out["mode"] = {"value": config.ERGANI_MODE, "source": source("ERGANI_MODE")}
    out["can_store_secrets"] = bool(config.PIN_KEY)
    out["env_only"] = env_only()
    out["problems"] = config.problems()
    return out


# ---------- Ergani login test and mode switch ----------
def creds_for(mode: str) -> tuple[str, str, str, str]:
    v = config.VALUES
    if mode == "trial" and v.get("ERGANI_TRIAL_USERNAME"):
        return v["ERGANI_TRIAL_USERNAME"], v.get("ERGANI_TRIAL_PASSWORD", ""), v.get("ERGANI_TRIAL_USER_TYPE") or "02", config.ERGANI_URLS["trial"]
    url = config.ERGANI_URLS["trial" if mode == "trial" else "production"]
    return v.get("ERGANI_USERNAME", ""), v.get("ERGANI_PASSWORD", ""), v.get("ERGANI_USER_TYPE") or "01", url


def login_test(username: str, password: str, user_type: str, url: str) -> tuple[bool, str]:
    if not (username and password):
        return False, "Λείπει όνομα χρήστη ή κωδικός."
    from .setup import ergani_login
    try:
        return ergani_login(username, password, user_type, url)
    finally:
        os.environ["ERGANI_USER_TYPE"] = config.ERGANI_USER_TYPE     # the test changed it for its own login


def set_mode(mode: str, afm_typed: str, admin: str) -> None:
    if mode not in config.MODES:
        raise ConfigError("Άγνωστη λειτουργία.")
    if mode == config.ERGANI_MODE:
        return
    if mode != "dry_run":
        if not config.EMPLOYER_AFM:
            raise ConfigError("Συμπλήρωσε πρώτα το ΑΦΜ της επιχείρησης.")
        if (afm_typed or "").strip() != config.EMPLOYER_AFM:
            raise ConfigError("Για επιβεβαίωση γράψε ακριβώς το ΑΦΜ της επιχείρησης.")
        ok, msg = login_test(*creds_for(mode))
        if not ok:
            env = "δοκιμαστικό ΕΡΓΑΝΗ" if mode == "trial" else "ΕΡΓΑΝΗ"
            raise ConfigError(f"Δεν έγινε η αλλαγή: η σύνδεση στο {env} απέτυχε ({msg}).")
    old = config.ERGANI_MODE
    with db.tx() as c:
        db.put_setting(c, PREFIX + "ERGANI_MODE", mode)
    load()
    db.audit(admin, "mode", f"{old} -> {mode}")
    log.warning("ERGANI_MODE changed from the admin page: %s -> %s (by %s)", old, mode, admin)
