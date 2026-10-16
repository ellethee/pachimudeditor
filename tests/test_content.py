"""Content: CRUD di razze e classi su copie temporanee di `definitions/` (mai la cartella reale)."""

import dataclasses
import shutil
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from pachimud.mob.models import MobPrototype
from sqlalchemy import update

from pachimudeditor.common.adapters.registry import get_registry
from tests.helpers import data, error_code
from tests.support import gamedb
from tests.support.extra_apps import build_app, make_client
from tests.support.stack import REPO_ROOT


@pytest.fixture(autouse=True)
def definitions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Copia di `definitions/` in tmp_path e `definitions_path` del mondo pachimud puntato li'."""
    target = tmp_path / "definitions"
    shutil.copytree(REPO_ROOT / "definitions", target, ignore=shutil.ignore_patterns("zones"))
    adapter = get_registry().get("pachimud")
    monkeypatch.setattr(adapter, "params", dataclasses.replace(adapter.params, definitions_path=target))
    return target


@pytest_asyncio.fixture
async def api(token: str) -> AsyncIterator[httpx.AsyncClient]:
    """Client sull'app con il modulo content."""
    async with make_client(build_app(), token) as client:
        yield client


async def _set_mob(**values: object) -> None:
    """Aggiorna il mob 1000 del DB temporaneo."""
    async with gamedb.get_session_factory()() as session:
        await session.execute(update(MobPrototype).where(MobPrototype.vnum == 1000).values(**values))
        await session.commit()


async def test_guard_not_real_definitions(definitions: Path) -> None:
    """La config in uso punta alla copia temporanea."""
    assert get_registry().get("pachimud").params.definitions_path == definitions
    assert REPO_ROOT / "definitions" != definitions


async def test_list_and_get(api: httpx.AsyncClient) -> None:
    """Elenco razze/classi con metadati; dettaglio camelCase."""
    races = data(await api.get("/api/content/races"))
    assert len(races) >= 30 and all(r["valid"] for r in races)
    human = next(r for r in races if r["raceId"] == "human")
    assert human["mobOnly"] is False and human["maxStats"]["strength"] == 18 and human["file"] == "human.yaml"
    classes = data(await api.get("/api/content/classes"))
    assert {c["classId"] for c in classes} >= {"mage", "cleric", "thief", "warrior"}
    one = data(await api.get("/api/content/classes/mage"))
    assert one["attrPrime"] == "intelligence" and one["attrsPriority"][0] == "intelligence"
    assert error_code(await api.get("/api/content/races/nope"), 404) == "content.not_found"


async def test_update_preserves_comments(api: httpx.AsyncClient, definitions: Path) -> None:
    """Un update tocca solo la chiave cambiata: commenti e resto del file restano identici."""
    path = definitions / "races" / "dragon.yaml"
    before = path.read_text(encoding="utf-8")
    assert "# Form era codificato" in before
    body = data(await api.get("/api/content/races/dragon"))
    body["description"] = "Un drago antico."
    body["points"] = 40
    result = data(await api.put("/api/content/races/dragon", json=body))
    assert result["description"] == "Un drago antico." and result["points"] == 40
    after = path.read_text(encoding="utf-8")
    assert "# Form era codificato" in after
    changed = [(a, b) for a, b in zip(before.splitlines(), after.splitlines()) if a != b]
    assert changed == [("description: An ancient, fire-breathing reptile of immense size and cunning.", "description: Un drago antico.")]
    assert "points: 40" in after
    assert not list(path.parent.glob(".*.tmp"))  # scrittura atomica: nessun temporaneo rimasto
    # PUT parziale: solo i campi inviati
    partial = data(await api.put("/api/content/races/dragon", json={"raceId": "dragon", "name": "Dragon", "description": "x"}))
    assert partial["points"] == 40


async def test_update_rules(api: httpx.AsyncClient) -> None:
    """Id immutabile, flag sconosciuti e campi invalidi: 422."""
    base = {"raceId": "bat", "name": "Bat", "description": "d"}
    assert error_code(await api.put("/api/content/races/bat", json={**base, "raceId": "other"}), 422) == "content.id_mismatch"
    r = await api.put("/api/content/races/bat", json={**base, "resistance": ["NOT_A_FLAG"]})
    assert error_code(r, 422) == "content.invalid" and "NOT_A_FLAG" in r.text
    assert error_code(await api.put("/api/content/races/bat", json={**base, "size": "ENORME"}), 422) == "content.invalid"
    assert (await api.put("/api/content/races/bat", json={**base, "points": "x"})).status_code == 422
    assert error_code(await api.put("/api/content/races/zzz", json={**base, "raceId": "zzz"}), 404) == "content.not_found"
    bad_class = {"classId": "mage", "attrPrime": "luck", "attrsPriority": ["strength", "strength"]}
    assert error_code(await api.put("/api/content/classes/mage", json=bad_class), 422) == "content.invalid"


