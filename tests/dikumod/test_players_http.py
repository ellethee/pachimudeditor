"""Rotte `/api/world/players` sul mondo Diku Modificato (fixture sintetiche), contratto, errori e guardia sulla password."""

import logging
import os
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

from pachimudeditor.common.adapters import registry as registry_module
from pachimudeditor.common.adapters.registry import WorldConfig, WorldRegistry, set_registry
from tests.helpers import data, error_code
from tests.support import stack
from pachimudeditor_adapter_dikumod.dikumod_lib.players_write import rent_revision
from tests.support.dikumod_players import PWD_MARKER, make_char, make_item, make_rent, standard_players, write_players

H = {"X-World": "dikumod"}
BASE = "/api/world/players"


@pytest_asyncio.fixture(autouse=True)
async def worlds(lib: Path, variant: str) -> AsyncIterator[None]:
    """Registro con pachimud (default) e `dikumod` (sola lettura: il default del kind) con i giocatori sintetici."""
    standard_players(lib)
    set_registry(
        WorldRegistry(
            [
                WorldConfig(id="pachimud", name="Pachimud", params=stack.current_params()),
                WorldConfig(id="dikumod", kind="dikumod", name="Diku Modificato", path=str(lib), params={"variant": variant}),
            ]
        )
    )
    yield
    await registry_module._registry.aclose_all()  # noqa: SLF001
    set_registry(None)


async def test_capabilities_and_info(client: httpx.AsyncClient) -> None:
    """Capability additive nel mondo, descrittore con colonne e sezioni; pachimud non le dichiara."""
    worlds = {w["id"]: w for w in data(await client.get("/api/worlds"))}
    assert worlds["dikumod"]["capabilities"]["supportsPlayerRecords"] and worlds["dikumod"]["capabilities"]["supportsPlayerInventory"]
    assert worlds["dikumod"]["capabilities"]["readOnly"] is True and not worlds["dikumod"]["capabilities"]["supportsPlayers"]
    assert not worlds["pachimud"]["capabilities"]["supportsPlayerRecords"]
    info = data(await client.get(f"{BASE}/info", headers=H))
    assert [c["name"] for c in info["columns"]][:3] == ["name", "level", "classLabel"]
    assert {"general", "abilities", "points", "state"} <= {f["group"] for f in info["detailFields"]}
    assert [x["name"] for x in info["detailLists"]] == ["skills", "affects"]
    assert info["hasAccounts"] is False and info["onlinePolicy"] == "warn"


async def test_list_and_paging(client: httpx.AsyncClient) -> None:
    """Elenco ordinato per nome, ricerca, ordinamento per livello, paginazione, campi mappati."""
    page = data(await client.get(BASE, params={"pageSize": 2, "page": 1}, headers=H))
    assert page["total"] == 4 and [p["id"] for p in page["items"]] == ["caio", "mevio"]
    items = {p["id"]: p for p in data(await client.get(BASE, headers=H))["items"]}
    tizio = items["tizio"]
    assert (tizio["name"], tizio["level"], tizio["classLabel"], tizio["raceLabel"], tizio["sex"]) == (
        "Tizio",
        12,
        "Warrior",
        "Human",
        "male",
    )
    assert (tizio["gold"], tizio["roomVnum"], tizio["playedSeconds"], tizio["hasPassword"], tizio["online"]) == (
        1234,
        3001,
        7200,
        True,
        None,
    )
    assert tizio["lastLoginAt"].startswith("2023-11-14") and tizio["extra"]["fileModifiedAt"]
    caio = items["caio"]
    assert caio["classLabel"] == "Warrior / Thief" and caio["level"] == 31 and caio["roomVnum"] is None and caio["sex"] == "female"
    sempronio = items["sempronio"]
    assert sempronio["hasPassword"] is False and sempronio["lastLoginAt"] is None
    found = data(await client.get(BASE, params={"search": "ZIO"}, headers=H))
    assert [p["id"] for p in found["items"]] == ["tizio"]
    order = data(await client.get(BASE, params={"orderBy": "-level"}, headers=H))
    assert [p["id"] for p in order["items"]][0] == "caio"
    assert (await client.get(BASE, params={"orderBy": "password"}, headers=H)).status_code == 422


