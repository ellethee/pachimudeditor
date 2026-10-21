"""Writer dei file giocatore (`dikumod_lib/players_write.py`): round-trip identico, ogni campo, validazione, rent, file corrotti."""

import struct
from typing import Any

import pytest

from pachimudeditor_adapter_dikumod.dikumod_lib.players import (
    CHAR_FILE_SIZE,
    RENT_ELEM_SIZE,
    RENT_HEADER_SIZE,
    PlayerFileError,
    parse_char_record,
    parse_rent,
)
from pachimudeditor_adapter_dikumod.dikumod_lib.players_write import (
    WRITABLE_FIELDS,
    PlayerValueError,
    RentEditor,
    apply_char_patch,
    char_revision,
    pack_item,
    rent_revision,
    rent_with_gold,
)
from tests.support.dikumod_players import PWD_MARKER, make_char, make_item, make_rent

PWD = slice(2974, 2985)
ITEM = {
    "values": (1, 2, 3, 4),
    "extra_flags": 8,
    "weight": 7,
    "name": "spada",
    "short": "Una spada",
    "description": "Una spada qui",
    "affects": [(18, 2)],
}


def changed(old: bytes, new: bytes) -> set[int]:
    """Gli offset dei byte diversi."""
    return {i for i, (a, b) in enumerate(zip(old, new, strict=True)) if a != b}


def test_no_change_is_identical_and_password_intact() -> None:
    """Nessun cambio (o gli stessi valori) = stesso file, byte per byte, con la password."""
    data = make_char("Tizio", skills={5: (80, 1)}, affects=[(3, 10, 2, 1, 0)])
    assert apply_char_patch(data, {}, {}) == data
    assert data[PWD].startswith(PWD_MARKER)
    same = {"title": "il Prode", "gold": 1234, "str": 16, "levels": {"Warrior": 12}, "conditions": {"drunk": 0}, "sex": 1}
    assert (
        apply_char_patch(
            data,
            same,
            {"skills": [{"index": 5, "learned": 80, "flags": 1}], "affects": [{"type": 3, "duration": 10, "modifier": 2, "location": 1}]},
        )
        == data
    )


# nome -> (valore valido, offset del campo, lunghezza in byte): il cambio tocca solo quel campo
FIELD_CASES: dict[str, tuple[Any, int, int]] = {
    "classMask": (8, 0, 4), "sex": (2, 4, 1), "played": (99, 32, 4), "race": (3, 36, 4), "weight": (77, 40, 4), "height": (88, 44, 4),
    "hometown": (5, 384, 2), "extraFlags": (3, 632, 4), "loadRoom": (-2, 636, 2),
    "str": (18, 638, 1), "strAdd": (50, 639, 1), "int": (11, 640, 1), "wis": (12, 641, 1), "dex": (13, 642, 1), "con": (14, 643, 1), "chr": (15, 644, 1),
    "mana": (21, 648, 2), "maxMana": (31, 650, 2), "hit": (101, 654, 2), "maxHit": (121, 656, 2), "move": (91, 660, 2), "maxMove": (111, 662, 2),
    "armor": (-70, 672, 2), "gold": (4321, 676, 4), "bankGold": (55, 680, 4), "exp": (66, 684, 4), "trueExp": (67, 688, 4),
    "hitroll": (-5, 696, 1), "damroll": (6, 697, 1), "spellsToLearn": (9, 2900, 1), "alignment": (-1000, 2904, 4), "affectedBy2": (2**32 - 1, 2912, 4),
    "actFlags": (0x40, 2920, 4), "startRoom": (3005, 3024, 4), "userFlags": (2, 3028, 4), "speaks": (3, 3032, 4),
    "title": ("il Saggio", 48, 80), "alias": ("ali", 2944, 30), "description": ("Alto e magro.", 386, 240), "extraStr": ("extra", 128, 255),
    "birth": ("2002-01-01T00:00:00+00:00", 28, 4), "lastLogon": ("2024-01-01T00:00:00Z", 2916, 4),
}  # fmt: skip


