import pytest
import requests

from frontend import api_client
from frontend.formatting import (
    fmt_grade, fmt_pct, fmt_points, grafana_panel_url, signal_markdown, similarity_caption,
)


class Resp:
    def __init__(self, status=200, payload=None):
        self.status_code, self._payload = status, payload

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def test_formatting_helpers():
    assert fmt_pct(0.1234) == "12%" and fmt_pct(0.1234, 1) == "12.3%"
    assert fmt_pct(0.18, 0, signed=True) == "+18%" and fmt_pct(None) == "n/a"
    assert fmt_points(-0.0012) == "-0.12 pts" and fmt_grade(0.55) == "+0.6 grades"
    assert signal_markdown("Elevated") == ":red[**Elevated**]"
    assert signal_markdown("whatever") == ":gray[**whatever**]"
    assert "largely unchanged" in similarity_caption(0.95) and "substantially" in similarity_caption(0.4)
    assert grafana_panel_url("http://g:3000/", 2).startswith("http://g:3000/d-solo/filinglens-main/")


def test_client_returns_json_and_uses_env_url(monkeypatch):
    seen = {}

    def fake_get(url, timeout):
        seen["url"] = url
        return Resp(200, {"tickers": []})

    monkeypatch.setenv("BACKEND_URL", "http://api:8000/")
    monkeypatch.setattr(requests, "get", fake_get)
    assert api_client.get_tickers() == {"tickers": []}
    assert seen["url"] == "http://api:8000/tickers"


def test_client_maps_backend_error_to_friendly_message(monkeypatch):
    err = {"error": {"code": "unknown_ticker", "message": "We don't have data for 'ZZZ'."}}
    monkeypatch.setattr(requests, "get", lambda *a, **k: Resp(404, err))
    with pytest.raises(api_client.ApiError) as e:
        api_client.get_analysis("ZZZ")
    assert e.value.code == "unknown_ticker" and "ZZZ" in e.value.message and e.value.status == 404


def test_client_unreachable_and_garbage(monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError("secret-internal-host:8000 refused")

    monkeypatch.setattr(requests, "get", boom)
    with pytest.raises(api_client.ApiError) as e:
        api_client.get_tickers()
    assert e.value.code == "unreachable" and "secret-internal-host" not in e.value.message

    monkeypatch.setattr(requests, "get", lambda *a, **k: Resp(500, None))
    with pytest.raises(api_client.ApiError, match="unexpected"):
        api_client.get_tickers()
