"""The setup assistant (app/setup.py), with Cloudflare, Ergani and ntfy simulated: nothing leaves the machine."""
import os
import re

import pytest
import requests
from requests.structures import CaseInsensitiveDict

from app import security
from app import setup as wizard

HOST = "karta.example.gr"


def test_afm_rule_matches_the_app():
    for afm in ("123456783", "123456789", "000000000", "094014201", "12345678"):
        assert wizard.valid_afm(afm) == security.valid_afm(afm)


@pytest.mark.parametrize("host, ok", [("karta.example.gr", True), ("example.gr", True), ("karta", False),
                                      ("https://karta.example.gr", False), ("-x.example.gr", False), ("", False)])
def test_hostname(host, ok):
    assert wizard.valid_hostname(host) is ok


def test_pin_key():
    key = wizard.new_pin_key()
    assert wizard.valid_pin_key(key)
    assert not wizard.valid_pin_key("short")


def test_env_round_trip_keeps_values_and_backs_up(tmp_path):
    path = str(tmp_path / ".env")
    env = {"ERGANI_MODE": "dry_run", "EMPLOYER_AFM": "123456783", "ERGANI_PASSWORD": "p@ss=word#1",
           "PUBLIC_ORIGIN": "https://karta.example.gr", "CUSTOM_SETTING": "kept"}
    assert wizard.write_env(path, env) is None
    assert oct(os.stat(path).st_mode & 0o777) == "0o600"
    back = wizard.read_env(path)
    assert back["ERGANI_PASSWORD"] == "p@ss=word#1"
    assert back["CUSTOM_SETTING"] == "kept"
    assert back["CF_ACCESS_AUD"] == ""                         # required keys are always written
    backup = wizard.write_env(path, {**env, "EMPLOYER_AFM": "094014201"})
    assert backup and os.path.exists(backup)
    assert wizard.read_env(backup)["EMPLOYER_AFM"] == "123456783"


def test_written_env_is_accepted_by_the_app_config(tmp_path):
    """What the assistant writes must be readable by docker's env_file and app.config's checks."""
    path = str(tmp_path / ".env")
    wizard.write_env(path, {"ERGANI_MODE": "dry_run", "EMPLOYER_AFM": "123456783", "CF_ACCESS_TEAM_DOMAIN": "t.cloudflareaccess.com",
                            "CF_ACCESS_AUD": "a" * 64, "ADMIN_EMAILS": "me@example.gr",
                            "PUBLIC_ORIGIN": "https://karta.example.gr", "PIN_KEY": wizard.new_pin_key()})
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        assert line == "" or line.startswith("#") or re.fullmatch(r"[A-Z_]+=\S*", line), line


# ------------------------------------------------------------------ Ergani

class _Resp:
    def __init__(self, status=200, data=None, text=""):
        self.status_code, self._data, self.text = status, data, text
        self.headers = CaseInsensitiveDict({"Content-Type": "application/json"})
        self.ok = status < 400

    def json(self):
        return self._data


def test_ergani_login_ok(monkeypatch):
    sent = {}

    def post(url, json=None, **kw):
        sent.update(url=url, **json)
        return _Resp(200, {"accessToken": "t"})
    monkeypatch.setattr(requests, "post", post)
    good, _ = wizard.ergani_login("user", "pass", "02")
    assert good
    assert sent["url"] == wizard.ERGANI_PRODUCTION + "/Authentication"
    assert sent["UserType"] == "02"


def test_ergani_login_rejected(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda url, json=None, **kw: _Resp(401, {"message": "Λάθος κωδικός"}))
    good, msg = wizard.ergani_login("user", "bad", "01")
    assert not good and "απέρριψε" in msg


def test_ergani_unreachable(monkeypatch):
    def post(*a, **kw):
        raise requests.ConnectionError("down")
    monkeypatch.setattr(requests, "post", post)
    good, msg = wizard.ergani_login("user", "pass", "01")
    assert not good and "δεν απαντά" in msg


