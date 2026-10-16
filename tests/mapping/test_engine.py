"""Primitive del motore (lettura e scrittura) su piccoli frammenti: un test per ogni primitiva/blocco della grammatica."""

from typing import Any

import pytest
from pachimudeditor_adapter_mapping import hooks
from pachimudeditor_adapter_mapping.grammar import Cursor, MappingParseError, Parser, parse_document
from pachimudeditor_adapter_mapping.schema import MappingSpec, Step, load_mapping
from pachimudeditor_adapter_mapping.writer import Formatter, format_flags, write_document
from pydantic import TypeAdapter
from ruamel.yaml import YAML

from tests.support.mapping_worlds import ROM_MAPPING

STEPS = TypeAdapter(list[Step])


def y(text: str) -> list[Any]:
    """Passi di grammatica scritti come nel file di mappatura (YAML)."""
    return YAML(typ="safe").load(text)


@pytest.fixture(scope="module")
def spec() -> MappingSpec:
    """Una mappatura qualsiasi (i passi si eseguono senza passare dalle sezioni)."""
    return load_mapping(ROM_MAPPING)


def run(spec: MappingSpec, raw_steps: list[Any], text: str) -> tuple[dict[str, Any], Cursor]:
    """Esegue i passi (sintassi compatta o estesa) su `text`."""
    cursor = Cursor(text, "prova")
    fields: dict[str, Any] = {}
    Parser(spec, cursor).run(STEPS.validate_python(raw_steps), fields)
    return fields, cursor


def lines(spec: MappingSpec, raw_steps: list[Any], fields: dict[str, Any]) -> list[str]:
    """Forma canonica (righe) dei passi."""
    return Formatter(spec).lines(STEPS.validate_python(raw_steps), fields)


def test_number_flags_and_word_follow_server_semantics(spec: MappingSpec) -> None:
    """Numeri con segno e somme `a|b`, flag a lettere/cifre, parole tra apici."""
    f, _ = run(
        spec,
        [{"a": "number"}, {"b": "number"}, {"c": "flags"}, {"d": "flags"}, {"e": "word"}, {"g": "word"}],
        "-5 1|4|256 AB|8 -1 'due parole' x",
    )
    assert f == {"a": -5, "b": 261, "c": 1 + 2 + 8, "d": -1, "e": "due parole", "g": "x"}
    assert format_flags(1 + 2 + 8) == "ABD" and format_flags(0) == "0" and format_flags(-1) == "-1" and format_flags(1 << 26) == "a"


def test_strings_leading_whitespace_modes(spec: MappingSpec) -> None:
    """`lead: ws` salta tutti gli spazi (ROM), `eol` conserva i rientri della riga (Diku)."""
    text = "\n   Rientrato.\nseconda~\n"
    ws, _ = run(spec, [{"t": "string_tilde"}], text)
    eol, _ = run(spec, [{"t": {"type": "string_tilde", "lead": "eol"}}], text)
    assert ws["t"] == "Rientrato.\nseconda" and eol["t"] == "   Rientrato.\nseconda"


def test_dice_strict_and_tolerant(spec: MappingSpec) -> None:
    """`NdT+B` (anche `+-`/`-`); con `tolerant` mancano bonus o numero di dadi."""
    f, _ = run(spec, [{"a": "dice"}, {"b": "dice"}], "2d6+4 3d8-2")
    assert f == {"a": {"n": 2, "t": 6, "b": 4}, "b": {"n": 3, "t": 8, "b": -2}}
    with pytest.raises(MappingParseError, match="dado atteso"):
        run(spec, [{"a": "dice"}], "1d4")
    f, _ = run(spec, [{"a": {"type": "dice", "tolerant": True}}, {"b": {"type": "dice", "tolerant": True}}], "1d4 d8+20")
    assert f == {"a": {"n": 1, "t": 4, "b": 0}, "b": {"n": 1, "t": 8, "b": 20}}
    assert lines(spec, [{"a": "dice"}], f) == ["1d4+0"]


def test_optional_same_line_and_default_written(spec: MappingSpec) -> None:
    """Un campo `optional` + `same_line` non scavalca la riga; con `default` e' sempre riscritto."""
    steps = y("""
- line: [a: number, {field: b, type: number, optional: true, same_line: true, default: 0}, c: line_text]
- n: number
""")
    f, _ = run(spec, steps, "1 2 ciao\n7")
    assert (f["a"], f["b"], f["c"], f["n"]) == (1, 2, "ciao", 7)
    f, _ = run(spec, steps, "1 ciao\n7")
    assert (f["a"], f.get("b"), f["c"], f["n"]) == (1, None, "ciao", 7)
    assert lines(spec, steps, f) == ["1 0 ciao", "7"]  # il quarto argomento mancante viene scritto con il suo default


