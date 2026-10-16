"""Suite di contratto di `WorldAdapter`: gira su ogni adapter di `ADAPTER_FACTORIES` usando solo l'interfaccia."""

from pachimudeditor.common.adapters.base import WorldAdapter
from pachimudeditor.common.adapters.models import (
    ExitIn,
    ExitPatch,
    ExtraDescriptionIn,
    ExtraDescriptionPatch,
    MobIn,
    MobPageParams,
    MobPatch,
    ObjectIn,
    ObjectPageParams,
    ObjectPatch,
    ResetCommandIn,
    ResetCommandDraft,
    ResetDraftScriptIn,
    ResetScriptIn,
    RoomCloneIn,
    RoomIn,
    RoomPageParams,
    RoomPatch,
    ZoneCloneIn,
    ZoneIn,
    ZonePageParams,
    ZonePatch,
)
from pachimudeditor.common.enums import ZoneCommandType
from pachimudeditor.common.enums import Direction, DoorFlag

from tests.adapter_contract.helpers import expect_error, new_mob, new_object, new_room, new_zone


def _load_mob(mob_vnum: int, room_vnum: int) -> ResetCommandIn:
    """Un `LOAD_MOB` valido."""
    return ResetCommandIn(command_type=ZoneCommandType.LOAD_MOB, arg1=mob_vnum, arg2=1, arg3=room_vnum, arg4=1)


# --------------------------------------------------------------------------- identita'


async def test_describe_and_capabilities(adapter: WorldAdapter) -> None:
    """`describe()` elenca le risorse del nucleo con campi; le capability sono coerenti."""
    info = adapter.describe()
    assert info.id and info.kind and info.name
    resources = {r.type: r for r in info.resources}
    assert {"zone", "room", "mob", "object"} <= set(resources)
    for resource in resources.values():
        names = [f.name for f in resource.fields]
        assert names and len(names) == len(set(names))
    assert any(f.name == "vnum" and f.required for f in resources["room"].fields)
    assert any(f.name == "id" and f.read_only for f in resources["zone"].fields)
    assert info.capabilities == adapter.capabilities()


async def test_meta(adapter: WorldAdapter) -> None:
    """Enum, razze e classi sono liste ben formate (anche vuote per razze/classi)."""
    enums = await adapter.enums()
    assert enums
    for options in enums.values():
        assert all(isinstance(o.value, int) and o.label for o in options)
    for ref in [*await adapter.races(), *await adapter.classes()]:
        assert ref.id and ref.name


# --------------------------------------------------------------------------- zone


async def test_zone_crud_and_paging(adapter: WorldAdapter) -> None:
    """Creazione, lettura, ricerca, paginazione, aggiornamento ed eliminazione di una zona."""
    zone = await new_zone(adapter, "Foresta contratto")
    assert (await adapter.get_zone(zone.id)).name == "Foresta contratto"
    assert zone.extra == {} or adapter.describe().kind != "pachimud"  # pachimud non ha campi extra

    found = await adapter.list_zones(ZonePageParams(search="Foresta contratto"))
    assert [z.id for z in found.items] == [zone.id] and found.total == 1

    other = await new_zone(adapter, "Altra")
    page = await adapter.list_zones(ZonePageParams(page=1, pageSize=1))
    assert len(page.items) == 1 and page.total >= 2 and page.pages >= 2
    vnums = [z.vnum for z in (await adapter.list_zones(ZonePageParams())).items]
    assert vnums == sorted(vnums)

    updated = await adapter.update_zone(zone.id, ZonePatch(name="Rinominata", enabled=False))
    assert updated.name == "Rinominata" and updated.vnum == zone.vnum
    assert updated.enabled is False or adapter.describe().kind == "dikumod"  # Diku Modificato non ha il concetto: `enabled` e' sempre vero

    await adapter.delete_zone(other.id)
    with expect_error(404, "zones.not_found"):
        await adapter.get_zone(other.id)


