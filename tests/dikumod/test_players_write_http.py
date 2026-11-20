"""Scrittura dei giocatori via `/api/world/players` (L3): permessi, sola lettura, server acceso, conflitti, backup, password, id malevoli."""

import logging
import os
import stat
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import pytest_asyncio

from pachimudeditor.common.adapters import registry as registry_module
from pachimudeditor.common.adapters.registry import WorldConfig, WorldRegistry, set_registry
from pachimudeditor_adapter_dikumod.dikumod_lib import tables as T
from pachimudeditor_adapter_dikumod.dikumod_lib.players import parse_rent
from tests.helpers import data, error_code
from tests.support import stack
from tests.support.dikumod_players import PWD_MARKER, make_char, make_item, make_rent, standard_players, write_players

H = {"X-World": "dikumod"}
BASE = "/api/world/players"
PWD = slice(2974, 2985)


@pytest_asyncio.fixture(autouse=True)
async def worlds(lib: Path) -> AsyncIterator[None]:
    """Registro con pachimud (default) e `dikumod` **scrivibile** con i giocatori sintetici standard."""
    standard_players(lib)
    set_registry(
        WorldRegistry(
            [
                WorldConfig(id="pachimud", name="Pachimud", params=stack.current_params()),
                WorldConfig(id="dikumod", kind="dikumod", name="Diku Modificato", path=str(lib), read_only=False),
            ]
        )
    )
    yield
    await registry_module._registry.aclose_all()  # noqa: SLF001
    set_registry(None)


def adapter() -> Any:
    """L'adapter dikumod del registro."""
    return registry_module._registry.get("dikumod")  # noqa: SLF001


def prototypes() -> tuple[int, int]:
    """`(vnum di un oggetto qualunque, vnum di un contenitore)` del mondo in uso."""
    objs = adapter().sync().objs
    container = next(v for v, r in objs.items() if r.item.type == T.ITEM_TYPES.index("container") and 0 < v < 32768)
    plain = next(v for v, r in objs.items() if r.item.type != T.ITEM_TYPES.index("container") and 0 < v < 32768)
    return plain, container


def files(lib: Path) -> dict[str, bytes]:
    """Tutti i file di `players/` e `rent/`."""
    return {f"{d}/{p.name}": p.read_bytes() for d in ("players", "rent") for p in sorted((lib / d).glob("*")) if p.is_file()}


async def test_capabilities(client: httpx.AsyncClient) -> None:
    """Le due capability di scrittura sono dichiarate da dikumod e non da pachimud; `PlayersInfo` espone gli slot."""
    worlds = {w["id"]: w for w in data(await client.get("/api/worlds"))}
    assert worlds["dikumod"]["capabilities"]["supportsPlayerWrite"] and worlds["dikumod"]["capabilities"]["supportsPlayerInventoryWrite"]
    assert worlds["dikumod"]["capabilities"]["readOnly"] is False
    assert (
        not worlds["pachimud"]["capabilities"]["supportsPlayerWrite"]
        and not worlds["pachimud"]["capabilities"]["supportsPlayerInventoryWrite"]
    )
    info = data(await client.get(f"{BASE}/info", headers=H))
    assert info["wearSlots"] == list(T.WEAR_POSITIONS)
    fields = {f["name"]: f for f in info["detailFields"]}
    assert [n for n, f in fields.items() if f["readOnly"]] == ["autoRent"] and fields["sex"]["enum"] == "dikumodSex"


