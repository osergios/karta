"""The business the card runs for (admin «Στοιχεία επιχείρησης»): name, short name, colour and logo.

Nothing about a specific shop is written in the code: the pages are filled in when served, the colours come
from /brand.css and the logo from /brand/logo (stored in the database, so it travels with the backups).
"""
import base64
import html
import json
from pathlib import Path

from . import db

DEFAULT_COLOR = "#16897b"
MAX_LOGO_BYTES = 1_000_000
_KEYS = ("brand_name", "brand_short", "brand_color")


def get() -> dict:
    vals = {r["key"]: r["value"] for r in db.all_rows(
        "SELECT key, value FROM settings WHERE key IN ('brand_name','brand_short','brand_color','brand_logo_type')")}
    name = (vals.get("brand_name") or "").strip()
    short = (vals.get("brand_short") or "").strip() or name
    color = vals.get("brand_color") or DEFAULT_COLOR
    return {"name": name, "short": short, "color": color, "has_logo": bool(vals.get("brand_logo_type"))}


_put = db.put_setting


def set_info(name: str, short: str, color: str) -> None:
    with db.tx() as c:
        _put(c, "brand_name", name.strip())
        _put(c, "brand_short", short.strip())
        _put(c, "brand_color", color.lower())


def sniff(data: bytes):
    """The image type from its first bytes (PNG / JPEG / WebP only: an SVG could carry scripts)."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def set_logo(data: bytes | None) -> None:
    with db.tx() as c:
        if data is None:
            c.execute("DELETE FROM settings WHERE key IN ('brand_logo', 'brand_logo_type')")
            return
        mime = sniff(data)
        if mime is None or len(data) > MAX_LOGO_BYTES:
            raise ValueError("logo")
        _put(c, "brand_logo", base64.b64encode(data).decode())
        _put(c, "brand_logo_type", mime)


def logo():
    """(bytes, mime) of the uploaded logo, or None."""
    data, mime = db.setting("brand_logo"), db.setting("brand_logo_type")
    if not data or not mime:
        return None
    return base64.b64decode(data), mime


def _rgb(h: str):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def _mix(h: str, t: float) -> str:
    """Mix the colour with white (t=0: the colour, t=1: white)."""
    return "#" + "".join(f"{round(v + (255 - v) * t):02x}" for v in _rgb(h))


def css() -> str:
    """Colour variables for the kiosk, the phone card and the admin page. The default colour keeps the
    original palette untouched."""
    b = get()
    c = b["color"]
    out = f":root {{ --brand: {c}; }}\n"
    if c.lower() != DEFAULT_COLOR:
        out += (f":root {{ --teal: {_mix(c, .3)}; --teal-deep: {c}; --teal-pale: {_mix(c, .86)}; }}\n"
                f"body.admin {{ --accent: {c}; --accent-pale: {_mix(c, .86)}; }}\n")
    return out


def render(text: str) -> str:
    """Fill the brand into a page: {{SUFFIX}} (« · <short name>» or nothing), {{NAME}}, {{SHORT}}."""
    b = get()
    return (text.replace("{{SUFFIX}}", html.escape(f" · {b['short']}") if b["short"] else "")
                .replace("{{NAME}}", html.escape(b["name"]))
                .replace("{{SHORT}}", html.escape(b["short"])))


def manifest(text: str) -> str:
    b = get()
    m = json.loads(text)
    if b["short"]:
        m["name"] = f"Κάρτα εργασίας · {b['short']}"
        m["description"] = f"Ψηφιακή κάρτα εργασίας · {b['name'] or b['short']}"
    else:
        m["name"], m["description"] = "Κάρτα εργασίας", "Ψηφιακή κάρτα εργασίας"
    return json.dumps(m, ensure_ascii=False, indent=2)


def migrate(static_dir: Path) -> None:
    """Once: an install that already has employees keeps the logo that used to be a fixed file
    (static/brand/logo.png). Everything else is filled in at «Στοιχεία επιχείρησης»."""
    if db.one("SELECT 1 FROM settings WHERE key='migr_brand'"):
        return
    existing = db.one("SELECT 1 FROM employees LIMIT 1") is not None
    with db.tx() as c:
        _put(c, "migr_brand", "1")
    old = static_dir / "brand" / "logo.png"
    if existing and old.is_file() and logo() is None:
        try:
            set_logo(old.read_bytes())
        except ValueError:
            pass