# ------------------------------------------------------------------ Cloudflare

class FakeCloudflare:
    """Just enough of the Cloudflare API to run cloudflare_auto(), recording every call."""

    def __init__(self, team="shop.cloudflareaccess.com", dns=None, app_policies_fail=False):
        self.headers, self.calls = {}, []
        self.team, self.dns, self.app_policies_fail = team, dns, app_policies_fail
        self.tunnels, self.apps = [], []

    def request(self, method, url, timeout=None, params=None, json=None):
        path = url.replace(wizard.CF_API, "")
        self.calls.append((method, path, params, json))
        r = lambda result: _Resp(200, {"success": True, "result": result})
        err = lambda msg: _Resp(400, {"success": False, "errors": [{"code": 1, "message": msg}]})
        if path == "/zones":
            return r([{"id": "Z1", "name": "example.gr", "account": {"id": "A1"}}] if params["name"] == "example.gr" else [])
        if path == "/accounts/A1/access/organizations":
            return r({"auth_domain": self.team}) if self.team else err("not set up")
        if path == "/accounts/A1/cfd_tunnel" and method == "GET":
            return r(self.tunnels)
        if path == "/accounts/A1/cfd_tunnel" and method == "POST":
            self.tunnels.append({"id": "T1", "name": json["name"]})
            return r(self.tunnels[-1])
        if path == "/accounts/A1/cfd_tunnel/T1/configurations":
            return r({})
        if path == "/accounts/A1/cfd_tunnel/T1/token":
            return r("TUNNEL-TOKEN")
        if path == "/zones/Z1/dns_records" and method == "GET":
            return r([self.dns] if self.dns else [])
        if path.startswith("/zones/Z1/dns_records"):
            self.dns = {"id": "D1", **json}
            return r(self.dns)
        if path == "/accounts/A1/access/apps" and method == "GET":
            return r(self.apps)
        if path == "/accounts/A1/access/apps" and method == "POST":
            self.apps.append({"id": "APP1", "aud": "b" * 64, **json})
            return r(self.apps[-1])
        if path.startswith("/accounts/A1/access/apps/APP1/policies"):
            return err("use reusable policies") if self.app_policies_fail else r([] if method == "GET" else {"id": "P1"})
        if path == "/accounts/A1/access/policies":
            return r({"id": "RP1"})
        if path == "/accounts/A1/access/apps/APP1" and method == "PUT":
            return r({"id": "APP1"})
        return err(f"unexpected {method} {path}")


def test_cloudflare_auto_creates_everything():
    cf = FakeCloudflare()
    out = wizard.cloudflare_auto("token", HOST, ["me@example.gr"], session=cf)
    assert out == {"CF_ACCESS_TEAM_DOMAIN": "shop.cloudflareaccess.com", "CF_ACCESS_AUD": "b" * 64,
                   "TUNNEL_TOKEN": "TUNNEL-TOKEN"}
    ingress = next(j for m, p, _, j in cf.calls if p.endswith("/configurations"))["config"]["ingress"]
    assert ingress[0] == {"hostname": HOST, "service": "http://karta:8000"}
    assert cf.dns["content"] == "T1.cfargotunnel.com" and cf.dns["proxied"] is True
    app = cf.apps[0]
    assert app["domain"] == f"{HOST}/admin" and app["type"] == "self_hosted"
    policy = next(j for m, p, _, j in cf.calls if m == "POST" and p.endswith("/policies"))
    assert policy["include"] == [{"email": {"email": "me@example.gr"}}]
    assert cf.headers["Authorization"] == "Bearer token"


def test_cloudflare_auto_is_safe_to_run_again():
    cf = FakeCloudflare()
    wizard.cloudflare_auto("token", HOST, ["me@example.gr"], session=cf)
    wizard.cloudflare_auto("token", HOST, ["me@example.gr"], session=cf)
    assert len(cf.tunnels) == 1 and len(cf.apps) == 1