async def test_patch_details_writes_backup_and_keeps_everything_else(client: httpx.AsyncClient, lib: Path) -> None:
    """PATCH: campi nuovi nel dettaglio, `.bak` col contenuto precedente (stessi permessi), password e altri file intatti, gold_left allineato."""
    path = lib / "players" / "tizio.dat"
    path.chmod(0o640)
    before = files(lib)
    detail = data(await client.get(f"{BASE}/tizio", headers=H))
    body = {
        "revision": detail["revision"],
        "details": {"gold": 777, "title": "il Saggio", "str": 18, "levels": {"Warrior": 30}, "affectedBy": [], "sex": 2, "race": 3},
        "lists": {"skills": [{"index": 7, "learned": 55, "flags": 1}]},
    }
    out = data(await client.patch(f"{BASE}/tizio", json=body, headers=H))
    assert (out["gold"], out["level"], out["sex"], out["raceLabel"]) == (777, 30, "female", "Dwarf")
    assert out["details"]["title"] == "il Saggio" and out["details"]["str"] == 18 and out["revision"] != detail["revision"]
    assert out["lists"]["skills"] == [{"index": 7, "learned": 55, "flags": 1, "special": 0, "nummem": 0}]
    after = files(lib)
    assert (
        after["players/.tizio.dat.bak"] == before["players/tizio.dat"]
        and stat.S_IMODE((lib / "players/.tizio.dat.bak").stat().st_mode) == 0o640
    )
    assert stat.S_IMODE(path.stat().st_mode) == 0o640 and after["players/tizio.dat"][PWD] == before["players/tizio.dat"][PWD]
    assert parse_rent(after["rent/tizio"]).gold_left == 777 and after["rent/tizio"][24:] == before["rent/tizio"][24:]
    assert {k for k in after if after[k] != before.get(k)} == {
        "players/tizio.dat",
        "players/.tizio.dat.bak",
        "rent/tizio",
        "rent/.tizio.bak",
    }
    assert {p.name for p in (lib / "players").iterdir()} == {f"{n}.dat" for n in ("tizio", "caio", "sempronio", "mevio")} | {
        ".tizio.dat.bak"
    }
    again = data(await client.patch(f"{BASE}/tizio", json={"details": {"gold": 5}}, headers=H))
    assert again["gold"] == 5 and (lib / "players/.tizio.dat.bak").read_bytes() == after["players/tizio.dat"]  # una sola generazione


async def test_noop_patch_does_not_touch_files(client: httpx.AsyncClient, lib: Path) -> None:
    """Una modifica che non cambia nulla non scrive ne' crea `.bak` (mtime invariato)."""
    before = {p: p.stat().st_mtime_ns for p in (lib / "players").glob("*")}
    detail = data(await client.get(f"{BASE}/tizio", headers=H))
    same = {k: detail["details"][k] for k in ("gold", "title", "str", "levels", "conditions", "savingThrows", "affectedBy")}
    out = data(await client.patch(f"{BASE}/tizio", json={"details": same, "lists": {"skills": detail["lists"]["skills"]}}, headers=H))
    assert out["revision"] == detail["revision"] and {p: p.stat().st_mtime_ns for p in (lib / "players").glob("*")} == before
    assert not list((lib / "players").glob("*.bak"))


@pytest.mark.parametrize(
    ("details", "field", "reason"),
    [
        ({"str": 999}, "str", "range"), ({"gold": "tanto"}, "gold", "type"), ({"title": "x" * 200}, "title", "too_long"),
        ({"title": "a\nb"}, "title", "charset"), ({"name": "Altro"}, "name", "read_only"), ({"password": "x"}, "password", "read_only"),
        ({"pwd": "x"}, "pwd", "read_only"), ({"level": 9}, "level", "read_only"), ({"boh": 1}, "boh", "unknown_field"),
        ({"affectedBy": ["nonesiste"]}, "affectedBy", "unknown_flag"), ({"levels": {"jedi": 1}}, "levels", "unknown_class"),
    ],
)  # fmt: skip
async def test_invalid_values_are_422_and_write_nothing(
    client: httpx.AsyncClient, lib: Path, details: dict, field: str, reason: str
) -> None:
    """Valori non validi: 422 `worldplayers.invalid_value` con campo e motivo, nessun file cambiato; mai 500."""
    before = files(lib)
    response = await client.patch(f"{BASE}/tizio", json={"details": details}, headers=H)
    assert error_code(response, 422) == "worldplayers.invalid_value"
    params = response.json()["detail"][0]["params"]
    assert (params["field"], params["reason"]) == (field, reason)
    assert files(lib) == before


