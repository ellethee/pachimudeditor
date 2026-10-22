"""Suite di contratto di `WorldAdapter`: gira su ogni adapter di `ADAPTER_FACTORIES` usando solo l'interfaccia."""

import pytest
from pachifast.errors import InvalidOrderByError

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
from pachimudeditor.common.enums import ObjectType, SectorType, Sex, ZoneCommandType
from pachimudeditor.common.enums import Direction, DoorFlag

from tests.adapter_contract.helpers import (
    assert_mob_queries_match_oracle,
    assert_room_queries_match_oracle,
    expect_error,
    new_mob,
    new_object,
    new_room,
    new_zone,
)


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


# --------------------------------------------------------------------------- oggetti: filtri e ordinamenti sulle statistiche


async def _stat_objects(adapter: WorldAdapter, apply: tuple[str, str]) -> tuple[int, dict[str, int]]:
    """Zona con 4 oggetti dai valori distinti (a: arma, b: armatura, c: cibo senza value, d: arma senza cost) -> (zona, nome -> id)."""
    zone = await new_zone(adapter, "Zona statistiche")
    specs = {
        "a": dict(object_type=ObjectType.WEAPON, weight=5, cost=100, value_0=2, value_1=6, extra_flags=["glow"], wear_flags=["take", "wield"], affects={apply[0]: 3}),
        "b": dict(object_type=ObjectType.ARMOR, weight=20, cost=50, value_0=-4, value_1=0, extra_flags=["glow", "magic"], wear_flags=["take", "body"], affects={apply[0]: 1, apply[1]: 2}),
        "c": dict(object_type=ObjectType.FOOD, weight=1, cost=500),
        "d": dict(object_type=ObjectType.WEAPON, weight=5, cost=0, value_0=2, value_1=8, wear_flags=["take"]),
    }  # fmt: skip
    ids: dict[str, int] = {}
    for name, spec in specs.items():
        vnum = await adapter.next_content_vnum(zone.id, "object")
        obj = await adapter.create_object(ObjectIn(vnum=vnum, zone_id=zone.id, keywords=name, short_description=f"oggetto {name}", **spec))
        ids[name] = obj.id
    return zone.id, ids


