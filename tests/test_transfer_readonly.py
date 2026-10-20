"""Trasferimento in un mondo `read_only`: l'import vero e' respinto con 409 e non scrive; l'anteprima resta ammessa."""

import io
import zipfile

import httpx
import pytest

from pachimudeditor.common.adapters.registry import get_registry
from tests.helpers import data, error_code


async def test_import_apply_is_409_in_read_only(client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """`dryRun=false&confirm=true` -> 409 `world.read_only`; il dry-run (anteprima) risponde 200; niente scritto."""
    zone_id = next(z["id"] for z in data(await client.get("/api/zones"))["items"] if z["vnum"] == 10)
    bundle = data(await client.get(f"/api/transfer/zones/{zone_id}/export/bundle"))["files"]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in bundle.items():
            archive.writestr(f"z/{name}", text.replace("name: Zona Alfa", "name: Rinominata"))
    upload = [("files", ("z.zip", buffer.getvalue(), "application/zip"))]
    monkeypatch.setattr(get_registry().get("pachimud").config, "read_only", True)

    assert (await client.post("/api/transfer/zones/import", files=upload)).status_code == 200
    applied = await client.post("/api/transfer/zones/import?dryRun=false&confirm=true", files=upload)
    assert error_code(applied, 409) == "world.read_only"
    names = {z["name"] for z in data(await client.get("/api/zones"))["items"]}
    assert "Rinominata" not in names and "Zona Alfa" in names
