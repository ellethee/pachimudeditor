"""Mondo pachimud `read_only`: ogni rotta di scrittura di players/instances/content risponde 409 e non scrive nulla."""

import re
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from fastapi.routing import APIRoute

from pachimudeditor_adapter_pachimud.apps.content.root import router as content_router
from pachimudeditor_adapter_pachimud.apps.instances.root import router as instances_router
from pachimudeditor_adapter_pachimud.apps.players import accounts as players_accounts
from pachimudeditor_adapter_pachimud.apps.players import characters as players_characters
from pachimudeditor_adapter_pachimud.apps.players import inventory as players_inventory
from pachimudeditor.common.adapters.registry import get_registry
from tests.helpers import error_code

PREFIXES = ("/api/players", "/api/instances", "/api/content")
ROUTERS = (
    ("/api/players", players_accounts.router),
    ("/api/players", players_characters.router),
    ("/api/players", players_inventory.router),
    ("/api", instances_router),  # i percorsi di instances/content includono gia' il proprio prefisso
    ("/api", content_router),
)
WRITES = sorted(
    (m, f"{prefix}{r.path}")
    for prefix, router in ROUTERS
    for r in router.routes
    if isinstance(r, APIRoute)
    for m in r.methods
    if m not in ("GET", "HEAD", "OPTIONS")
)


@pytest_asyncio.fixture
async def ro(client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch) -> httpx.AsyncClient:
    """Il client della suite, con il mondo pachimud messo in sola lettura."""
    monkeypatch.setattr(get_registry().get("pachimud").config, "read_only", True)
    return client


def test_writes_are_censused() -> None:
    """La lista parametrica non e' vuota e copre i tre router."""
    assert len(WRITES) >= 25 and {re.match(r"/api/\w+", p).group() for _, p in WRITES} == set(PREFIXES)  # type: ignore[union-attr]


@pytest.mark.parametrize(("method", "path"), WRITES)
async def test_write_is_409(ro: httpx.AsyncClient, method: str, path: str) -> None:
    """Ogni POST/PUT/PATCH/DELETE e' respinto con `world.read_only`."""
    url = re.sub(r"\{[^}]+\}", "1", path)
    response = await ro.request(method, url, json={})
    assert error_code(response, 409) == "world.read_only"


async def test_nothing_written_and_reads_ok(ro: httpx.AsyncClient) -> None:
    """Una creazione vera non lascia righe/file e le GET restano 200."""
    body = {"username": "mario", "password": "password123", "email": "m@example.com"}
    assert error_code(await ro.post("/api/players/accounts", json=body), 409) == "world.read_only"
    assert (await ro.get("/api/players/accounts")).json()["data"]["total"] == 0
    adapter = get_registry().get("pachimud")
    before = sorted(Path(adapter.params.definitions_path).rglob("*")) if adapter.params.definitions_path else []
    await ro.post("/api/content/races", json={})
    after = sorted(Path(adapter.params.definitions_path).rglob("*")) if adapter.params.definitions_path else []
    assert before == after
    for path in ("/api/players/accounts", "/api/instances/mobs", "/api/content/races"):
        assert (await ro.get(path)).status_code == 200, path