async def test_object_list_filters_and_ordering(adapter: WorldAdapter) -> None:
    """Ogni filtro e ordinamento sulle statistiche, nulli in fondo, combinazioni, errori 422, retrocompatibilita'."""
    apply = ("str", "dex") if "dikumod" in type(adapter).__module__ else ("strength", "dexterity")
    zone_id, ids = await _stat_objects(adapter, apply)
    name = {v: k for k, v in ids.items()}

    async def run(**kw: object) -> str:
        page = await adapter.list_objects(ObjectPageParams(zone_id=zone_id, **kw))  # type: ignore[arg-type]
        assert page.total == len(page.items) or kw.get("pageSize")
        return "".join(name[o.id] for o in page.items)

    assert await run() == "abcd"  # nessun nuovo parametro: ordine per vnum come sempre
    assert await run(object_type=[int(ObjectType.WEAPON)]) == "ad"
    assert await run(object_type=[int(ObjectType.ARMOR), int(ObjectType.FOOD)]) == "bc"
    assert await run(min_cost=50, max_cost=100) == "ab"
    assert await run(min_weight=5) == "abd" and await run(max_weight=4) == "c"
    # i valueN dipendono dalla mappatura dell'adapter (es. ROM porta a 0 i valori del cibo): atteso calcolato sui DTO
    dtos = {name[o.id]: o for o in (await adapter.list_objects(ObjectPageParams(zone_id=zone_id))).items}
    for n in range(4):
        field = f"value_{n}"
        for low, high in ((0, None), (None, -1), (7, 9), (0, 0), (2, 2)):
            want = "".join(
                k
                for k, o in dtos.items()
                if getattr(o, field) is not None
                and (low is None or getattr(o, field) >= low)
                and (high is None or getattr(o, field) <= high)
            )
            assert await run(**{f"min_{field}": low, f"max_{field}": high}) == want, (field, low, high)
    assert await run(extra_flag=["glow"]) == "ab" and await run(extra_flag=["glow", "magic"]) == "b"
    assert await run(wear_flag=["take"]) == "abd" and await run(wear_flag=["take", "body"]) == "b"
    assert await run(affect=apply[0]) == "ab" and await run(affect=apply[0], min_affect=2) == "a"
    assert await run(affect="inesistente") == ""
    assert await run(object_type=[int(ObjectType.WEAPON)], min_cost=1, extra_flag=["glow"]) == "a"  # combinazione = AND
    assert await run(search="oggetto c", min_cost=1) == "c"
    assert await run(orderBy="cost") == "dbac" and await run(orderBy="-cost") == "cabd"
    assert await run(orderBy="weight,-cost") == "cadb"
    assert await run(orderBy="-weight,vnum") == "bad"[:0] + "bad" + "c"
    assert await run(orderBy="shortDescription") == "abcd" and await run(orderBy="-shortDescription") == "dcba"
    assert await run(orderBy="objectType,vnum") == "adbc" and await run(orderBy="zoneId") == "abcd"
    # nulli in fondo in entrambe le direzioni; a parita' decide il vnum (atteso calcolato sui DTO)
    for n in range(4):
        field = f"value_{n}"
        have = [k for k, o in dtos.items() if getattr(o, field) is not None]
        null = "".join(k for k, o in dtos.items() if getattr(o, field) is None)
        for desc in (False, True):
            want = "".join(sorted(have, key=lambda k: getattr(dtos[k], field), reverse=desc)) + null
            assert await run(orderBy=("-" if desc else "") + f"value{n}") == want, (field, desc)
            assert await run(orderBy=("-" if desc else "") + field) == want
    for field in ("value2", "value3", "rent", "weight", "cost", "zoneId", "shortDescription", "vnum", "id", "objectType"):
        assert len(await run(orderBy=field)) == 4 and len(await run(orderBy=f"-{field}")) == 4
    # paginazione: totale dopo i filtri, finestra dopo l'ordinamento
    page = await adapter.list_objects(ObjectPageParams(zone_id=zone_id, min_weight=5, orderBy="-cost", page=1, pageSize=2))
    assert page.total == 3 and [name[o.id] for o in page.items] == ["a", "b"]
    page = await adapter.list_objects(ObjectPageParams(zone_id=zone_id, min_weight=5, orderBy="-cost", page=2, pageSize=2))
    assert [name[o.id] for o in page.items] == ["d"]
    # tutte le zone: i nuovi oggetti sono nel mondo
    assert {ids["a"], ids["b"]} <= {o.id for o in (await adapter.list_objects(ObjectPageParams(extra_flag=["glow"]))).items}


async def test_object_list_invalid_params(adapter: WorldAdapter) -> None:
    """Parametri non validi: 422 con codice stabile, mai errori interni."""
    with expect_error(422, "objects.invalid_range"):
        await adapter.list_objects(ObjectPageParams(min_cost=10, max_cost=5))
    with expect_error(422, "objects.invalid_range"):
        await adapter.list_objects(ObjectPageParams(min_value_2=3, max_value_2=1))
    with expect_error(422, "objects.invalid_object_type"):
        await adapter.list_objects(ObjectPageParams(object_type=[999]))
    with expect_error(422, "objects.affect_required"):
        await adapter.list_objects(ObjectPageParams(min_affect=1))
    with pytest.raises(InvalidOrderByError):
        await adapter.list_objects(ObjectPageParams(orderBy="descrizione"))
    with pytest.raises(InvalidOrderByError):
        await adapter.list_objects(ObjectPageParams(orderBy="cost,-nope"))


# --------------------------------------------------------------------------- mob: filtri e ordinamenti sulle statistiche


async def _stat_mobs(adapter: WorldAdapter) -> tuple[int, dict[str, int]]:
    """Zona con 4 mob dai valori distinti (a: livello 5 maschio, b: 20 femmina, c: 1 neutro, d: 5 maschio) -> (zona, nome -> id).
    Solo campi che tutti gli adapter sanno rappresentare."""
    zone = await new_zone(adapter, "Zona statistiche mob")
    specs = {
        "a": dict(level=5, sex=Sex.MALE, gold=100, armor_class=10, alignment=-500, flags=["sentinel", "aggressive"], hp_dice_count=2, hp_die_size=6, hp_bonus=3),
        "b": dict(level=20, sex=Sex.FEMALE, gold=0, armor_class=-20, alignment=500, flags=["sentinel"], hp_dice_count=5, hp_die_size=10, damage_bonus=4),
        "c": dict(level=1, sex=Sex.NEUTRAL, gold=500, armor_class=0, alignment=0, flags=[]),
        "d": dict(level=5, sex=Sex.MALE, gold=50, armor_class=10, alignment=1000, flags=["aggressive"], damage_dice_count=3),
    }  # fmt: skip
    ids: dict[str, int] = {}
    for name, spec in specs.items():
        vnum = await adapter.next_content_vnum(zone.id, "mob")
        mob = await adapter.create_mob(MobIn(vnum=vnum, zone_id=zone.id, keywords=name, short_description=f"mob {name}", **spec))
        ids[name] = mob.id
    return zone.id, ids


