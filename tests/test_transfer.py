"""Transfer: esportazione/importazione di zone nel formato YAML dell'importer del gioco."""

import io
import zipfile
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest_asyncio
from pachimud.database.base import Base
from pachimud.database.database import create_engine
from pachimud.zone.models import Zone
from sqlalchemy import select

from pachimudeditor.common.adapters.registry import WorldConfig, WorldRegistry, get_registry, set_registry
from tests.helpers import data, error_code
from tests.support import gamedb, stack
from tests.support.extra_apps import build_app, make_client

FILES = ("zone.yaml", "rooms.yaml", "mobs.yaml", "objects.yaml", "resets.yaml")


@pytest_asyncio.fixture
async def api(token: str) -> AsyncIterator[httpx.AsyncClient]:
    """Client sull'app con il modulo transfer."""
    async with make_client(build_app(), token) as client:
        yield client


def _zip(files: dict[str, str], folder: str = "z") -> bytes:
    """Zip in memoria con `files` sotto `folder/`."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in files.items():
            archive.writestr(f"{folder}/{name}" if folder else name, text)
    return buffer.getvalue()


async def _export_files(api: httpx.AsyncClient, zone_id: int, world: dict[str, str] | None = None) -> dict[str, str]:
    """I cinque testi YAML della zona via `/export/bundle` (nel mondo `world` = header `X-World`, se dato)."""
    return data(await api.get(f"/api/transfer/zones/{zone_id}/export/bundle", headers=world))["files"]


async def _zone_id(api: httpx.AsyncClient, vnum: int, world: dict[str, str] | None = None) -> int:
    """L'id della zona con quel vnum."""
    items = data(await api.get("/api/zones", headers=world))["items"]
    return next(z["id"] for z in items if z["vnum"] == vnum)


async def test_export_zip_and_bundle(api: httpx.AsyncClient) -> None:
    """Lo zip contiene i cinque file sotto una cartella e coincide con il bundle JSON."""
    zid = await _zone_id(api, 10)
    response = await api.get(f"/api/transfer/zones/{zid}/export")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "attachment" in response.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = archive.namelist()
        assert sorted(n.split("/")[1] for n in names) == sorted(FILES)
        texts = {n.split("/")[1]: archive.read(n).decode() for n in names}
    bundle = data(await api.get(f"/api/transfer/zones/{zid}/export/bundle"))
    assert bundle["files"] == texts and bundle["warnings"] == []
    assert "name: Zona Alfa" in texts["zone.yaml"] and "reset_mode: EMPTY" in texts["zone.yaml"]
    assert "type: LOAD_MOB" in texts["resets.yaml"] and "hp_dice: 1d8+0" in texts["mobs.yaml"]


async def test_export_not_found(api: httpx.AsyncClient) -> None:
    """Zona inesistente: 404 con codice stabile."""
    assert error_code(await api.get("/api/transfer/zones/9999/export"), 404) == "transfer.zone_not_found"


