"""Setup assistant: asks the questions in Greek, checks the answers and writes .env.

    python -m app.setup            interactive setup (writes .env in the current folder)
    python -m app.setup check      checks an existing .env: Ergani login, Cloudflare, the public address...

Runs before Karta is configured, so it must not import app.config (which refuses to start without a
complete .env). Normally started through setup.sh, inside the Karta image, as the host user.
"""
import base64
import getpass
import os
import re
import shutil
import socket
import sys
from datetime import datetime

import requests

ERGANI_PRODUCTION = "https://eservices.yeka.gr/WebServicesAPI/api"
ERGANI_TRIAL = "https://trialv2eservices.yeka.gr/WebServicesAPI/api"
CF_API = "https://api.cloudflare.com/client/v4"
TIMEOUT = 20
TUNNEL_SERVICE = "http://karta:8000"     # the karta service in docker-compose.yml

GREEN, RED, YELLOW, BOLD, END = ("\033[32m", "\033[31m", "\033[33m", "\033[1m", "\033[0m") \
    if sys.stdout.isatty() else ("",) * 5


def ok(msg): print(f"  {GREEN}✓{END} {msg}")
def bad(msg): print(f"  {RED}✗{END} {msg}")
def warn(msg): print(f"  {YELLOW}!{END} {msg}")
def title(msg): print(f"\n{BOLD}{msg}{END}")


# ------------------------------------------------------------------ small checks

def valid_afm(afm: str) -> bool:
    """Greek ΑΦΜ check digit (same rule as app.security.valid_afm)."""
    if not re.fullmatch(r"\d{9}", afm or "") or afm == "000000000":
        return False
    total = sum(int(afm[i]) * (2 ** (8 - i)) for i in range(8))
    return (total % 11) % 10 == int(afm[8])