def test_cloudflare_auto_uses_reusable_policies_when_needed():
    cf = FakeCloudflare(app_policies_fail=True)
    wizard.cloudflare_auto("token", HOST, ["me@example.gr"], session=cf)
    put = next(j for m, p, _, j in cf.calls if m == "PUT" and p == "/accounts/A1/access/apps/APP1")
    assert put["policies"] == [{"id": "RP1", "precedence": 1}]


def test_cloudflare_auto_needs_zero_trust_first():
    with pytest.raises(wizard.CloudflareError, match="Zero Trust"):
        wizard.cloudflare_auto("token", HOST, ["me@example.gr"], session=FakeCloudflare(team=None))


def test_cloudflare_auto_unknown_domain():
    with pytest.raises(wizard.CloudflareError, match="δεν βρέθηκε"):
        wizard.cloudflare_auto("token", "karta.other.gr", ["me@example.gr"], session=FakeCloudflare())


def test_cloudflare_auto_asks_before_replacing_a_dns_record():
    existing = {"id": "D0", "type": "A", "content": "1.2.3.4"}
    with pytest.raises(wizard.CloudflareError):
        wizard.cloudflare_auto("token", HOST, ["me@example.gr"], session=FakeCloudflare(dns=existing),
                               confirm=lambda q: False)
    cf = FakeCloudflare(dns=dict(existing))
    wizard.cloudflare_auto("token", HOST, ["me@example.gr"], session=cf, confirm=lambda q: True)
    assert any(m == "PUT" and p == "/zones/Z1/dns_records/D0" for m, p, _, _ in cf.calls)


# ------------------------------------------------------------------ check

class FakeWeb:
    def __init__(self, admin_protected=True):
        self.admin_protected = admin_protected

    def get(self, url, timeout=None, allow_redirects=True):
        if url.endswith("/cdn-cgi/access/certs"):
            return _Resp(200, {}, text='{"keys": []}')
        if url.endswith("/healthz"):
            return _Resp(200, {"ok": True, "mode": "dry_run"})
        if url.endswith("/admin"):
            if self.admin_protected:
                r = _Resp(302, None)
                r.headers = CaseInsensitiveDict({"Location": "https://shop.cloudflareaccess.com/cdn-cgi/access/login"})
                return r
            r = _Resp(403, {"detail": "Access token missing"}, text='{"detail":"Access token missing"}')
            return r
        return _Resp(404, {})


def _good_env(tmp_path):
    path = str(tmp_path / ".env")
    wizard.write_env(path, {"ERGANI_MODE": "dry_run", "EMPLOYER_AFM": "123456783",
                            "CF_ACCESS_TEAM_DOMAIN": "shop.cloudflareaccess.com", "CF_ACCESS_AUD": "b" * 64,
                            "ADMIN_EMAILS": "me@example.gr", "PUBLIC_ORIGIN": "https://karta.example.gr",
                            "PIN_KEY": wizard.new_pin_key()})
    return path


def test_check_passes_on_a_good_installation(tmp_path):
    assert wizard.check(_good_env(tmp_path), session=FakeWeb()) == 0


def test_check_catches_an_unprotected_admin_page(tmp_path, capsys):
    assert wizard.check(_good_env(tmp_path), session=FakeWeb(admin_protected=False)) == 1
    assert "ΔΕΝ προστατεύεται" in capsys.readouterr().out


def test_check_catches_bad_values(tmp_path):
    path = str(tmp_path / ".env")
    wizard.write_env(path, {"ERGANI_MODE": "live", "EMPLOYER_AFM": "123456789", "PUBLIC_ORIGIN": "http://x/"})
    assert wizard.check(path, session=FakeWeb()) >= 5


def test_check_without_env(tmp_path):
    assert wizard.check(str(tmp_path / "missing.env"), session=FakeWeb()) == 1