async def test_export_requires_auth() -> None:
    """Senza token: 401."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=build_app()), base_url="http://test") as c:
        assert (await c.get("/api/transfer/zones/1/export")).status_code == 401


async def test_roundtrip_into_empty_db(api: httpx.AsyncClient) -> None:
    """Esporta, importa in un DB vuoto, riesporta: i cinque file sono identici."""
    original = await _export_files(api, await _zone_id(api, 10))
    # secondo mondo pachimud con un DB di gioco vuoto (stesso schema): l'import avviene li', scelto con X-World
    from tests.stack_fixtures import WORKDIR

    path = WORKDIR / "roundtrip.db"
    for suffix in ("", "-wal", "-shm"):
        Path(f"{path}{suffix}").unlink(missing_ok=True)
    engine = create_engine(f"sqlite+aiosqlite:///{path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    previous = get_registry()
    registry = WorldRegistry(
        [
            WorldConfig(id="pachimud", kind="pachimud", params=stack.world_params(WORKDIR)),
            WorldConfig(
                id="rt",
                kind="pachimud",
                params={**stack.world_params(WORKDIR), "database_url": f"sqlite+aiosqlite:///{path}"},
            ),
        ],
        "pachimud",
    )
    set_registry(registry)
    rt = {"X-World": "rt"}
    try:
        upload = [("files", ("zona.zip", _zip(original), "application/zip"))]
        preview = data(await api.post("/api/transfer/zones/import", files=upload, headers=rt))
        assert preview["applied"] is False
        assert preview["zone"]["action"] == "create"
        assert (preview["rooms"]["create"], preview["mobs"]["create"], preview["objects"]["create"]) == (3, 2, 2)
        assert preview["resets"] == {"inFile": 2, "inDb": 0, "changed": True}
        assert preview["conflicts"] == []
        # dry-run: niente scritto
        assert data(await api.get("/api/zones", headers=rt))["total"] == 0

        no_confirm = await api.post("/api/transfer/zones/import?dryRun=false", files=upload, headers=rt)
        assert error_code(no_confirm, 422) == "transfer.confirm_required"
        assert data(await api.get("/api/zones", headers=rt))["total"] == 0

        done = data(await api.post("/api/transfer/zones/import?dryRun=false&confirm=true", files=upload, headers=rt))
        assert done["applied"] is True
        new_id = await _zone_id(api, 10, rt)
        assert await _export_files(api, new_id, rt) == original

        # secondo import identico: tutto invariato
        again = data(await api.post("/api/transfer/zones/import", files=upload, headers=rt))
        assert again["zone"]["action"] == "unchanged"
        for kind in ("rooms", "mobs", "objects"):
            assert again[kind]["create"] == 0 and again[kind]["update"] == 0
        assert again["resets"]["changed"] is False

        # modifica di un mob: update su quel vnum soltanto
        changed = dict(original)
        changed["mobs.yaml"] = original["mobs.yaml"].replace("level: 1\n", "level: 7\n", 1)
        diff = data(await api.post("/api/transfer/zones/import", files=[("files", ("m.zip", _zip(changed), ""))], headers=rt))
        assert diff["mobs"]["update"] == 1 and diff["mobs"]["unchanged"] == 1
        # il mondo di default non e' stato toccato
        assert data(await api.get("/api/zones"))["total"] == 2
    finally:
        await registry.aclose_all()
        set_registry(previous)


async def test_import_loose_yaml_files_and_kept_vnums(api: httpx.AsyncClient) -> None:
    """File yaml sciolti; un vnum assente dal file e' segnalato come 'kept' (mai cancellato)."""
    original = await _export_files(api, await _zone_id(api, 10))
    trimmed = original["rooms.yaml"].split("- vnum: 1002")[0]
    upload = [
        ("files", ("zone.yaml", original["zone.yaml"], "text/yaml")),
        ("files", ("rooms.yaml", trimmed, "text/yaml")),
    ]
    preview = data(await api.post("/api/transfer/zones/import", files=upload))
    assert preview["zone"]["action"] == "unchanged"
    assert preview["rooms"]["keptNotInFile"] == [1002]
    done = data(await api.post("/api/transfer/zones/import?dryRun=false&confirm=true", files=upload))
    assert done["applied"] is True
    rooms = data(await api.get("/api/rooms"))["items"]
    assert {r["vnum"] for r in rooms} == {1000, 1001, 1002}


async def test_import_vnum_conflict(api: httpx.AsyncClient) -> None:
    """Un vnum di stanza che nel DB appartiene a un'altra zona: segnalato e import bloccato (409)."""
    files = {
        "zone.yaml": "zone_id: altra\nvnum: 99\nname: Altra\nbuilder: x\nbottom_vnum: 9000\ntop_vnum: 9099\n",
        "rooms.yaml": "rooms:\n  - vnum: 1000\n    name: Rubata\n    description: x\n",
    }
    upload = [("files", ("z.zip", _zip(files), ""))]
    preview = data(await api.post("/api/transfer/zones/import", files=upload))
    assert preview["conflicts"] == [{"kind": "room", "vnum": 1000, "zoneVnum": 10, "zoneName": "Zona Alfa"}]
    assert any(w["code"] == "out_of_range" for w in preview["warnings"])
    blocked = await api.post("/api/transfer/zones/import?dryRun=false&confirm=true", files=upload)
    assert error_code(blocked, 409) == "transfer.vnum_conflict"
    room = next(r for r in data(await api.get("/api/rooms"))["items"] if r["vnum"] == 1000)
    assert room["name"] == "Piazza"