@pytest.mark.parametrize("name", sorted(FIELD_CASES))
def test_every_scalar_field_changes_only_its_bytes(name: str) -> None:
    """Ogni campo si scrive: cambiano solo i suoi byte, la password resta, il parser rilegge il valore."""
    data = make_char("Tizio")
    value, offset, size = FIELD_CASES[name]
    new = apply_char_patch(data, {name: value})
    assert len(new) == CHAR_FILE_SIZE and new[PWD] == data[PWD]
    assert changed(data, new) and changed(data, new) <= set(range(offset, offset + size)), name
    rec = parse_char_record(new)
    reread = {
        "gold": rec.points["gold"], "title": rec.title, "sex": rec.sex, "race": rec.race, "str": rec.abilities["str"],
        "hit": rec.points["hit"], "loadRoom": rec.load_room, "birth": rec.birth, "lastLogon": rec.last_logon,
    }  # fmt: skip
    if name in reread and name not in ("birth", "lastLogon"):
        assert reread[name] == value
    if name == "birth":
        assert rec.birth == 1_009_843_200
    if name == "lastLogon":
        assert rec.last_logon == 1_704_067_200


def test_unchanged_values_are_accepted_even_if_out_of_range() -> None:
    """Un valore uguale all'attuale non si valida (i file reali hanno maschere di classe e titoli da 80 byte pieni)."""
    raw = bytearray(make_char("Tizio"))
    struct.pack_into("<i", raw, 0, 1 << 20)
    raw[48:128] = b"t" * 80
    data = bytes(raw)
    assert apply_char_patch(data, {"classMask": 1 << 20, "title": "t" * 80}) == data
    with pytest.raises(PlayerValueError):
        apply_char_patch(data, {"classMask": (1 << 20) + 1})


def test_all_writable_fields_are_covered() -> None:
    """Ogni campo scrivibile e' provato (scalari/stringhe/date sopra; speciali sotto)."""
    assert set(FIELD_CASES) | {"affectedBy", "levels", "conditions", "savingThrows"} == set(WRITABLE_FIELDS)


def test_special_fields() -> None:
    """Livelli, flag, condizioni, tiri salvezza; i bit di affect senza nome restano."""
    data = bytearray(make_char("Tizio", class_mask=4 | 8))
    struct.pack_into("<I", data, 2908, 1 << 30 | 0x1)  # un bit senza nome + un flag noto
    new = apply_char_patch(
        bytes(data),
        {"affectedBy": [], "levels": {"Warrior": 20, "thief": 5}, "conditions": {"full": 3}, "savingThrows": [1, 2, 3, 4, 5, 6, 7, -8]},
    )
    rec = parse_char_record(new)
    assert rec.affected_by == 1 << 30 and rec.levels[2] == 20 and rec.levels[3] == 5 and rec.level == 20
    assert rec.conditions[1] == 3 and rec.saving_throws[-1] == -8
    flag = next(iter(__import__("pachimudeditor_adapter_dikumod.dikumod_lib.tables", fromlist=["T"]).FLAG_TABLES["affect_flags"]))
    assert parse_char_record(apply_char_patch(bytes(data), {"affectedBy": [flag]})).affected_by & ~(1 << 30)


def test_skills_and_affects_lists() -> None:
    """Sostituzione delle tabelle: voci tolte azzerate, voci nascoste (solo special/nummem) conservate, affect compattati."""
    data = bytearray(make_char("Tizio", skills={5: (80, 1), 9: (10, 0)}, affects=[(3, 10, 2, 1, 0), (4, 5, 1, 2, 3)]))
    data[700 + 20 * 4 + 2 : 700 + 20 * 4 + 4] = bytes((7, 8))  # skill 20: special/nummem senza learned/flags (non elencata)
    new = apply_char_patch(
        bytes(data),
        {},
        {
            "skills": [{"index": 5, "learned": 99, "flags": 2, "special": 1, "nummem": 2}],
            "affects": [{"type": 9, "duration": 1, "modifier": -1, "location": 2, "bitvector": 4}],
        },
    )
    rec = parse_char_record(new)
    assert [(s.index, s.learned, s.flags, s.special, s.nummem) for s in rec.skills] == [(5, 99, 2, 1, 2)]
    assert new[700 + 20 * 4 + 2 : 700 + 20 * 4 + 4] == bytes((7, 8))
    assert [(a.type, a.modifier, a.bitvector) for a in rec.affects] == [(9, -1, 4)]
    assert apply_char_patch(bytes(data), {}, {"affects": []})[2100:2900] == bytes(800)