async def test_malformed_bodies_are_422(client: httpx.AsyncClient, lib: Path) -> None:
    """Corpo malformato (tipi sbagliati, JSON vuoto, tabelle strane): 422, mai 500, nulla di scritto."""
    before = files(lib)
    for body in ({"details": [1]}, {"lists": {"skills": "x"}}, {"revision": 5}, {"confirmServerRunning": "forse"}):
        assert (await client.patch(f"{BASE}/tizio", json=body, headers=H)).status_code == 422
    assert (
        error_code(await client.patch(f"{BASE}/tizio", json={"lists": {"skills": [{"index": 999}]}}, headers=H), 422)
        == "worldplayers.invalid_value"
    )
    assert error_code(await client.patch(f"{BASE}/tizio", json={"lists": {"altro": []}}, headers=H), 422) == "worldplayers.invalid_value"
    assert (await client.patch(f"{BASE}/tizio", content=b"{", headers={**H, "Content-Type": "application/json"})).status_code == 422
    assert files(lib) == before


async def test_conflict_on_stale_revision(client: httpx.AsyncClient, lib: Path) -> None:
    """Se il file e' cambiato dopo la lettura: 409 `worldplayers.conflict` (anche per l'inventario) e nessuna scrittura."""
    detail = data(await client.get(f"{BASE}/tizio", headers=H))
    inv = data(await client.get(f"{BASE}/tizio/inventory", headers=H))
    data(await client.patch(f"{BASE}/tizio", json={"revision": detail["revision"], "details": {"gold": 1}}, headers=H))
    before = files(lib)
    stale = await client.patch(f"{BASE}/tizio", json={"revision": detail["revision"], "details": {"gold": 2}}, headers=H)
    assert error_code(stale, 409) == "worldplayers.conflict"
    plain, _ = prototypes()
    (lib / "rent" / "tizio").write_bytes(make_rent("Tizio", [make_item(1)]))  # il gioco riscrive il rent
    for call in (
        client.post(f"{BASE}/tizio/inventory/items", json={"vnum": plain, "revision": inv["revision"]}, headers=H),
        client.patch(f"{BASE}/tizio/inventory/items/0", json={"wearSlot": None, "revision": inv["revision"]}, headers=H),
        client.delete(f"{BASE}/tizio/inventory/items/0", params={"revision": inv["revision"]}, headers=H),
    ):
        assert error_code(await call, 409) == "worldplayers.conflict"
    assert files(lib)["players/tizio.dat"] == before["players/tizio.dat"]
    assert (lib / "rent" / "tizio").read_bytes() == make_rent("Tizio", [make_item(1)])  # i rifiuti non hanno scritto


async def test_server_running_requires_confirmation(client: httpx.AsyncClient, lib: Path) -> None:
    """Server non rilevabile (`null`): si scrive. Server acceso: 409 `worldplayers.server_running` senza conferma, ok con."""
    if not os.path.isdir("/proc/self"):
        pytest.skip("rilevamento via /proc")
    assert data(await client.get(f"{BASE}/status", headers=H))["serverRunning"] is None
    data(await client.patch(f"{BASE}/tizio", json={"details": {"gold": 10}}, headers=H))
    code = "import socket,time; s=socket.socket(); s.bind(('127.0.0.1',0)); s.listen(); print('up',flush=True); time.sleep(60)"
    child = subprocess.Popen([sys.executable, "-c", code], cwd=lib, stdout=subprocess.PIPE, text=True)
    try:
        assert child.stdout is not None and child.stdout.readline().strip() == "up"
        assert data(await client.get(f"{BASE}/status", headers=H))["serverRunning"] is True
        before = files(lib)
        plain, _ = prototypes()
        for call in (
            client.patch(f"{BASE}/tizio", json={"details": {"gold": 11}}, headers=H),
            client.post(f"{BASE}/tizio/inventory/items", json={"vnum": plain}, headers=H),
            client.patch(f"{BASE}/tizio/inventory/items/0", json={"wearSlot": None}, headers=H),
            client.delete(f"{BASE}/tizio/inventory/items/0", headers=H),
            client.patch(f"{BASE}/tizio", json={"details": {"gold": 11}, "confirmServerRunning": False}, headers=H),
        ):
            assert error_code(await call, 409) == "worldplayers.server_running"
        assert files(lib) == before
        assert (
            data(await client.patch(f"{BASE}/tizio", json={"details": {"gold": 11}, "confirmServerRunning": True}, headers=H))["gold"] == 11
        )
        assert data(await client.delete(f"{BASE}/tizio/inventory/items/2", params={"confirmServerRunning": "true"}, headers=H))["items"]
    finally:
        child.kill()
        child.wait()