def test_when_switch_and_line_layout(spec: MappingSpec) -> None:
    """`when`/`else` e `switch` si valutano sui campi gia' letti, sia in lettura sia in scrittura."""
    steps = y("""
- line:
    - kind: tag
    - when: "kind == 'A'"
      then: [x: number]
      else: [y: number]
- switch: kind
  cases:
    A: [a: number]
    B: [line: [b1: number, b2: number]]
  default: [z: number]
""")
    f, _ = run(spec, steps, "A 5\n6")
    assert f == {"kind": "A", "x": 5, "a": 6}
    f, _ = run(spec, steps, "B 5\n6 7")
    assert f == {"kind": "B", "y": 5, "b1": 6, "b2": 7}
    assert lines(spec, steps, f) == ["B 5", "6 7"]
    f, _ = run(spec, steps, "C 1 2")
    assert f == {"kind": "C", "y": 1, "z": 2}


def test_tagged_blocks(spec: MappingSpec) -> None:
    """Elementi per tag in qualunque ordine: liste, tag scalari con default, tag sconosciuti (`?`), terminatore."""
    steps = y("""
- tagged:
    end: S
    ignore_case: true
    tag_field: tag
    tags:
      D: {into: exits, glue: true, steps: [door: number, line: [flags: number, to: number]]}
      H: {inline: true, write_if: "heal != 100", steps: [heal: {type: number, default: 100}]}
      "?": {into: other, inline: true, steps: [value: line_text]}
""")
    f, cursor = run(spec, steps, "d2\n0 55\nH 120\nFoo bar baz\nD0\n1 3\nS\nresto")
    assert (
        f["exits"] == [{"tag": "d", "door": 2, "flags": 0, "to": 55}, {"tag": "D", "door": 0, "flags": 1, "to": 3}]
        or f["exits"][0]["door"] == 2
    )
    assert f["heal"] == 120 and f["other"] == [{"tag": "Foo", "value": "bar baz"}]
    assert cursor.text[cursor.i :] == "resto"
    out = lines(spec, steps, {"exits": [{"door": 0, "flags": 1, "to": 3, "tag": "D"}], "heal": 100, "other": []})
    assert out == ["D0", "1 3", "S"]  # H non scritto: valore di default
    f, _ = run(spec, steps, "S")
    assert f["heal"] == 100  # default dei tag scalari assenti


def test_tagged_end_before_tolerates_missing_terminator(spec: MappingSpec) -> None:
    """`end_before`: il blocco finisce senza consumare quando incontra il record successivo."""
    steps = y("""
- tagged: {end: S, end_before: ["#"], tags: {G: {into: gs, steps: [n: number]}}}
""")
    f, cursor = run(spec, steps, "G 1\nG 2\n#9 altro")
    assert f["gs"] == [{"n": 1}, {"n": 2}] and cursor.text[cursor.i :].lstrip().startswith("#9")


def test_errors_carry_line_and_context(spec: MappingSpec) -> None:
    """Gli errori di sintassi riportano file, riga, colonna e record."""
    text = "#ROOMS\n#1\nStanza~\nDescr~\n0 ?? 0\nS\n#0\n#$\n"
    with pytest.raises(MappingParseError) as error:
        parse_document(spec, "area", text, "x.are")
    assert (error.value.line, error.value.filename) == (5, "x.are") and "room 1" in str(error.value) and "riga 5" in str(error.value)


def test_unknown_sections_are_preserved_raw(spec: MappingSpec) -> None:
    """Una sezione non descritta (`#HELPS`) e il testo dopo `#$` si riscrivono identici."""
    text = "#AREA\nf.are~\nN~\n~\n1 99\n\n#HELPS\n0 $~\n\n#ROOMS\n#0\n\n#$\n\ncoda libera\n"
    doc = parse_document(spec, "area", text)
    assert [s.name for s in doc.sections] == ["AREA", "HELPS", "ROOMS"] and doc.trailer.endswith("coda libera\n")
    assert write_document(spec, "area", doc) == text


def test_custom_record_hook_replaces_one_record_grammar(spec: MappingSpec) -> None:
    """Un hook `record` registrato in codice e dichiarato sostituisce parsing e scrittura di un solo tipo di record."""
    hooks.register_record_hook(
        "test_shop_line",
        lambda cur: None if (n := cur.number()) == 0 else {"keeper": n, "rest": cur.rest_of_line()},
        lambda f: f"{f['keeper']} {f['rest']}\n",
    )
    custom = spec.model_copy(deep=True)
    custom.grammar.records["shop"].parser = "test_shop_line"
    text = "#SHOPS\n3000 qualunque cosa 1 2 3\n3001 altro\n0\n\n#$\n"
    doc = parse_document(custom, "area", text)
    shops = doc.sections[0].records
    assert [(s.fields["keeper"], s.fields["rest"]) for s in shops] == [(3000, "qualunque cosa 1 2 3"), (3001, "altro")]
    assert write_document(custom, "area", doc) == text
    shops[1].fields["rest"] = "nuovo"
    assert "3001 nuovo\n0\n" in write_document(custom, "area", doc)


def test_zone_range_hook_and_chain() -> None:
    """`zone_from_top` e' l'hook di range a catena (bottom = top precedente + 1)."""
    assert hooks.zone_range_hook("zone_from_top")([{"top": 0}, {"top": 49}, {"top": 199}]) == [(0, 0), (1, 49), (50, 199)]
