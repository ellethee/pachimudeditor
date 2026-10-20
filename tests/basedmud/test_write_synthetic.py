"""Scritture dell'adapter BasedMud sul mondo ROM sintetico (`tests/support/synthetic_worlds.py`): girano sempre, anche in CI.

Gli equivalenti sui dati reali di basedmud sono in `test_write.py` (marcati `real_rom`).
"""

import asyncio
import re
from collections.abc import Callable
from pathlib import Path

import pytest
from pachimudeditor_adapter_basedmud.adapter import BasedMudAdapter
from pachimudeditor_adapter_basedmud.rom_lib import read_area_list

from pachimudeditor.common.adapters.models import (
    ExitIn,
    ExitPatch,
    MobIn,
    MobPageParams,
    MobPatch,
    ObjectPageParams,
    ObjectPatch,
    ResetCommandIn,
    ResetScriptIn,
    RoomIn,
    RoomPageParams,
    RoomPatch,
    ZoneIn,
    ZonePatch,
)
from pachimudeditor.common.adapters.registry import WorldConfig
from pachimudeditor.common.enums import Direction, DoorFlag
from tests.adapter_contract.helpers import expect_error
from tests.support.synthetic_worlds import write_rom_area

ZONE, MOB, ROOM, ROOM_S, OBJ, KEY = 5000, 5000, 5000, 5002, 5001, 5004
"""Zona `prato.are` (5000-5099): mob con negozio e special, stanza con porta a nord, bottiglia, chiave."""


@pytest.fixture
def area(tmp_path: Path) -> Path:
    """Copia scrivibile del mondo sintetico (cartella `area/`)."""
    return write_rom_area(tmp_path / "root" / "area")


@pytest.fixture
def make(area: Path) -> Callable[..., BasedMudAdapter]:
    """Factory di adapter nuovi (cache vuota) sulla copia."""

    def build(read_only: bool = False) -> BasedMudAdapter:
        """Un adapter sulla copia."""
        return BasedMudAdapter(WorldConfig(id="syn", kind="basedmud", name="Sintetico", path=str(area), read_only=read_only))

    return build


@pytest.fixture
def adapter(make: Callable[..., BasedMudAdapter]) -> BasedMudAdapter:
    """Adapter scrivibile."""
    return make()


def _block(text: str, vnum: int) -> tuple[int, int]:
    """Intervallo `[inizio, fine)` del blocco `#vnum` (fino al prossimo `#<numero>`)."""
    start = text.index(f"\n#{vnum}\n") + 1
    nxt = re.compile(r"\n#\d+\n").search(text, start + 1)
    return start, nxt.start() + 1 if nxt else len(text)


# --------------------------------------------------------------------------- regressione: nessuna cache sporca


async def test_failed_update_leaves_cache_and_disk_clean(
    adapter: BasedMudAdapter, make: Callable[..., BasedMudAdapter], area: Path
) -> None:
    """`update_room` con `extra` invalido (422) dopo aver applicato i campi: `get_room` invariato, nessun valore sul disco al
    salvataggio successivo e una nuova istanza dell'adapter non lo rilegge."""
    before = await adapter.get_room(ROOM)
    raw = (area / "prato.are").read_bytes()
    with expect_error(422, "basedmud.extra_unknown"):
        await adapter.update_room(ROOM, RoomPatch(name="Mutata", heal_rate=77, extra={"boh": 1}))
    assert await adapter.get_room(ROOM) == before
    assert (area / "prato.are").read_bytes() == raw
    await adapter.update_mob(MOB, MobPatch(level=30))  # una scrittura successiva sullo stesso file non porta con se' il valore scartato
    assert "Mutata" not in (area / "prato.are").read_text(encoding="latin-1")
    fresh = make()
    assert (await fresh.get_room(ROOM)).name == before.name and (await fresh.get_mob(MOB)).level == 30


