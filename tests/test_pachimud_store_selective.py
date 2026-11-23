"""Riscrittura selettiva dell'archivio YAML pachimud: un salvataggio cambia nel file SOLO le righe delle voci modificate, aggiunte o tolte."""

from pathlib import Path

import pytest
from ruamel.yaml.comments import CommentedMap

from pachimudeditor_adapter_pachimud.store import YamlStore, new_yaml

ZONE = """\
zone_id: z
vnum: 10
name: Zona
builder: t
bottom_vnum: 1000
top_vnum: 1099
min_level: 1
max_level: 10
lifespan_minutes: 30
reset_mode: EMPTY
enabled: true
"""
MOBS = """\
# mob della zona (commento di testa)
mobs:
  # la prima guardia
  - vnum: 1000
    keywords: guardia
    short_description: una guardia
    long_description: Una guardia sorveglia il passaggio con aria severa, lo sguardo
      fisso sui viandanti che passano di qui ogni giorno.
    detailed_description: ""
    level: 1
    thac0: 20
    armor_class: 0
    hp_dice: 1d8+0
    damage_dice: 1d4+0  # colpisce piano

  # il ratto, dopo una riga vuota
  - vnum: 1001
    keywords: ratto
    short_description: un ratto
    long_description: Un ratto
      si muove tra le casse.
    detailed_description: ""
    level: 1
    thac0: 20
    armor_class: 0
    hp_dice: 1d8+0
    damage_dice: 1d4+0
  - vnum: 1002
    keywords: gatto
    short_description: un gatto
    long_description: Un gatto dorme.
    detailed_description: ""
    level: 1
    thac0: 20
    armor_class: 0
    hp_dice: 1d8+0
    damage_dice: 1d4+0
# coda del file
"""


@pytest.fixture
def mobs_file(tmp_path: Path) -> tuple[YamlStore, Path]:
    """Un archivio con una zona e un `mobs.yaml` scritto a mano (testi a capo, commenti, righe vuote)."""
    zone = tmp_path / "zones" / "Zona"
    zone.mkdir(parents=True)
    (zone / "zone.yaml").write_text(ZONE)
    (zone / "mobs.yaml").write_text(MOBS)
    store = YamlStore(tmp_path)
    store.refresh()
    return store, zone / "mobs.yaml"


def changed_lines(before: str, after: str) -> tuple[list[str], list[str]]:
    """Righe tolte e righe aggiunte fra due testi (senza il contesto)."""
    a, b = before.splitlines(), after.splitlines()
    return [x for x in a if x not in b], [x for x in b if x not in a]


def test_unchanged_save_is_byte_identical(mobs_file: tuple[YamlStore, Path]) -> None:
    """Un salvataggio senza modifiche non cambia nemmeno un byte (nessun reflow dei testi a capo)."""
    store, path = mobs_file
    store.save(store.find("mob", 1000).file)
    assert path.read_text() == MOBS


def test_one_field_changes_only_that_entry(mobs_file: tuple[YamlStore, Path]) -> None:
    """Cambiare un campo di un mob riscrive solo quel mob: le altre voci, i commenti e la coda del file restano identici."""
    store, path = mobs_file
    item = store.find("mob", 1001)
    item.raw["level"] = 7
    item.revalidate()
    store.save(item.file)
    text = path.read_text()
    removed, added = changed_lines(MOBS, text)
    assert "    level: 1" not in added and "    level: 7" in added
    assert all("1000" not in x and "gatto" not in x and "guardia" not in x for x in added)
    # la voce non toccata conserva il testo a capo, i commenti prima e dopo restano
    assert "    long_description: Una guardia sorveglia il passaggio con aria severa, lo sguardo\n      fisso sui viandanti" in text
    assert text.startswith("# mob della zona (commento di testa)\nmobs:\n  # la prima guardia\n  - vnum: 1000")
    assert "  # il ratto, dopo una riga vuota\n  - vnum: 1001" in text and text.endswith("# coda del file\n")
    assert "damage_dice: 1d4+0  # colpisce piano" in text
    assert store.find("mob", 1001).model.level == 7


def test_second_save_after_the_first_stays_selective(mobs_file: tuple[YamlStore, Path]) -> None:
    """Dopo un salvataggio i nodi restano vivi: un secondo salvataggio riscrive ancora solo la voce cambiata."""
    store, path = mobs_file
    first = store.find("mob", 1000)
    first.raw["level"] = 3
    first.revalidate()
    store.save(first.file)
    second = store.find("mob", 1002)
    second.raw["level"] = 9
    second.revalidate()
    store.save(second.file)
    text = path.read_text()
    assert "    long_description: Un ratto\n      si muove tra le casse." in text
    assert "    level: 3" in text and "    level: 9" in text
    assert [m.model.level for m in store.all_items("mob")] == [3, 1, 9]


def test_add_and_remove_entries(mobs_file: tuple[YamlStore, Path]) -> None:
    """Aggiungere una voce la mette in coda, toglierne una la toglie con la sua testata: le altre non cambiano."""
    store, path = mobs_file
    file = store.find("mob", 1000).file
    seq = file.list_of()
    new = CommentedMap(
        new_yaml().load(
            "vnum: 1003\nkeywords: cane\nshort_description: un cane\nlong_description: Un cane.\ndetailed_description: ''\nlevel: 2\nthac0: 20\narmor_class: 0\nhp_dice: 1d8+0\ndamage_dice: 1d4+0\n"
        )
    )
    seq.append(new)
    store.save(file)
    added_text = path.read_text()
    assert "  - vnum: 1003" in added_text and "    long_description: Un ratto\n      si muove tra le casse." in added_text
    assert store.find("mob", 1003) is not None
    seq = file.list_of()
    victim = next(n for n in seq if n["vnum"] == 1001)
    seq.remove(victim)
    store.save(file)
    text = path.read_text()
    assert "1001" not in text and "il ratto" not in text and "# la prima guardia" in text and "# coda del file" in text
    assert [m.vnum for m in store.all_items("mob")] == [1000, 1002, 1003]
    assert "    long_description: Una guardia sorveglia il passaggio con aria severa, lo sguardo\n      fisso sui viandanti" in text


def test_unusual_layout_falls_back_to_full_write(tmp_path: Path) -> None:
    """Un file con la lista in forma insolita (trattino su riga a parte) si riscrive per intero ma senza perdere dati."""
    zone = tmp_path / "zones" / "Zona"
    zone.mkdir(parents=True)
    (zone / "zone.yaml").write_text(ZONE)
    weird = "mobs:\n  -\n    vnum: 1000\n    keywords: guardia\n    short_description: una guardia\n    long_description: ''\n    detailed_description: ''\n    level: 1\n    thac0: 20\n    armor_class: 0\n    hp_dice: 1d8+0\n    damage_dice: 1d4+0\n"
    (zone / "mobs.yaml").write_text(weird)
    store = YamlStore(tmp_path)
    store.refresh()
    item = store.find("mob", 1000)
    item.raw["level"] = 4
    item.revalidate()
    store.save(item.file)
    again = YamlStore(tmp_path)
    again.refresh()
    assert again.find("mob", 1000).model.level == 4 and again.find("mob", 1000).model.keywords == "guardia"
