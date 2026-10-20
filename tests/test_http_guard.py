"""Header di sicurezza (API, SPA, /docs) e limite di richieste sugli endpoint costosi."""

import httpx
import pytest

from pachimudeditor.common.http_guard import CSP_APP, CSP_DOCS, is_heavy

SECURITY = {"x-content-type-options": "nosniff", "x-frame-options": "DENY", "referrer-policy": "no-referrer"}


@pytest.mark.parametrize("path", ["/api/auth/token", "/api/zones", "/docs", "/", "/zones"])
async def test_security_headers(anon: httpx.AsyncClient, path: str) -> None:
    """Gli header ci sono su API (anche 401), pagina docs e SPA; /docs ha la CSP piu' larga, il resto quella stretta."""
    response = await anon.get(path)
    for name, value in SECURITY.items():
        assert response.headers[name] == value, path
    csp = response.headers["content-security-policy"]
    assert csp == (CSP_DOCS if path == "/docs" else CSP_APP)
    assert "frame-ancestors 'none'" in csp


def test_which_endpoints_are_heavy() -> None:
    """Solo conversione e import (POST) sono contati."""
    assert is_heavy("POST", "/api/convert/run") and is_heavy("POST", "/api/convert/preview")
    assert is_heavy("POST", "/api/transfer/zones/import") and is_heavy("POST", "/api/transfer/zones/import/")
    assert not is_heavy("GET", "/api/convert/pairs") and not is_heavy("GET", "/api/transfer/zones/1/export")
    assert not is_heavy("POST", "/api/zones")


async def test_heavy_rate_limit(client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Oltre il limite: 429 con `Retry-After` e codice stabile; gli altri endpoint non sono toccati."""
    monkeypatch.setenv("WEBEDITOR_HEAVY_RATE_LIMIT", "2")
    monkeypatch.setenv("WEBEDITOR_HEAVY_RATE_WINDOW", "7919")  # finestra propria: non condivide il contatore con altri test
    body = {"sourceWorld": "x", "targetWorld": "y", "zoneIds": []}
    codes = [(await client.post("/api/convert/preview", json=body)).status_code for _ in range(3)]
    assert codes[:2] != [429, 429] and codes[2] == 429
    limited = await client.post("/api/convert/preview", json=body)
    assert limited.json()["detail"][0]["code"] == "auth.rate_limited" and int(limited.headers["retry-after"]) >= 1
    assert "x-frame-options" in limited.headers
    assert (await client.get("/api/convert/pairs")).status_code == 200
    monkeypatch.setenv("WEBEDITOR_HEAVY_RATE_LIMIT", "0")
    assert (await client.post("/api/convert/preview", json=body)).status_code != 429