async def test_mob_list_filters_and_ordering(adapter: WorldAdapter) -> None:
    """Ogni filtro e ordinamento sulle statistiche dei mob, nulli in fondo, combinazioni, paginazione, retrocompatibilita'."""
    zone_id, ids = await _stat_mobs(adapter)
    name = {v: k for k, v in ids.items()}

    async def run(**kw: object) -> str:
        page = await adapter.list_mobs(MobPageParams(zone_id=zone_id, **kw))  # type: ignore[arg-type]
        assert page.total == len(page.items) or kw.get("pageSize")
        return "".join(name[m.id] for m in page.items)

    dtos = {name[m.id]: m for m in (await adapter.list_mobs(MobPageParams(zone_id=zone_id))).items}
    assert await run() == "abcd"  # nessun nuovo parametro: ordine per vnum come sempre
    assert await run(orderBy="-level") == "badc" and await run(orderBy="level,vnum") == "cadb"
    assert await run(min_level=5, max_level=5) == "ad" and await run(min_level=6) == "b" and await run(max_level=1) == "c"
    assert await run(sex=[int(Sex.MALE)]) == "ad" and await run(sex=[int(Sex.FEMALE), int(Sex.NEUTRAL)]) == "bc"
    assert (
        await run(flag=["sentinel"]) == "ab"
        and await run(flag=["AGGRESSIVE"]) == "ad"
        and await run(flag=["sentinel", "aggressive"]) == "a"
    )
    assert await run(flag=["inesistente"]) == ""
    assert await run(min_gold=50, max_gold=100) == "ad" and await run(orderBy="-gold") == "cadb"
    assert await run(min_alignment=0) == "bcd" and await run(max_alignment=-1) == "a" and await run(orderBy="-alignment") == "dbca"
    assert await run(orderBy="armorClass,-vnum") == "bcda"  # -20, 0, poi 10 (d prima di a per -vnum)
    assert await run(sex=[int(Sex.MALE)], min_level=5, flag=["aggressive"], max_gold=60) == "d"  # combinazione = AND
    assert await run(search="mob b", min_level=10) == "b"
    assert await run(orderBy="shortDescription") == "abcd" and await run(orderBy="-shortDescription") == "dcba"
    assert await run(orderBy="sex,-vnum") == "cdab" and await run(orderBy="zoneId") == "abcd"
    for field in (
        "hp_dice_count",
        "hp_die_size",
        "hp_bonus",
        "damage_dice_count",
        "damage_die_size",
        "damage_bonus",
        "thac0",
        "experience",
    ):
        want_low = "".join(sorted(dtos, key=lambda k: getattr(dtos[k], field)))
        assert await run(orderBy=field) == want_low, field
        assert await run(**{f"min_{field}": 1}) == "".join(k for k in dtos if getattr(dtos[k], field) >= 1), field
    # razza/classe: dipendono dalla mappatura dell'adapter -> atteso calcolato sui DTO (un id nullo non soddisfa il filtro)
    for attr in ("race_id", "class_id"):
        values = sorted({v for m in dtos.values() if (v := getattr(m, attr))})
        assert await run(**{attr: values + ["inesistente"]}) == "".join(k for k, m in dtos.items() if getattr(m, attr) in values)
        assert await run(**{attr: ["inesistente"]}) == ""
        have = [k for k, m in dtos.items() if getattr(m, attr) is not None]
        null = "".join(k for k, m in dtos.items() if getattr(m, attr) is None)
        for desc in (False, True):
            want = "".join(sorted(have, key=lambda k: getattr(dtos[k], attr), reverse=desc)) + null
            assert await run(orderBy=("-" if desc else "") + attr) == want
    page = await adapter.list_mobs(MobPageParams(zone_id=zone_id, min_level=5, orderBy="-level", page=1, pageSize=2))
    assert page.total == 3 and [name[m.id] for m in page.items] == ["b", "a"]
    page = await adapter.list_mobs(MobPageParams(zone_id=zone_id, min_level=5, orderBy="-level", page=2, pageSize=2))
    assert [name[m.id] for m in page.items] == ["d"]
    # tutte le zone: i nuovi mob sono nel mondo
    assert {ids["b"]} <= {m.id for m in (await adapter.list_mobs(MobPageParams(min_level=20))).items}
    await assert_mob_queries_match_oracle(adapter)


