"""Trigger dei mob pachimud: il campo `triggers:` (`extra.triggers`), validazione e scrittura selettiva."""

import httpx

from tests.helpers import by_vnum, data, error_code
from tests.support.stack import zones_dir

TRIGGER = {"type": "speech", "argument": "aiuto", "chance": 50, "actions": ["say Ciao $n", "emote sorride a $n"]}


def _text() -> str:
    """Il testo dei file `mobs*.yaml` della zona di prova."""
    return "".join(p.read_text() for p in (zones_dir() / "ZonaAlfa").glob("mobs*.yaml"))


async def test_triggers_roundtrip_and_untouched(client: httpx.AsyncClient) -> None:
    """Si scrivono e si rileggono; un PUT che non li tocca o li ripete uguali non cambia il file; `[]` li toglie."""
    mob = await by_vnum(client, "mobs", 1000)
    assert mob["extra"]["triggers"] == []
    out = data(
        await client.put(f"/api/mobs/{mob['id']}", json={"extra": {"triggers": [TRIGGER, {"type": "death", "actions": ["say Ahi"]}]}})
    )
    assert out["extra"]["triggers"][0] == TRIGGER and out["extra"]["triggers"][1]["chance"] == 100
    written = _text()
    assert "triggers:" in written and "chance: 100" not in written
    # invariato: stesso file
    data(await client.put(f"/api/mobs/{mob['id']}", json={"extra": {"triggers": out["extra"]["triggers"]}}))
    data(await client.put(f"/api/mobs/{mob['id']}", json={"level": mob["level"]}))
    assert _text() == written
    cleared = data(await client.put(f"/api/mobs/{mob['id']}", json={"extra": {"triggers": []}}))
    assert cleared["extra"]["triggers"] == []


async def test_triggers_invalid(client: httpx.AsyncClient) -> None:
    """Tipo, probabilita' e azioni non valide sono 422 con code stabile."""
    mob = await by_vnum(client, "mobs", 1000)
    url = f"/api/mobs/{mob['id']}"
    bad_type = {**TRIGGER, "type": "nope"}
    assert error_code(await client.put(url, json={"extra": {"triggers": [bad_type]}}), 422) == "pachimud.invalid_choice"
    assert error_code(await client.put(url, json={"extra": {"triggers": [{**TRIGGER, "chance": 101}]}}), 422) == "pachimud.invalid_range"
    assert error_code(await client.put(url, json={"extra": {"triggers": [{**TRIGGER, "chance": 0}]}}), 422) == "pachimud.invalid_range"
    assert error_code(await client.put(url, json={"extra": {"triggers": [{**TRIGGER, "actions": []}]}}), 422) == "pachimud.invalid_length"
