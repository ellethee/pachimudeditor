"""Importa (upsert) una cartella di zona nel database, con le stesse regole dell'importer del gioco.

Riscrittura sull'insieme di tabelle riflesse (nessun import di `pachimud`): idempotente per vnum, mai cancellazioni di
stanze/mob/oggetti assenti dal file; uscite non piu' presenti rimosse; extra description e reset sostituiti per intero.
L'equivalenza con `pachimud.zone.importer` e' verificata da `tests/test_game_compat.py`. Non committa: lo fa chi chiama.
"""

import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError
from pachifast.i18n import api_error
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pachimudeditor_adapter_pachimud.schema import models_of
from pachimudeditor_adapter_pachimud.transfer.schemas import (
    LoaderMobsFile,
    LoaderObjectsFile,
    LoaderReset,
    LoaderResetsFile,
    LoaderRoomsFile,
    LoaderZone,
    load_yaml,
)
from pachimudeditor.common.enums import Direction, DoorFlag, ObjectType, SectorType, Sex, ZoneCommandType, ZoneResetMode

log = logging.getLogger(__name__)


class ParsedZone(BaseModel):
    """I cinque file gia' validati."""

    zone: LoaderZone
    rooms: LoaderRoomsFile
    mobs: LoaderMobsFile
    objects: LoaderObjectsFile
    resets: LoaderResetsFile


def _load(path: Path, schema: type[BaseModel]) -> Any:
    """Carica `path` con lo schema (file mancante -> default vuoto); errore -> 422 `transfer.invalid_file`."""
    if not path.exists():
        return schema()
    try:
        return load_yaml(path, schema)
    except ValidationError as error:
        first = error.errors()[0]
        where = ".".join(str(part) for part in first["loc"])
        raise api_error(422, "transfer.invalid_file", file=path.name, detail=f"{where}: {first['msg']}") from error
    except Exception as error:  # YAML malformato, encoding, ...
        raise api_error(422, "transfer.invalid_file", file=path.name, detail=str(error).splitlines()[0][:200]) from error


MAX_RECORDS = 5_000
"""Massimo di record (stanze, mob, oggetti, reset) per ciascun file di una richiesta di import."""


def parse_zone_dir(directory: Path) -> ParsedZone:
    """Valida i file della cartella (`zone.yaml` obbligatorio, gli altri opzionali); troppi record -> 422."""
    zone_file = directory / "zone.yaml"
    parsed = ParsedZone(
        zone=_load(zone_file, LoaderZone),
        rooms=_load(directory / "rooms.yaml", LoaderRoomsFile),
        mobs=_load(directory / "mobs.yaml", LoaderMobsFile),
        objects=_load(directory / "objects.yaml", LoaderObjectsFile),
        resets=_load(directory / "resets.yaml", LoaderResetsFile),
    )
    for name, records in (
        ("rooms.yaml", parsed.rooms.rooms),
        ("mobs.yaml", parsed.mobs.mobs),
        ("objects.yaml", parsed.objects.objects),
        ("resets.yaml", parsed.resets.resets),
    ):
        if len(records) > MAX_RECORDS:
            raise api_error(422, "transfer.invalid_file", file=name, detail=f"troppi record (massimo {MAX_RECORDS})")
    return parsed


def parse_dice(text: str) -> tuple[int, int, int]:
    """Spezza una notazione dadi ROM `XdY+Z` (gia' validata) in (count, size, bonus)."""
    count_part, rest = text.split("d", 1)
    size_part, bonus_part = rest.split("+", 1)
    return int(count_part), int(size_part), int(bonus_part)


def reset_args(data: LoaderReset) -> tuple[int | None, int | None, int | None, int | None, str | None]:
    """`(arg1, arg2, arg3, arg4, arg_str)` di un reset tipizzato, in base al suo `type`."""
    if data.type == "LOAD_MOB":
        return data.mob_vnum, data.max_existing, data.room_vnum, data.room_limit, None
    if data.type == "LOAD_OBJECT":
        return data.obj_vnum, data.max_existing, data.room_vnum, data.room_limit, None
    if data.type == "GIVE_OBJECT":
        return data.obj_vnum, data.max_existing, None, None, None
    if data.type == "EQUIP_OBJECT":
        return data.obj_vnum, data.max_existing, None, None, data.wear_slot
    if data.type == "PUT_OBJECT":
        return data.obj_vnum, data.max_existing, data.container_vnum, None, None
    if data.type == "SET_DOOR_STATE":
        return data.room_vnum, int(Direction[data.direction]), None, None, data.state
    if data.type == "RANDOMIZE_EXITS":
        return data.room_vnum, None, None, None, None
    raise TypeError(f"tipo di reset non gestito: {data.type!r}")  # pragma: no cover