def valid_hostname(host: str) -> bool:
    labels = (host or "").lower().split(".")
    return len(labels) >= 2 and all(re.fullmatch(r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?", lab) for lab in labels)


def valid_email(email: str) -> bool:
    return bool(re.fullmatch(r"[^@\s,]+@[^@\s,]+\.[^@\s,]+", email or ""))


def new_pin_key() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode()


def valid_pin_key(key: str) -> bool:
    try:
        return len(base64.urlsafe_b64decode(key + "=" * (-len(key) % 4))) == 32
    except (ValueError, TypeError):
        return False


# ------------------------------------------------------------------ .env

ENV_LAYOUT = [
    ("ΕΡΓΑΝΗ", ["ERGANI_MODE", "ERGANI_USERNAME", "ERGANI_PASSWORD", "ERGANI_USER_TYPE",
                "ERGANI_TRIAL_USERNAME", "ERGANI_TRIAL_PASSWORD", "ERGANI_TRIAL_USER_TYPE",
                "EMPLOYER_AFM", "BRANCH_NUMBER", "ERGANI_EMPLOYER_ID"]),
    ("Cloudflare Access (σελίδα διαχείρισης)", ["CF_ACCESS_TEAM_DOMAIN", "CF_ACCESS_AUD", "ADMIN_EMAILS"]),
    ("Εφαρμογή", ["PUBLIC_ORIGIN", "LATE_THRESHOLD_SECONDS", "DEBOUNCE_SECONDS", "PIN_KEY"]),
    ("Ειδοποιήσεις στο κινητό (ntfy)", ["NTFY_URL", "NTFY_TOPIC", "NTFY_TOKEN"]),
    ("Cloudflare Tunnel (docker-compose.yml)", ["TUNNEL_TOKEN", "TUNNEL_PROTOCOL"]),
]


def read_env(path: str) -> dict:
    env = {}
    if not os.path.exists(path):
        return env
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
            v = v[1:-1]
        env[k.strip()] = v
    return env


def render_env(env: dict) -> str:
    out = [f"# Karta: δημιουργήθηκε από τον οδηγό ρύθμισης, {datetime.now():%d/%m/%Y %H:%M}.",
           "# Περιέχει κωδικούς: μην το στείλετε πουθενά. Για αλλαγές: ./setup.sh ή επεξεργασία εδώ.", ""]
    done = set()
    for section, keys in ENV_LAYOUT:
        out.append(f"# ---- {section} ----")
        for k in keys:
            if env.get(k, "") != "" or k in ("ERGANI_MODE", "EMPLOYER_AFM", "CF_ACCESS_TEAM_DOMAIN", "CF_ACCESS_AUD",
                                             "ADMIN_EMAILS", "PUBLIC_ORIGIN", "PIN_KEY"):
                out.append(f"{k}={env.get(k, '')}")
            done.add(k)
        out.append("")
    extra = [k for k in env if k not in done]
    if extra:
        out.append("# ---- Άλλες ρυθμίσεις ----")
        out += [f"{k}={env[k]}" for k in extra]
        out.append("")
    return "\n".join(out)


def write_env(path: str, env: dict) -> str | None:
    """Writes .env (mode 600). An existing file is kept as .env.bak-<date>; returns that name."""
    backup = None
    if os.path.exists(path):
        backup = f"{path}.bak-{datetime.now():%Y%m%d-%H%M%S}"
        shutil.copy2(path, backup)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(render_env(env))
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    return backup


# ------------------------------------------------------------------ Ergani

def ergani_login(username: str, password: str, user_type: str, base_url: str = ERGANI_PRODUCTION) -> tuple[bool, str]:
    """Tries to log in (read-only: nothing is submitted). Returns (ok, message)."""
    os.environ["ERGANI_USER_TYPE"] = user_type        # read by the vendored SDK at login
    from ergani.auth import ErganiAuthentication
    from ergani.exceptions import AuthenticationError
    old = socket.getdefaulttimeout()
    socket.setdefaulttimeout(TIMEOUT)
    try:
        ErganiAuthentication(username, password, base_url=base_url)
        return True, "η σύνδεση στο ΕΡΓΑΝΗ πέτυχε"
    except AuthenticationError as e:
        return False, f"το ΕΡΓΑΝΗ απέρριψε τη σύνδεση: {e}"
    except requests.RequestException as e:
        return False, f"δεν απαντά το ΕΡΓΑΝΗ ({type(e).__name__}). Ελέγξτε τη σύνδεση στο internet."
    finally:
        socket.setdefaulttimeout(old)


# ------------------------------------------------------------------ Cloudflare

class CloudflareError(Exception):
    pass


class Cloudflare:
    """Minimal Cloudflare API client for what Karta needs: tunnel, DNS record, Access application."""

    def __init__(self, token: str, session=None):
        self.s = session or requests.Session()
        self.s.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})

    def call(self, method: str, path: str, **kw):
        try:
            r = self.s.request(method, CF_API + path, timeout=TIMEOUT, **kw)
            data = r.json()
        except (requests.RequestException, ValueError) as e:
            raise CloudflareError(f"δεν απαντά το Cloudflare ({type(e).__name__})")
        if not data.get("success"):
            msgs = "; ".join(f"{e.get('code')}: {e.get('message')}" for e in data.get("errors") or []) or f"HTTP {r.status_code}"
            raise CloudflareError(msgs)
        return data.get("result")

    def zone_for(self, host: str) -> dict:
        labels = host.lower().split(".")
        for i in range(len(labels) - 1):
            zones = self.call("GET", "/zones", params={"name": ".".join(labels[i:])}) or []
            if zones:
                return zones[0]
        raise CloudflareError(f"δεν βρέθηκε το domain του {host} στον λογαριασμό Cloudflare (ή το κλειδί δεν έχει πρόσβαση σε αυτό)")

    def team_domain(self, account: str) -> str | None:
        try:
            org = self.call("GET", f"/accounts/{account}/access/organizations")
        except CloudflareError:
            return None
        return (org or {}).get("auth_domain") or None

    def tunnel(self, account: str, name: str) -> dict:
        found = self.call("GET", f"/accounts/{account}/cfd_tunnel", params={"name": name, "is_deleted": "false"}) or []
        if found:
            return found[0]
        return self.call("POST", f"/accounts/{account}/cfd_tunnel", json={"name": name, "config_src": "cloudflare"})

    def tunnel_token(self, account: str, tunnel_id: str) -> str:
        return self.call("GET", f"/accounts/{account}/cfd_tunnel/{tunnel_id}/token")

    def route(self, account: str, tunnel_id: str, host: str) -> None:
        self.call("PUT", f"/accounts/{account}/cfd_tunnel/{tunnel_id}/configurations",
                  json={"config": {"ingress": [{"hostname": host, "service": TUNNEL_SERVICE},
                                               {"service": "http_status:404"}]}})

    def dns_record(self, zone: str, host: str):
        recs = self.call("GET", f"/zones/{zone}/dns_records", params={"name": host}) or []
        return recs[0] if recs else None

    def set_dns(self, zone: str, host: str, tunnel_id: str, existing=None) -> None:
        body = {"type": "CNAME", "name": host, "content": f"{tunnel_id}.cfargotunnel.com", "proxied": True,
                "comment": "Karta (Cloudflare Tunnel)"}
        if existing:
            self.call("PUT", f"/zones/{zone}/dns_records/{existing['id']}", json=body)
        else:
            self.call("POST", f"/zones/{zone}/dns_records", json=body)

    def access_app(self, account: str, host: str, emails: list[str]) -> dict:
        domain = f"{host}/admin"
        apps = self.call("GET", f"/accounts/{account}/access/apps") or []
        app = next((a for a in apps if (a.get("domain") or "").rstrip("/") == domain), None)
        if app is None:
            app = self.call("POST", f"/accounts/{account}/access/apps",
                            json={"name": "Karta admin", "domain": domain, "type": "self_hosted",
                                  "session_duration": "24h", "app_launcher_visible": False})
        include = [{"email": {"email": e}} for e in emails]
        policy = {"name": "Karta admins", "decision": "allow", "include": include}
        try:
            existing = self.call("GET", f"/accounts/{account}/access/apps/{app['id']}/policies") or []
            if existing:
                self.call("PUT", f"/accounts/{account}/access/apps/{app['id']}/policies/{existing[0]['id']}",
                          json={**policy, "precedence": existing[0].get("precedence", 1)})
            else:
                self.call("POST", f"/accounts/{account}/access/apps/{app['id']}/policies", json={**policy, "precedence": 1})
        except CloudflareError:
            # newer accounts: reusable policies, attached to the application
            pol = self.call("POST", f"/accounts/{account}/access/policies", json=policy)
            self.call("PUT", f"/accounts/{account}/access/apps/{app['id']}",
                      json={"name": app.get("name", "Karta admin"), "domain": domain, "type": "self_hosted",
                            "session_duration": app.get("session_duration", "24h"),
                            "policies": [{"id": pol["id"], "precedence": 1}]})
        return app