async def test_detail(client: httpx.AsyncClient) -> None:
    """Dettaglio: sezioni, tabelle, `details` coerenti col descrittore; nessun campo password."""
    info = data(await client.get(f"{BASE}/info", headers=H))
    detail = data(await client.get(f"{BASE}/tizio", headers=H))
    assert set(detail["details"]) == {f["name"] for f in info["detailFields"]}
    assert detail["details"]["str"] == 16 and detail["details"]["hit"] == 100 and detail["details"]["title"] == "il Prode"
    assert detail["details"]["levels"] == {"Warrior": 12}
    assert detail["lists"]["skills"] == [
        {"index": 5, "learned": 80, "flags": 1, "special": 0, "nummem": 0},
        {"index": 9, "learned": 0, "flags": 1, "special": 0, "nummem": 0},
    ]
    assert detail["lists"]["affects"][0]["type"] == 3
    assert data(await client.get(f"{BASE}/caio", headers=H))["details"]["autoRent"] is True
    assert "password" not in detail and "pwd" not in detail["details"]


async def test_inventory(client: httpx.AsyncClient) -> None:
    """Inventario/equipaggiamento: slot, annidamento, prototipo noto/ignoto, effetti; rent vuoto/assente/owner diverso."""
    inv = data(await client.get(f"{BASE}/tizio/inventory", headers=H))
    assert inv["problem"] is None and inv["extra"]["goldLeft"] == 500 and inv["extra"]["declaredNumber"] == 3
    worn, bag, unknown = inv["items"]
    assert (worn["vnum"], worn["wearSlot"], worn["known"], worn["name"]) == (1, "body", True, "Un gile in pelle")
    assert len(worn["extra"]["affects"]) == 2 and worn["extra"]["itemType"] is not None
    assert (bag["wearSlot"], bag["depth"]) == (None, 0) and bag["name"] == "Un sacco"
    assert (unknown["vnum"], unknown["known"], unknown["depth"]) == (9999, False, 1)
    assert data(await client.get(f"{BASE}/caio/inventory", headers=H)) == {
        "items": [],
        "problem": None,
        "revision": rent_revision(b""),
        "extra": {"rentFile": True, "goldLeft": 0, "totalCost": 0, "lastUpdate": None, "minimumStay": 0, "declaredNumber": 0},
    }
    assert data(await client.get(f"{BASE}/sempronio/inventory", headers=H))["extra"] == {"rentFile": False}
    assert data(await client.get(f"{BASE}/mevio/inventory", headers=H))["problem"] == "owner_mismatch"


async def test_corrupted_files_do_not_break_the_list(client: httpx.AsyncClient, lib: Path) -> None:
    """File troncato, rent con `number` assurdo, symlink fuori cartella: righe/inventari con `problem`, mai 500."""
    players = lib / "players"
    (players / "corto.dat").write_bytes(make_char()[:100])
    (players / "grande.dat").write_bytes(make_char() + b"x")
    outside = lib.parent / "esterno.dat"
    outside.write_bytes(make_char("Esterno"))
    (players / "evil.dat").symlink_to(outside)
    write_players(lib, {}, {"corto": make_rent("Corto", [make_item()], number=999)})
    items = {p["id"]: p for p in data(await client.get(BASE, headers=H))["items"]}
    assert (
        items["corto"]["problem"] == "bad_size" and items["grande"]["problem"] == "bad_size" and items["evil"]["problem"] == "outside_dir"
    )
    assert items["corto"]["level"] is None and items["tizio"]["problem"] is None
    detail = data(await client.get(f"{BASE}/corto", headers=H))
    assert detail["problem"] == "bad_size" and detail["details"] == {}
    assert data(await client.get(f"{BASE}/corto/inventory", headers=H))["problem"] == "bad_size"
    (players / "corto.dat").write_bytes(make_char("Corto"))
    assert data(await client.get(f"{BASE}/corto/inventory", headers=H))["problem"] == "too_many_items"