@pytest.mark.parametrize(
    ("details", "reason"),
    [
        ({"str": 128}, "range"), ({"str": -129}, "range"), ({"hit": 2**15}, "range"), ({"gold": -1}, "range"), ({"gold": 2**31}, "range"),
        ({"sex": 3}, "range"), ({"race": 10_000}, "range"), ({"classMask": 1 << 11}, "range"), ({"spellsToLearn": 256}, "range"),
        ({"str": "5"}, "type"), ({"str": 5.0}, "type"), ({"str": True}, "type"), ({"str": None}, "type"), ({"gold": [1]}, "type"),
        ({"title": "x" * 80}, "too_long"), ({"alias": "x" * 30}, "too_long"), ({"description": "x" * 240}, "too_long"),
        ({"title": "a\nb"}, "charset"), ({"title": "a\0b"}, "charset"), ({"title": "€"}, "charset"), ({"title": 5}, "type"),
        ({"birth": "ieri"}, "type"), ({"birth": 5}, "type"), ({"lastLogon": "1900-01-01"}, "range"),
        ({"affectedBy": ["nonesiste"]}, "unknown_flag"), ({"affectedBy": "sanctuary"}, "type"),
        ({"levels": {"jedi": 5}}, "unknown_class"), ({"levels": {"warrior": 256}}, "range"), ({"levels": [1]}, "type"),
        ({"conditions": {"boh": 1}}, "unknown_field"), ({"conditions": 5}, "type"), ({"savingThrows": [1, 2]}, "type"),
        ({"name": "Altro"}, "read_only"), ({"level": 5}, "read_only"), ({"autoRent": True}, "read_only"),
        ({"password": "x"}, "read_only"), ({"pwd": "x"}, "read_only"), ({"inesistente": 1}, "unknown_field"),
    ],
)  # fmt: skip
def test_invalid_values_are_refused(details: dict[str, Any], reason: str) -> None:
    """Valori fuori intervallo, di tipo sbagliato, troppo lunghi o non rappresentabili: `PlayerValueError` con motivo stabile."""
    with pytest.raises(PlayerValueError) as caught:
        apply_char_patch(make_char(), details)
    assert caught.value.reason == reason


@pytest.mark.parametrize(
    "lists",
    [
        {"skills": [{"index": 350}]}, {"skills": [{"index": 1}, {"index": 1}]}, {"skills": [{"learned": 5}]}, {"skills": [{"index": 1, "learned": 256}]},
        {"skills": [{"index": 1, "boh": 1}]}, {"skills": "x"}, {"affects": [{"type": 1}] * 41}, {"affects": [{"type": 2**15}]}, {"affects": [{"zz": 1}]},
        {"altro": []},
    ],
)  # fmt: skip
def test_invalid_lists_are_refused(lists: dict[str, Any]) -> None:
    """Tabelle malformate: errore, nessuna scrittura."""
    with pytest.raises(PlayerValueError):
        apply_char_patch(make_char(), {}, lists)


def test_corrupted_files_are_refused() -> None:
    """File di dimensione sbagliata: `bad_size`, mai una scrittura parziale."""
    for bad in (b"", make_char()[:100], make_char() + b"x"):
        with pytest.raises(PlayerFileError) as caught:
            apply_char_patch(bad, {"gold": 1})
        assert caught.value.code == "bad_size"


def test_revisions_ignore_the_password() -> None:
    """La revisione cambia con i dati, non con la password (e non la rivela)."""
    a, b = make_char("Tizio", password=b"AAAA"), make_char("Tizio", password=b"BBBB")
    assert char_revision(a) == char_revision(b) != char_revision(make_char("Tizio", gold=1))
    assert rent_revision(None) == rent_revision(b"") != rent_revision(b"x")