def cloudflare_auto(token: str, host: str, emails: list[str], session=None, confirm=None) -> dict:
    """Creates (or reuses) everything Karta needs in Cloudflare. Returns the .env values.
    confirm(question) -> bool is asked before replacing an existing DNS record."""
    cf = Cloudflare(token, session)
    zone = cf.zone_for(host)
    account = zone["account"]["id"]
    ok(f"domain {zone['name']}")
    team = cf.team_domain(account)
    if not team:
        raise CloudflareError("δεν έχει ενεργοποιηθεί το Zero Trust. Ανοίξτε μία φορά dash.cloudflare.com → Zero Trust, "
                              "διαλέξτε team name και το Free πλάνο, και ξανατρέξτε τον οδηγό.")
    ok(f"Zero Trust: {team}")
    tun = cf.tunnel(account, "karta")
    cf.route(account, tun["id"], host)
    ok(f"tunnel «karta» → {host}")
    rec = cf.dns_record(zone["id"], host)
    target = f"{tun['id']}.cfargotunnel.com"
    if rec and rec.get("content") != target:
        if confirm and not confirm(f"Υπάρχει ήδη εγγραφή DNS για το {host} ({rec.get('type')} {rec.get('content')}). Να αντικατασταθεί;"):
            raise CloudflareError(f"η εγγραφή DNS του {host} δεν άλλαξε· διαλέξτε άλλο όνομα (π.χ. karta2.{zone['name']})")
        cf.set_dns(zone["id"], host, tun["id"], rec)
    elif not rec:
        cf.set_dns(zone["id"], host, tun["id"])
    ok(f"διεύθυνση https://{host}")
    app = cf.access_app(account, host, emails)
    ok(f"προστασία της σελίδας διαχείρισης για {', '.join(emails)}")
    return {"CF_ACCESS_TEAM_DOMAIN": team, "CF_ACCESS_AUD": app["aud"],
            "TUNNEL_TOKEN": cf.tunnel_token(account, tun["id"])}