async def _upsert_zone(session: AsyncSession, data: LoaderZone) -> Any:
    """Crea o aggiorna la zona per vnum."""
    Zone = models_of(session).Zone  # noqa: N806
    zone = (await session.execute(select(Zone).where(Zone.vnum == data.vnum))).scalar_one_or_none()
    if zone is None:
        zone = Zone(vnum=data.vnum)
        session.add(zone)
    zone.name = data.name
    zone.builder = data.builder
    zone.bottom_vnum = data.bottom_vnum
    zone.top_vnum = data.top_vnum
    zone.min_level = data.min_level
    zone.max_level = data.max_level
    zone.lifespan_minutes = data.lifespan_minutes
    zone.reset_mode = int(ZoneResetMode[data.reset_mode])
    zone.enabled = data.enabled
    await session.flush()
    return zone


async def _upsert_rooms(session: AsyncSession, zone: Any, rooms_file: LoaderRoomsFile) -> dict[int, Any]:
    """Upsert di tutte le stanze della zona. Ritorna vnum -> riga, per risolvere le uscite (anche quelle in avanti)."""
    Room = models_of(session).Room  # noqa: N806
    rooms_by_vnum: dict[int, Any] = {}
    for data in rooms_file.rooms:
        room = (await session.execute(select(Room).where(Room.vnum == data.vnum))).scalar_one_or_none()
        if room is None:
            room = Room(vnum=data.vnum)
            session.add(room)
        room.zone_id = zone.id
        room.name = data.name
        room.description = data.description
        room.sector_type = int(SectorType[data.sector_type])
        room.flags = data.flags
        room.heal_rate = data.heal_rate
        room.mana_rate = data.mana_rate
        room.clan_id = data.clan_id
        room.owner = data.owner
        rooms_by_vnum[data.vnum] = room
    await session.flush()
    return rooms_by_vnum


async def _resolve_room_id(session: AsyncSession, vnum: int, rooms_by_vnum: dict[int, Any]) -> int | None:
    """L'id della stanza con quel vnum (nel file o gia' nel DB)."""
    room = rooms_by_vnum.get(vnum)
    if room is not None:
        return room.id  # type: ignore[no-any-return]
    Room = models_of(session).Room  # noqa: N806
    return (await session.execute(select(Room.id).where(Room.vnum == vnum))).scalar_one_or_none()


async def _sync_exits_and_extras(session: AsyncSession, rooms_file: LoaderRoomsFile, rooms_by_vnum: dict[int, Any]) -> None:
    """Allinea uscite (upsert per direzione, le assenti dal file sono rimosse) ed extra description (sostituite)."""
    m = models_of(session)
    for data in rooms_file.rooms:
        room = rooms_by_vnum[data.vnum]
        existing_exits = (await session.execute(select(m.Exit).where(m.Exit.room_id == room.id))).scalars().all()
        existing_by_direction = {Direction(e.direction): e for e in existing_exits}

        for direction_name, exit_data in data.exits.items():
            direction = Direction[direction_name]
            target_room_id = None
            if exit_data.target_vnum is not None:
                target_room_id = await _resolve_room_id(session, exit_data.target_vnum, rooms_by_vnum)
                if target_room_id is None:
                    log.warning(
                        "Stanza %s: uscita %s punta al vnum %s, non ancora importato - "
                        "uscita creata senza destinazione, si risolve al prossimo import.",
                        data.vnum,
                        direction_name,
                        exit_data.target_vnum,
                    )
            exit_row = existing_by_direction.pop(direction, None)
            if exit_row is None:
                exit_row = m.Exit(room_id=room.id, direction=int(direction))
                session.add(exit_row)
            exit_row.description = exit_data.description
            exit_row.keywords = exit_data.keywords
            exit_row.door_flag = int(DoorFlag[exit_data.door_flag])
            exit_row.is_open = exit_data.is_open
            exit_row.is_locked = exit_data.is_locked
            exit_row.key_vnum = exit_data.key_vnum
            exit_row.target_room_id = target_room_id

        for stale_exit in existing_by_direction.values():
            await session.delete(stale_exit)

        if m.RoomExtraDescription is not None:
            existing_extras = (
                (await session.execute(select(m.RoomExtraDescription).where(m.RoomExtraDescription.room_id == room.id))).scalars().all()
            )
            for extra in existing_extras:
                await session.delete(extra)
            for extra_data in data.extra_descriptions:
                session.add(m.RoomExtraDescription(room_id=room.id, keywords=extra_data.keywords, text=extra_data.text))
    await session.flush()