async def test_zone_validation(adapter: WorldAdapter) -> None:
    """Vnum duplicato 409, range incoerenti 422 anche cambiando un solo estremo."""
    zone = await new_zone(adapter)
    with expect_error(409, "zones.vnum_taken"):
        await adapter.create_zone(ZoneIn(vnum=zone.vnum, name="Doppia"))
    with expect_error(422, "zones.invalid_vnum_range"):
        await adapter.update_zone(zone.id, ZonePatch(bottom_vnum=zone.top_vnum + 1))
    with expect_error(422, "zones.invalid_level_range"):
        await adapter.update_zone(zone.id, ZonePatch(min_level=zone.max_level + 1))
    with expect_error(404, "zones.not_found"):
        await adapter.update_zone(10**9, ZonePatch(name="x"))


async def test_next_vnums(adapter: WorldAdapter) -> None:
    """I vnum suggeriti sono liberi e il range non tocca altre zone; nuovo contenuto parte dal range."""
    zone = await new_zone(adapter)
    free = await adapter.next_zone_vnum(99)
    assert free.vnum != zone.vnum and free.top_vnum - free.bottom_vnum == 99
    assert free.bottom_vnum > zone.top_vnum or free.top_vnum < zone.bottom_vnum
    first = await adapter.next_content_vnum(zone.id, "room")
    assert first == zone.bottom_vnum
    room = await new_room(adapter, zone)
    assert await adapter.next_content_vnum(zone.id, "room") == room.vnum + 1


async def test_zone_summary_and_not_empty(adapter: WorldAdapter) -> None:
    """Il riepilogo conta il contenuto e una zona non vuota non si elimina."""
    zone = await new_zone(adapter)
    assert (await adapter.zone_summary(zone.id)).room_count == 0
    await new_room(adapter, zone)
    await new_mob(adapter, zone)
    await new_object(adapter, zone)
    summary = await adapter.zone_summary(zone.id)
    assert (summary.room_count, summary.mob_count, summary.object_count) == (1, 1, 1)
    with expect_error(409, "zones.not_empty"):
        await adapter.delete_zone(zone.id)


async def test_zone_clone(adapter: WorldAdapter) -> None:
    """La copia ha nuovo vnum/nome, range 0-0 se omesso, e copia lo script solo su richiesta."""
    zone = await new_zone(adapter)
    room = await new_room(adapter, zone)
    mob = await new_mob(adapter, zone)
    await adapter.replace_reset_commands(zone.id, ResetScriptIn(commands=[_load_mob(mob.vnum, room.vnum)]))

    free = await adapter.next_zone_vnum(99)
    plain = await adapter.clone_zone(zone.id, ZoneCloneIn(vnum=free.vnum, name="Copia"))
    assert plain.name == "Copia" and (plain.bottom_vnum, plain.top_vnum) == (0, 0) and plain.id != zone.id
    assert await adapter.list_reset_commands(plain.id) == []

    free = await adapter.next_zone_vnum(99)
    full = await adapter.clone_zone(zone.id, ZoneCloneIn(vnum=free.vnum, name="Copia 2", copy_reset_commands=True))
    assert [c.arg1 for c in await adapter.list_reset_commands(full.id)] == [mob.vnum]

    with expect_error(409, "zones.range_overlap"):
        await adapter.clone_zone(
            zone.id,
            ZoneCloneIn(vnum=free.vnum + 50, name="Sovrapposta", bottom_vnum=zone.bottom_vnum, top_vnum=zone.top_vnum),
        )
    with expect_error(409, "zones.vnum_taken"):
        await adapter.clone_zone(zone.id, ZoneCloneIn(vnum=zone.vnum, name="Doppia"))


# --------------------------------------------------------------------------- stanze


