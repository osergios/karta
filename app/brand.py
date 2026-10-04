"""The business the card runs for (admin «Στοιχεία επιχείρησης»): name, short name, colour and logo.

Nothing about a specific shop is written in the code: the pages are filled in when served, the colours come
from /brand.css and the logo from /brand/logo (stored in the database, so it travels with the backups).
"""
import base64
import html
import json

from . import db

DEFAULT_COLOR = "#16897b"
MAX_LOGO_BYTES = 1_000_000
# colours the admin can set (empty = the theme's default); dark_* are "1"/"0"
COLOR_KEYS = ("bg", "side", "ink", "in", "out")
DEFAULTS = {"bg": "#f7f5f1", "side": "#ece3d6", "ink": "#232323", "out": "#333333"}
# «Έτοιμα θέματα»: the admin page fills the colours from one of these, then they can be changed one by one
THEMES = {
    "karta": {"label": "Karta (τιρκουάζ)", "color": DEFAULT_COLOR},
    "ocean": {"label": "Θάλασσα (μπλε)", "color": "#1f5fae", "bg": "#f4f7fb", "side": "#dfe8f3", "out": "#22344d"},
    "burgundy": {"label": "Μπορντό", "color": "#8c2a3c", "bg": "#faf6f5", "side": "#efe1df", "out": "#3a2328"},
    "olive": {"label": "Ελιά (πράσινο)", "color": "#4f7a28", "bg": "#f7f8f2", "side": "#e5ead8", "out": "#2f3a24"},
    "terracotta": {"label": "Τερακότα", "color": "#b0502a", "bg": "#fbf6f2", "side": "#f1e2d6", "out": "#3d2a20"},
    "graphite": {"label": "Γραφίτης", "color": "#3d4a57", "bg": "#f5f6f7", "side": "#e2e5e8", "out": "#1f262d"},
    "night": {"label": "Νύχτα (σκούρο)", "color": "#2fa898", "dark_kiosk": "1", "dark_admin": "1"},
}
_KEYS = ("brand_name", "brand_short", "brand_color", "brand_theme", "brand_dark_kiosk", "brand_dark_admin",
         *(f"brand_{k}" for k in COLOR_KEYS))


def get() -> dict:
    vals = {r["key"]: r["value"] for r in db.all_rows(
        f"SELECT key, value FROM settings WHERE key IN ({','.join('?' * (len(_KEYS) + 1))})", (*_KEYS, "brand_logo_type"))}
    name = (vals.get("brand_name") or "").strip()
    short = (vals.get("brand_short") or "").strip() or name
    color = vals.get("brand_color") or DEFAULT_COLOR
    return {"name": name, "short": short, "color": color, "has_logo": bool(vals.get("brand_logo_type")),
            "theme": vals.get("brand_theme") or "", **{k: vals.get(f"brand_{k}") or "" for k in COLOR_KEYS},
            "dark_kiosk": vals.get("brand_dark_kiosk") == "1", "dark_admin": vals.get("brand_dark_admin") == "1",
            "themes": {k: v for k, v in THEMES.items()}, "defaults": DEFAULTS}


_put = db.put_setting


def set_info(name: str, short: str, color: str, colors: dict | None = None) -> None:
    """Name, short name and main colour; `colors` (optional) sets the other colours, the theme and dark mode:
    a key that is missing stays as it is, an empty colour means the default."""
    with db.tx() as c:
        _put(c, "brand_name", name.strip())
        _put(c, "brand_short", short.strip())
        _put(c, "brand_color", color.lower())
        for k, v in (colors or {}).items():
            if k in COLOR_KEYS or k == "theme":
                _put(c, f"brand_{k}", (v or "").lower())
            elif k in ("dark_kiosk", "dark_admin"):
                _put(c, f"brand_{k}", "1" if v else "0")


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


def _blend(a: str, b: str, t: float) -> str:
    """t=0: a, t=1: b."""
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(_rgb(a), _rgb(b)))


def _mix(h: str, t: float) -> str:
    """Mix the colour with white (t=0: the colour, t=1: white)."""
    return _blend(h, "#ffffff", t)


def _lum(h: str) -> float:
    c = [v / 255 for v in _rgb(h)]
    c = [v / 12.92 if v <= .03928 else ((v + .055) / 1.055) ** 2.4 for v in c]
    return .2126 * c[0] + .7152 * c[1] + .0722 * c[2]