async def test_failed_operations_keep_state_for_every_kind(adapter: BasedMudAdapter, area: Path) -> None:
    """Mob, oggetto, zona, reset ed extra description: un errore a meta' di una scrittura non lascia modifiche in memoria."""
    raw = (area / "prato.are").read_bytes()
    mob, obj, zone = await adapter.get_mob(MOB), await adapter.get_object(OBJ), await adapter.get_zone(ZONE)
    with expect_error(422, "basedmud.extra_unknown"):
        await adapter.update_mob(MOB, MobPatch(level=1, short_description="x", extra={"boh": 1}))
    with expect_error(422, "basedmud.extra_unknown"):
        await adapter.update_object(OBJ, ObjectPatch(cost=1, extra={"boh": 1}))
    with expect_error(422, "basedmud.vnum_out_of_range"):
        await adapter.update_room(5003, RoomPatch(name="Fuori", vnum=9999))
    with expect_error(409, "rooms.vnum_taken"):
        await adapter.create_room(RoomIn(vnum=ROOM, zone_id=ZONE, name="Doppia"))
    assert (await adapter.get_mob(MOB), await adapter.get_object(OBJ), await adapter.get_zone(ZONE)) == (mob, obj, zone)
    assert (area / "prato.are").read_bytes() == raw


# --------------------------------------------------------------------------- fedelta' byte per byte


async def test_edit_mob_changes_only_its_bytes(adapter: BasedMudAdapter, area: Path) -> None:
    """Modificare un mob riscrive solo il suo blocco: prefisso e suffisso del file restano identici."""
    path = area / "prato.are"
    before = path.read_bytes().decode("latin-1")
    await adapter.update_mob(MOB, MobPatch(level=30, short_description="il gran maestro"))
    after = path.read_bytes().decode("latin-1")
    start, end = _block(before, MOB)
    new_start, new_end = _block(after, MOB)
    assert before[:start] == after[:new_start] and before[end:] == after[new_end:]
    assert "il gran maestro" in after[new_start:new_end]
    mob = await adapter.get_mob(MOB)
    assert mob.level == 30 and mob.extra["shop"]["profitBuy"] == 105  # il negozio e' intatto


async def test_echoing_dtos_is_a_noop(adapter: BasedMudAdapter, area: Path) -> None:
    """Rimandare come patch l'intero DTO letto (extra compreso) non cambia un solo byte dei file."""
    before = {p.name: p.read_bytes() for p in area.iterdir()}
    for mob in (await adapter.list_mobs(MobPageParams())).items:
        await adapter.update_mob(mob.id, MobPatch.model_validate(mob.model_dump(by_alias=True, exclude={"id"})))
    for room in (await adapter.list_rooms(RoomPageParams())).items:
        await adapter.update_room(room.id, RoomPatch.model_validate(room.model_dump(by_alias=True, exclude={"id"})))
    for obj in (await adapter.list_objects(ObjectPageParams())).items:
        await adapter.update_object(obj.id, ObjectPatch.model_validate(obj.model_dump(by_alias=True, exclude={"id"})))
    for zone_id in (ZONE, 6000):
        zone = await adapter.get_zone(zone_id)
        await adapter.update_zone(zone_id, ZonePatch.model_validate(zone.model_dump(by_alias=True, exclude={"id"})))
        script = await adapter.list_reset_commands(zone_id)
        await adapter.replace_reset_commands(
            zone_id, ResetScriptIn(commands=[ResetCommandIn.model_validate(c.model_dump(by_alias=True)) for c in script])
        )
    assert {p.name: p.read_bytes() for p in area.iterdir()} == before


async def test_header_edits_do_not_grow_blank_lines(adapter: BasedMudAdapter, area: Path) -> None:
    """Modificare l'intestazione di una zona (`#AREADATA` e `#AREA`) piu' volte non aggiunge righe vuote."""
    for zone_id, name in ((ZONE, "prato.are"), (6000, "fucina.are")):
        await adapter.update_zone(zone_id, ZonePatch(name="Uno"))
        once = (area / name).read_text(encoding="latin-1")
        await adapter.update_zone(zone_id, ZonePatch(name="Due"))
        twice = (area / name).read_text(encoding="latin-1")
        assert once.replace("Uno", "Due") == twice and "\n\n\n" not in twice.split("#MOBILES")[0]


# --------------------------------------------------------------------------- riferimenti, negozi, area.lst


