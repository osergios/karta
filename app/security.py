"""PINs, device tokens, AFM validation and Cloudflare Access JWT verification."""
import hashlib
import re
import secrets

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import HTTPException, Request

from . import config

_ph = PasswordHasher()
_ENROLL_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O/1/I/L


def hash_pin(pin: str) -> str:
    return _ph.hash(pin)


def verify_pin(pin_hash: str, pin: str) -> bool:
    try:
        return _ph.verify(pin_hash, pin)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


PIN_LENGTH = 6


def _pin_cipher(pin_key: str | None = None):
    from . import config
    pin_key = pin_key or config.PIN_KEY
    if not pin_key:
        return None
    import base64
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    key = base64.urlsafe_b64decode(pin_key + "=" * (-len(pin_key) % 4))
    if len(key) != 32:
        raise RuntimeError("PIN_KEY must be 32 bytes (urlsafe base64)")
    return AESGCM(key)


def seal_pin(pin: str, aad: bytes = b"workcard-pin") -> str | None:
    """Encrypt a PIN (or QR code) so the admin can view it later; None when PIN_KEY is not configured."""
    aead = _pin_cipher()
    if aead is None:
        return None
    import base64, os
    nonce = os.urandom(12)
    return base64.urlsafe_b64encode(nonce + aead.encrypt(nonce, pin.encode(), aad)).decode()


def open_pin(token: str | None, aad: bytes = b"workcard-pin", pin_key: str | None = None) -> str | None:
    """pin_key: another key than this installation's (checking a backup's key before restoring it)."""
    try:
        aead = _pin_cipher(pin_key)
    except (ValueError, RuntimeError):
        return None
    if aead is None or not token:
        return None
    import base64
    raw = base64.urlsafe_b64decode(token)
    try:
        return aead.decrypt(raw[:12], raw[12:], aad).decode()
    except Exception:
        return None


# ---- personal QR cards: "CK1:" + 128 random bits in base32 (QR alphanumeric mode -> small, easy to scan)
QR_AAD = b"workcard-qr"
_QR_RE = re.compile(r"CK1:[A-Z2-7]{26}")


def new_qr_code() -> str:
    import base64
    return "CK1:" + base64.b32encode(secrets.token_bytes(16)).decode().rstrip("=")


def normalize_qr(text: str | None) -> str | None:
    t = (text or "").strip().upper()
    return t if _QR_RE.fullmatch(t) else None


# Ergani's own personal QR (eservices / myErgani): plain text, no secret, e.g.
# "\ufefferg|nm:ΜΑΡΙΑ;ln:ΠΑΠΑΔΟΠΟΥΛΟΥ;afm:123456789;id:123456"  (id = employer's system id in Ergani)
_ERG_RE = re.compile(r"\ufeff?\s*erg\|(.+)", re.IGNORECASE | re.DOTALL)


def parse_ergani_qr(text: str | None) -> dict | None:
    """{'afm','ln','nm','id'} from an Ergani employee QR, or None if it isn't one."""
    m = _ERG_RE.fullmatch((text or "").strip())
    if not m:
        return None
    kv = {}
    for part in m.group(1).split(";"):
        k, sep, v = part.partition(":")
        if sep:
            kv[k.strip().lower()] = v.strip()
    if not re.fullmatch(r"\d{9}", kv.get("afm", "")) or not kv.get("ln"):
        return None
    return {"afm": kv["afm"], "ln": kv["ln"], "nm": kv.get("nm", ""), "id": kv.get("id", "")}


def name_key(name: str | None) -> str:
    """Compare names ignoring accents, case, spaces and punctuation (ΣΤΡΆΤΗ == Στράτη)."""
    import unicodedata
    t = unicodedata.normalize("NFD", (name or "").upper())
    return "".join(ch for ch in t if ch.isalpha() and not unicodedata.combining(ch))


def qr_svg(code: str) -> str:
    """The QR as an SVG document (no external renderer needed)."""
    import io
    import segno
    buf = io.BytesIO()
    segno.make_qr(code, error="m").save(buf, kind="svg", scale=10, border=2, dark="#232323", light="#ffffff",
                                        xmldecl=False, svgns=True, nl=False)
    return buf.getvalue().decode()


def valid_pin_format(pin: str) -> bool:
    return bool(re.fullmatch(r"\d{%d}" % PIN_LENGTH, pin or ""))


def weak_pin(pin: str) -> bool:
    """Too easy to guess: fewer than 3 different digits, or a straight run like 123456/987654."""
    steps = {int(b) - int(a) for a, b in zip(pin, pin[1:])}
    return len(set(pin)) < 3 or steps in ({1}, {-1})


def generate_pin() -> str:
    """Random 6-digit PIN that is not weak."""
    while True:
        pin = "".join(secrets.choice("0123456789") for _ in range(PIN_LENGTH))
        if not weak_pin(pin):
            return pin


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def new_device_token() -> str:
    return secrets.token_urlsafe(32)


def new_enroll_code() -> str:
    return "".join(secrets.choice(_ENROLL_ALPHABET) for _ in range(8))


def normalize_enroll_code(code: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (code or "").upper())


def valid_afm(afm: str) -> bool:
    """Greek AFM checksum."""
    if not re.fullmatch(r"\d{9}", afm or "") or afm == "000000000":
        return False
    total = sum(int(afm[i]) * (2 ** (8 - i)) for i in range(8))
    return (total % 11) % 10 == int(afm[8])


# ---- Cloudflare Access ----
_jwks = jwt.PyJWKClient(
    f"https://{config.CF_ACCESS_TEAM_DOMAIN}/cdn-cgi/access/certs",
    cache_keys=True,
    headers={"User-Agent": "karta-workcard/1.0"},
    timeout=10,
)


def require_admin(request: Request) -> str:
    """Returns the admin email or raises 403. Fails closed."""
    token = request.headers.get("cf-access-jwt-assertion")
    if not token:
        raise HTTPException(status_code=403, detail="Access token missing")
    try:
        key = _jwks.get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=config.CF_ACCESS_AUD,
            issuer=f"https://{config.CF_ACCESS_TEAM_DOMAIN}",
            options={"require": ["exp", "iat", "aud", "iss"]},
        )
    except Exception:
        raise HTTPException(status_code=403, detail="Invalid access token")
    email = (claims.get("email") or "").lower()
    if email not in config.ADMIN_EMAILS:
        raise HTTPException(status_code=403, detail="Not an admin")
    return email