def contrast(a: str, b: str) -> float:
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + .05) / (lb + .05)


def on(h: str) -> str:
    """Readable text colour on a background: near-black or white, whichever contrasts more."""
    return "#0c1a17" if contrast(h, "#0c1a17") >= contrast(h, "#ffffff") else "#ffffff"


def _vars(d: dict) -> str:
    return " ".join(f"--{k}: {v};" for k, v in d.items())


DARK = {"bg": "#14191a", "side": "#1c2224", "panel": "#232a2c", "panel-2": "#2b3436", "line": "#364043",
        "ink": "#eef1f0", "ink-soft": "#a9b4b2", "charcoal": "#0d1112", "warn-bg": "#3a2f1c", "warn-ink": "#f0c27a",
        "bad-bg": "#3e2323", "bad-ink": "#f3b4b4", "glass": "rgba(255, 255, 255, .07)"}


def css() -> str:
    """Colour variables for the kiosk, the phone card and the admin page. With the default colour and nothing
    else changed, the original palette stays untouched."""
    b = get()
    c = b["color"]
    out = f":root {{ --brand: {c}; }}\n"
    custom = any(b[k] for k in COLOR_KEYS)
    if c.lower() != DEFAULT_COLOR or custom:
        bg, side, ink = b["bg"] or DEFAULTS["bg"], b["side"] or DEFAULTS["side"], b["ink"] or DEFAULTS["ink"]
        teal = _mix(c, .3)
        k = {"teal": teal, "teal-deep": c, "teal-pale": _mix(c, .86), "on-teal": on(teal),
             "aura1": "rgba({}, {}, {}, .33)".format(*_rgb(teal)), "aura3": "rgba({}, {}, {}, .20)".format(*_rgb(c)),
             "shadow-teal": "0 1px 2px rgba({0}, {1}, {2}, .18), 0 10px 24px -10px rgba({0}, {1}, {2}, .45)".format(*_rgb(c))}
        if custom:
            k.update({"bg": bg, "side": side, "ink": ink, "ink-soft": _blend(ink, bg, .38),
                      "panel-2": _blend(side, "#ffffff", .35), "line": _blend(side, ink, .07)})
        if b["in"]:
            k.update({"in": b["in"], "on-in": on(b["in"])})
        if b["out"]:
            k.update({"out": b["out"], "on-out": on(b["out"])})
        out += f":root {{ {_vars(k)} }}\n"
        a = {"accent": c, "accent-pale": _mix(c, .86), "on-accent": on(c)}
        if custom:
            a.update({"page": bg, "sand": side, "ink": ink, "ink-soft": _blend(ink, bg, .38),
                      "line": _blend(side, ink, .07), "th": _blend(bg, "#ffffff", .5), "salon": _blend(side, "#ffffff", .6)})
        out += f"body.admin {{ {_vars(a)} }}\n"
    if b["dark_kiosk"]:
        teal = _mix(c, .2)
        k = {**DARK, "teal": teal, "teal-deep": _mix(c, .45), "teal-pale": _blend(c, DARK["bg"], .78),
             "on-teal": on(teal), "in": b["in"] or teal, "on-in": on(b["in"] or teal),
             "out": b["out"] or "#4a5559", "on-out": on(b["out"] or "#4a5559"),
             "shadow": "0 1px 2px rgba(0, 0, 0, .3)", "shadow-teal": "0 8px 22px -12px rgba(0, 0, 0, .7)"}
        out += f"html.kiosk-page {{ {_vars(k)} color-scheme: dark; }}\nhtml.kiosk-page .aura {{ display: none; }}\n"
    if b["dark_admin"]:
        acc = _mix(c, .25)
        a = {"page": "#14191a", "surface": "#1f2527", "ink": "#eef1f0", "ink-soft": "#a9b4b2", "line": "#343d40",
             "accent": acc, "accent-pale": _blend(c, "#14191a", .8), "on-accent": on(acc), "sand": "#252c2e",
             "charcoal": "#0b0e0f", "th": "#1a2022", "salon": "#20272a", "warn-bg": "#3a2f1c", "warn-ink": "#f0c27a",
             "bad-bg": "#3e2323"}
        out += f"body.admin {{ {_vars(a)} color-scheme: dark; }}\n"
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