async def test_import_warnings(api: httpx.AsyncClient) -> None:
    """Uscite e reset verso vnum inesistenti, razza ignota e range sovrapposto producono warning."""
    files = {
        "zone.yaml": "zone_id: w\nvnum: 77\nname: W\nbuilder: x\nbottom_vnum: 1000\ntop_vnum: 1500\n",
        "rooms.yaml": "rooms:\n  - vnum: 1400\n    name: A\n    description: x\n    exits:\n      north:\n        target_vnum: 55555\n",
        "mobs.yaml": (
            "mobs:\n  - vnum: 1400\n    keywords: k\n    short_description: s\n    long_description: l\n"
            "    detailed_description: d\n    level: 1\n    thac0: 1\n    armor_class: 1\n"
            "    hp_dice: 1d1+0\n    damage_dice: 1d1+0\n    race_id: nonesiste\n"
        ),
        "resets.yaml": "resets:\n  - type: LOAD_MOB\n    mob_vnum: 1400\n    room_vnum: 4444\n",
    }
    preview = data(await api.post("/api/transfer/zones/import", files=[("files", ("w.zip", _zip(files), ""))]))
    codes = {w["code"] for w in preview["warnings"]}
    assert {"dangling_exit", "unknown_reset_ref", "unknown_race", "range_overlap"} <= codes


async def test_import_rejects_bad_uploads(api: httpx.AsyncClient) -> None:
    """Errori 422: yaml non valido, file sconosciuto, zip corrotto, zone.yaml mancante, nessun file."""
    bad = {"zone.yaml": "zone_id: x\nvnum: notanint\nname: n\nbuilder: b\nbottom_vnum: 1\ntop_vnum: 2\n"}
    r = await api.post("/api/transfer/zones/import", files=[("files", ("z.zip", _zip(bad), ""))])
    assert error_code(r, 422) == "transfer.invalid_file"
    r = await api.post("/api/transfer/zones/import", files=[("files", ("evil.txt", b"x", "text/plain"))])
    assert error_code(r, 422) == "transfer.unsupported_file"
    r = await api.post("/api/transfer/zones/import", files=[("files", ("z.zip", b"PKnotazip", ""))])
    assert error_code(r, 422) == "transfer.invalid_archive"
    r = await api.post("/api/transfer/zones/import", files=[("files", ("rooms.yaml", "rooms: []", ""))])
    assert error_code(r, 422) == "transfer.zone_missing"
    assert (await api.post("/api/transfer/zones/import")).status_code == 422


async def test_zip_slip_names_are_ignored(api: httpx.AsyncClient, tmp_path: Path) -> None:
    """I path dentro lo zip non vengono mai usati per scrivere: `../` e' innocuo."""
    original = await _export_files(api, await _zone_id(api, 10))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("../../zone.yaml", original["zone.yaml"])
        archive.writestr("/etc/evil.yaml", "x")
    preview = data(await api.post("/api/transfer/zones/import", files=[("files", ("s.zip", buffer.getvalue(), ""))]))
    assert preview["zone"]["vnum"] == 10
    assert not (tmp_path.parent / "zone.yaml").exists()


async def test_real_game_db_untouched() -> None:
    """Rete di sicurezza: la sessione dei test non e' quella reale."""
    async with gamedb.get_session_factory()() as session:
        assert "pachimudeditor-pytest" in str(get_registry().get("pachimud").params.database_url)  # type: ignore[attr-defined]
        assert (await session.execute(select(Zone))).scalars().first() is not None


def test_zip_members_summing_over_limit(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Ogni membro sta nel limite ma la somma dei byte letti lo supera: 413 (il totale non si fida del dichiarato)."""
    import pytest
    from fastapi import HTTPException

    from pachimudeditor_adapter_pachimud.apps.transfer import archive

    monkeypatch.setattr(archive, "MAX_UPLOAD_BYTES", 100)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in ("zone.yaml", "rooms.yaml"):
            zf.writestr(f"z/{name}", "a" * 60)
    with pytest.raises(HTTPException) as err:
        archive._extract_zip(buffer.getvalue(), "z.zip", tmp_path)
    assert err.value.status_code == 413