async def test_mob_trainer_filter(adapter: WorldAdapter) -> None:
    """Filtro `trainer` e `isTrainer`: pachimud `guildmaster`, ROM `train|practice|gain` (non `healer`), dikumod dalle procedure
    speciali di `spec_assign.c` (senza il file il campo e' non supportato e il filtro e' ignorato)."""
    kind = adapter.config.kind
    zone = await new_zone(adapter, "Zona maestri")
    flag = {"pachimud": "guildmaster", "basedmud": "gain", "mapping": "practice"}.get(kind)
    ids: dict[str, int] = {}
    vnums: dict[str, int] = {}
    for name, flags in (("a", [flag] if flag else []), ("b", []), ("c", ["sentinel"])):
        vnum = await adapter.next_content_vnum(zone.id, "mob")
        mob = await adapter.create_mob(MobIn(vnum=vnum, zone_id=zone.id, keywords=name, short_description=f"mob {name}", flags=flags))
        ids[name], vnums[name] = mob.id, vnum
    names = {v: k for k, v in ids.items()}

    async def run(**kw: object) -> str:
        page = await adapter.list_mobs(MobPageParams(zone_id=zone.id, **kw))  # type: ignore[arg-type]
        return "".join(names[m.id] for m in page.items)

    async def field_unsupported() -> bool:
        mob = next(r for r in adapter.describe().resources if r.type == "mob")
        return next(f for f in mob.fields if f.name == "isTrainer").unsupported

    if kind == "dikumod":
        assert await field_unsupported() and (await adapter.get_mob(ids["a"])).is_trainer is None
        assert await run(trainer=True) == "abc" and await run(trainer=False) == "abc"  # non supportato: ignorato
        src = adapter.spec.path  # type: ignore[attr-defined]
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text(
            f"static struct special_proc_entry specials[] = {{ {{ {vnums['a']}, MageGuildMaster }}, {{ {vnums['c']}, Cityguard }}, {{ -1, NULL }} }};"
        )
        assert not await field_unsupported()
        assert (await adapter.get_mob(ids["a"])).extra["specProc"] == "MageGuildMaster"
    else:
        assert not await field_unsupported()
    assert [(await adapter.get_mob(ids[k])).is_trainer for k in "abc"] == [True, False, False]
    assert await run(trainer=True) == "a" and await run(trainer=False) == "bc" and await run() == "abc"
    assert await run(trainer=True, search="mob b") == "" and await run(trainer=False, flag=["sentinel"]) == "c"
    assert {ids["a"]} <= {m.id for m in (await adapter.list_mobs(MobPageParams(trainer=True))).items}  # tutte le zone
    await assert_mob_queries_match_oracle(adapter)


async def test_mob_list_invalid_params(adapter: WorldAdapter) -> None:
    """Parametri non validi: 422 con codice stabile, mai errori interni."""
    with expect_error(422, "mobs.invalid_range"):
        await adapter.list_mobs(MobPageParams(min_level=10, max_level=5))
    with expect_error(422, "mobs.invalid_range"):
        await adapter.list_mobs(MobPageParams(min_hp_bonus=3, max_hp_bonus=1))
    with expect_error(422, "mobs.invalid_sex"):
        await adapter.list_mobs(MobPageParams(sex=[99]))
    with pytest.raises(InvalidOrderByError):
        await adapter.list_mobs(MobPageParams(orderBy="descrizione"))
    with pytest.raises(InvalidOrderByError):
        await adapter.list_mobs(MobPageParams(orderBy="level,-nope"))


# --------------------------------------------------------------------------- stanze: filtri e ordinamenti sulle statistiche


async def _stat_rooms(adapter: WorldAdapter) -> tuple[int, dict[str, int]]:
    """Zona con 4 stanze (a: foresta con flag dark, b: citta' con dark+nomob, c: dentro senza flag, d: foresta) -> (zona, nome -> id)."""
    zone = await new_zone(adapter, "Zona statistiche stanze")
    specs = {
        "a": dict(name="Bosco", sector_type=SectorType.FOREST, flags=["dark"]),
        "b": dict(name="Piazza", sector_type=SectorType.CITY, flags=["dark", "no_mob"]),
        "c": dict(name="Cantina", sector_type=SectorType.INSIDE, flags=[]),
        "d": dict(name="Radura", sector_type=SectorType.FOREST, flags=[]),
    }  # fmt: skip
    ids: dict[str, int] = {}
    for key, spec in specs.items():
        vnum = await adapter.next_content_vnum(zone.id, "room")
        ids[key] = (await adapter.create_room(RoomIn(vnum=vnum, zone_id=zone.id, **spec))).id
    return zone.id, ids