async def test_room_crud_and_listing(adapter: WorldAdapter) -> None:
    """CRUD di una stanza, filtro per zona, ricerca, vnum duplicato."""
    zone = await new_zone(adapter)
    room = await new_room(adapter, zone, "Atrio")
    assert room.exits == [] and room.extra_descriptions == [] and room.zone_id == zone.id
    with expect_error(409, "rooms.vnum_taken"):
        await adapter.create_room(RoomIn(vnum=room.vnum, zone_id=zone.id, name="Doppia"))

    other = await new_zone(adapter)
    await new_room(adapter, other, "Altrove")
    in_zone = await adapter.list_rooms(RoomPageParams(zone_id=zone.id))
    assert [r.id for r in in_zone.items] == [room.id]
    assert (await adapter.list_rooms(RoomPageParams(search="Altrove"))).total == 1

    updated = await adapter.update_room(room.id, RoomPatch(name="Salone", description="Ampio."))
    assert (updated.name, updated.description) == ("Salone", "Ampio.")
    assert (await adapter.get_room(room.id)).name == "Salone"

    await adapter.delete_room(room.id)
    with expect_error(404, "rooms.not_found"):
        await adapter.get_room(room.id)


async def test_exits_and_graph(adapter: WorldAdapter) -> None:
    """Uscite: una per direzione, coerenza, destinazione risolta; il grafo unisce le uscite reciproche."""
    zone = await new_zone(adapter)
    a, b = await new_room(adapter, zone, "A"), await new_room(adapter, zone, "B")
    north = await adapter.create_exit(a.id, ExitIn(direction=Direction.NORTH, target_room_id=b.id))
    assert (north.target_room_vnum, north.target_room_name) == (b.vnum, "B")
    with expect_error(409, "rooms.exit_direction_taken"):
        await adapter.create_exit(a.id, ExitIn(direction=Direction.NORTH))
    with expect_error(422, "rooms.exit_self_loop"):
        await adapter.create_exit(a.id, ExitIn(direction=Direction.EAST, target_room_id=a.id))
    with expect_error(422, "rooms.exit_locked_needs_key"):
        await adapter.create_exit(a.id, ExitIn(direction=Direction.WEST, door_flag=DoorFlag.CLOSABLE, is_locked=True))
    with expect_error(422, "rooms.exit_door_state_invalid"):
        await adapter.create_exit(a.id, ExitIn(direction=Direction.UP, is_open=False))

    graph = await adapter.room_graph(zone.id)
    assert len(graph.nodes) == 2 and len(graph.edges) == 1 and not graph.edges[0].two_way
    assert next(n for n in graph.nodes if n.id == b.id).dangling_exits == 0
    await adapter.create_exit(b.id, ExitIn(direction=Direction.SOUTH, target_room_id=a.id))
    graph = await adapter.room_graph(zone.id)
    assert len(graph.edges) == 1 and graph.edges[0].two_way and graph.edges[0].reverse_exit_id is not None

    patched = await adapter.update_exit(a.id, north.id, ExitPatch(description="Un corridoio."))
    assert patched.description == "Un corridoio."
    with expect_error(409, "rooms.exit_not_in_room"):
        await adapter.update_exit(b.id, north.id, ExitPatch(description="x"))
    await adapter.delete_exit(a.id, north.id)
    assert (await adapter.get_room(a.id)).exits == []


async def test_extra_descriptions(adapter: WorldAdapter) -> None:
    """CRUD delle extra description, con controllo di appartenenza alla stanza."""
    zone = await new_zone(adapter)
    room, other = await new_room(adapter, zone), await new_room(adapter, zone)
    extra = await adapter.create_extra_description(room.id, ExtraDescriptionIn(keywords="botte", text="Grossa."))
    assert [e.id for e in (await adapter.get_room(room.id)).extra_descriptions] == [extra.id]
    edited = await adapter.update_extra_description(room.id, extra.id, ExtraDescriptionPatch(text="Enorme."))
    assert edited.text == "Enorme."
    with expect_error(409, "rooms.extra_not_in_room"):
        await adapter.delete_extra_description(other.id, extra.id)
    await adapter.delete_extra_description(room.id, extra.id)
    assert (await adapter.get_room(room.id)).extra_descriptions == []