# ------------------------------------------------------------------ questions

def ask(question: str, default: str = "", check=None, error: str = "Μη έγκυρη τιμή, δοκιμάστε ξανά.") -> str:
    while True:
        shown = f" [{default}]" if default else ""
        try:
            value = input(f"  {question}{shown}: ").strip() or default
        except EOFError:
            print(); sys.exit(1)
        if check is None or check(value):
            return value
        bad(error)


def ask_secret(question: str, keep: str = "") -> str:
    hint = " [Enter = κρατάει τον τωρινό]" if keep else ""
    while True:
        value = getpass.getpass(f"  {question}{hint}: ").strip()
        if value or keep:
            return value or keep
        bad("Δεν μπορεί να είναι κενό.")


def yes(question: str, default: bool = True) -> bool:
    d = "Ν/ο" if default else "ν/Ο"
    while True:
        try:
            a = input(f"  {question} ({d}): ").strip().lower()
        except EOFError:
            print(); sys.exit(1)
        if not a:
            return default
        if a in ("ν", "ναι", "nai", "y", "yes"):
            return True
        if a in ("ο", "όχι", "οχι", "o", "oxi", "n", "no"):   # a Latin "n" means no, as in English
            return False
        bad("Γράψτε ν (ναι) ή ο (όχι).")


# ------------------------------------------------------------------ setup