async def test_object_room_and_exit_edits(adapter: BasedMudAdapter, area: Path) -> None:
    """Oggetto, stanza, uscita ed extra description: round trip dei valori ROM (flag, settore, porte, extra)."""
    obj = await adapter.update_object(OBJ, ObjectPatch(cost=99, extra={"values": ["300", "300", "wine", "0", "0"]}))
    assert obj.cost == 99 and obj.extra["values"][2] == "wine"
    room = await adapter.update_room(ROOM, RoomPatch(flags=["dark", "indoors"], extra={"sector": 10}))
    assert room.flags == ["dark", "indoors"] and room.extra["sector"] == 10
    with expect_error(422, "basedmud.unknown_flag"):
        await adapter.update_room(ROOM, RoomPatch(flags=["nonesiste"]))
    south = next(e for e in room.exits if e.direction is Direction.SOUTH)
    door = await adapter.update_exit(ROOM, south.id, ExitPatch(door_flag=DoorFlag.PICKPROOF, is_open=False, key_vnum=KEY))
    assert (door.door_flag, door.is_open, door.key_vnum) == (DoorFlag.PICKPROOF, False, KEY)
    resets = await adapter.list_reset_commands(ZONE)
    assert any(c.arg1 == ROOM and c.arg_str == "CLOSED" for c in resets if c.command_type.name == "SET_DOOR_STATE")
    await adapter.delete_exit(ROOM, door.id)
    assert not any(
        c.arg1 == ROOM and c.arg2 == 2 for c in await adapter.list_reset_commands(ZONE) if c.command_type.name == "SET_DOOR_STATE"
    )
    new_exit = await adapter.create_exit(ROOM, ExitIn(direction=Direction.WEST, target_room_id=5003))
    assert new_exit.target_room_name == "Il Pozzo"


async def test_vnum_change_follows_references(adapter: BasedMudAdapter) -> None:
    """Un vnum usato da un reset non cambia; altrimenti uscite entranti, negozio e special seguono il nuovo vnum."""
    with expect_error(409, "rooms.vnum_in_use"):
        await adapter.update_room(ROOM, RoomPatch(vnum=5090))
    with expect_error(409, "mobs.vnum_in_use"):
        await adapter.update_mob(MOB, MobPatch(vnum=5090))
    with expect_error(409, "rooms.vnum_taken"):
        await adapter.update_room(5003, RoomPatch(vnum=ROOM))
    a = await adapter.create_room(RoomIn(vnum=5090, zone_id=ZONE, name="A"))
    b = await adapter.create_room(RoomIn(vnum=5091, zone_id=ZONE, name="B"))
    await adapter.create_exit(a.id, ExitIn(direction=Direction.EAST, target_room_id=b.id))
    moved = await adapter.update_room(b.id, RoomPatch(vnum=5092))
    assert moved.id == 5092 and (await adapter.get_room(5090)).exits[0].target_room_id == 5092
    await adapter.delete_room(5092)
    dangling = (await adapter.get_room(5090)).exits[0]
    assert dangling.target_room_id is None and dangling.target_room_vnum is None
    mob = await adapter.create_mob(
        MobIn(
            vnum=5093,
            zone_id=ZONE,
            keywords="oste",
            short_description="un oste",
            extra={"shop": {"buyTypes": ["food"]}, "special": "spec_fido"},
        )
    )
    moved_mob = await adapter.update_mob(mob.id, MobPatch(vnum=5094))
    assert moved_mob.extra["shop"]["buyTypes"][0] == "food" and moved_mob.extra["special"] == "spec_fido"
    zone = await adapter.create_zone(ZoneIn(vnum=1, name="Altro", bottom_vnum=40000, top_vnum=40099))
    shifted = await adapter.update_mob(5094, MobPatch(vnum=40001, zone_id=zone.id))
    assert shifted.zone_id == zone.id and shifted.extra["special"] == "spec_fido" and shifted.extra["shop"]


async def test_delete_mob_removes_shop_and_special(adapter: BasedMudAdapter, area: Path) -> None:
    """Eliminare un mob toglie anche il suo negozio e la sua spec_fun (se nessun reset lo usa)."""
    mob = await adapter.create_mob(
        MobIn(
            vnum=5090,
            zone_id=ZONE,
            keywords="tester",
            short_description="un tester",
            extra={"shop": {"buyTypes": ["weapon"]}, "special": "spec_fido"},
        )
    )
    assert mob.extra["special"] == "spec_fido" and "npc" in mob.flags
    text = (area / "prato.are").read_text(encoding="latin-1")
    assert re.search(r"^M\s+5090\s+spec_fido", text, re.M) and re.search(r"^\s*5090\s", text, re.M)
    await adapter.delete_mob(5090)
    assert "5090" not in (area / "prato.are").read_text(encoding="latin-1")


