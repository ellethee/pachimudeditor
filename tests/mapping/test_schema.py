"""Caricamento e validazione del YAML di mappatura: errori con file:riga, riferimenti incrociati, JSON Schema."""

import json
from pathlib import Path

import pytest
from pachimudeditor_adapter_mapping import hooks
from pachimudeditor_adapter_mapping.schema import SCHEMA_FILE, MappingConfigError, json_schema, load_mapping

from tests.support.mapping_worlds import DIKU_MAPPING, ROM_MAPPING


def test_examples_load() -> None:
    """I due esempi sono validi (grammatica, tabelle da file, hook dichiarati)."""
    rom, diku = load_mapping(ROM_MAPPING), load_mapping(DIKU_MAPPING)
    assert rom.layout.mode == "zone_files" and diku.layout.mode == "type_files"
    assert set(rom.grammar.records) >= {"mob", "object", "room", "reset", "zone_data", "zone_old"}
    assert [s.header for s in rom.grammar.files["area"].sections][:3] == ["AREADATA", "AREA", "MOBILES"]


def test_json_schema_file_is_in_sync() -> None:
    """`mapping.schema.json` (autocompletamento nell'editor) e' quello generato dai modelli: se cambia lo schema va rigenerato
    (`uv run python -c "from pachimudeditor_adapter_mapping.schema import write_json_schema; write_json_schema()"`)."""
    assert json.loads(SCHEMA_FILE.read_text(encoding="utf-8")) == json_schema()
    schema = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
    assert {"layout", "grammar", "model", "tables", "hooks", "rules"} <= set(schema["properties"])
    any_step = schema["$defs"]["AnyStep"]["anyOf"]
    assert any(s.get("maxProperties") == 1 for s in any_step)  # sintassi compatta `- nome: tipo`


def broken(tmp_path: Path, old: str, new: str, *, mapping: Path = ROM_MAPPING, locate: str | None = None) -> tuple[Path, int]:
    """Copia della mappatura con `old` sostituito da `new` (la prima volta); restituisce anche la riga (1-based) della sostituzione."""
    text = mapping.read_text(encoding="utf-8")
    assert old in text
    patched = text.replace(old, new, 1)
    line = patched[: patched.index(locate or new)].count("\n") + 1  # riga attesa nell'errore (default: la modifica)
    target = tmp_path / "broken" / "m.yaml"
    target.parent.mkdir(exist_ok=True)
    (target.parent / "rom_tables.yaml").write_text((mapping.parent / "rom_tables.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    target.write_text(patched, encoding="utf-8")
    return target, line


@pytest.mark.parametrize(
    ("old", "new", "fragment", "locate"),
    [
        ("  zone_file: area\n", "  zone_file: area\n  typo_key: 1\n", "typo_key", None),
        ("{from: ac.0, in_extra: true}", "{from: nessuno.0}", "campo del record sconosciuto", None),
        ('expr: "min_vnum or 0"', "expr: \"__import__('os')\"", "chiamata non ammessa", None),
        ("map: wear_loc_types}", "map: tabella_che_non_c_e}", "tabella sconosciuta", None),
        ("builder: {hook: rom_credits_builder}", "builder: {hook: hook_inesistente}", "hook field sconosciuto", None),
        (
            "hooks: [rom_credits_min_level, rom_credits_max_level, rom_credits_builder]",
            "hooks: [rom_credits_min_level, rom_credits_max_level]",
            "non dichiarato",
            "builder: {hook: rom_credits_builder}",
        ),
        ("record: reset, entity: reset", "record: nessun_record, entity: reset", "record sconosciuto", None),
        ("- name: string_tilde\n        - short_descr", "- name: string_tildee\n        - short_descr", "string_tildee", None),
        ('when: "min_vnum is None"', 'when: "campo_nuovo is None"', "campi sconosciuti nell'espressione", None),
        ("map: {0: INSIDE, 1: CITY", "map: {0: INSIDEE, 1: CITY", "membri non validi per SectorType", None),
        ("type: LOAD_MOB", "type: CARICA_MOB", "tipo di comando sconosciuto", None),
        (
            "      name: {from: name}\n      builder",
            "      name: {from: nome_che_non_c_e}\n      builder",
            "campo del record sconosciuto",
            None,
        ),
    ],
)
def test_errors_report_line_numbers(tmp_path: Path, old: str, new: str, fragment: str, locate: str | None) -> None:
    """Ogni errore e' riportato come `file:riga` della riga sbagliata, con un messaggio comprensibile."""
    path, line = broken(tmp_path, old, new, locate=locate)
    with pytest.raises(MappingConfigError) as error:
        load_mapping(path)
    message = str(error.value)
    assert fragment in message, message
    reported = {int(part.split(":")[1]) for part in message.split() if part.startswith(str(path)) and part.count(":") >= 2}
    assert any(abs(r - line) <= 1 for r in reported), (line, reported, message)


def test_invalid_yaml_and_missing_file(tmp_path: Path) -> None:
    """YAML malformato o file assente: `MappingConfigError`, mai un'eccezione generica."""
    bad = tmp_path / "bad.yaml"
    bad.write_text("layout: [unclosed\n", encoding="utf-8")
    with pytest.raises(MappingConfigError):
        load_mapping(bad)
    with pytest.raises(MappingConfigError):
        load_mapping(tmp_path / "manca.yaml")


def test_custom_hook_must_be_registered_and_declared(tmp_path: Path) -> None:
    """Un hook registrato in codice e dichiarato in `hooks:` e' usabile; il YAML non puo' importare codice."""
    hooks.register_field_hook(
        "test_upper_name", lambda f: str(f.get("name", "")).upper(), lambda f, v: f.__setitem__("name", str(v).lower())
    )
    path, _ = broken(tmp_path, "builder: {hook: rom_credits_builder}", "builder: {hook: test_upper_name}")
    with pytest.raises(MappingConfigError, match="non dichiarato"):
        load_mapping(path)
    path, _ = broken(
        tmp_path,
        "hooks: [rom_credits_min_level, rom_credits_max_level, rom_credits_builder]",
        "hooks: [rom_credits_min_level, rom_credits_max_level, rom_credits_builder, test_upper_name]",
    )
    text = path.read_text(encoding="utf-8").replace("builder: {hook: rom_credits_builder}", "builder: {hook: test_upper_name}")
    path.write_text(text, encoding="utf-8")
    assert load_mapping(path).model.zone.fields["builder"].hook == "test_upper_name"
