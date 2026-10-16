"""API `/api/convert` (autenticata): mondi scelti per id nel corpo, anteprima, esecuzione con conferma, errori."""

import json
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

from pachimudeditor.common.adapters.registry import WorldConfig, WorldRegistry, set_registry
from tests.convert.conftest import make_rom_dir
from tests.support import stack
from tests.helpers import data, error_code


@pytest_asyncio.fixture(autouse=True)
async def worlds(tmp_path: Path) -> AsyncIterator[None]:
    """pachimud (default), `rom` scrivibile, `rom-ro` in sola lettura (su un'altra copia dei dati)."""
    rw = make_rom_dir(tmp_path / "rw" / "area")
    ro = make_rom_dir(tmp_path / "ro" / "area")
    registry = WorldRegistry(
        [
            WorldConfig(id="pachimud", name="Pachimud", params=stack.current_params()),
            WorldConfig(id="rom", kind="basedmud", name="ROM", path=str(rw)),
            WorldConfig(id="rom-ro", kind="basedmud", name="ROM ro", path=str(ro), read_only=True),
        ]
    )
    set_registry(registry)
    yield
    await registry.aclose_all()  # engine/aiosqlite chiusi prima che il loop finisca
    set_registry(None)


def body(**kw) -> dict:  # type: ignore[type-arg]
    """Corpo base: la zona 3700 di `rom` verso pachimud."""
    return {"sourceWorld": "rom", "targetWorld": "pachimud", "zoneIds": [3700], **kw}


async def test_auth_required(anon: httpx.AsyncClient) -> None:
    """Senza token tutte le rotte rispondono 401."""
    assert (await anon.get("/api/convert/pairs")).status_code == 401
    assert (await anon.post("/api/convert/preview", json=body())).status_code == 401
    assert (await anon.post("/api/convert/run", json=body())).status_code == 401


async def test_pairs(client: httpx.AsyncClient) -> None:
    """Mondi e coppie: sola lettura e stesso mondo non ammessi; il convertitore e' specifico per i kind noti."""
    result = data(await client.get("/api/convert/pairs"))
    assert {w["id"] for w in result["worlds"]} == {"pachimud", "rom", "rom-ro"}
    pairs = {(p["source"], p["target"]): p for p in result["pairs"]}
    assert pairs[("rom", "pachimud")]["allowed"] and pairs[("rom", "pachimud")]["converter"] == "specific"
    assert pairs[("rom", "rom-ro")]["reason"] == "target_read_only"
    assert pairs[("rom", "rom")]["reason"] == "same_world"
    assert pairs[("rom-ro", "pachimud")]["allowed"]
    assert result["journalEnabled"] is False


async def test_preview_then_run(client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """L'anteprima non scrive, i messaggi sono tradotti; `/run` richiede dryRun=false e confirm=true e scrive il giornale."""
    journal = tmp_path / "journal"
    monkeypatch.setenv("WEBEDITOR_CONVERT_JOURNAL_DIR", str(journal))
    # `X-World` non conta: i mondi stanno nel corpo
    preview = data(await client.post("/api/convert/preview", json=body(dryRun=False, confirm=True), headers={"X-World": "rom-ro"}))
    assert preview["dryRun"] is True and preview["applied"] is False and preview["zones"][0]["action"] == "create"
    assert all(item["message"] for item in preview["losses"])
    assert any("negozio" in item["message"] for item in preview["losses"] if item["code"] == "shop_unsupported")
    assert [z["vnum"] for z in data(await client.get("/api/zones"))["items"]] == [10, 20]

    default = data(await client.post("/api/convert/run", json=body()))  # dryRun di default: nessuna scrittura
    assert default["dryRun"] is True
    refused = await client.post("/api/convert/run", json=body(dryRun=False))
    assert error_code(refused, 422) == "convert.confirm_required"

    done = data(await client.post("/api/convert/run", json=body(dryRun=False, confirm=True)))
    assert done["applied"] is True and done["journal"]["enabled"] is True
    assert [z["vnum"] for z in data(await client.get("/api/zones"))["items"]] == [10, 20, 3700]
    saved = json.loads((journal / done["journal"]["file"]).read_text(encoding="utf-8"))
    assert saved["report"]["applied"] is True and saved["sourceWorld"] == "rom"
    again = data(await client.post("/api/convert/run", json=body(dryRun=False, confirm=True)))
    assert again["zones"][0]["action"] == "skip"


async def test_errors(client: httpx.AsyncClient) -> None:
    """Arrivo in sola lettura 409, stesso mondo 422, mondo o zona inesistenti 404, piano non valido 422."""
    assert error_code(await client.post("/api/convert/preview", json=body(targetWorld="rom-ro")), 409) == "world.read_only"
    assert error_code(await client.post("/api/convert/preview", json=body(targetWorld="rom")), 422) == "convert.same_world"
    assert error_code(await client.post("/api/convert/preview", json=body(targetWorld="nope")), 404) == "world.not_found"
    assert error_code(await client.post("/api/convert/preview", json=body(zoneIds=[424242])), 404) == "convert.zone_not_found"
    assert (await client.post("/api/convert/preview", json=body(zoneIds=[]))).status_code == 422
    assert (await client.post("/api/convert/preview", json=body(vnumPolicy={"mode": "keep", "offset": 5}))).status_code == 422