# ------------------------------------------------------------------ rent


def editor(items: list[bytes], owner: str = "Tizio") -> RentEditor:
    """Un editor su un rent sintetico."""
    return RentEditor(make_rent(owner, items), "Tizio", gold=900, now=1_800_000_000)


def test_rent_roundtrip_is_identical() -> None:
    """Aprire e riserializzare un rent coerente non cambia un byte (anche con owner di maiuscole diverse)."""
    data = make_rent("tizio", [make_item(1, wearpos=6, affects=2), make_item(2), make_item(3, depth=1)])
    assert RentEditor(data, "Tizio", gold=0, now=1).to_bytes() == data
    dirty = make_rent("Tizio\0avanzi", [make_item(1)])  # i file reali hanno residui dopo il NUL dell'owner
    assert RentEditor(dirty, "Tizio", gold=0, now=1).to_bytes() == dirty
    assert RentEditor(make_rent("Tizio", []), "Tizio", gold=0, now=1).to_bytes() == make_rent("Tizio", [])


def test_pack_item_matches_the_independent_fixture() -> None:
    """`pack_item` produce lo stesso layout della fixture scritta con `struct.pack` contiguo."""
    element = pack_item(7, **ITEM)
    parsed = parse_rent(make_rent("Tizio", [element])).items[0]
    assert (parsed.item_number, parsed.values, parsed.extra_flags, parsed.weight, parsed.timer, parsed.bitvector) == (
        7,
        (1, 2, 3, 4),
        8,
        7,
        0,
        0,
    )
    assert (parsed.name, parsed.short, parsed.description, parsed.wearpos, parsed.depth) == ("spada", "Una spada", "Una spada qui", 0, 0)
    assert [(a.location, a.modifier) for a in parsed.affects] == [(18, 2)] and len(element) == RENT_ELEM_SIZE
    long = pack_item(1, **{**ITEM, "name": "n" * 500, "description": "d" * 500})
    assert long[36 + 127] == 0 and long[292 + 255] == 0  # sempre terminate da NUL dentro il campo
    for bad in ({"vnum": 40000}, {"vnum": -1}):
        with pytest.raises(PlayerValueError):
            pack_item(**{"vnum": 1, **ITEM, **bad})
    with pytest.raises(PlayerValueError):
        pack_item(1, **{**ITEM, "values": (2**40, 0, 0, 0)})


def test_add_equip_and_container() -> None:
    """Aggiunta portata, equipaggiata e dentro un contenitore: posizione, profondita', numero e testata."""
    rent = editor([make_item(1, wearpos=6), make_item(2), make_item(3, depth=1), make_item(4)])
    element = pack_item(9, **ITEM)
    assert rent.add(element, 0, None) == 4  # in fondo
    assert rent.add(element, 17, None) == 5
    assert rent.add(element, 0, 1) == 3  # dopo il contenuto del contenitore 1 (posizione 2), prima dell'oggetto 3
    out = parse_rent(rent.to_bytes())
    assert out.problem is None and out.number == 7 and out.owner == "Tizio"
    assert [(i.item_number, i.wearpos, i.depth) for i in out.items] == [
        (1, 6, 0),
        (2, 0, 0),
        (3, 0, 1),
        (9, 0, 1),
        (4, 0, 0),
        (9, 0, 0),
        (9, 17, 0),
    ]
    assert (out.gold_left, out.total_cost, out.last_update) == (500, 10, 1_700_000_000)  # la testata esistente resta