async def test_create_race_and_class(api: httpx.AsyncClient, definitions: Path) -> None:
    """Creazione: file scritto con le sole chiavi inviate; duplicato 409; id non sicuro 422."""
    body = {
        "raceId": "tiefling",
        "name": "Tiefling",
        "description": "Sangue infernale.\nSeconda riga.",
        "mobOnly": False,
        "resistance": ["FIRE"],
        "stats": {"strength": 10},
    }
    created = data(await api.post("/api/content/races", json=body), 201)
    assert created["raceId"] == "tiefling" and created["resistance"] == ["FIRE"]
    text = (definitions / "races" / "tiefling.yaml").read_text(encoding="utf-8")
    assert "race_id: tiefling" in text and "description: |" in text and "resistance:" in text
    assert "points" not in text and "immunity" not in text
    assert error_code(await api.post("/api/content/races", json=body), 409) == "content.id_taken"
    for bad in ("../evil", "A/B", "x" * 80, "", "con spazio"):
        r = await api.post("/api/content/races", json={**body, "raceId": bad})
        assert error_code(r, 422) == "content.invalid_id", bad
    assert not (definitions.parent / "evil.yaml").exists()
    cls = data(await api.post("/api/content/classes", json={"classId": "bard", "name": "Bard", "attrPrime": "charisma"}), 201)
    assert cls["classId"] == "bard" and (definitions / "classes" / "bard.yaml").is_file()
    # appare nel manager del gioco (stesse cartelle)
    assert any(c["classId"] == "bard" for c in data(await api.get("/api/content/classes")))


async def test_path_traversal_in_url(api: httpx.AsyncClient) -> None:
    """Id con caratteri di path nell'URL: mai risolti su disco."""
    for bad in ("..%2Fraces%2Fhuman", "..", "human.yaml"):
        r = await api.get(f"/api/content/races/{bad}")
        assert r.status_code in (404, 422)
    r = await api.delete("/api/content/races/..%2F..%2Fx")
    assert r.status_code in (404, 422)


async def test_delete_blocked_when_in_use(api: httpx.AsyncClient, definitions: Path) -> None:
    """Razza/classe usata da mob: 409 con count; libera: 204 e file rimosso."""
    await _set_mob(race_id="bat", class_id="mage", teaches_class_ids=["thief"])
    assert data(await api.get("/api/content/races/bat"))["mobCount"] == 1
    r = await api.delete("/api/content/races/bat")
    assert error_code(r, 409) == "content.race_in_use"
    detail = r.json()["detail"][0]
    assert detail["params"]["count"] == 1
    assert (definitions / "races" / "bat.yaml").exists()
    assert error_code(await api.delete("/api/content/classes/mage"), 409) == "content.class_in_use"
    assert error_code(await api.delete("/api/content/classes/thief"), 409) == "content.class_in_use"  # insegnata
    assert (await api.delete("/api/content/classes/cleric")).status_code == 204
    assert not (definitions / "classes" / "cleric.yaml").exists()
    assert (await api.delete("/api/content/races/wolf")).status_code == 204
    assert error_code(await api.delete("/api/content/races/wolf"), 404) == "content.not_found"


async def test_disable_enable(api: httpx.AsyncClient, definitions: Path) -> None:
    """Razza e classe: rinomina in .yaml.disabled (non piu' caricate dal gioco)."""
    race = data(await api.post("/api/content/races/fox/disable"))
    assert race["disabled"] is True and race["file"] == "fox.yaml.disabled"
    assert not (definitions / "races" / "fox.yaml").exists()
    # il RaceManager del gioco non la vede piu'
    from pachimud.character.race.manager import RaceManager
    from pachimud.config.schema.pachimud import PachimudConfig

    manager = RaceManager(PachimudConfig(definition_path=str(definitions)))
    manager.load_races()
    assert "fox" not in manager.races and "wolf" in manager.races
    # modificabile anche da disattivata, poi riattivabile
    assert data(await api.get("/api/content/races/fox"))["disabled"] is True
    assert data(await api.post("/api/content/races/fox/enable"))["file"] == "fox.yaml"
    klass = data(await api.post("/api/content/classes/thief/disable"))
    assert klass["disabled"] is True and klass["file"] == "thief.yaml.disabled"
    from pachimud.character.classes.manager import ClassManager

    cm = ClassManager(PachimudConfig(definition_path=str(definitions)))
    cm.load_classes()
    assert "thief" not in cm.classes
    assert data(await api.post("/api/content/classes/thief/enable"))["disabled"] is False
    assert (definitions / "classes" / "thief.yaml").is_file()


async def test_invalid_file_is_listed(api: httpx.AsyncClient, definitions: Path) -> None:
    """Un file con YAML/schema rotto compare nell'elenco con valid=false (e si puo' eliminare)."""
    (definitions / "races" / "rotta.yaml").write_text("race_id: rotta\nname: [", encoding="utf-8")
    item = next(r for r in data(await api.get("/api/content/races")) if r["file"] == "rotta.yaml")
    assert item["valid"] is False and item["error"] is not None
    assert (await api.delete("/api/content/races/rotta")).status_code == 204


async def test_options_and_status(api: httpx.AsyncClient) -> None:
    """Opzioni per le select e stato per il banner."""
    options = data(await api.get("/api/content/options"))
    assert "DRAGON" in options["formFlags"] and options["sizes"][0] == "TINY" and "strength" in options["stats"]
    assert "FIRE" in options["resistanceFlags"]
    status = data(await api.get("/api/content/status"))
    assert status["races"] >= 30 and status["lastModified"] > 0


async def test_requires_auth() -> None:
    """Senza token: 401."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=build_app()), base_url="http://test") as c:
        assert (await c.get("/api/content/races")).status_code == 401