async def _upsert_mobs(
    session: AsyncSession, zone: Any, mobs_file: LoaderMobsFile, race_ids: set[str] | None, class_ids: set[str] | None
) -> None:
    """Upsert dei mob per vnum (dadi spezzati nelle tre colonne)."""
    MobPrototype = models_of(session).MobPrototype  # noqa: N806
    for data in mobs_file.mobs:
        mob = (await session.execute(select(MobPrototype).where(MobPrototype.vnum == data.vnum))).scalar_one_or_none()
        if mob is None:
            mob = MobPrototype(vnum=data.vnum)
            session.add(mob)
        hp_count, hp_size, hp_bonus = parse_dice(data.hp_dice)
        dmg_count, dmg_size, dmg_bonus = parse_dice(data.damage_dice)
        mob.zone_id = zone.id
        mob.keywords = data.keywords
        mob.short_description = data.short_description
        mob.long_description = data.long_description
        mob.detailed_description = data.detailed_description
        mob.level = data.level
        mob.thac0 = data.thac0
        mob.armor_class = data.armor_class
        mob.hp_dice_count = hp_count
        mob.hp_die_size = hp_size
        mob.hp_bonus = hp_bonus
        mob.damage_dice_count = dmg_count
        mob.damage_die_size = dmg_size
        mob.damage_bonus = dmg_bonus
        mob.gold = data.gold
        mob.experience = data.experience
        mob.sex = int(Sex[data.sex])
        mob.flags = data.flags
        mob.alignment = data.alignment
        mob.debuff_skill_id = data.debuff_skill_id
        mob.shop_id = data.shop_id
        mob.quest_ids = data.quest_ids
        mob.is_banker = data.is_banker
        mob.teaches_class_ids = data.teaches_class_ids
        mob.teaches_skill_ids = data.teaches_skill_ids
        mob.race_id = data.race_id
        mob.class_id = data.class_id
        if race_ids is not None and data.race_id is not None and data.race_id not in race_ids:
            log.warning("Mob %s: race_id %r non trovato tra le razze caricate.", data.vnum, data.race_id)
        if class_ids is not None and data.class_id is not None and data.class_id not in class_ids:
            log.warning("Mob %s: class_id %r non trovato tra le classi caricate.", data.vnum, data.class_id)
    await session.flush()


async def _upsert_objects(session: AsyncSession, zone: Any, objects_file: LoaderObjectsFile) -> None:
    """Upsert dei prototipi di oggetto per vnum."""
    ObjectPrototype = models_of(session).ObjectPrototype  # noqa: N806
    for data in objects_file.objects:
        obj = (await session.execute(select(ObjectPrototype).where(ObjectPrototype.vnum == data.vnum))).scalar_one_or_none()
        if obj is None:
            obj = ObjectPrototype(vnum=data.vnum)
            session.add(obj)
        obj.zone_id = zone.id
        obj.keywords = data.keywords
        obj.short_description = data.short_description
        obj.long_description = data.long_description
        obj.action_description = data.action_description
        obj.object_type = int(ObjectType[data.object_type])
        obj.weight = data.weight
        obj.cost = data.cost
        obj.rent = data.rent
        obj.value_0 = data.value_0
        obj.value_1 = data.value_1
        obj.value_2 = data.value_2
        obj.value_3 = data.value_3
        obj.extra_flags = data.extra_flags
        obj.wear_flags = data.wear_flags
        obj.affects = data.affects
    await session.flush()


async def _sync_resets(session: AsyncSession, zone: Any, resets_file: LoaderResetsFile) -> None:
    """Sostituisce per intero lo script di reset della zona."""
    ZoneResetCommand = models_of(session).ZoneResetCommand  # noqa: N806
    existing = (await session.execute(select(ZoneResetCommand).where(ZoneResetCommand.zone_id == zone.id))).scalars().all()
    for row in existing:
        await session.delete(row)
    await session.flush()
    for order_index, data in enumerate(resets_file.resets):
        arg1, arg2, arg3, arg4, arg_str = reset_args(data)
        session.add(
            ZoneResetCommand(
                zone_id=zone.id,
                order_index=order_index,
                command_type=int(ZoneCommandType[data.type]),
                if_flag=data.if_flag,
                arg1=arg1,
                arg2=arg2,
                arg3=arg3,
                arg4=arg4,
                arg_str=arg_str,
            )
        )
    await session.flush()


async def import_zone_directory(
    session: AsyncSession,
    zone_dir: Path,
    *,
    race_ids: set[str] | None = None,
    class_ids: set[str] | None = None,
    parsed: ParsedZone | None = None,
) -> Any:
    """Importa (upsert) una cartella di zona. Non committa. `race_ids`/`class_ids` servono solo ai warning nel log.

    `parsed` evita di rileggere i file se il chiamante li ha gia' validati (`parse_zone_dir`).
    """
    data = parsed or parse_zone_dir(zone_dir)
    zone = await _upsert_zone(session, data.zone)
    rooms_by_vnum = await _upsert_rooms(session, zone, data.rooms)
    await _sync_exits_and_extras(session, data.rooms, rooms_by_vnum)
    await _upsert_mobs(session, zone, data.mobs, race_ids, class_ids)
    await _upsert_objects(session, zone, data.objects)
    await _sync_resets(session, zone, data.resets)
    log.info(
        "Zona '%s' (vnum %d): %d stanze, %d mob, %d oggetti, %d reset.",
        zone.name,
        zone.vnum,
        len(data.rooms.rooms),
        len(data.mobs.mobs),
        len(data.objects.objects),
        len(data.resets.resets),
    )
    return zone
