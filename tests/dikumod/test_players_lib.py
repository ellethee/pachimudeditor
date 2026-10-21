"""Parser dei file giocatore Diku Modificato (`dikumod_lib.players`): layout, rent, file corrotti, confinamento."""

import os
import struct
from pathlib import Path

import pytest

from pachimudeditor_adapter_dikumod.dikumod_lib.players import (
    CHAR_FILE_SIZE,
    PlayerFileError,
    parse_char_record,
    parse_rent,
    player_names,
    read_char_file,
    read_rent_file,
)
from tests.support.dikumod_players import PWD_MARKER, make_char, make_item, make_rent, write_players

# offset di char_file_u ottenuti compilando le struct di DikuMod con g++ (`offsetof`); qui solo come guardia
C_OFFSETS = {"name": 2924, "pwd": 2974, "last_logon": 2916, "gold": 676, "bankgold": 680, "exp": 684, "load_room": 636, "skills": 700}


def test_layout_matches_c_offsets() -> None:
    """Le fixture (formato contiguo con padding) e il parser concordano sugli offset del C."""
    data = make_char("Tizio", gold=777, bank=888, exp=999, load_room=42, last_logon=123456)
    assert len(data) == CHAR_FILE_SIZE == 3036
    assert data[C_OFFSETS["name"] : C_OFFSETS["name"] + 5] == b"Tizio"
    assert data[C_OFFSETS["pwd"] : C_OFFSETS["pwd"] + len(PWD_MARKER)] == PWD_MARKER
    assert struct.unpack_from("<iii", data, C_OFFSETS["gold"]) == (777, 888, 999)
    assert struct.unpack_from("<h", data, C_OFFSETS["load_room"])[0] == 42
    assert struct.unpack_from("<i", data, C_OFFSETS["last_logon"])[0] == 123456
    rec = parse_char_record(data)
    assert (rec.name, rec.points["gold"], rec.points["bankGold"], rec.points["exp"], rec.load_room, rec.last_logon) == (
        "Tizio", 777, 888, 999, 42, 123456,
    )  # fmt: skip


def test_fields_and_classes() -> None:
    """Classe a bitmask, livello massimo tra le classi accese, abilita' ed effetti non nulli."""
    rec = parse_char_record(
        make_char(class_mask=4 | 8, levels=(0, 0, 20, 31) + (0,) * 16, skills={5: (80, 1), 9: (0, 0)}, affects=[(3, 10, 2, 1, 0)])
    )
    assert rec.classes == ["warrior", "thief"] and rec.level == 31
    assert [(s.index, s.learned, s.flags) for s in rec.skills] == [(5, 80, 1)]
    assert [(a.type, a.duration, a.modifier) for a in rec.affects] == [(3, 10, 2)]
    assert rec.abilities["str"] == 16 and rec.points["hit"] == 100 and rec.points["armor"] == -50


def test_password_never_in_record() -> None:
    """Il record espone solo `has_password`: il valore non compare in nessun campo ne' nella repr."""
    rec = parse_char_record(make_char(password=PWD_MARKER))
    assert rec.has_password is True and parse_char_record(make_char(password=b"")).has_password is False
    blob = repr(rec) + repr(rec.__dict__)
    assert PWD_MARKER.decode() not in blob


@pytest.mark.parametrize("size", [0, 1, 3035, 3037, 6072])
def test_bad_record_size(size: int) -> None:
    """Dimensione diversa da 3036 -> `PlayerFileError(bad_size)`, senza contenuti nel messaggio."""
    with pytest.raises(PlayerFileError) as caught:
        parse_char_record((make_char() * 2)[:size])
    assert caught.value.code == "bad_size" and PWD_MARKER.decode() not in str(caught.value)


def test_rent_items() -> None:
    """Rent: testata, equipaggiamento (`wearpos`), annidamento (`depth`), effetti."""
    rent = parse_rent(make_rent("Tizio", [make_item(1, wearpos=6, affects=2), make_item(7, depth=1)], gold_left=42))
    assert rent.problem is None and rent.owner == "Tizio" and rent.gold_left == 42 and rent.number == 2
    first, second = rent.items
    assert (first.item_number, first.wearpos, len(first.affects)) == (1, 6, 2) and (second.item_number, second.depth) == (7, 1)
    assert first.short == "Un gile in pelle" and first.values == (9, 9, 0, 0)


@pytest.mark.parametrize(
    ("data", "problem", "count"),
    [
        (b"", None, 0),  # rent azzerato
        (b"x" * 39, "truncated_header", 0),
        (make_rent("A", [], number=0), None, 0),
        (make_rent("A", [make_item()], number=201), "too_many_items", 0),  # il gioco andrebbe in overflow: nessun oggetto letto
        (make_rent("A", [make_item()], number=-1), "too_many_items", 0),
        (make_rent("A", [make_item(), make_item(2)], number=3), "truncated", 2),
        (make_rent("A", [make_item(), make_item(2)])[:-5], "truncated", 1),  # ultimo elemento a meta'
        (make_rent("A", [make_item()], number=0) + b"zz", "trailing_data", 0),
    ],
)
def test_rent_corrupted(data: bytes, problem: str | None, count: int) -> None:
    """File vuoti, troncati o con `number` impossibile: mai eccezioni, `problem` stabile e solo gli oggetti leggibili."""
    rent = parse_rent(data)
    assert (rent.problem, len(rent.items)) == (problem, count)


def test_rent_wearpos_out_of_range_is_kept_raw() -> None:
    """`wearpos` oltre MAX_WEAR non fa crashare il parser (la mappatura lo etichetta)."""
    assert parse_rent(make_rent("A", [make_item(wearpos=200)])).items[0].wearpos == 200


