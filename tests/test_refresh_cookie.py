"""Refresh token in cookie HttpOnly: default dell'editor (pachifast `auth.refresh_mode=cookie`)."""

import httpx

from tests.support import stack


async def test_login_sets_httponly_cookie_without_body_token(anon: httpx.AsyncClient) -> None:
    """Il login non mette il refresh token nel JSON ma in un cookie HttpOnly limitato a /api/auth."""
    response = await anon.post("/api/auth/token", data={"username": stack.TEST_USER, "password": stack.TEST_PASSWORD})
    assert response.status_code == 200
    assert "refresh_token" not in response.json()
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "path=/api/auth" in cookie


async def test_refresh_needs_csrf_header(anon: httpx.AsyncClient) -> None:
    """Con il cookie il refresh funziona solo con `X-Pachi-Auth`; senza e' 403 `auth.csrf_rejected`."""
    await anon.post("/api/auth/token", data={"username": stack.TEST_USER, "password": stack.TEST_PASSWORD})
    rejected = await anon.post("/api/auth/refresh-token", json={})
    assert rejected.status_code == 403 and "auth.csrf_rejected" in rejected.text
    ok = await anon.post("/api/auth/refresh-token", json={}, headers={"X-Pachi-Auth": "refresh"})
    assert ok.status_code == 200 and ok.json()["access_token"]