@pytest.mark.parametrize("bad", ["nessuno", "..", "%2e%2e", "Tizio", "tizio.dat", "tizio%00", "a%5Cb", "%2e%2e%2festerno", "x" * 200])
async def test_unknown_or_malicious_ids_are_404(client: httpx.AsyncClient, bad: str) -> None:
    """Id inesistenti o con tentativi di path traversal: 404 `worldplayers.not_found`, anche per l'inventario."""
    for suffix in ("", "/inventory"):
        response = await client.get(f"{BASE}/{bad}{suffix}", headers=H)
        assert response.status_code == 404, (bad, response.status_code)
        assert error_code(response, 404) in {"worldplayers.not_found", None}


async def test_capability_missing_and_unknown_world(client: httpx.AsyncClient) -> None:
    """Mondo senza la capability: 409 `world.capability_missing` su tutte le rotte; mondo ignoto: 404."""
    for path in ("/info", "/status", "", "/tizio", "/tizio/inventory"):
        assert error_code(await client.get(BASE + path), 409) == "world.capability_missing"  # default = pachimud
    assert (await client.get(f"{BASE}/tizio", headers={"X-World": "nope"})).status_code == 404


async def test_read_only_and_no_writes(client: httpx.AsyncClient, lib: Path) -> None:
    """Mondo in sola lettura: ogni scrittura e' 409 `world.read_only` e nessun file e' toccato (hash e mtime di players/ e rent/ invariati)."""

    def snapshot() -> dict[str, tuple[int, int, bytes]]:
        return {
            str(p.relative_to(lib)): (p.stat().st_mtime_ns, p.stat().st_size, p.read_bytes())
            for d in ("players", "rent")
            for p in sorted((lib / d).glob("*"))
        }

    before = snapshot()
    for path in ("/info", "/status", "", "/tizio", "/tizio/inventory", "/caio/inventory"):
        data(await client.get(BASE + path, headers=H))
    for method in ("post", "put"):
        assert (await getattr(client, method)(f"{BASE}/tizio", headers=H)).status_code in {404, 405}
    for method, path in (("patch", ""), ("post", "/inventory/items"), ("patch", "/inventory/items/0"), ("delete", "/inventory/items/0")):
        response = await client.request(method, f"{BASE}/tizio{path}", headers=H, json={"vnum": 1, "wearSlot": None})
        assert error_code(response, 409) == "world.read_only"  # il mondo e' in sola lettura (default del kind)
    assert snapshot() == before


async def test_password_never_leaks(client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture) -> None:
    """Il valore del campo `pwd` non compare in nessuna risposta (elenco, dettaglio, inventario, errori) ne' nei log."""
    caplog.set_level(logging.DEBUG)
    marker = PWD_MARKER.decode()
    texts = []
    for path in ("/info", "/status", "", "/tizio", "/caio", "/sempronio", "/tizio/inventory", "/nessuno", "/..", "/tizio.dat"):
        texts.append((await client.get(BASE + path, headers=H)).text)
    assert not any(marker in t or marker.lower() in t.lower() for t in texts)
    assert marker not in caplog.text


async def test_status_detects_server_process(client: httpx.AsyncClient, lib: Path) -> None:
    """Senza server `serverRunning` e' nullo (mai falso); con un processo che ha cwd = lib/ e un socket aperto e' vero."""
    if not os.path.isdir("/proc/self"):
        pytest.skip("rilevamento via /proc")
    assert data(await client.get(f"{BASE}/status", headers=H))["serverRunning"] is None
    code = "import socket,sys,time; s=socket.socket(); s.bind(('127.0.0.1',0)); s.listen(); print('up',flush=True); time.sleep(60)"
    child = subprocess.Popen([sys.executable, "-c", code], cwd=lib, stdout=subprocess.PIPE, text=True)
    try:
        assert child.stdout is not None and child.stdout.readline().strip() == "up"
        status = data(await client.get(f"{BASE}/status", headers=H))
        assert status["serverRunning"] is True and status["detection"] == "proc"
    finally:
        child.kill()
        child.wait()
