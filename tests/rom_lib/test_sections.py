"""Parsing di ogni sezione con aree scritte a mano."""

from pachimudeditor_adapter_basedmud.rom_lib import CommentLine, Reset, parse_area, parse_flags, write_area

from . import samples as S


def test_old_header() -> None:
    a = parse_area(S.OLD_HEADER + "#$\n")
    h = a.header
    assert h is not None and h.style == "AREA"
    assert (h.filename, h.name, h.credits) == ("test.are", "Test Area", "{ 1 10} Luca  Test Area")
    assert (h.min_vnum, h.max_vnum) == (100, 199)


def test_old_header_non_numeric_vnums() -> None:
    a = parse_area("#AREA\nx.are~\nx~\ncr~\nXX00 XX99\n\n#$\n")
    assert a.header.vnum_raw == "XX00 XX99"
    assert write_area(a) == "#AREA\nx.are~\nx~\ncr~\nXX00 XX99\n\n#$\n"
    assert "XX00 XX99" in write_area(a, preserve=False)


def test_areadata_header() -> None:
    a = parse_area(S.AREADATA + "#$\n")
    h = a.header
    assert h is not None and h.style == "AREADATA"
    assert (h.name, h.builders, h.credits, h.security) == ("Test Area", "Luca", "Luca Test", 5)
    assert (h.min_vnum, h.max_vnum) == (100, 199)


def test_areadata_unknown_key_kept() -> None:
    a = parse_area("#AREADATA\nName X~\nFoo bar baz\nEnd\n\n#$\n")
    assert a.header.extra == [("Foo", "bar baz")]
    assert "Foo bar baz\n" in write_area(a, preserve=False)


def test_mobiles() -> None:
    a = parse_area(S.MOBILES + "#$\n")
    assert [m.vnum for m in a.mobiles] == [100, 101]
    m = a.find_mobile(100)
    assert m.name == "wizard oldname" and m.short_descr == "the wizard"
    assert m.long_descr == "A wizard walks around.\n"
    assert m.description == "The wizard looks old.\n"
    assert m.race == "human"
    assert m.act == parse_flags("ABV") and m.affected_by == parse_flags("D")
    assert (m.alignment, m.group, m.level, m.hitroll) == (900, 0, 23, 2)
    assert (m.hit.number, m.hit.type, m.hit.bonus) == (1, 1, 999)
    assert (m.damage.number, m.damage.type, m.damage.bonus) == (1, 8, 32)
    assert m.dam_type == "magic" and m.ac == [-15, -15, -15, -15]
    assert (m.off_flags, m.imm_flags, m.res_flags, m.vuln_flags) == (parse_flags("AF"), parse_flags("ABCD"), 0, 0)
    assert (m.start_pos, m.default_pos, m.sex, m.wealth) == ("stand", "stand", "male", 15000)
    assert (m.size, m.material) == ("medium", "0")
    assert [(f.word, f.value) for f in m.flag_removals] == [("act", 1), ("vul", 2)]
    assert [(p.trigger, p.vnum, p.phrase) for p in m.mprogs] == [("act_prog", 101, "hello")]
    assert m.act_names[0] == "npc"
    assert a.find_mobile(101).sex == "none"


def test_dice_negative_bonus() -> None:
    from pachimudeditor_adapter_basedmud.rom_lib import Dice

    assert Dice.parse("1d8-2").bonus == -2
    assert str(Dice(1, 8, -2)) == "1d8+-2"
    txt = S.MOBILES.replace("1d8+32", "1d8+-5") + "#$\n"
    assert parse_area(txt).mobiles[0].damage.bonus == -5


def test_objects() -> None:
    a = parse_area(S.OBJECTS + "#$\n")
    sword = a.find_object(100)
    assert sword.item_type == "weapon" and sword.values == ["sword", "4", "10", "slash", "EF"]
    assert sword.named_values()["dice_size"] == "10"
    assert sword.extra_flags == parse_flags("BI") and sword.wear_flags == parse_flags("AN")
    assert (sword.level, sword.weight, sword.cost, sword.condition) == (20, 100, 500, "P")
    assert [(x.where, x.location, x.modifier, x.bits) for x in sword.affects] == [("", 18, 3, 0), ("A", 12, -2, parse_flags("F"))]
    assert sword.affects[1].is_flag_affect
    assert (sword.extra_descs[0].keyword, sword.extra_descs[0].description) == ("sword", "Fine steel.\n")
    assert a.find_object(101).values[2] == "local specialty"
    assert a.find_object(102).named_values()["capacity"] == "50"
    assert a.find_object(103).values == ["10", "sanctuary", "cure light", "", ""]
    assert a.find_object(104).value_int(2) == 100
    assert a.find_object(101).condition == "G"
    assert "'local specialty'" in write_area(a, preserve=False)
    assert "10 'sanctuary' 'cure light' '' ''" in write_area(a, preserve=False)