async def test_room_clone(adapter: WorldAdapter) -> None:
    """La copia ha vnum nuovo, stessi campi, extra description copiate e nessuna uscita."""
    zone = await new_zone(adapter)
    a, b = await new_room(adapter, zone, "Originale"), await new_room(adapter, zone)
    await adapter.create_extra_description(a.id, ExtraDescriptionIn(keywords="k", text="t"))
    await adapter.create_exit(a.id, ExitIn(direction=Direction.NORTH, target_room_id=b.id))
    vnum = await adapter.next_content_vnum(zone.id, "room")
    clone = await adapter.clone_room(a.id, RoomCloneIn(vnum=vnum))
    assert clone.vnum == vnum and clone.name == "Originale" and clone.id != a.id
    assert clone.exits == [] and [e.text for e in clone.extra_descriptions] == ["t"]
    with expect_error(409, "rooms.vnum_taken"):
        await adapter.clone_room(a.id, RoomCloneIn(vnum=a.vnum))


# --------------------------------------------------------------------------- mob e oggetti


async def test_mob_crud_and_listing(adapter: WorldAdapter) -> None:
    """CRUD di un mob, filtro per zona, ricerca, vnum duplicato, patch con null solo sui campi opzionali."""
    zone = await new_zone(adapter)
    mob = await new_mob(adapter, zone, "goblin")
    assert mob.keywords == "goblin"
    with expect_error(409, "mobs.vnum_taken"):
        await adapter.create_mob(MobIn(vnum=mob.vnum, zone_id=zone.id, keywords="x", short_description="x"))
    assert [m.id for m in (await adapter.list_mobs(MobPageParams(zone_id=zone.id))).items] == [mob.id]
    assert (await adapter.list_mobs(MobPageParams(search="goblin"))).total >= 1
    edited = await adapter.update_mob(mob.id, MobPatch(level=5, race_id="human"))
    assert edited.level == 5 and edited.race_id == "human"
    cleared = await adapter.update_mob(mob.id, MobPatch(race_id=None))
    assert cleared.race_id is None
    await adapter.delete_mob(mob.id)
    with expect_error(404, "mobs.not_found"):
        await adapter.get_mob(mob.id)


async def test_object_crud_and_listing(adapter: WorldAdapter) -> None:
    """CRUD di un oggetto, filtro per zona, vnum duplicato."""
    zone = await new_zone(adapter)
    obj = await new_object(adapter, zone, "ascia")
    assert [o.id for o in (await adapter.list_objects(ObjectPageParams(zone_id=zone.id))).items] == [obj.id]
    assert (await adapter.update_object(obj.id, ObjectPatch(cost=50))).cost == 50
    with expect_error(409, "objects.vnum_taken"):
        await adapter.create_object(ObjectIn(vnum=obj.vnum, zone_id=zone.id, keywords="x", short_description="x"))
    await adapter.delete_object(obj.id)
    with expect_error(404, "objects.not_found"):
        await adapter.get_object(obj.id)


# --------------------------------------------------------------------------- reset e uso


async def test_reset_script_roundtrip_and_usage(adapter: WorldAdapter) -> None:
    """Lo script viene rinumerato, il suo uso blocca delete e cambio vnum, poi si sblocca svuotandolo."""
    zone = await new_zone(adapter)
    room, mob = await new_room(adapter, zone), await new_mob(adapter, zone)
    obj = await new_object(adapter, zone)
    script = ResetScriptIn(
        commands=[
            _load_mob(mob.vnum, room.vnum),
            ResetCommandIn(command_type=ZoneCommandType.GIVE_OBJECT, arg1=obj.vnum, arg2=1),
        ]
    )
    saved = await adapter.replace_reset_commands(zone.id, script)
    assert [c.order_index for c in saved] == [0, 1] and [c.command_type for c in saved] == [
        ZoneCommandType.LOAD_MOB,
        ZoneCommandType.GIVE_OBJECT,
    ]
    assert [c.arg1 for c in await adapter.list_reset_commands(zone.id)] == [mob.vnum, obj.vnum]

    for usage in (await adapter.mob_usage(mob.id), await adapter.room_usage(room.id), await adapter.object_usage(obj.id)):
        assert len(usage) == 1 and usage[0].zone_id == zone.id and usage[0].source == "reset"

    with expect_error(409, "mobs.in_reset_usage"):
        await adapter.delete_mob(mob.id)
    with expect_error(409, "rooms.in_reset_usage"):
        await adapter.delete_room(room.id)
    with expect_error(409, "objects.in_reset_usage"):
        await adapter.delete_object(obj.id)
    with expect_error(409, "mobs.vnum_in_use"):
        await adapter.update_mob(mob.id, MobPatch(vnum=mob.vnum + 500))
    with expect_error(409, "rooms.vnum_in_use"):
        await adapter.update_room(room.id, RoomPatch(vnum=room.vnum + 500))
    # rinominare senza cambiare vnum e' sempre lecito
    assert (await adapter.update_mob(mob.id, MobPatch(vnum=mob.vnum, level=2))).level == 2

    await adapter.replace_reset_commands(zone.id, ResetScriptIn(commands=[]))
    assert await adapter.mob_usage(mob.id) == []
    await adapter.delete_mob(mob.id)
    await adapter.delete_room(room.id)
    await adapter.delete_object(obj.id)