def setup(path: str = ".env") -> int:
    env = read_env(path)
    print(f"{BOLD}Karta: οδηγός ρύθμισης{END}")
    print("Θα σας κάνω μερικές ερωτήσεις και θα γράψω το αρχείο ρυθμίσεων (.env).")
    print("Πατήστε Enter για να κρατήσετε την τιμή σε [αγκύλες]. Ctrl+C για έξοδο χωρίς αλλαγές.")
    if env:
        warn(f"Βρέθηκε υπάρχον {path}: οι τιμές του προτείνονται ως προεπιλογές.")

    print("  Εδώ ρυθμίζεται μόνο η διεύθυνση και το Cloudflare. ΑΦΜ, χρήστης ΕΡΓΑΝΗ, ειδοποιήσεις στο κινητό")
    print("  και λειτουργία ρυθμίζονται μετά, από τη σελίδα διαχείρισης («Ρυθμίσεις»).")
    env.setdefault("ERGANI_MODE", "dry_run")

    title("1/2 · Διεύθυνση και διαχειριστές")
    print("  Η διεύθυνση όπου θα ανοίγει η Karta, π.χ. karta.tokatastimamou.gr (το domain πρέπει να είναι στο Cloudflare).")
    old_host = re.sub(r"^https?://", "", env.get("PUBLIC_ORIGIN", "")).rstrip("/")
    host = ask("Διεύθυνση", old_host, valid_hostname, "Γράψτε ένα όνομα όπως karta.tokatastimamou.gr (χωρίς https://).").lower()
    env["PUBLIC_ORIGIN"] = f"https://{host}"
    print("  Τα email που μπορούν να μπαίνουν στη σελίδα διαχείρισης (το Cloudflare στέλνει εκεί κωδικό σύνδεσης).")
    emails = ask("Email διαχειριστών (χωρισμένα με κόμμα)", env.get("ADMIN_EMAILS", ""),
                 lambda v: v and all(valid_email(e.strip()) for e in v.split(",")), "Γράψτε έγκυρα email.")
    emails_list = [e.strip().lower() for e in emails.split(",")]
    env["ADMIN_EMAILS"] = ",".join(emails_list)

    title("2/2 · Cloudflare (HTTPS, tunnel, προστασία διαχείρισης)")
    env["TUNNEL_PROTOCOL"] = tunnel_protocol(env.get("TUNNEL_PROTOCOL", ""))
    print("  Αυτόματα: δίνετε ένα κλειδί API του Cloudflare και φτιάχνω εγώ το tunnel, τη διεύθυνση")
    print("  και την προστασία της σελίδας διαχείρισης. Πώς φτιάχνεται το κλειδί: δείτε την Εύκολη εγκατάσταση στο wiki.")
    if yes("Να γίνει αυτόματα;"):
        while True:
            token = ask_secret("Κλειδί API του Cloudflare (δεν αποθηκεύεται)")
            try:
                env.update(cloudflare_auto(token, host, emails_list, confirm=yes))
                break
            except CloudflareError as e:
                bad(str(e))
                if not yes("Να το ξαναδοκιμάσουμε;"):
                    print("  Συνεχίζουμε χειροκίνητα.")
                    manual_cloudflare(env)
                    break
    else:
        manual_cloudflare(env)

    if not valid_pin_key(env.get("PIN_KEY", "")):
        env["PIN_KEY"] = new_pin_key()
    backup = write_env(path, env)
    title("Έτοιμο")
    ok(f"Γράφτηκε το {path}" + (f" (το παλιό κρατήθηκε ως {backup})" if backup else ""))
    print(f"  Η σελίδα διαχείρισης: {env['PUBLIC_ORIGIN']}/admin  ·  εκεί, στις «Ρυθμίσεις», συμπληρώστε ΑΦΜ και χρήστη ΕΡΓΑΝΗ.")
    return 0


def tunnel_protocol(current: str = "") -> str:
    """How the tunnel talks to Cloudflare. On a home or shop connection, HTTP/2 (TCP): many home routers handle
    the UDP of QUIC (HTTP/3) badly and pages become slow. On a VPS, auto: QUIC, falling back to HTTP/2."""
    print("  Πού τρέχει η Karta;")
    print("    1) στο κατάστημα ή στο σπίτι (Raspberry Pi, παλιό PC ή laptop, server στο τοπικό δίκτυο)")
    print("    2) σε VPS / cloud server (π.χ. Oracle Cloud)")
    default = "2" if current in ("auto", "quic") else "1"
    choice = ask("Επιλογή", default, lambda v: v in ("1", "2"), "Γράψτε 1 ή 2.")
    proto = "http2" if choice == "1" else "auto"
    ok("σύνδεση tunnel: " + ("HTTP/2, η πιο σταθερή με router σπιτιού/καταστήματος" if proto == "http2"
                             else "αυτόματη (QUIC / HTTP/3, με HTTP/2 αν χρειαστεί)"))
    return proto


