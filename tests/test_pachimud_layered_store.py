"""Razze e classi a strati: quelle di serie del gioco (base) compaiono nell'elenco, modificarle crea la copia nello strato dell'utente."""

from pathlib import Path

import pytest
from fastapi import HTTPException

from pachimudeditor_adapter_pachimud.apps.content.yaml_store import YamlDirStore
from pachimudeditor_adapter_pachimud.definitions import LoaderRace


def _store(tmp_path: Path) -> YamlDirStore:
    """Uno store con una razza di base (con commento) e una dell'utente che ne maschera un'altra."""
    base, user = tmp_path / "base", tmp_path / "user"
    (base / "races").mkdir(parents=True)
    (base / "races" / "elf.yaml").write_text("---\n# razza di serie\nrace_id: elf\nname: Elfo\ndescription: d\n", encoding="utf-8")
    (base / "races" / "orc.yaml").write_text("---\nrace_id: orc\nname: Orco\ndescription: d\n", encoding="utf-8")
    (user / "races").mkdir(parents=True)
    (user / "races" / "orc.yaml").write_text("---\nrace_id: orc\nname: Orco mio\ndescription: d\n", encoding="utf-8")
    return YamlDirStore(lambda: user, "races", LoaderRace, "race_id", base_roots=lambda: [base])


def test_base_items_are_listed_and_user_layer_wins(tmp_path: Path) -> None:
    """L'elenco unisce base e utente; a parita' di id vale quello dell'utente."""
    names = {s.raw["race_id"]: (s.raw["name"], s.base) for s in _store(tmp_path).stored()}
    assert names == {"elf": ("Elfo", True), "orc": ("Orco mio", False)}


def test_editing_a_base_item_copies_it_keeping_comments(tmp_path: Path) -> None:
    """Modificare una razza di base ne crea la copia nello strato dell'utente (commenti salvi); la base resta intatta."""
    store = _store(tmp_path)
    store.update("elf", {"name": "Elfo alto"})
    copy = tmp_path / "user" / "races" / "elf.yaml"
    assert "# razza di serie" in copy.read_text(encoding="utf-8") and "Elfo alto" in copy.read_text(encoding="utf-8")
    assert "Elfo alto" not in (tmp_path / "base" / "races" / "elf.yaml").read_text(encoding="utf-8")
    assert store.locate("elf").base is False  # type: ignore[union-attr]


def test_base_item_cannot_be_deleted_but_its_copy_can(tmp_path: Path) -> None:
    """Un elemento solo di base non si elimina (409); eliminare la copia dell'utente ripristina quello di base."""
    store = _store(tmp_path)
    with pytest.raises(HTTPException) as error:
        store.delete("elf")
    assert error.value.status_code == 409
    store.delete("orc")
    assert store.locate("orc").raw["name"] == "Orco"  # type: ignore[union-attr]