async def test_object_exit_key_usage(adapter: WorldAdapter) -> None:
    """Un oggetto usato come chiave di un'uscita risulta in uso (`source == exit_key`) e non si elimina."""
    zone = await new_zone(adapter)
    a, b = await new_room(adapter, zone), await new_room(adapter, zone)
    key = await new_object(adapter, zone, "chiave")
    await adapter.create_exit(
        a.id,
        ExitIn(
            direction=Direction.NORTH, target_room_id=b.id, door_flag=DoorFlag.CLOSABLE, is_open=False, is_locked=True, key_vnum=key.vnum
        ),
    )
    usage = await adapter.object_usage(key.id)
    assert [u.source for u in usage] == ["exit_key"] and usage[0].room_vnum == a.vnum
    with expect_error(409, "objects.in_exit_key_usage"):
        await adapter.delete_object(key.id)
    with expect_error(422, "rooms.exit_key_unknown"):
        await adapter.create_exit(b.id, ExitIn(direction=Direction.SOUTH, door_flag=DoorFlag.CLOSABLE, key_vnum=key.vnum + 777))


async def test_reset_validation(adapter: WorldAdapter) -> None:
    """`replace` rifiuta i vnum inesistenti (422, nulla salvato); `validate` riporta errori e avvertimenti."""
    zone = await new_zone(adapter)
    room, mob = await new_room(adapter, zone), await new_mob(adapter, zone)
    with expect_error(422, "zones.reset_unknown_mob"):
        await adapter.replace_reset_commands(zone.id, script_with(_load_mob(mob.vnum + 9999, room.vnum)))
    assert await adapter.list_reset_commands(zone.id) == []

    draft = ResetDraftScriptIn(
        commands=[
            ResetCommandDraft(command_type=ZoneCommandType.GIVE_OBJECT, arg1=mob.vnum + 9999, if_flag=True),
            ResetCommandDraft(command_type=ZoneCommandType.LOAD_MOB, arg1=mob.vnum, arg2=0, arg3=room.vnum),
            ResetCommandDraft(command_type=ZoneCommandType.SET_DOOR_STATE, arg1=room.vnum, arg2=0, arg_str="OPEN"),
        ]
    )
    result = await adapter.validate_reset_commands(zone.id, draft)
    by_code = {(i.index, i.code): i.severity for i in result.issues}
    assert result.ok is False
    assert by_code[(0, "zones.reset_unknown_object")] == "error"
    assert by_code[(0, "zones.reset_if_flag_first")] == "warning"
    assert by_code[(1, "zones.reset_max_zero")] == "warning"
    assert by_code[(2, "zones.reset_no_such_exit")] == "warning"
    assert all(i.message for i in result.issues)

    ok = await adapter.validate_reset_commands(zone.id, ResetDraftScriptIn(commands=[]))
    assert ok.ok and ok.issues == []
    with expect_error(404, "zones.not_found"):
        await adapter.validate_reset_commands(10**9, draft)


def script_with(*commands: ResetCommandIn) -> ResetScriptIn:
    """Uno script con i comandi dati."""
    return ResetScriptIn(commands=list(commands))
