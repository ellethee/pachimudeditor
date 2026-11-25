"""File YAML grezzi delle zone pachimud: elenco, lettura, scrittura validata, percorsi, sola lettura e rilettura."""

import httpx
import pytest

from pachimudeditor.common.adapters.registry import get_registry

from tests.helpers import data, error_code
from tests.support.stack import zones_dir

URL = "/api/content/zonefiles"
MOBS = "ZonaAlfa/mobs.yaml"


async def test_list_and_read(client: httpx.AsyncClient) -> None:
    """L'elenco ha zona, tipo e schema; la lettura restituisce il testo identico al disco."""
    listed = {e["path"]: e for e in data(await client.get(URL))}
    assert listed[MOBS]["kind"] == "mobs" and listed[MOBS]["schemaName"] == "mobs" and listed[MOBS]["zone"] == "ZonaAlfa"
    assert listed["ZonaAlfa/zone.yaml"]["schemaName"] == "zone" and "ZonaVuota/zone.yaml" in listed
    one = data(await client.get(f"{URL}/{MOBS}"))
    assert one["text"] == (zones_dir() / MOBS).read_text() and one["etag"] == listed[MOBS]["etag"]


async def test_valid_write_minimal_diff_and_reread(client: httpx.AsyncClient) -> None:
    """Un PUT valido cambia solo il testo inviato, uno identico non riscrive il file e GET /api/mobs vede la modifica."""
    path = zones_dir() / MOBS
    old = path.read_text()
    assert data(await client.put(f"{URL}/{MOBS}", json={"text": old}))["text"] == old
    mtime = path.stat().st_mtime_ns
    assert data(await client.put(f"{URL}/{MOBS}", json={"text": old}))["path"] == MOBS and path.stat().st_mtime_ns == mtime
    new = old.replace("una guardia", "una guardia scelta", 1)
    saved = data(await client.put(f"{URL}/{MOBS}", json={"text": new}))
    assert path.read_text() == new and saved["etag"] != data(await client.get(f"{URL}/ZonaAlfa/rooms.yaml"))["etag"]
    mobs = data(await client.get("/api/mobs"))
    assert "una guardia scelta" in str(mobs)
    assert error_code(await client.put(f"{URL}/{MOBS}", json={"text": new, "etag": "vecchio"}), 409) == "pachimud.zonefile_changed"


async def test_invalid_yaml_and_schema_do_not_write(client: httpx.AsyncClient) -> None:
    """YAML rotto -> 422 con riga e colonna; campo ignoto, tipo errato o trigger sbagliato -> 422 con campo e riga; il file resta com'era."""
    path = zones_dir() / MOBS
    old = path.read_text()
    broken = await client.put(f"{URL}/{MOBS}", json={"text": "mobs:\n  - vnum: [1\n"})
    assert error_code(broken, 422) == "pachimud.yaml_invalid"
    assert "riga" in str(broken.json()) and "colonna" in str(broken.json())
    unknown = (zones_dir() / "ZonaAlfa/objects.yaml").read_text().replace("cost: 1\n", "cost: 1\n    colore: rosso\n", 1)
    r = await client.put(f"{URL}/ZonaAlfa/objects.yaml", json={"text": unknown})
    assert error_code(r, 422) == "pachimud.zonefile_invalid" and "colore" in str(r.json())
    wrong = old.replace("level: 1\n", "level: tanti\n", 1)
    r = await client.put(f"{URL}/{MOBS}", json={"text": wrong})
    assert error_code(r, 422) == "pachimud.zonefile_invalid" and "mobs[0].level" in str(r.json()) and "riga 7" in str(r.json())
    trig = old.replace(
        "level: 1\n",
        "level: 1\n    triggers:\n      - type: inesistente\n        argument: ''\n        chance: 100\n        actions: [say ciao]\n",
        1,
    )
    assert error_code(await client.put(f"{URL}/{MOBS}", json={"text": trig}), 422) == "pachimud.zonefile_invalid"
    assert error_code(await client.put(f"{URL}/ZonaAlfa/zone.yaml", json={"text": "vnum: x\n"}), 422) == "pachimud.zonefile_invalid"
    assert error_code(await client.put(f"{URL}/ZonaAlfa/resets.yaml", json={"text": "resets: 3\n"}), 422) == "pachimud.zonefile_invalid"
    assert path.read_text() == old


async def test_paths_and_missing_files(client: httpx.AsyncClient) -> None:
    """Niente traversal, niente file fuori dalle zone o inesistenti (404), niente creazione."""
    for rel in (
        "..%2Fraces%2Fhuman.yaml",
        "ZonaAlfa%2F..%2F..%2Fx.yaml",
        "ZonaAlfa/nuovo.yaml",
        "ZonaAlfa/rooms_nuovo.yaml",
        "/etc/passwd",
    ):
        assert error_code(await client.get(f"{URL}/{rel}"), 404) == "pachimud.zonefile_not_found"
        assert error_code(await client.put(f"{URL}/{rel}", json={"text": "rooms: []\n"}), 404) == "pachimud.zonefile_not_found"
    assert not (zones_dir() / "ZonaAlfa" / "rooms_nuovo.yaml").exists()


async def test_read_only_world(client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Mondo `read_only`: elenco e lettura ok, il PUT e' 409 `world.read_only` e il file non cambia."""
    monkeypatch.setattr(get_registry().get("pachimud").config, "read_only", True)
    old = (zones_dir() / MOBS).read_text()
    assert data(await client.get(URL)) and data(await client.get(f"{URL}/{MOBS}"))["text"] == old
    assert error_code(await client.put(f"{URL}/{MOBS}", json={"text": old + "# x\n"}), 409) == "world.read_only"
    assert (zones_dir() / MOBS).read_text() == old
