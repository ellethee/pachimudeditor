"""Header di sicurezza (API, SPA, /docs) e limite di richieste sugli endpoint costosi."""

from collections.abc import Awaitable

import httpx
import pytest

from pachifast.auth.security import create_access_token
from fastapi import HTTPException, Request, Response
from pachifast.config import get_settings
from pachifast.ratelimit import rate_limit

from pachimudeditor.common.http_guard import CSP_APP, CSP_DOCS
from pachimudeditor.common.rate_limit import apply_rate_limit_defaults

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


async def test_heavy_rate_limit(client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Oltre il limite: 429 `api.rate_limited` con `Retry-After`; gli altri endpoint non sono toccati; `0` spegne."""
    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_default", 2)
    monkeypatch.setattr(settings, "rate_limit_window_seconds", 7919)  # finestra propria: contatore non condiviso con altri test
    body = {"sourceWorld": "x", "targetWorld": "y", "zoneIds": []}
    codes = [(await client.post("/api/convert/preview", json=body)).status_code for _ in range(3)]
    assert 429 not in codes[:2] and codes[2] == 429
    limited = await client.post("/api/convert/preview", json=body)
    assert limited.json()["detail"][0]["code"] == "api.rate_limited" and int(limited.headers["retry-after"]) >= 1
    assert limited.headers["x-ratelimit-limit"] == "2" and limited.headers["x-ratelimit-remaining"] == "0"
    assert "x-frame-options" in limited.headers  # gli header di sicurezza restano sul 429
    assert (await client.get("/api/convert/pairs")).status_code == 200
    monkeypatch.setattr(settings, "rate_limit_default", 0)
    assert (await client.post("/api/convert/preview", json=body)).status_code != 429


async def test_rate_limit_key_is_per_user() -> None:
    """Utenti diversi (token diversi) non condividono il contatore, anche dallo stesso indirizzo; lo stesso utente si'."""
    check = rate_limit(1, 7907, key="user", scope="test_per_user")

    def call(user: int) -> Awaitable[None]:
        headers = [(b"authorization", f"Bearer {create_access_token(str(user))}".encode())]
        request = Request({"type": "http", "headers": headers, "client": ("10.0.0.1", 1), "method": "POST", "path": "/"})
        return check(request, Response())

    await call(9001)
    await call(9002)  # altro utente, stesso IP: passa
    with pytest.raises(HTTPException) as err:
        await call(9001)
    assert err.value.status_code == 429 and "Retry-After" in (err.value.headers or {})


def test_legacy_env_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    """Gli env `WEBEDITOR_HEAVY_RATE_*` valgono solo se `rate_limit.*` non e' scritto; senza nulla: 60/60."""
    settings = get_settings().model_copy()
    settings.__pydantic_fields_set__.difference_update({"rate_limit_default", "rate_limit_window_seconds"})
    monkeypatch.setattr("pachimudeditor.common.rate_limit.get_settings", lambda: settings)
    monkeypatch.setenv("WEBEDITOR_HEAVY_RATE_LIMIT", "5")
    apply_rate_limit_defaults()
    assert settings.rate_limit_default == 5
    monkeypatch.delenv("WEBEDITOR_HEAVY_RATE_LIMIT")
    settings.__pydantic_fields_set__.difference_update({"rate_limit_default", "rate_limit_window_seconds"})
    apply_rate_limit_defaults()
    assert settings.rate_limit_default == 60 and settings.rate_limit_window_seconds == 60
