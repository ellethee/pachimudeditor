"""Servizio statico del frontend buildato: fallback SPA per le route client."""

import httpx
import pytest

from pachimudeditor.spa import static_dir

pytestmark = pytest.mark.skipif(static_dir() is None, reason="frontend non buildato (pachimudeditor build-frontend)")


@pytest.mark.parametrize("path", ["/", "/zones", "/rooms/map", "/zones/1/resets"])
async def test_client_routes_serve_index(anon: httpx.AsyncClient, path: str) -> None:
    """Ricaricare una route client serve index.html (history mode)."""
    response = await anon.get(path)
    assert response.status_code == 200 and "<title>" in response.text


async def test_missing_asset_and_api_stay_404(anon: httpx.AsyncClient) -> None:
    """Un file mancante o una route /api sconosciuta non diventano index.html."""
    assert (await anon.get("/assets/nope.js")).status_code == 404
    assert (await anon.get("/api/nope")).status_code == 404
