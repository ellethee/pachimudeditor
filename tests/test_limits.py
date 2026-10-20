"""Limiti sugli interi nel mondo pachimud: id/page/pageSize/vnum fuori range -> 422 (mai 500), e limiti dell'upload."""

import io
import zipfile
from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from pachifast import create_app

from pachimudeditor_adapter_pachimud.apps.content.module import module as content_module
from pachimudeditor_adapter_pachimud.apps.instances.module import module as instances_module
from pachimudeditor_adapter_pachimud.apps.players.module import module as players_module
from pachimudeditor_adapter_pachimud.apps.transfer.module import module as transfer_module
from pachimudeditor.common.adapters.plugins import available_kinds
from pachimudeditor.modules import build_modules
from tests.helpers import error_code
from tests.support.extra_apps import make_client

HUGE = 10**30
OVER_INT = 2**63
_modules = build_modules(available_kinds())
_names = {m.name for m in _modules}
_app = create_app((*_modules, *(m for m in (content_module, instances_module, players_module, transfer_module) if m.name not in _names)))

LISTS = ["zones", "rooms", "mobs", "objects", "instances/mobs", "instances/objects", "players/accounts", "players/characters"]
BY_ID = [
    "zones/{}",
    "zones/{}/usage",
    "zones/{}/summary",
    "zones/{}/reset-commands",
    "rooms/{}",
    "rooms/{}/usage",
    "mobs/{}",
    "mobs/{}/usage",
    "objects/{}",
    "objects/{}/usage",
    "instances/mobs/{}",
    "instances/objects/{}",
    "players/accounts/{}",
    "players/characters/{}",
    "players/characters/{}/inventory",
    "transfer/zones/{}/export",
    "transfer/zones/{}/export/bundle",
]


@pytest_asyncio.fixture
async def api(token: str) -> AsyncIterator[httpx.AsyncClient]:
    """Client sull'app con tutti i moduli pachimud."""
    async with make_client(_app, token) as client:
        yield client


@pytest.mark.parametrize("path", LISTS)
@pytest.mark.parametrize("query", ["page=99999999999999999999", f"pageSize={OVER_INT}", f"page={OVER_INT}&pageSize=2"])
async def test_huge_paging_is_not_a_500(api: httpx.AsyncClient, path: str, query: str) -> None:
    """Pagine e dimensioni enormi: mai 500."""
    assert (await api.get(f"/api/{path}?{query}")).status_code < 500


@pytest.mark.parametrize("path", BY_ID)
@pytest.mark.parametrize("value", [OVER_INT, HUGE])
async def test_huge_ids_are_not_a_500(api: httpx.AsyncClient, path: str, value: int) -> None:
    """Id enormi: 404 o 422, mai 500."""
    assert (await api.get(f"/api/{path.format(value)}")).status_code in (404, 422)


@pytest.mark.parametrize("vnum", [2**31, 3_000_000_000, OVER_INT, HUGE])
async def test_huge_vnum_rejected(api: httpx.AsyncClient, vnum: int) -> None:
    """Un vnum oltre il massimo e' un 422 chiaro, per stanze, mob, oggetti e zone."""
    assert (await api.post("/api/rooms", json={"vnum": vnum, "name": "x", "zoneId": 1})).status_code == 422
    assert (await api.post("/api/zones", json={"vnum": vnum, "name": "x"})).status_code == 422


def _zip(files: dict[str, str], folder: str = "z") -> bytes:
    """Zip in memoria."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, text in files.items():
            archive.writestr(f"{folder}/{name}", text)
    return buffer.getvalue()


ZONE = "zone_id: z\nvnum: 777\nname: n\nbuilder: b\nbottom_vnum: 1\ntop_vnum: 2\n"


async def test_multiple_zips_are_422_not_500(api: httpx.AsyncClient) -> None:
    """Due o sei zip nello stesso upload: 422 `multiple_zones` (prima FileExistsError -> 500)."""
    files = [("files", (f"z{i}.zip", _zip({"zone.yaml": ZONE}), "")) for i in range(6)]
    assert error_code(await api.post("/api/transfer/zones/import", files=files[:2]), 422) == "transfer.multiple_zones"
    assert error_code(await api.post("/api/transfer/zones/import", files=files), 422) == "transfer.multiple_zones"


async def test_too_many_files(api: httpx.AsyncClient) -> None:
    """Oltre il numero massimo di file: 422."""
    files = [("files", ("zone.yaml", ZONE, "")) for _ in range(11)]
    assert error_code(await api.post("/api/transfer/zones/import", files=files), 422) == "transfer.invalid_archive"


async def test_total_bytes_shared_across_zips(api: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Il limite sui byte e' cumulativo su tutti gli zip dell'upload."""
    from pachimudeditor_adapter_pachimud.apps.transfer import archive

    monkeypatch.setattr(archive, "MAX_UPLOAD_BYTES", 150)
    body = "a" * 60
    files = [("files", (f"z{i}.zip", _zip({"zone.yaml": body}, folder=f"d{i}"), "")) for i in range(3)]
    assert error_code(await api.post("/api/transfer/zones/import", files=files), 413) == "transfer.file_too_large"


async def test_zip_bomb_and_big_yaml_rejected(api: httpx.AsyncClient) -> None:
    """Uno zip minuscolo che si espande oltre la soglia del singolo YAML, e un YAML sopra soglia: 413."""
    bomb = _zip({"zone.yaml": ZONE, "rooms.yaml": "#" + "a" * (3 * 1024 * 1024)})
    assert len(bomb) < 10_000
    assert (
        error_code(await api.post("/api/transfer/zones/import", files=[("files", ("b.zip", bomb, ""))]), 413) == "transfer.file_too_large"
    )
    big = ("files", ("rooms.yaml", b"#" + b"a" * (3 * 1024 * 1024), ""))
    assert error_code(await api.post("/api/transfer/zones/import", files=[big]), 413) == "transfer.file_too_large"


async def test_too_many_records_and_many_vnums(api: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Troppi record: 422; molti vnum (oltre il limite variabili SQLite) in una dry-run: nessun errore SQL."""
    from pachimudeditor_adapter_pachimud.transfer import importer

    rooms = "rooms:\n" + "".join(f"- {{vnum: {n}, name: r, description: d}}\n" for n in range(10001, 12001))
    files = [("files", ("zone.yaml", ZONE.replace("top_vnum: 2", "top_vnum: 20000"), "")), ("files", ("rooms.yaml", rooms, ""))]
    r = await api.post("/api/transfer/zones/import", files=files)
    assert r.status_code == 200 and r.json()["data"]["rooms"]["create"] == 2000
    monkeypatch.setattr(importer, "MAX_RECORDS", 1000)
    assert error_code(await api.post("/api/transfer/zones/import", files=files), 422) == "transfer.invalid_file"