async def test_read_only_world_and_missing_capability(client: httpx.AsyncClient, lib: Path) -> None:
    """Mondo `read_only`: 409 `world.read_only` su tutte le scritture. Mondo senza capability: 409 `world.capability_missing`."""
    registry_module._registry.get("dikumod").read_only = True  # noqa: SLF001
    registry_module._registry.get("dikumod").config.read_only = True  # noqa: SLF001
    before = files(lib)
    for method, path in (("patch", ""), ("post", "/inventory/items"), ("patch", "/inventory/items/0"), ("delete", "/inventory/items/0")):
        response = await client.request(
            method, f"{BASE}/tizio{path}", headers=H, json={"vnum": 1, "wearSlot": None, "details": {"gold": 1}}
        )
        assert error_code(response, 409) == "world.read_only"
    assert files(lib) == before
    for method, path in (("patch", ""), ("post", "/inventory/items"), ("patch", "/inventory/items/0"), ("delete", "/inventory/items/0")):
        response = await client.request(method, f"{BASE}/tizio{path}", json={"vnum": 1, "wearSlot": None})  # mondo di default = pachimud
        assert error_code(response, 409) == "world.capability_missing"


async def test_requires_authentication(anon: httpx.AsyncClient) -> None:
    """Senza token ogni scrittura risponde 401."""
    for method, path in (("patch", ""), ("post", "/inventory/items"), ("patch", "/inventory/items/0"), ("delete", "/inventory/items/0")):
        assert (await anon.request(method, f"{BASE}/tizio{path}", headers=H, json={"vnum": 1})).status_code == 401


@pytest.mark.parametrize("bad", ["nessuno", "..", "%2e%2e", "Tizio", "tizio.dat", "tizio%00", "a%5Cb", "%2e%2e%2festerno", "x" * 200])
async def test_malicious_ids_are_404_on_every_write(client: httpx.AsyncClient, lib: Path, bad: str) -> None:
    """Id inesistenti o con path traversal: 404 e nessun file creato o cambiato (neanche fuori da `lib/`)."""
    before = files(lib)
    outside = {p.name for p in lib.parent.iterdir()}
    for method, suffix, body in (
        ("patch", "", {"details": {"gold": 1}}), ("post", "/inventory/items", {"vnum": 1}),
        ("patch", "/inventory/items/0", {"wearSlot": None}), ("delete", "/inventory/items/0", None),
    ):  # fmt: skip
        response = await client.request(method, f"{BASE}/{bad}{suffix}", headers=H, json=body)
        assert response.status_code in ((404, 405) if bad.startswith(("..", "%2e")) else (404,)), (
            bad,
            method,
            response.status_code,
        )  # il client collassa `..`
    assert files(lib) == before and {p.name for p in lib.parent.iterdir()} == outside


