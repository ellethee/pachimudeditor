"""CHIAVE: round trip su tutte le aree reali di basedmud (lavorando su una copia temporanea)."""

from collections import Counter
from pathlib import Path


from pachimudeditor_adapter_basedmud.rom_lib import load_area_file, parse_area, read_area_list, save_area_file, write_area
from pachimudeditor_adapter_basedmud.rom_lib.writer import CANONICAL_TAIL, format_item, is_unchanged
from tests.support.real_data import HAVE_ROM

MIN_FILES = 50 if HAVE_ROM else 2
"""Quanti file ci si aspetta: i dati reali ne hanno decine, il mondo sintetico due."""
EDIT_FILE, EDIT_VNUM = ("midgaard.are", 3000) if HAVE_ROM else ("prato.are", 5000)


def area_files(folder: Path) -> list[Path]:
    """Tutti i file di dati del server: i `.are` piu' `olc.hlp` (file di help elencato in area.lst)."""
    return sorted(p for p in folder.iterdir() if p.suffix in (".are", ".hlp"))


def test_area_list_roundtrip_and_all_listed_files_parse(real_area_dir: Path) -> None:
    lst = read_area_list(real_area_dir / "area.lst")
    assert lst.to_text() == (real_area_dir / "area.lst").read_text()
    assert len(lst.names) >= MIN_FILES
    for name in lst.names:
        load_area_file(real_area_dir / name)


def test_preserve_mode_is_byte_identical(real_area_dir: Path) -> None:
    files = area_files(real_area_dir)
    assert len(files) >= MIN_FILES
    identical = 0
    for p in files:
        raw = p.read_bytes()
        area = load_area_file(p)
        out = write_area(area).encode(area.encoding)
        assert out == raw, f"{p.name}: il round trip non e' byte-identico"
        identical += 1
    print(f"\n[rom_lib] modo preserve: {identical}/{len(files)} file byte-identici")


def test_canonical_semantic_roundtrip(real_area_dir: Path) -> None:
    """parse(write(parse(x))) == parse(x) con riscrittura completamente canonica (stile olc_save.c)."""
    files = area_files(real_area_dir)
    byte_identical = 0
    for p in files:
        text = p.read_bytes().decode("latin-1")
        a = parse_area(text, filename=p.name)
        canon = write_area(a, preserve=False)
        b = parse_area(canon, filename=p.name)
        assert b == a, f"{p.name}: round trip semantico fallito"
        assert write_area(b, preserve=False) == canon, f"{p.name}: la scrittura canonica non e' idempotente"
        byte_identical += canon == text
    print(
        f"\n[rom_lib] modo canonico: {byte_identical}/{len(files)} file gia' identici al formato olc_save.c; "
        f"parse(write(parse)) == parse per {len(files)}/{len(files)}"
    )


def test_canonical_item_statistics(real_area_dir: Path) -> None:
    """Quantifica per categoria quanti elementi sono gia' nel formato canonico del saver C."""
    exact: Counter[str] = Counter()
    total: Counter[str] = Counter()
    for p in area_files(real_area_dir):
        a = load_area_file(p)
        for sec in a.sections:
            for item in sec.items:
                total[sec.kind] += 1
                exact[sec.kind] += format_item(item) == item._src  # type: ignore[attr-defined]
                assert is_unchanged(item)
    lines = [f"{k}: {exact[k]}/{total[k]}" for k in sorted(total)]
    print("\n[rom_lib] elementi gia' canonici -> " + ", ".join(lines))
    # i blocchi mob sono scritti dal vecchio ROM in formato identico a quello del saver OLC
    assert exact["MOBILES"] == total["MOBILES"]
    assert exact["OBJECTS"] >= total["OBJECTS"] - 5
    assert exact["ROOMS"] >= total["ROOMS"] - 10


def test_sections_found_in_real_files(real_area_dir: Path) -> None:
    kinds: Counter[str] = Counter()
    raw: list[str] = []
    for p in area_files(real_area_dir):
        a = load_area_file(p)
        for s in a.sections:
            kinds[s.kind] += 1
            if s.kind == "RAW":
                raw.append(f"{p.name}:{s.name}")
    print(f"\n[rom_lib] sezioni nei file reali: {dict(kinds)}; RAW: {raw}")
    assert kinds["MOBILES"] >= MIN_FILES - 10 if HAVE_ROM else kinds["MOBILES"] >= 2
    if HAVE_ROM:
        assert kinds["HELPS"] >= 3 and kinds["SOCIALS"] >= 1


def test_edit_real_file_and_save(real_area_dir: Path, tmp_path: Path) -> None:
    """Mutazione su un'area reale: cambia un mob, salva (atomico), rileggi; il resto e' invariato."""
    src = real_area_dir / EDIT_FILE
    dst = tmp_path / EDIT_FILE
    dst.write_bytes(src.read_bytes())
    area = load_area_file(dst)
    mob = area.find_mobile(EDIT_VNUM)
    assert mob is not None
    mob.level = 99
    mob.short_descr = "the grand wizard"
    save_area_file(dst, area)
    again = load_area_file(dst)
    assert again.find_mobile(EDIT_VNUM).level == 99
    assert again == area
    old_lines = src.read_text().splitlines()
    new_lines = dst.read_text().splitlines()
    changed = [i for i, (x, y) in enumerate(zip(old_lines, new_lines, strict=False)) if x != y]
    assert 1 <= len(changed) <= 3 and len(old_lines) == len(new_lines)


def test_tail_constants_cover_real_terminators(real_area_dir: Path) -> None:
    for p in area_files(real_area_dir):
        for s in load_area_file(p).sections:
            if s.kind in CANONICAL_TAIL and s.tail is not None:
                assert s.tail.strip() in ("#0", "S", "0", "", "-1 $~", "0 $~", "#0") or s.kind in ("HELPS", "AREA", "AREADATA")