async def test_area_list_edits(adapter: BasedMudAdapter, area: Path) -> None:
    """Creare/disabilitare/riabilitare/eliminare una zona modifica `area.lst` mantenendo il `$` finale."""
    zone = await adapter.create_zone(ZoneIn(vnum=1, name="Nuova Terra", builder="Anna", bottom_vnum=20000, top_vnum=20099))
    assert zone.id == 20000 and zone.extra["file"] == "nuovaterra.are" and zone.enabled
    lst = (area / "area.lst").read_text()
    assert lst.rstrip().endswith("nuovaterra.are\n$") and lst.count("nuovaterra.are") == 1
    assert (area / "nuovaterra.are").read_text().startswith("#AREADATA\nName Nuova Terra~\nBuilders Anna~\nVNUMs 20000 20099")
    off = await adapter.update_zone(zone.id, ZonePatch(enabled=False))
    assert off.enabled is False and "nuovaterra.are" not in read_area_list(area / "area.lst").names
    await adapter.update_zone(zone.id, ZonePatch(enabled=True, name="Terra Nuova"))
    assert read_area_list(area / "area.lst").names[-1] == "nuovaterra.are"
    await adapter.delete_zone(20000)
    assert not (area / "nuovaterra.are").exists() and (area / "area.lst").read_text().rstrip().endswith("$")
    with expect_error(409, "zones.not_empty"):
        await adapter.delete_zone(ZONE)
    with expect_error(409, "zones.range_overlap"):
        await adapter.create_zone(ZoneIn(vnum=2, name="Sovrapposta", bottom_vnum=5050, top_vnum=5200))
    with expect_error(422, "basedmud.vnum_out_of_range"):
        await adapter.create_mob(MobIn(vnum=4950, zone_id=ZONE, keywords="x", short_description="x"))


async def test_read_only(make: Callable[..., BasedMudAdapter], area: Path) -> None:
    """Un mondo `read_only` legge ma rifiuta ogni scrittura (409 `world.read_only`) senza toccare i file."""
    adapter = make(read_only=True)
    before = {p.name: p.read_bytes() for p in area.iterdir()}
    assert adapter.capabilities().read_only and (await adapter.get_mob(MOB)).level == 23
    with expect_error(409, "world.read_only"):
        await adapter.update_mob(MOB, MobPatch(level=1))
    with expect_error(409, "world.read_only"):
        await adapter.create_zone(ZoneIn(vnum=1, name="X"))
    with expect_error(409, "world.read_only"):
        await adapter.delete_room(ROOM)
    assert {p.name: p.read_bytes() for p in area.iterdir()} == before


@pytest.mark.parametrize("bad", ["../evil.are", "a/b.are", "x.txt", "/etc/passwd", "..", ".hidden.are", "a b.are", "x" * 80 + ".are"])
async def test_path_traversal_is_rejected(adapter: BasedMudAdapter, area: Path, bad: str) -> None:
    """Il nome del file di una nuova zona non puo' uscire dalla cartella ne' avere suffissi diversi da `.are`."""
    with expect_error(422, "basedmud.invalid_file_name"):
        await adapter.create_zone(ZoneIn(vnum=1, name="Zona", extra={"file": bad}))
    assert not (area.parent / "evil.are").exists() and sorted(p.name for p in area.parent.iterdir()) == ["area"]


async def test_concurrent_writes_are_serialized(adapter: BasedMudAdapter) -> None:
    """Molte scritture concorrenti sullo stesso file non si perdono: tutte presenti e file ancora valido."""
    before = (await adapter.list_mobs(MobPageParams(zone_id=ZONE))).total
    creates = [
        adapter.create_mob(MobIn(vnum=5010 + i, zone_id=ZONE, keywords=f"clone{i}", short_description=f"clone {i}")) for i in range(20)
    ]
    edits = [adapter.update_mob(5001, MobPatch(level=i)) for i in range(1, 11)]
    assert len(await asyncio.gather(*creates, *edits)) == 30
    fresh = BasedMudAdapter(adapter.config)  # cache nuova: legge davvero da disco
    page = await fresh.list_mobs(MobPageParams(zone_id=ZONE))
    assert page.total == before + 20 and (await fresh.get_mob(5001)).level == 10
    assert sorted(m.vnum for m in page.items if m.keywords.startswith("clone")) == list(range(5010, 5030))


