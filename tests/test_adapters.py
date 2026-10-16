"""Registro dei mondi, selezione per richiesta, `GET /api/worlds`, guardia sulle capability e sola lettura."""

import json
from pathlib import Path
from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from fastapi import HTTPException

from pachimudeditor_adapter_pachimud.adapter import PachimudAdapter
from pachimudeditor.common.adapters.base import AdapterCapabilities, WorldAdapter
from pachimudeditor.common.adapters.models import ZoneIn
from pachimudeditor.common.adapters import registry as registry_module
from pachimudeditor.common.adapters.registry import (
    WorldConfig,
    WorldRegistry,
    build_registry,
    register_kind,
    registered_kinds,
    set_registry,
)
from tests.adapter_contract.helpers import expect_error
from tests.helpers import data, error_code
from tests.support import stack


class MinimalAdapter(PachimudAdapter):
    """Pachimud senza funzioni opzionali: simula un MUD semplice (nessuna capability extra)."""

    def capabilities(self) -> AdapterCapabilities:
        """Solo il nucleo; `read_only` dalla configurazione."""
        return AdapterCapabilities(read_only=self.config.read_only)


@pytest_asyncio.fixture(autouse=True)
async def _kinds_and_registry() -> AsyncIterator[None]:
    """Registra il kind di prova `minimal` e azzera il registro prima e dopo ogni test."""
    register_kind("minimal", MinimalAdapter)
    set_registry(None)
    yield
    current = registry_module._registry  # noqa: SLF001 - chiude gli adapter creati dal test (aiosqlite) prima del loop
    if current is not None:
        await current.aclose_all()
    set_registry(None)


def _two_worlds(**lite: object) -> WorldRegistry:
    """Registro con `pachimud` (default) e `lite` (kind `minimal`)."""
    return WorldRegistry(
        [
            WorldConfig(id="pachimud", name="Pachimud", params=stack.current_params()),
            WorldConfig(id="lite", kind="minimal", name="Lite", params=stack.current_params(), **lite),  # type: ignore[arg-type]
        ]
    )


# --------------------------------------------------------------------------- registro


