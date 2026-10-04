"""The vendored Ergani SDK and Karta's one change to it."""
import requests

from ergani.auth import ErganiAuthentication


class _Resp:
    status_code = 200

    def json(self):
        return {"accessToken": "token"}


def _login_payload(monkeypatch, user_type=None):
    sent = {}

    def fake_post(url, json=None, **kw):
        sent.update(json)
        return _Resp()

    monkeypatch.setattr(requests, "post", fake_post)
    if user_type is None:
        monkeypatch.delenv("ERGANI_USER_TYPE", raising=False)
    else:
        monkeypatch.setenv("ERGANI_USER_TYPE", user_type)
    ErganiAuthentication("user", "pass", base_url="https://example.invalid/api")
    return sent


def test_login_uses_the_sdk_default_user_type(monkeypatch):
    assert _login_payload(monkeypatch)["UserType"] == "01"


def test_login_user_type_comes_from_the_environment(monkeypatch):
    assert _login_payload(monkeypatch, "02")["UserType"] == "02"