# --------------------------------------------------------------------------- regressione: iniezione di righe e testo non codificabile

INJECT = "x\n#0\n#999"

WORD_FIELDS = [
    ("mob", {"size": INJECT}),
    ("mob", {"material": INJECT}),
    ("mob", {"startPos": INJECT}),
    ("mob", {"defaultPos": INJECT}),
    ("mob", {"damType": INJECT}),
    ("mob", {"special": INJECT}),
    ("mob", {"size": "due parole"}),
    ("mob", {"size": "a\0b"}),
    ("mob", {"flagRemovals": [{"word": INJECT, "value": 1}]}),
    ("mob", {"mprogs": [{"trigger": INJECT, "vnum": 1, "phrase": "p"}]}),
    ("object", {"itemType": INJECT}),
    ("object", {"condition": INJECT}),
    ("object", {"values": ["0", "0", INJECT, "0", "0"]}),
    ("object", {"values": ["0", "0", "it's", "0", "0"]}),
]


async def _vnums(adapter: BasedMudAdapter) -> tuple[list[int], list[int]]:
    """Vnum di mob e oggetti visibili da un adapter."""
    mobs = await adapter.list_mobs(MobPageParams(page_size=100))
    objs = await adapter.list_objects(ObjectPageParams(page_size=100))
    return [m.vnum for m in mobs.items], [o.vnum for o in objs.items]


@pytest.mark.parametrize(("kind", "extra"), WORD_FIELDS, ids=lambda v: str(v)[:40])
async def test_unsafe_tokens_are_rejected_without_touching_disk(
    kind: str, extra: dict, adapter: BasedMudAdapter, make: Callable[..., BasedMudAdapter], area: Path
) -> None:
    """Un token libero con a capo/spazi/NUL darebbe un `.are` troncato: 422 `basedmud.unsafe_text`, disco e cache invariati."""
    before_vnums = await _vnums(adapter)
    raw = (area / "prato.are").read_bytes()
    with expect_error(422, "basedmud.unsafe_text"):
        if kind == "mob":
            await adapter.update_mob(MOB, MobPatch(extra=extra))
        else:
            await adapter.update_object(OBJ, ObjectPatch(extra=extra))
    assert (area / "prato.are").read_bytes() == raw
    assert await _vnums(adapter) == before_vnums == await _vnums(make())


@pytest.mark.parametrize(
    "text", [INJECT, "riga\n#0\nS\n", "a\n$\nb", "\n#5001\nfinta", "x~y"], ids=["inject", "section-end", "dollar", "fake-vnum", "tilde"]
)
async def test_free_text_never_changes_record_count(
    text: str, adapter: BasedMudAdapter, make: Callable[..., BasedMudAdapter], area: Path
) -> None:
    """I testi con `~` ammettono righe qualsiasi: o sono riscritti fedelmente o rifiutati (422), ma i record non cambiano."""
    before_vnums = await _vnums(adapter)
    try:
        await adapter.update_mob(MOB, MobPatch(description=text, short_description=text))
        await adapter.update_object(OBJ, ObjectPatch(description=text))
    except Exception as error:  # noqa: BLE001
        assert getattr(error, "status_code", None) == 422
    assert await _vnums(make()) == before_vnums


async def test_unencodable_text_is_422_and_leaves_disk_untouched(make: Callable[..., BasedMudAdapter], area: Path) -> None:
    """Un'emoji in un `.are` latin-1: 422 `basedmud.unencodable_text` (non 500), nessuna scrittura."""
    path = area / "prato.are"
    path.write_bytes(path.read_bytes().replace(b"passeggia qui.", b"passeggia qu\xec."))  # un byte non UTF-8: il file e' latin-1
    adapter, raw = make(), path.read_bytes()
    with expect_error(422, "basedmud.unencodable_text"):
        await adapter.update_room(ROOM, RoomPatch(name="Prato \U0001f600"))
    assert (area / "prato.are").read_bytes() == raw
    assert (await adapter.get_room(ROOM)).name != "Prato \U0001f600"