def manual_cloudflare(env: dict) -> None:
    print("  Ακολουθήστε τα βήματα 4 και 5 της Εύκολης εγκατάστασης στο wiki και δώστε μου τις τιμές:")
    team = ask("Team domain (π.χ. tokatastimamou.cloudflareaccess.com)", env.get("CF_ACCESS_TEAM_DOMAIN", ""),
               lambda v: valid_hostname(re.sub(r"^https?://", "", v).rstrip("/")), "Γράψτε κάτι όπως tokatastimamou.cloudflareaccess.com.")
    env["CF_ACCESS_TEAM_DOMAIN"] = re.sub(r"^https?://", "", team).rstrip("/")
    env["CF_ACCESS_AUD"] = ask("Application Audience (AUD) Tag", env.get("CF_ACCESS_AUD", ""),
                               lambda v: re.fullmatch(r"[0-9a-f]{32,128}", v or ""), "Το AUD είναι μεγάλη σειρά από 0-9 και a-f.")
    env["TUNNEL_TOKEN"] = ask_secret("Token του tunnel", env.get("TUNNEL_TOKEN", ""))


# ------------------------------------------------------------------ check

def check(path: str = ".env", session=None) -> int:
    """Checks an existing .env and the live installation. Returns the number of problems."""
    http = session or requests.Session()
    env = read_env(path)
    problems = 0

    def fail(msg):
        nonlocal problems
        problems += 1
        bad(msg)

    print(f"{BOLD}Karta: έλεγχος ρυθμίσεων ({path}){END}")
    if not env:
        bad(f"Δεν βρέθηκε το {path}. Τρέξτε ./setup.sh")
        return 1

    title("Ρυθμίσεις")
    mode = env.get("ERGANI_MODE", "dry_run")
    (ok if mode in ("dry_run", "trial", "production") else fail)(f"ERGANI_MODE={mode}")
    if env.get("EMPLOYER_AFM"):
        (ok if valid_afm(env["EMPLOYER_AFM"]) else fail)("ΑΦΜ επιχείρησης" + ("" if valid_afm(env["EMPLOYER_AFM"]) else ": μη έγκυρο"))
    for k in ("CF_ACCESS_TEAM_DOMAIN", "CF_ACCESS_AUD", "ADMIN_EMAILS"):
        (ok if env.get(k) else fail)(k + ("" if env.get(k) else ": λείπει"))
    origin = env.get("PUBLIC_ORIGIN", "")
    if re.fullmatch(r"https://[^/\s]+", origin):
        ok(f"PUBLIC_ORIGIN={origin}")
    else:
        fail(f"PUBLIC_ORIGIN «{origin}»: πρέπει να είναι π.χ. https://karta.tokatastimamou.gr (χωρίς / στο τέλος)")
    (ok if valid_pin_key(env.get("PIN_KEY", "")) else warn)("PIN_KEY" + ("" if valid_pin_key(env.get("PIN_KEY", "")) else
                                                              ": λείπει ή δεν είναι έγκυρο (τα PIN δεν θα μπορούν να εμφανιστούν)"))
    if os.path.exists(os.path.join(os.path.dirname(os.path.abspath(path)), "docker-compose.yml")):
        (ok if env.get("TUNNEL_TOKEN") else fail)("TUNNEL_TOKEN" + ("" if env.get("TUNNEL_TOKEN") else ": λείπει"))
        proto = env.get("TUNNEL_PROTOCOL") or "http2"
        (ok if proto in ("http2", "auto", "quic") else fail)(
            f"TUNNEL_PROTOCOL={proto}" + {"http2": " (μηχάνημα στο κατάστημα/σπίτι)", "auto": " (VPS)", "quic": " (VPS)"}.get(proto, ": http2 ή auto"))

    title("ΕΡΓΑΝΗ")
    if mode == "trial" and env.get("ERGANI_TRIAL_USERNAME"):
        creds = (env["ERGANI_TRIAL_USERNAME"], env.get("ERGANI_TRIAL_PASSWORD", ""), env.get("ERGANI_TRIAL_USER_TYPE", "02"), ERGANI_TRIAL)
    else:
        creds = (env.get("ERGANI_USERNAME", ""), env.get("ERGANI_PASSWORD", ""), env.get("ERGANI_USER_TYPE", "01"), ERGANI_PRODUCTION)
    if creds[0] and creds[1]:
        good, msg = ergani_login(*creds)
        (ok if good else fail)(msg)
    else:
        print("  ΑΦΜ, χρήστης ΕΡΓΑΝΗ και λειτουργία ρυθμίζονται στη σελίδα διαχείρισης («Ρυθμίσεις»): εκεί υπάρχει")
        print("  και η «Δοκιμή σύνδεσης». Ό,τι συμπληρώνεται εκεί υπερισχύει του .env.")

    title("Cloudflare και διεύθυνση")
    team = env.get("CF_ACCESS_TEAM_DOMAIN", "")
    if team:
        try:
            r = http.get(f"https://{team}/cdn-cgi/access/certs", timeout=TIMEOUT)
            (ok if r.ok and "keys" in r.text else fail)(f"team domain {team}" + ("" if r.ok else f": HTTP {r.status_code}"))
        except requests.RequestException as e:
            fail(f"team domain {team}: δεν απαντά ({type(e).__name__})")
    if origin.startswith("https://"):
        try:
            r = http.get(origin + "/healthz", timeout=TIMEOUT)
            if r.ok and r.headers.get("content-type", "").startswith("application/json") and r.json().get("ok"):
                ok(f"η Karta απαντά στο {origin} (λειτουργία {r.json().get('mode')})")
            else:
                fail(f"{origin}/healthz: HTTP {r.status_code}. Τρέχει η Karta; (docker compose ps)")
        except requests.RequestException as e:
            fail(f"{origin}: δεν απαντά ({type(e).__name__}). Τρέχει το tunnel; (docker compose logs cloudflared)")
        try:
            r = http.get(origin + "/admin", timeout=TIMEOUT, allow_redirects=False)
            body = r.text if r.headers.get("content-type", "").startswith("application/json") else ""
            if "Access token missing" in body:
                fail("Η σελίδα διαχείρισης ΔΕΝ προστατεύεται από το Cloudflare Access! Ελέγξτε την εφαρμογή Access (διαδρομή admin).")
            elif r.status_code in (301, 302, 303, 307) and "cloudflareaccess.com" in r.headers.get("location", ""):
                ok("η σελίδα διαχείρισης ζητά σύνδεση μέσω Cloudflare Access")
            elif r.status_code in (401, 403):
                ok("η σελίδα διαχείρισης δεν ανοίγει χωρίς σύνδεση")
            else:
                warn(f"η σελίδα διαχείρισης απάντησε HTTP {r.status_code}· ελέγξτε την εφαρμογή Access")
        except requests.RequestException:
            pass

    if env.get("NTFY_URL") and env.get("NTFY_TOPIC"):
        title("Ειδοποιήσεις")
        try:
            r = http.get(env["NTFY_URL"].rstrip("/") + "/v1/health", timeout=TIMEOUT)
            (ok if r.ok else warn)(f"server ntfy {env['NTFY_URL']}" + ("" if r.ok else f": HTTP {r.status_code}"))
        except requests.RequestException as e:
            warn(f"server ntfy {env['NTFY_URL']}: δεν απαντά ({type(e).__name__})")

    title("Αποτέλεσμα")
    if problems:
        bad(f"{problems} πρόβλημα(τα). Διορθώστε τα με ./setup.sh ή στο {path}, και ξανατρέξτε ./setup.sh check")
    else:
        ok("όλα εντάξει")
    return problems


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    path = ".env"
    if "--env" in args:
        i = args.index("--env")
        path = args[i + 1]
        del args[i:i + 2]
    cmd = args[0] if args else "setup"
    try:
        if cmd == "setup":
            return setup(path)
        if cmd == "check":
            return 1 if check(path) else 0
    except KeyboardInterrupt:
        print("\nΔιακόπηκε. Δεν άλλαξε τίποτα.")
        return 130
    print("Χρήση: python -m app.setup [setup|check] [--env .env]")
    return 2


if __name__ == "__main__":
    sys.exit(main())