async def test_room_list_filters_and_ordering(adapter: WorldAdapter) -> None:
    """Ogni filtro e ordinamento sulle statistiche delle stanze, combinazioni, paginazione, retrocompatibilita'."""
    zone_id, ids = await _stat_rooms(adapter)
    name = {v: k for k, v in ids.items()}

    async def run(**kw: object) -> str:
        page = await adapter.list_rooms(RoomPageParams(zone_id=zone_id, **kw))  # type: ignore[arg-type]
        assert page.total == len(page.items) or kw.get("pageSize")
        return "".join(name[r.id] for r in page.items)

    dtos = {name[r.id]: r for r in (await adapter.list_rooms(RoomPageParams(zone_id=zone_id))).items}
    assert await run() == "abcd"
    assert (
        await run(sector_type=[int(SectorType.FOREST)]) == "ad"
        and await run(sector_type=[int(SectorType.CITY), int(SectorType.INSIDE)]) == "bc"
    )
    assert await run(orderBy="name") == "acbd" and await run(orderBy="-name") == "dbca"
    assert await run(orderBy="sectorType,vnum") == "cbad" and await run(orderBy="-sectorType") == "adbc"
    assert await run(flag=["dark"]) == "ab" and await run(flag=["DARK", "no_mob"]) == "b" and await run(flag=["inesistente"]) == ""
    assert await run(sector_type=[int(SectorType.FOREST)], flag=["dark"]) == "a"  # combinazione = AND
    assert await run(search="Cantina", sector_type=[int(SectorType.INSIDE)]) == "c"
    assert await run(orderBy="zoneId") == "abcd" and await run(orderBy="-vnum") == "dcba"
    # tasso di cura/mana, clan e proprietario: dipendono dalla mappatura dell'adapter -> atteso calcolato sui DTO
    for field in ("heal_rate", "mana_rate"):
        values = sorted({getattr(r, field) for r in dtos.values()})
        assert await run(**{f"min_{field}": values[-1]}) == "".join(k for k in dtos if getattr(dtos[k], field) >= values[-1])
        assert await run(**{f"min_{field}": values[-1] + 1}) == ""
        assert await run(orderBy=f"-{field}") == "".join(sorted("abcd", key=lambda k: -getattr(dtos[k], field)))
    for attr in ("clan_id", "owner"):
        have = [k for k, r in dtos.items() if getattr(r, attr) is not None]
        null = "".join(k for k, r in dtos.items() if getattr(r, attr) is None)
        for desc in (False, True):
            want = "".join(sorted(have, key=lambda k: getattr(dtos[k], attr), reverse=desc)) + null
            assert await run(orderBy=("-" if desc else "") + attr) == want
    assert await run(clan_id=["inesistente"]) == "" and await run(owner="inesistente") == ""
    page = await adapter.list_rooms(RoomPageParams(zone_id=zone_id, flag=["dark"], orderBy="-name", page=1, pageSize=1))
    assert page.total == 2 and [name[r.id] for r in page.items] == [max("ab", key=lambda k: dtos[k].name)]
    assert {ids["b"]} <= {r.id for r in (await adapter.list_rooms(RoomPageParams(flag=["no_mob"]))).items}
    await assert_room_queries_match_oracle(adapter)


async def test_room_list_invalid_params(adapter: WorldAdapter) -> None:
    """Parametri non validi: 422 con codice stabile, mai errori interni."""
    with expect_error(422, "rooms.invalid_range"):
        await adapter.list_rooms(RoomPageParams(min_heal_rate=10, max_heal_rate=5))
    with expect_error(422, "rooms.invalid_sector_type"):
        await adapter.list_rooms(RoomPageParams(sector_type=[99]))
    with pytest.raises(InvalidOrderByError):
        await adapter.list_rooms(RoomPageParams(orderBy="descrizione"))
    with pytest.raises(InvalidOrderByError):
        await adapter.list_rooms(RoomPageParams(orderBy="name,-nope"))
