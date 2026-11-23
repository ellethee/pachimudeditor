"""Controllo dei contenuti pachimud: da `file:riga` alla voce (`/api/content/checks/locate`) e soglie del lint di stile."""

import httpx

from tests.helpers import data
from tests.support.stack import zones_dir

ALFA = "ZonaAlfa"


async def test_locate_resolves_entries_by_line(client: httpx.AsyncClient) -> None:
    """La riga di una voce porta a quella stanza; il file dei reset e `zone.yaml` alla zona; un file sconosciuto a `none`."""
    rooms = zones_dir() / ALFA / "rooms.yaml"
    lines = rooms.read_text().splitlines()
    first = next(n for n, ln in enumerate(lines, 1) if ln.strip().startswith("- vnum: 1000"))
    asked = [
        {"file": str(rooms), "line": first + 1},
        {"file": str(rooms), "line": None},
        {"file": str(zones_dir() / ALFA / "zone.yaml"), "line": 3},
        {"file": str(zones_dir() / ALFA / "resets.yaml"), "line": 2},
        {"file": "/altrove/zones/ZonaAlfa/rooms.yaml", "line": first + 1},  # stesso ramo `zones/<zona>/<file>`: percorso del gioco diverso
        {"file": "/nulla/di/noto.yaml", "line": 1},
    ]
    out = data(await client.post("/api/content/checks/locate", json={"items": asked}))
    assert out[0]["kind"] == "room" and out[0]["vnum"] == 1000 and out[0]["zoneId"] == 10
    assert out[1] == {"kind": "file", "vnum": None, "zoneId": 10}
    assert out[2]["kind"] == "zone" and out[3]["kind"] == "resets"
    assert out[4]["kind"] == "room" and out[4]["vnum"] == 1000
    assert out[5] == {"kind": "none", "vnum": None, "zoneId": None}


async def test_style_limits_default_to_the_manual(client: httpx.AsyncClient) -> None:
    """Senza `validate.style` nel `pachimud.yaml` valgono i default del manuale (titolo 80, descrizione 3-8 righe da 80, corta 40, lunga 80)."""
    out = data(await client.get("/api/content/checks/style"))
    assert (out["enabled"], out["roomNameMax"], out["descriptionMinLines"], out["descriptionMaxLines"]) == (True, 80, 3, 8)
    assert (out["descriptionWidth"], out["shortMax"], out["longMax"]) == (80, 40, 80) and "notte" in out["timeWords"]