def test_rooms() -> None:
    a = parse_area(S.ROOMS + "#$\n")
    r = a.find_room(100)
    assert r.name == "The Hall" and r.description == "A big hall.\nSecond line.\n"
    assert r.room_flags == parse_flags("CDS") and r.sector == 1 and r.sector_name == "city"
    assert [(e.door, e.locks, e.key, e.to_vnum, e.keyword) for e in r.exits] == [(0, 1, 101, 101, "door"), (2, 0, -1, 101, "")]
    assert r.exits[0].is_door and not r.exits[0].pickproof and r.exits[0].direction == "north"
    assert r.exit_for(2).description == ""
    assert (r.heal_rate, r.mana_rate, r.owner, r.clan) == (130, 120, "Luca", "mystic")
    assert r.extra_descs[0].keyword == "plaque"
    r2 = a.find_room(101)
    assert (r2.heal_rate, r2.mana_rate, r2.owner, r2.clan, r2.exits) == (100, 100, "", "", [])


def test_resets() -> None:
    a = parse_area(S.RESETS + "#$\n")
    rs = a.resets
    assert [x.command if isinstance(x, Reset) else "*" for x in rs] == ["D", "M", "E", "G", "O", "P", "R", "*"]
    m = rs[1]
    assert m.named() == {"if_flag": 0, "mob_vnum": 100, "global_limit": 1, "room_vnum": 100, "room_limit": 1}
    assert m.comment == "* the wizard"
    assert rs[2].get("wear_loc") == 16 and rs[3].get("global_limit") == -1
    assert rs[5].get("into_vnum") == 102 and rs[0].get("locks") == 2
    assert isinstance(rs[7], CommentLine) and rs[7].text == "* una nota"
    assert Reset.make("M", mob_vnum=5, room_vnum=6).args == [0, 5, 1, 6, 1]


def test_shops_specials_mobprogs() -> None:
    a = parse_area(S.SHOPS + S.SPECIALS + S.MOBPROGS + "#$\n")
    s = a.shops[0]
    assert (s.keeper, s.buy_types, s.profit_buy, s.profit_sell, s.open_hour, s.close_hour) == (100, [2, 3, 4, 10, 0], 105, 15, 0, 23)
    assert s.comment == "* the wizard"
    sp = a.specials
    assert (sp[0].mob_vnum, sp[0].function, sp[0].comment) == (100, "spec_cast_mage", "* the wizard")
    assert isinstance(sp[1], CommentLine)
    assert a.mobprogs[0].vnum == 101 and a.mobprogs[0].code == "say Hello there\nmob echo hi\n"


def test_helps_and_socials() -> None:
    a = parse_area(S.HELPS + S.SOCIALS + "#$\n")
    assert [(h.level, h.keyword) for h in a.helps] == [(0, "TEST HELP"), (-1, "LEVEL")]
    assert a.helps[0].text == "This is help text.\n"
    g, k = a.socials
    assert g.name == "gack" and len(g.lines) == 8 and g.lines[0] == "Gaaack!"
    assert k.name == "kiss" and k.params == "0 0" and k.lines[1] is None and k.truncated and len(k.lines) == 6


def test_raw_unknown_section_preserved() -> None:
    txt = "#MOBOLD\n#1\nfoo~\nbar\n#0\n\n#MYSTERY\nqualcosa\n#$\n"
    a = parse_area(txt)
    assert [s.kind for s in a.sections] == ["RAW", "RAW"]
    assert a.raw_sections[1].name == "MYSTERY" and a.raw_sections[1].text == "qualcosa\n"
    assert write_area(a) == txt
    assert write_area(a, preserve=False) == txt


def test_full_roundtrip_byte_identical() -> None:
    for text in (S.FULL, S.FULL_DATA):
        a = parse_area(text)
        assert write_area(a) == text
        assert parse_area(write_area(a, preserve=False)) == a


def test_canonical_matches_c_saver_for_saver_output() -> None:
    """Un testo gia' nel formato di olc_save.c deve riemergere identico anche in modo canonico."""
    text = S.AREADATA + S.MOBILES + S.OBJECTS + S.ROOMS.replace("M 120 H 130", "M 120 H 130") + "#$\n"
    a = parse_area(text)
    assert write_area(a, preserve=False) == text


def test_crlf_and_missing_terminator() -> None:
    text = (S.OLD_HEADER + S.MOBILES).replace("\n", "\r\n")
    a = parse_area(text)
    assert a.newline == "\r\n" and not a.has_terminator
    assert write_area(a) == text
    canon = write_area(a, preserve=False)
    assert "\r\n" in canon and "\n" not in canon.replace("\r\n", "")
    assert parse_area(canon) == a
    assert a.find_mobile(100).long_descr == "A wizard walks around.\n"


def test_trailer_preserved() -> None:
    text = "#AREA\nx~\nx~\nx~\n1 2\n\n#$\nroba dopo\n"
    assert write_area(parse_area(text)) == text