async def test_unwritable_files_are_409(client: httpx.AsyncClient, lib: Path) -> None:
    """File corrotto, symlink fuori cartella o rent di un altro proprietario: 409 `worldplayers.file_unwritable`, nulla di scritto."""
    outside = lib.parent / "esterno.dat"
    outside.write_bytes(make_char("Esterno"))
    (lib / "players" / "evil.dat").symlink_to(outside)
    (lib / "players" / "corto.dat").write_bytes(make_char()[:100])
    evil_rent = lib.parent / "esterno_rent"
    evil_rent.write_bytes(make_rent("Tizio", []))
    (lib / "players" / "link.dat").write_bytes(make_char("Link"))
    (lib / "rent" / "link").symlink_to(evil_rent)
    before, ext = files(lib), (outside.read_bytes(), evil_rent.read_bytes())
    plain, _ = prototypes()
    problems = []
    for pid, call in (
        ("evil", client.patch(f"{BASE}/evil", json={"details": {"gold": 1}}, headers=H)),
        ("corto", client.patch(f"{BASE}/corto", json={"details": {"gold": 1}}, headers=H)),
        ("link", client.post(f"{BASE}/link/inventory/items", json={"vnum": plain}, headers=H)),
        ("mevio", client.post(f"{BASE}/mevio/inventory/items", json={"vnum": plain}, headers=H)),
    ):
        response = await call
        assert error_code(response, 409) == "worldplayers.file_unwritable", pid
        problems.append(response.json()["detail"][0]["params"]["problem"])
    assert problems == ["outside_dir", "bad_size", "outside_dir", "owner_mismatch"]
    assert files(lib) == before and (outside.read_bytes(), evil_rent.read_bytes()) == ext


@pytest.mark.real_dikumod  # usa un oggetto (40019) che esiste solo nei dati reali: nei mondi sintetici il giocatore non lo trova (404)
async def test_inventory_vnum_over_short_is_explained(client: httpx.AsyncClient) -> None:
    """Un vnum oltre 32767 (il rent lo salva in uno `short`) e' rifiutato con un messaggio che spiega il limite, in it e in en."""
    for lang, text in (("it", "intervallo che il file del giocatore"), ("en", "range the player file can hold")):
        r = await client.post(f"{BASE}/tizio/inventory/items", json={"vnum": 40019}, headers={**H, "Accept-Language": lang})
        detail = r.json()["detail"][0]
        assert error_code(r, 422) == "worldplayers.invalid_value" and (detail["params"]["field"], detail["params"]["reason"]) == (
            "vnum",
            "range",
        )
        assert detail["params"]["max"] == 32767 and text in detail["msg"] and "32767" in detail["msg"]
    other = await client.post(f"{BASE}/tizio/inventory/items", json={"vnum": 1, "wearSlot": "naso"}, headers=H)
    assert error_code(other, 422) == "worldplayers.invalid_value" and "intervallo" not in other.json()["detail"][0]["msg"]