def test_player_names_filter(tmp_path: Path) -> None:
    """Solo `<nome>.dat` con nome ammesso: niente `.dat~`, maiuscole, punti, separatori."""
    write_players(tmp_path, {"tizio": make_char(), "ok_1": make_char(), "Maiusc": make_char()})
    for junk in ("tizio.dat~", "x.dat.bak", "..dat", "a b.dat", "-x.dat", "notes.txt"):
        (tmp_path / "players" / junk).write_bytes(b"x")
    (tmp_path / "players" / "dir.dat").mkdir()
    assert player_names(tmp_path / "players") == ["dir", "ok_1", "tizio"]  # dir.dat e' una cartella: nome valido, la lettura la rifiutera'
    assert player_names(tmp_path / "nope") == []


def test_read_confinement(tmp_path: Path) -> None:
    """Symlink verso l'esterno, cartelle e nomi con percorso sono rifiutati; un symlink interno e' accettato."""
    outside = tmp_path / "outside.dat"
    outside.write_bytes(make_char("Fuori"))
    write_players(tmp_path / "lib", {"tizio": make_char()})
    players = tmp_path / "lib" / "players"
    (players / "evil.dat").symlink_to(outside)
    (players / "alias.dat").symlink_to(players / "tizio.dat")
    (players / "folder.dat").mkdir()
    with pytest.raises(PlayerFileError) as caught:
        read_char_file(players, "evil")
    assert caught.value.code == "outside_dir"
    with pytest.raises(PlayerFileError) as caught:
        read_char_file(players, "folder")
    assert caught.value.code == "not_regular"
    assert read_char_file(players, "alias")[0].name == "Tizio"
    for bad in ("../outside", "a/b", "", ".", "..", "x\0y", "A"):
        with pytest.raises(FileNotFoundError):
            read_char_file(players, bad)
    with pytest.raises(FileNotFoundError):
        read_char_file(players, "assente")


def test_rent_missing_and_symlink(tmp_path: Path) -> None:
    """Rent assente = `None`; rent symlink all'esterno rifiutato; file enorme letto solo fino al massimo."""
    write_players(tmp_path, {"tizio": make_char()}, {"tizio": make_rent("Tizio", [make_item()])})
    rent = tmp_path / "rent"
    assert read_rent_file(rent, "ghost") is None and read_rent_file(rent, "../x") is None
    assert read_rent_file(rent, "tizio").problem is None  # type: ignore[union-attr]
    outside = tmp_path / "out"
    outside.write_bytes(b"x" * 10)
    os.symlink(outside, rent / "evil")
    with pytest.raises(PlayerFileError) as caught:
        read_rent_file(rent, "evil")
    assert caught.value.code == "outside_dir"
    (rent / "big").write_bytes(b"\0" * (1 << 20))
    assert read_rent_file(rent, "big").problem == "trailing_data"  # type: ignore[union-attr]


def test_player_modules_are_read_only_and_never_touch_pwd() -> None:
    """Guardia (AST): i moduli dei giocatori non scrivono/cancellano file e non leggono i byte del campo `pwd` oltre a «e' vuoto?»."""
    import ast

    import pachimudeditor_adapter_dikumod as pkg

    base = Path(pkg.__file__).parent
    forbidden_attrs = {
        "write_bytes", "write_text", "unlink", "rename", "rmdir", "mkdir", "chmod", "touch", "symlink_to", "truncate", "write",
        "remove", "removedirs", "utime", "chown",
    }  # fmt: skip
    forbidden_names = {"atomic_write_bytes", "save", "shutil"}
    for path in (base / "dikumod_lib" / "players.py", base / "players.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Attribute):
                assert node.attr not in forbidden_attrs, (path.name, node.lineno, node.attr)
            if isinstance(node, ast.Name | ast.alias):
                assert getattr(node, "id", getattr(node, "name", "")) not in forbidden_names, (path.name, node.lineno)
            if isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", "")) == "open":
                modes = [
                    a.value for a in [*node.args[1:2], *[k.value for k in node.keywords if k.arg == "mode"]] if isinstance(a, ast.Constant)
                ]
                assert all(set(str(m)) <= {"r", "b"} for m in modes), (path.name, node.lineno)
    # il parser non espone mai il campo password: `pwd` compare solo per l'offset e per «e' vuoto?»
    lib_text = (base / "dikumod_lib" / "players.py").read_text(encoding="utf-8")
    assert lib_text.count("data[_O_PWD") == 1  # unico uso: il calcolo di has_password
    adapter = ast.parse((base / "players.py").read_text(encoding="utf-8"))
    idents = {n.attr for n in ast.walk(adapter) if isinstance(n, ast.Attribute)} | {
        n.id for n in ast.walk(adapter) if isinstance(n, ast.Name)
    }
    assert not {i for i in idents if "pwd" in i.lower() or ("password" in i.lower() and i != "has_password")}


def test_sdk_player_dtos_have_no_password_fields() -> None:
    """Nessun campo dei DTO giocatori (SDK) si chiama password/hash/pwd/secret: solo `has_password`."""
    from pachimudeditor import sdk

    for name in ("PlayerSummary", "PlayerDetail", "PlayerItem", "PlayerInventory", "PlayersInfo", "PlayersStatus"):
        for field in getattr(sdk, name).model_fields:
            assert not any(w in field.lower() for w in ("pwd", "hash", "secret", "token")), (name, field)
            assert "password" not in field.lower() or field == "has_password", (name, field)
