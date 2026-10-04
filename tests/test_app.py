"""The app starts, its pages load, and the security headers and access checks are in place."""
import pytest


@pytest.mark.parametrize("path", ["/healthz", "/", "/enroll", "/brand.css", "/manifest.webmanifest",
                                  "/sw.js", "/favicon.ico", "/robots.txt", "/static/kiosk.js",
                                  "/static/cardart.js", "/static/style.css"])
def test_public_pages_load(client, path):
    assert client.get(path).status_code == 200


def test_health_reports_dry_run(client):
    assert client.get("/healthz").json() == {"ok": True, "mode": "dry_run"}


def test_security_headers(client):
    h = client.get("/").headers
    assert "script-src 'self'" in h["content-security-policy"]
    assert "frame-ancestors 'none'" in h["content-security-policy"]
    assert "noindex" in h["x-robots-tag"]
    assert h["cache-control"] == "no-store"
    assert "camera=(self)" in h["permissions-policy"]


def test_robots_disallow_everything(client):
    assert "Disallow: /" in client.get("/robots.txt").text


def test_admin_requires_cloudflare_access(client):
    assert client.get("/admin").status_code == 403
    assert client.get("/admin/api/overview").status_code == 403


def test_admin_rejects_a_forged_token(client):
    r = client.get("/admin", headers={"cf-access-jwt-assertion": "not.a.jwt"})
    assert r.status_code == 403


def test_admin_page_loads_for_an_admin(client, admin):
    assert client.get("/admin").status_code == 200
    assert client.get("/admin/api/overview").status_code == 200


def test_writes_from_another_site_are_refused(client, admin):
    r = client.post("/admin/api/brand", json={"name": "X", "short": "X", "color": "#16897b"},
                    headers={"origin": "https://evil.example"})
    assert r.status_code == 403
    assert r.json()["detail"] == "Bad origin"


def test_kiosk_api_needs_a_registered_device(client, employee):
    assert client.get("/api/kiosk/employees").status_code == 401


def test_brand_name_reaches_pages_and_manifest(client, admin):
    r = client.post("/admin/api/brand", json={"name": "Demo Business", "short": "Demo", "color": "#16897b"})
    assert r.status_code == 200
    assert "Κάρτα εργασίας · Demo" in client.get("/").text
    assert client.get("/manifest.webmanifest").json()["name"] == "Κάρτα εργασίας · Demo"


def test_no_logo_means_not_found(client):
    assert client.get("/brand/logo").status_code == 404


def test_default_colours_leave_the_palette_untouched(client):
    assert client.get("/brand.css").text.strip() == ":root { --brand: #16897b; }"


def test_themes_colours_and_dark_mode(client, admin):
    base = {"name": "Demo", "short": "Demo", "color": "#1f5fae"}
    r = client.post("/admin/api/brand", json={**base, "theme": "ocean", "bg": "#f4f7fb", "side": "#dfe8f3", "ink": "",
                                              "in_color": "#ffcc00", "out_color": "", "dark_kiosk": True, "dark_admin": False})
    assert r.status_code == 200
    css = client.get("/brand.css").text
    assert "--bg: #f4f7fb;" in css and "--in: #ffcc00;" in css and "--on-in: #0c1a17;" in css   # dark text on yellow
    assert "html.kiosk-page {" in css and "color-scheme: dark" in css
    assert "body.admin { --page: #14191a" not in css                                        # admin stays light
    client.post("/admin/api/brand", json=base)                                               # name/colour only: the rest stays
    d = client.get("/admin/api/overview").json()["brand"]
    assert d["theme"] == "ocean" and d["in"] == "#ffcc00" and d["dark_kiosk"] and not d["dark_admin"]
    assert client.post("/admin/api/brand", json={**base, "bg": "red"}).status_code == 422