def test_no_implicit_world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Senza configurazione non esiste nessun mondo (il mondo `pachimud` non e' implicito)."""
    for var in ("WEBEDITOR_WORLDS", "PACHIMUDEDITOR_WORLDS", "WEBEDITOR_DEFAULT_WORLD", "PACHIFAST_CONFIG_FILE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(tmp_path)
    registry = build_registry()
    assert registry.world_ids == [] and registry.describe_all() == []
    with pytest.raises(HTTPException) as error:
        registry.get()
    assert error.value.status_code == 404


def test_configured_pachimud_registry() -> None:
    """Con il mondo `pachimud` configurato (ambiente dei test) e' il default e l'adapter e' unico."""
    registry = build_registry()
    assert registry.world_ids == ["pachimud"] and registry.default_id == "pachimud"
    assert isinstance(registry.get(), PachimudAdapter)
    assert registry.get() is registry.get("pachimud")  # istanziato una volta sola


def test_registry_validation() -> None:
    """Id duplicati, kind sconosciuto, default sconosciuto e lista vuota sono errori di configurazione."""
    with pytest.raises(ValueError, match="duplicati"):
        WorldRegistry([WorldConfig(id="a"), WorldConfig(id="a")])
    with pytest.raises(ValueError, match="non disponibile"):
        WorldRegistry([WorldConfig(id="a", kind="inesistente")])
    with pytest.raises(ValueError, match="default"):
        WorldRegistry([WorldConfig(id="a")], default_id="b")
    assert WorldRegistry([]).world_ids == []  # nessun mondo e' ammesso


def test_default_world_choice() -> None:
    """Il default e' quello indicato, altrimenti `pachimud` se presente, altrimenti il primo."""
    assert _two_worlds().default_id == "pachimud"
    assert WorldRegistry([WorldConfig(id="x"), WorldConfig(id="y")]).default_id == "x"
    assert WorldRegistry([WorldConfig(id="x"), WorldConfig(id="y")], "y").default_id == "y"


def test_kinds_are_extensible() -> None:
    """Un nuovo kind (es. `mapping`) si registra con una factory e riceve path/mapping/params dalla config."""
    seen: list[WorldConfig] = []

    def factory(config: WorldConfig) -> WorldAdapter:
        """Cattura la config e restituisce un adapter di prova."""
        seen.append(config)
        return MinimalAdapter(config.model_copy(update={"params": {**config.params, **stack.current_params()}}))

    register_kind("mapping", factory)
    assert "mapping" in registered_kinds()
    registry = WorldRegistry(
        [WorldConfig.model_validate({"id": "tba", "kind": "mapping", "mapping": "/x/tba.yaml", "path": "/x/lib", "params": {"a": 1}})]
    )
    registry.get("tba")
    assert (seen[0].mapping, seen[0].path, seen[0].params) == ("/x/tba.yaml", "/x/lib", {"a": 1})


def test_registry_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """`WEBEDITOR_WORLDS` (JSON) e `WEBEDITOR_DEFAULT_WORLD` configurano i mondi."""
    monkeypatch.setenv(
        "WEBEDITOR_WORLDS",
        json.dumps(
            [
                {"id": "p", "kind": "pachimud", "params": stack.current_params()},
                {"id": "lite", "kind": "minimal", "read_only": True, "params": stack.current_params()},
            ]
        ),
    )
    monkeypatch.setenv("WEBEDITOR_DEFAULT_WORLD", "lite")
    registry = build_registry()
    assert registry.world_ids == ["p", "lite"] and registry.default_id == "lite"
    assert registry.get("lite").capabilities().read_only is True


def test_describe_pachimud_fields() -> None:
    """`describe()` espone risorse e campi derivati dagli schemi (tipo, required, enum, readOnly)."""
    info = build_registry().get().describe()
    zone = next(r for r in info.resources if r.type == "zone")
    fields = {f.name: f for f in zone.fields}
    assert fields["id"].read_only and fields["vnum"].required and fields["name"].type == "string"
    assert fields["resetMode"].type == "enum" and fields["resetMode"].enum == "zoneResetMode"
    room = {f.name: f for f in next(r for r in info.resources if r.type == "room").fields}
    assert room["sectorType"].enum == "sectorType" and room["flags"].type == "flags"
    assert room["description"].type == "text" and room["clanId"].nullable
    assert "exits" not in room and "extra" not in room


# --------------------------------------------------------------------------- HTTP


async def test_worlds_endpoint(client: httpx.AsyncClient) -> None:
    """`GET /api/worlds` elenca i mondi con capability e campi; richiede l'autenticazione."""
    worlds = data(await client.get("/api/worlds"))
    assert [w["id"] for w in worlds] == ["pachimud"]
    world = worlds[0]
    assert world["kind"] == "pachimud" and world["default"] is True
    caps = world["capabilities"]
    assert caps["supportsTransfer"] and caps["supportsPlayers"] and caps["readOnly"] is False
    assert {r["type"] for r in world["resources"]} >= {"zone", "room", "mob", "object"}
    assert (await client.get("/api/worlds", headers={"Authorization": ""})).status_code in (401, 403)


async def test_worlds_endpoint_multiple(client: httpx.AsyncClient) -> None:
    """Con piu' mondi configurati compaiono tutti, con le rispettive capability."""
    set_registry(_two_worlds())
    worlds = {w["id"]: w for w in data(await client.get("/api/worlds"))}
    assert set(worlds) == {"pachimud", "lite"}
    assert worlds["lite"]["capabilities"]["supportsPlayers"] is False and worlds["lite"]["default"] is False


async def test_world_selection_by_header_and_query(client: httpx.AsyncClient) -> None:
    """`X-World` e `?world=` scelgono il mondo; senza, il default; un id ignoto e' 404 `world.not_found`."""
    assert data(await client.get("/api/zones", headers={"X-World": "pachimud"}))["total"] == 2
    assert data(await client.get("/api/zones?world=pachimud"))["total"] == 2
    response = await client.get("/api/zones", headers={"X-World": "nope"})
    assert error_code(response, 404) == "world.not_found"
    assert error_code(await client.get("/api/zones?world=nope"), 404) == "world.not_found"
    assert "nope" in response.json()["detail"][0]["msg"]  # messaggio tradotto (it) con il parametro


async def test_world_not_found_message_in_english(client: httpx.AsyncClient) -> None:
    """Il messaggio e' tradotto anche in inglese (`Accept-Language: en`)."""
    response = await client.get("/api/zones", headers={"X-World": "nope", "Accept-Language": "en"})
    assert error_code(response, 404) == "world.not_found"
    assert "not configured" in response.json()["detail"][0]["msg"]


async def test_capability_guard(client: httpx.AsyncClient) -> None:
    """Un mondo senza la capability risponde 409 `world.capability_missing` sulle aree opzionali."""
    set_registry(_two_worlds())
    headers = {"X-World": "lite"}
    for path in (
        "/api/players/accounts",
        "/api/world/overview",
        "/api/instances/mobs",
        "/api/content/races",
        "/api/transfer/zones/1/export/bundle",
    ):
        response = await client.get(path, headers=headers)
        assert error_code(response, 409) == "world.capability_missing", path
    # il nucleo funziona
    assert data(await client.get("/api/zones", headers=headers))["total"] == 2
    # e sul mondo che la supporta le stesse aree rispondono
    assert (await client.get("/api/players/accounts")).status_code == 200


async def test_read_only_world(client: httpx.AsyncClient) -> None:
    """Un mondo `read_only` legge ma rifiuta ogni scrittura (409 `world.read_only`)."""
    set_registry(_two_worlds(read_only=True))
    headers = {"X-World": "lite"}
    assert data(await client.get("/api/zones", headers=headers))["total"] == 2
    response = await client.post("/api/zones", json={"vnum": 99, "name": "X"}, headers=headers)
    assert error_code(response, 409) == "world.read_only"
    assert error_code(await client.delete("/api/zones/2", headers=headers), 409) == "world.read_only"
    # direttamente sull'adapter (ultima difesa)
    adapter = _two_worlds(read_only=True).get("lite")
    with expect_error(409, "world.read_only"):
        await adapter.create_zone(ZoneIn(vnum=99, name="X"))


async def test_extra_not_supported_by_pachimud(client: httpx.AsyncClient) -> None:
    """`extra` e' sempre vuoto in uscita; in ingresso valorizzato e' rifiutato (422 `world.extra_unsupported`)."""
    zone = data(await client.get("/api/zones/1"))
    assert zone["extra"] == {}
    response = await client.post("/api/zones", json={"vnum": 77, "name": "X", "extra": {"a": 1}})
    assert error_code(response, 422) == "world.extra_unsupported"
    assert data(await client.post("/api/zones", json={"vnum": 77, "name": "X", "extra": {}}), 201)["extra"] == {}


async def test_worlds_endpoint_empty(client: httpx.AsyncClient) -> None:
    """Senza mondi configurati `/api/worlds` e' vuoto e le risorse rispondono 404 `world.none_configured`."""
    set_registry(WorldRegistry([]))
    assert data(await client.get("/api/worlds")) == []
    assert error_code(await client.get("/api/zones"), 404) == "world.none_configured"