def test_add_rules() -> None:
    """Slot occupato, slot in contenitore, contenitore inesistente, profondita' massima, capienza."""
    element = pack_item(9, **ITEM)
    rent = editor([make_item(1, wearpos=6), make_item(2)])
    for call, reason in (
        (lambda: rent.add(element, 6), "slot_taken"), (lambda: rent.add(element, 24), "range"), (lambda: rent.add(element, 3, 1), "slot_in_container"),
        (lambda: rent.add(element, 0, 5), "not_found"), (lambda: rent.add(element, 0, -1), "not_found"),
    ):  # fmt: skip
        with pytest.raises(PlayerValueError) as caught:
            call()
        assert caught.value.reason == reason
    deep = editor([make_item(1, depth=min(d, 60)) for d in range(0, 61)])
    with pytest.raises(PlayerValueError) as caught:
        deep.add(element, 0, 60)
    assert caught.value.reason == "too_deep"
    full = editor([make_item(1) for _ in range(200)])
    with pytest.raises(PlayerValueError) as caught:
        full.add(element)
    assert caught.value.reason == "inventory_full"


def test_delete_takes_the_contents_and_set_slot() -> None:
    """Togliere un contenitore toglie anche il contenuto; lo slot si cambia solo sul primo livello e se libero."""
    rent = editor([make_item(1, wearpos=6), make_item(2), make_item(3, depth=1), make_item(4, depth=2), make_item(5)])
    removed = rent.delete(1)
    assert [parse_rent(make_rent("Tizio", [r])).items[0].item_number for r in removed] == [2, 3, 4]
    assert [r[0] for r in rent.records] == [1, 5]
    rent.set_wearpos(1, 7)
    rent.set_wearpos(0, 0)
    assert [(r[548], r[549]) for r in rent.records] == [(0, 0), (7, 0)]
    for call, reason in (
        (lambda: rent.set_wearpos(0, 7), "slot_taken"),
        (lambda: rent.set_wearpos(9, 0), "not_found"),
        (lambda: rent.delete(9), "not_found"),
    ):
        with pytest.raises(PlayerValueError) as caught:
            call()
        assert caught.value.reason == reason
    nested = editor([make_item(2), make_item(3, depth=1)])
    with pytest.raises(PlayerValueError) as caught:
        nested.set_wearpos(1, 4)
    assert caught.value.reason == "slot_in_container"
    only = editor([make_item(1)])
    only.delete(0)
    assert len(only.to_bytes()) == RENT_HEADER_SIZE and parse_rent(only.to_bytes()).problem is None


def test_new_rent_and_unsafe_rent_files() -> None:
    """Rent assente/vuoto: testata nuova coerente. File incoerente o di un altro proprietario: rifiutato (il gioco farebbe `assert`)."""
    for empty in (None, b""):
        fresh = RentEditor(empty, "Tizio", gold=321, now=1_800_000_000)
        fresh.add(pack_item(9, **ITEM))
        out = parse_rent(fresh.to_bytes())
        assert (out.owner, out.gold_left, out.total_cost, out.last_update, out.minimum_stay, out.number, out.problem) == (
            "Tizio",
            321,
            100,
            1_800_000_000,
            0,
            1,
            None,
        )
    cases = {
        "truncated_header": b"x" * 10, "too_many_items": make_rent("Tizio", [make_item()], number=999), "truncated": make_rent("Tizio", [make_item()], number=3),
        "trailing_data": make_rent("Tizio", [make_item()]) + b"xx", "owner_mismatch": make_rent("Altro", [make_item()]),
    }  # fmt: skip
    for problem, data in cases.items():
        with pytest.raises(PlayerFileError) as caught:
            RentEditor(data, "Tizio", gold=0, now=1)
        assert caught.value.code == problem
    with pytest.raises(PlayerValueError):
        RentEditor(None, "../x", gold=0, now=1)


def test_rent_gold_sync_helper() -> None:
    """`gold_left` si allinea solo per un rent con testata completa e proprietario giusto."""
    data = make_rent("Tizio", [make_item()])
    out = rent_with_gold(data, "tizio", 77)
    assert out is not None and parse_rent(out).gold_left == 77 and out[:20] == data[:20] and out[24:] == data[24:]
    assert (
        rent_with_gold(data, "Altro", 1) is None
        and rent_with_gold(b"", "Tizio", 1) is None
        and rent_with_gold(b"x" * 39, "Tizio", 1) is None
    )
