"""Content a strati: skill, tabelle, social, cataloghi e testi su copie temporanee (strato di base + strato dell'utente)."""

import dataclasses
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

from pachimudeditor.common.adapters.registry import get_registry
from tests.helpers import data, error_code
from tests.support.extra_apps import build_app, make_client

SKILL = """# commento da non perdere
skill_id: fireball
kind: spell
name: fireball
mana: 50
levels:
  mage: 25
effects:
- type: damage
  amount: dice(level, 8)
messages:
  hit.you:
    it: Colpisci
"""
SOCIALS = """# social di base
smile:
  aliases: []
  position: resting
  victim_min_position: 0
  hide: true
  messages:
    it:
      no_arg: Sorridi felice.
"""


@pytest.fixture(autouse=True)
def layers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Strato di base (con una skill, un social, una tabella e un catalogo) e strato dell'utente vuoto."""
    base, user = tmp_path / "base", tmp_path / "user"
    for root in (base, user):
        root.mkdir()
    (base / "skills").mkdir()
    (base / "skills" / "fireball.yaml").write_text(SKILL, encoding="utf-8")
    (base / "skills" / "fireball.en.yaml").write_text("messages:\n  hit.you: You hit\n", encoding="utf-8")
    (base / "tables").mkdir()
    (base / "tables" / "socials.yaml").write_text(SOCIALS, encoding="utf-8")
    (base / "tables" / "socials.en.yaml").write_text("smile:\n  no_arg: You smile.\n", encoding="utf-8")
    (base / "tables" / "liquids.yaml").write_text("water:\n  drunk: 0\n", encoding="utf-8")
    (base / "locales" / "it").mkdir(parents=True)
    (base / "locales" / "it" / "fight.yaml").write_text("hit: Colpisci\n", encoding="utf-8")
    (base / "texts").mkdir()
    (base / "texts" / "news.it.txt").write_text("Novita'\n", encoding="utf-8")
    adapter = get_registry().get("pachimud")
    monkeypatch.setattr(adapter, "params", dataclasses.replace(adapter.params, definitions_path=user, base_definitions_path=base))
    return base, user


@pytest_asyncio.fixture
async def api(token: str) -> AsyncIterator[httpx.AsyncClient]:
    """Client sull'app con il modulo content."""
    async with make_client(build_app(), token) as client:
        yield client


async def test_skills_layers_and_copy_on_write(api: httpx.AsyncClient, layers: tuple[Path, Path]) -> None:
    """La skill di base si legge (le traduzioni `.en.yaml` non sono skill); modificarla la copia nello strato dell'utente coi commenti."""
    listed = data(await api.get("/api/content/skills"))
    assert [s["skillId"] for s in listed] == ["fireball"] and listed[0]["layer"] == "base" and listed[0]["levels"] == {"mage": 25}
    one = data(await api.get("/api/content/skills/fireball"))
    assert one["mana"] == 50 and "effects:" in one["advanced"] and "skill_id" not in one["advanced"]
    saved = data(await api.put("/api/content/skills/fireball", json={"mana": 40, "advanced": one["advanced"] + "handler: m:f\n"}))
    assert saved["layer"] == "user" and saved["mana"] == 40 and "handler: m:f" in saved["advanced"]
    text = (layers[1] / "skills" / "fireball.yaml").read_text(encoding="utf-8")
    assert "# commento da non perdere" in text and "mana: 40" in text and "dice(level, 8)" in text
    assert "mana: 50" in (layers[0] / "skills" / "fireball.yaml").read_text(encoding="utf-8")  # la base non si tocca
    assert (await api.delete("/api/content/skills/fireball")).status_code == 204
    assert data(await api.get("/api/content/skills/fireball"))["layer"] == "base"
    assert error_code(await api.delete("/api/content/skills/fireball"), 404) == "content.not_found"


async def test_skill_create_and_errors(api: httpx.AsyncClient, layers: tuple[Path, Path]) -> None:
    """Creazione, id doppio/non valido, YAML avanzato rotto o che ripete i campi del form."""
    created = await api.post("/api/content/skills", json={"skillId": "zap", "kind": "spell", "name": "zap", "mana": 5})
    assert created.status_code == 201 and (layers[1] / "skills" / "zap.yaml").is_file()
    assert error_code(await api.post("/api/content/skills", json={"skillId": "zap"}), 409) == "content.id_taken"
    assert error_code(await api.post("/api/content/skills", json={"skillId": "Zap!"}), 422) == "content.invalid_id"
    bad = await api.put("/api/content/skills/zap", json={"advanced": "effects: [\n"})
    assert error_code(bad, 422) == "content.invalid" and "riga" in bad.json()["detail"][0]["msg"]
    assert error_code(await api.put("/api/content/skills/zap", json={"advanced": "mana: 3\n"}), 422) == "content.invalid"
    assert error_code(await api.put("/api/content/skills/nope", json={"mana": 1}), 404) == "content.not_found"