async def test_inventory_add_equip_container_and_backup(client: httpx.AsyncClient, lib: Path) -> None:
    """Aggiunta portata/equipaggiata/in contenitore, slot occupato, oggetto ignoto, contenitore non valido; `.bak` del rent e costo."""
    plain, container = prototypes()
    proto = adapter().sync().objs[plain].item
    rent_before = (lib / "rent" / "tizio").read_bytes()
    inv = data(await client.post(f"{BASE}/tizio/inventory/items", json={"vnum": plain}, headers=H), 201)
    assert (
        len(inv["items"]) == 4 and inv["items"][-1]["vnum"] == plain and inv["items"][-1]["wearSlot"] is None and inv["items"][-1]["known"]
    )
    assert inv["items"][-1]["extra"]["values"] == list(proto.values) and inv["items"][-1]["extra"]["timer"] == 0
    assert (lib / "rent" / ".tizio.bak").read_bytes() == rent_before and inv["problem"] is None
    assert inv["extra"]["totalCost"] == 10 + max(proto.rent, 0) and inv["extra"]["goldLeft"] == 500
    worn = data(await client.post(f"{BASE}/tizio/inventory/items", json={"vnum": plain, "wearSlot": "head"}, headers=H), 201)
    assert worn["items"][-1]["wearSlot"] == "head"
    taken = await client.post(f"{BASE}/tizio/inventory/items", json={"vnum": plain, "wearSlot": "head"}, headers=H)
    assert error_code(taken, 409) == "worldplayers.item_invalid" and taken.json()["detail"][0]["params"]["reason"] == "slot_taken"
    assert (
        error_code(await client.post(f"{BASE}/tizio/inventory/items", json={"vnum": plain, "wearSlot": "naso"}, headers=H), 422)
        == "worldplayers.invalid_value"
    )
    assert (
        error_code(await client.post(f"{BASE}/tizio/inventory/items", json={"vnum": 31999}, headers=H), 404)
        == "worldplayers.unknown_object"
    )
    assert (
        error_code(await client.post(f"{BASE}/tizio/inventory/items", json={"vnum": 40000}, headers=H), 404)
        == "worldplayers.unknown_object"
    )
    bag = next(i["id"] for i in worn["items"] if i["name"] == "Un sacco")
    unknown = next(i["id"] for i in worn["items"] if i["vnum"] == 9999)
    bad = await client.post(f"{BASE}/tizio/inventory/items", json={"vnum": plain, "containerId": bag}, headers=H)
    assert (
        error_code(bad, 409) == "worldplayers.item_invalid" and bad.json()["detail"][0]["params"]["reason"] == "container_invalid"
    )  # il sacco ha vnum 1
    assert (
        error_code(await client.post(f"{BASE}/tizio/inventory/items", json={"vnum": plain, "containerId": 99}, headers=H), 404)
        == "worldplayers.item_not_found"
    )
    assert unknown >= 0
    # un contenitore vero: aggiunto e poi riempito
    boxed = data(await client.post(f"{BASE}/tizio/inventory/items", json={"vnum": container}, headers=H), 201)
    box = boxed["items"][-1]["id"]
    filled = data(await client.post(f"{BASE}/tizio/inventory/items", json={"vnum": plain, "containerId": box}, headers=H), 201)
    assert [(i["vnum"], i["depth"]) for i in filled["items"][-2:]] == [(container, 0), (plain, 1)]
    both = await client.post(f"{BASE}/tizio/inventory/items", json={"vnum": plain, "containerId": box, "wearSlot": "body"}, headers=H)
    assert error_code(both, 409) == "worldplayers.item_invalid"
    again = parse_rent((lib / "rent" / "tizio").read_bytes())
    assert again.problem is None and again.number == len(filled["items"]) and again.owner == "Tizio"


async def test_inventory_creates_the_rent_file_when_missing_or_empty(client: httpx.AsyncClient, lib: Path) -> None:
    """Giocatore senza rent o con rent vuoto (0 byte): file nuovo con testata coerente (owner, oro, costo minimo), senza `.bak`."""
    plain, _ = prototypes()
    for pid, name, gold in (("sempronio", "Sempronio", 1234), ("caio", "Caio", 0)):
        inv = data(await client.post(f"{BASE}/{pid}/inventory/items", json={"vnum": plain, "wearSlot": "light"}, headers=H), 201)
        assert [(i["vnum"], i["wearSlot"]) for i in inv["items"]] == [(plain, "light")] and inv["problem"] is None
        rent = parse_rent((lib / "rent" / pid).read_bytes())
        assert (rent.owner, rent.gold_left, rent.number, rent.problem, rent.minimum_stay) == (name, gold, 1, None, 0)
        assert rent.total_cost >= 100 and rent.last_update > 1_700_000_000
        assert not (lib / "rent" / f".{pid}.bak").exists() or pid == "caio"
    assert (lib / "rent" / ".caio.bak").read_bytes() == b""  # il file esisteva (vuoto): una copia c'e'


