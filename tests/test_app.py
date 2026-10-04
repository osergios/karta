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