async def test_socials_merge_languages_and_write_user_layer(api: httpx.AsyncClient, layers: tuple[Path, Path]) -> None:
    """Social di base con la traduzione `socials.en.yaml` fusa; la modifica scrive tutte le lingue nello strato dell'utente."""
    smile = data(await api.get("/api/content/socials"))[0]
    assert (
        smile["name"] == "smile"
        and smile["hide"] is True
        and smile["messages"] == {"it": {"no_arg": "Sorridi felice."}, "en": {"no_arg": "You smile."}}
    )
    smile["messages"]["it"]["found"] = "Sorridi a $N."
    body = {k: smile[k] for k in ("aliases", "position", "victimMinPosition", "hide", "messages")}
    saved = data(await api.put("/api/content/socials/smile", json=body))
    assert saved["layer"] == "user" and saved["messages"]["it"]["found"] == "Sorridi a $N."
    assert "found: Sorridi a $N." in (layers[1] / "tables" / "socials.yaml").read_text(encoding="utf-8")
    assert (
        await api.post("/api/content/socials/wave", json={"messages": {"it": {"no_arg": "Saluti."}, "en": {"no_arg": "  "}}})
    ).status_code == 201
    assert data(await api.get("/api/content/socials"))[-1]["messages"] == {"it": {"no_arg": "Saluti."}}  # testi vuoti non scritti
    assert error_code(await api.post("/api/content/socials/wave", json={}), 409) == "content.id_taken"
    assert (await api.delete("/api/content/socials/smile")).status_code == 204
    assert data(await api.get("/api/content/socials"))[0]["layer"] == "base"


async def test_files_list_read_write_delete(api: httpx.AsyncClient, layers: tuple[Path, Path]) -> None:
    """Tabelle, cataloghi e testi: elenco con strato, lettura, scrittura (solo strato dell'utente), eliminazione."""
    tables = data(await api.get("/api/content/files/tables"))
    assert [(f["path"], f["layer"]) for f in tables] == [("liquids.yaml", "base")]  # i social hanno la loro pagina
    assert data(await api.get("/api/content/files/locales"))[0]["path"] == "it/fight.yaml"
    assert data(await api.get("/api/content/files/texts/news.it.txt"))["text"] == "Novita'\n"
    out = data(await api.put("/api/content/files/locales/it/fight.yaml", json={"text": "# nota\nhit: Colpisci forte\n"}))
    assert out["layer"] == "user" and (layers[1] / "locales" / "it" / "fight.yaml").read_text(encoding="utf-8").startswith("# nota")
    assert "Novita'" in (layers[0] / "texts" / "news.it.txt").read_text(encoding="utf-8")
    assert data(await api.get("/api/content/files/locales/it/fight.yaml"))["layer"] == "user"
    assert (await api.delete("/api/content/files/locales/it/fight.yaml")).status_code == 204
    assert data(await api.get("/api/content/files/locales/it/fight.yaml"))["layer"] == "base"
    assert error_code(await api.delete("/api/content/files/locales/it/fight.yaml"), 404) == "content.not_found"


async def test_files_reject_bad_paths_and_yaml(api: httpx.AsyncClient, layers: tuple[Path, Path]) -> None:
    """Niente `..`, estensioni sbagliate, social nelle tabelle, YAML rotto o non UTF-8, file enormi; nulla viene scritto."""
    for rel in ("..%2Fskills%2Ffireball.yaml", "it/../../x.yaml", "it/x.txt", "socials.yaml", "a b.yaml"):
        r = await api.put(f"/api/content/files/{'tables' if rel == 'socials.yaml' else 'locales'}/{rel}", json={"text": "a: 1\n"})
        assert r.status_code in (404, 405, 422), rel  # httpx normalizza `..` prima di inviare
    bad = await api.put("/api/content/files/tables/x.yaml", json={"text": "a: [1\n"})
    assert error_code(bad, 422) == "content.invalid" and "riga" in bad.json()["detail"][0]["msg"]
    assert error_code(await api.put("/api/content/files/tables/x.yaml", json={"text": "just a string"}), 422) == "content.invalid"
    assert error_code(await api.put("/api/content/files/tables/x.yaml", json={"text": "a: " + "x" * 600_000}), 422) == "content.too_large"
    (layers[0] / "texts" / "bad.it.txt").write_bytes(b"\xff\xfe")
    assert error_code(await api.get("/api/content/files/texts/bad.it.txt"), 422) == "content.invalid"
    assert not list(layers[1].rglob("*.yaml"))
    assert (await api.get("/api/content/files/nothing/x.yaml")).status_code == 422


def test_safe_path_rejects_traversal(layers: tuple[Path, Path]) -> None:
    """`_safe` rifiuta `..` anche se il client non lo normalizza."""
    from fastapi import HTTPException

    from pachimudeditor_adapter_pachimud.apps.content import files_store

    for rel in ("../skills/fireball.yaml", "it/../../x.yaml", "/etc/passwd.yaml", "it//x.yaml"):
        with pytest.raises(HTTPException):
            files_store._safe(layers[1], "locales", rel)  # noqa: SLF001
