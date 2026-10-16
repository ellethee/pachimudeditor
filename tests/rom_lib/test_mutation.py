"""Mutazioni: modifica un elemento, scrivi, rileggi; il resto deve restare identico byte per byte."""

from pachimudeditor_adapter_basedmud.rom_lib import (
    Exit,
    Mobile,
    Object,
    Reset,
    Room,
    Shop,
    Special,
    is_unchanged,
    parse_area,
    parse_flags,
    write_area,
)

from . import samples as S


def test_unchanged_items_keep_source() -> None:
    a = parse_area(S.FULL)
    assert all(is_unchanged(m) for m in a.mobiles)
    a.find_mobile(100).level = 40
    assert not is_unchanged(a.find_mobile(100)) and is_unchanged(a.find_mobile(101))


def test_edit_mob() -> None:
    a = parse_area(S.FULL)
    m = a.find_mobile(100)
    m.level = 40
    m.short_descr = "the archmage"
    m.act |= parse_flags("D")
    m.hit.bonus = 5
    text = write_area(a)
    b = parse_area(text)
    assert b == a
    assert b.find_mobile(100).level == 40 and b.find_mobile(100).hit.bonus == 5
    # tutto il resto del file e' invariato (solo il blocco del mob 100 e' cambiato)
    old_block = parse_area(S.FULL).find_mobile(100)._src
    new_block = write_area(a).split("#101\nrat~")[0]
    assert text.replace(new_block.split("#100\n", 1)[1], old_block.split("#100\n", 1)[1]) == S.FULL
    assert "40 2 1d1+5" in text and "the archmage~" in text


def test_edit_object_values_by_name() -> None:
    a = parse_area(S.FULL)
    sw = a.find_object(100)
    sw.set_named("dice_size", 12)
    sw.cost = 999
    b = parse_area(write_area(a))
    assert b.find_object(100).values[2] == "12" and b.find_object(100).cost == 999
    assert b == a


def test_edit_room_exits() -> None:
    a = parse_area(S.FULL)
    r = a.find_room(101)
    r.exits.append(Exit(door=0, keyword="gate", locks=Exit.locks_from(True, pickproof=True), key=100, to_vnum=100))
    r.extra_descs.clear()
    r.heal_rate = 150
    b = parse_area(write_area(a))
    assert b.find_room(101).exits[0].locks == 2 and b.find_room(101).heal_rate == 150
    assert b == a


def test_add_remove_entities() -> None:
    a = parse_area(S.FULL)
    a.mobiles.append(Mobile(vnum=102, name="orc", short_descr="an orc", long_descr="An orc.\n", description="Ugly.\n", race="orc", level=5))
    a.objects.append(
        Object(vnum=105, name="ring", short_descr="a ring", description="A ring.", item_type="armor", values=["1", "1", "1", "1", "0"])
    )
    a.rooms.append(Room(vnum=102, name="New", description="New room.\n"))
    a.resets.append(Reset.make("M", comment="* orc", mob_vnum=102, room_vnum=102))
    a.shops.append(Shop(keeper=102, buy_types=[1, 0, 0, 0, 0]))
    a.specials.append(Special(102, "spec_thief"))
    del a.mobiles[1]
    b = parse_area(write_area(a))
    assert b == a
    assert [m.vnum for m in b.mobiles] == [100, 102]
    assert b.find_mobile(102).race == "orc" and b.find_room(102).exits == []
    assert b.shops[-1].keeper == 102 and b.specials[-1].function == "spec_thief"
    # le parti non toccate (stanze 100/101) sono ancora identiche al sorgente
    assert a.find_room(100)._src in write_area(a)


def test_new_sections_created_in_canonical_order() -> None:
    a = parse_area("#AREA\nx~\nx~\nx~\n1 2\n\n#$\n")
    a.mobiles.append(Mobile(vnum=1, name="m"))
    a.rooms.append(Room(vnum=1, name="r"))
    a.objects  # accesso senza modifiche: sezione vuota non scritta
    text = write_area(a)
    assert text.index("#MOBILES") < text.index("#ROOMS") and "#OBJECTS" not in text
    assert text.endswith("#0\n\n#$\n") and "1 2\n\n#MOBILES" in text
    b = parse_area(text)
    assert b.mobiles == a.mobiles and b.rooms == a.rooms and b.section("OBJECTS", create=False) is None


def test_header_edit_and_style_switch() -> None:
    a = parse_area(S.FULL)
    a.header.name = "Nuovo nome"
    assert "Nuovo nome~" in write_area(a)
    a.header.style = "AREADATA"
    a.header.builders = "Luca"
    text = write_area(a)
    assert text.startswith("#AREADATA\n")
    b = parse_area(text)
    assert b.header.name == "Nuovo nome" and b.header.builders == "Luca"