async def test_inventory_change_slot_and_remove(client: httpx.AsyncClient, lib: Path) -> None:
    """Cambio slot (anche a portato), rimozione con il contenuto, indici inesistenti 404; il costo giornaliero scende."""
    plain, _ = prototypes()
    inv = data(await client.get(f"{BASE}/tizio/inventory", headers=H))
    worn, bag, _unknown = inv["items"]
    moved = data(
        await client.patch(f"{BASE}/tizio/inventory/items/{worn['id']}", json={"wearSlot": "legs", "revision": inv["revision"]}, headers=H)
    )
    assert moved["items"][0]["wearSlot"] == "legs" and moved["revision"] != inv["revision"]
    carried = data(await client.patch(f"{BASE}/tizio/inventory/items/{worn['id']}", json={"wearSlot": None}, headers=H))
    assert carried["items"][0]["wearSlot"] is None
    nested = await client.patch(f"{BASE}/tizio/inventory/items/2", json={"wearSlot": "head"}, headers=H)
    assert error_code(nested, 409) == "worldplayers.item_invalid" and nested.json()["detail"][0]["params"]["reason"] == "slot_in_container"
    assert (
        error_code(await client.patch(f"{BASE}/tizio/inventory/items/9", json={"wearSlot": None}, headers=H), 404)
        == "worldplayers.item_not_found"
    )
    assert (await client.patch(f"{BASE}/tizio/inventory/items/0", json={}, headers=H)).status_code == 422  # wearSlot obbligatorio
    assert (await client.patch(f"{BASE}/tizio/inventory/items/x", json={"wearSlot": None}, headers=H)).status_code == 422
    left = data(await client.delete(f"{BASE}/tizio/inventory/items/{bag['id']}", headers=H))
    assert [i["vnum"] for i in left["items"]] == [1] and left["problem"] is None  # il contenuto (depth 1) se n'e' andato col sacco
    assert error_code(await client.delete(f"{BASE}/tizio/inventory/items/5", headers=H), 404) == "worldplayers.item_not_found"
    empty = data(await client.delete(f"{BASE}/tizio/inventory/items/0", headers=H))
    assert empty["items"] == [] and empty["problem"] is None and len((lib / "rent" / "tizio").read_bytes()) == 40
    assert plain  # fixture usata per coerenza di mondo


async def test_password_never_changes_or_leaks(client: httpx.AsyncClient, lib: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Dopo ogni scrittura i byte della password sono quelli di prima e non compaiono in nessuna risposta o log."""
    caplog.set_level(logging.DEBUG)
    plain, _ = prototypes()
    pwd = (lib / "players" / "tizio.dat").read_bytes()[PWD]
    texts = [
        (await client.patch(f"{BASE}/tizio", json={"details": {"gold": 3, "password": "x"}}, headers=H)).text,
        (await client.patch(f"{BASE}/tizio", json={"details": {"gold": 3, "title": "ok"}}, headers=H)).text,
        (await client.post(f"{BASE}/tizio/inventory/items", json={"vnum": plain}, headers=H)).text,
        (await client.delete(f"{BASE}/tizio/inventory/items/0", headers=H)).text,
        (await client.patch(f"{BASE}/nessuno", json={}, headers=H)).text,
    ]
    assert (lib / "players" / "tizio.dat").read_bytes()[PWD] == pwd == PWD_MARKER + b"\0\0"
    assert (lib / "players" / ".tizio.dat.bak").read_bytes()[PWD] == pwd
    marker = PWD_MARKER.decode()
    assert not any(marker.lower() in t.lower() for t in texts) and marker not in caplog.text


async def test_write_keeps_unknown_bytes_and_other_players(client: httpx.AsyncClient, lib: Path) -> None:
    """Campi che l'editor non conosce (extra, padding, puntatori) restano com'erano; gli altri giocatori non sono toccati."""
    raw = bytearray((lib / "players" / "tizio.dat").read_bytes())
    raw[646:648] = b"\xaa\xbb"  # abilities.extra/extra2 area di padding
    raw[2900 - 3 : 2900] = b"\x01\x02\x03"
    (lib / "players" / "tizio.dat").write_bytes(bytes(raw))
    others = {k: v for k, v in files(lib).items() if "tizio" not in k}
    data(await client.patch(f"{BASE}/tizio", json={"details": {"hit": 300}}, headers=H))
    new = (lib / "players" / "tizio.dat").read_bytes()
    assert {i for i, (a, b) in enumerate(zip(raw, new, strict=True)) if a != b} == {654, 655}
    assert {k: v for k, v in files(lib).items() if "tizio" not in k} == others
    write_players(lib, {"extra": make_char("Extra")})  # un nuovo giocatore e' scrivibile subito
    assert data(await client.patch(f"{BASE}/extra", json={"details": {"gold": 1}}, headers=H))["gold"] == 1
