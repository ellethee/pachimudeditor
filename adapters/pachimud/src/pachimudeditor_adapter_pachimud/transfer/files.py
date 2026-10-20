"""Esportazione di una zona dal database nel formato YAML letto dall'importer del gioco.

Produce i cinque file di una cartella `definitions/zones/<Nome>/`: `zone.yaml`, `rooms.yaml`, `mobs.yaml`,
`objects.yaml`, `resets.yaml`. Ogni elemento e' un dict con le stesse chiavi dei modelli `Loader*` (enum scritti per
*nome*, dadi `XdY+Z`, uscite come dict per direzione); i campi `None` sono omessi, perche' per il loader assente ==
default/None. Le tabelle sono quelle riflesse del mondo (`models_of(session)`), le colonne assenti valgono il neutro.
"""

import re
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pachimudeditor_adapter_pachimud.schema import GameRow, models_of
from pachimudeditor.common.enums import Direction, DoorFlag, ObjectType, SectorType, Sex, ZoneCommandType, ZoneResetMode

ZONE_FILES: tuple[str, ...] = ("zone.yaml", "rooms.yaml", "mobs.yaml", "objects.yaml", "resets.yaml")
"""I nomi canonici dei file di una zona."""


def zone_slug(zone: GameRow) -> str:
    """Identificativo testuale della zona (`zone_id` di `zone.yaml`): il nome in minuscolo senza simboli."""
    slug = re.sub(r"[^a-z0-9]+", "_", str(zone.name).lower()).strip("_")  # type: ignore[attr-defined]
    return slug or f"zone{zone.vnum}"  # type: ignore[attr-defined]


def _clean(data: dict[str, Any]) -> dict[str, Any]:
    """Il dict senza le chiavi con valore `None`."""
    return {key: value for key, value in data.items() if value is not None}


def zone_dict(zone: Any) -> dict[str, Any]:
    """`zone.yaml` di una zona."""
    return {
        "zone_id": zone_slug(zone),
        "vnum": zone.vnum,
        "name": zone.name,
        "builder": zone.builder,
        "bottom_vnum": zone.bottom_vnum,
        "top_vnum": zone.top_vnum,
        "min_level": zone.min_level,
        "max_level": zone.max_level,
        "lifespan_minutes": zone.lifespan_minutes,
        "reset_mode": ZoneResetMode(zone.reset_mode).name,
        "enabled": zone.enabled,
    }


def chunks(items: list[int], size: int = 500) -> list[list[int]]:
    """Blocchi per le query `IN`, sotto il limite di variabili di SQLite."""
    return [items[i : i + size] for i in range(0, len(items), size)]


async def room_dicts(session: AsyncSession, rooms: list[Any]) -> list[dict[str, Any]]:
    """Le stanze (con uscite ed extra description) come voci di `rooms.yaml`, ordinate per vnum."""
    if not rooms:
        return []
    m = models_of(session)
    ids = [room.id for room in rooms]
    exits: list[Any] = []
    extras: list[Any] = []
    for part in chunks(ids):  # blocchi: SQLite ha un limite di variabili per query
        exits += (await session.execute(select(m.Exit).where(m.Exit.room_id.in_(part)).order_by(m.Exit.direction))).scalars()
        if m.RoomExtraDescription is not None:
            extras += (
                await session.execute(
                    select(m.RoomExtraDescription).where(m.RoomExtraDescription.room_id.in_(part)).order_by(m.RoomExtraDescription.id)
                )
            ).scalars()
    target_ids = list({e.target_room_id for e in exits if e.target_room_id is not None})
    vnum_by_id: dict[int, int] = {}
    for part in chunks(target_ids):
        rows = await session.execute(select(m.Room.id, m.Room.vnum).where(m.Room.id.in_(part)))
        vnum_by_id |= {row.id: row.vnum for row in rows}
    out: list[dict[str, Any]] = []
    for room in sorted(rooms, key=lambda r: r.vnum):
        room_exits = {
            Direction(e.direction).name.lower(): _clean(
                {
                    "target_vnum": vnum_by_id.get(e.target_room_id) if e.target_room_id is not None else None,
                    "description": e.description,
                    "keywords": e.keywords,
                    "door_flag": DoorFlag(e.door_flag).name,
                    "is_open": e.is_open,
                    "is_locked": e.is_locked,
                    "key_vnum": e.key_vnum,
                }
            )
            for e in exits
            if e.room_id == room.id
        }
        entry = _clean(
            {
                "vnum": room.vnum,
                "name": room.name,
                "description": room.description,
                "sector_type": SectorType(room.sector_type).name,
                "flags": list(room.flags),
                "heal_rate": room.heal_rate,
                "mana_rate": room.mana_rate,
                "clan_id": room.clan_id,
                "owner": room.owner,
            }
        )
        if room_exits:
            entry["exits"] = room_exits
        room_extras = [{"keywords": x.keywords, "text": x.text} for x in extras if x.room_id == room.id]
        if room_extras:
            entry["extra_descriptions"] = room_extras
        out.append(entry)
    return out


def mob_dict(mob: Any) -> dict[str, Any]:
    """Un mob come voce di `mobs.yaml` (dadi nella notazione `XdY+Z`)."""
    return _clean(
        {
            "vnum": mob.vnum,
            "keywords": mob.keywords,
            "short_description": mob.short_description,
            "long_description": mob.long_description,
            "detailed_description": mob.detailed_description,
            "level": mob.level,
            "thac0": mob.thac0,
            "armor_class": mob.armor_class,
            "hp_dice": f"{mob.hp_dice_count}d{mob.hp_die_size}+{mob.hp_bonus}",
            "damage_dice": f"{mob.damage_dice_count}d{mob.damage_die_size}+{mob.damage_bonus}",
            "gold": mob.gold,
            "experience": mob.experience,
            "sex": Sex(mob.sex).name,
            "flags": list(mob.flags),
            "alignment": mob.alignment,
            "race_id": mob.race_id,
            "class_id": mob.class_id,
            "debuff_skill_id": mob.debuff_skill_id,
            "shop_id": mob.shop_id,
            "quest_ids": list(mob.quest_ids),
            "is_banker": mob.is_banker,
            "teaches_class_ids": list(mob.teaches_class_ids) if mob.teaches_class_ids is not None else None,
            "teaches_skill_ids": list(mob.teaches_skill_ids) if mob.teaches_skill_ids is not None else None,
        }
    )


def object_dict(obj: Any) -> dict[str, Any]:
    """Un prototipo di oggetto come voce di `objects.yaml`."""
    return _clean(
        {
            "vnum": obj.vnum,
            "keywords": obj.keywords,
            "short_description": obj.short_description,
            "long_description": obj.long_description,
            "action_description": obj.action_description,
            "object_type": ObjectType(obj.object_type).name,
            "weight": obj.weight,
            "cost": obj.cost,
            "rent": obj.rent,
            "value_0": obj.value_0,
            "value_1": obj.value_1,
            "value_2": obj.value_2,
            "value_3": obj.value_3,
            "extra_flags": list(obj.extra_flags),
            "wear_flags": list(obj.wear_flags),
            "affects": dict(obj.affects),
        }
    )


def reset_dict(cmd: Any) -> dict[str, Any]:
    """Un comando di reset come voce di `resets.yaml` (inverso di `importer.reset_args`)."""
    kind = ZoneCommandType(cmd.command_type)
    base: dict[str, Any] = {"type": kind.name}
    if cmd.if_flag:
        base["if_flag"] = True
    if kind == ZoneCommandType.LOAD_MOB:
        extra = {"mob_vnum": cmd.arg1, "max_existing": cmd.arg2, "room_vnum": cmd.arg3, "room_limit": cmd.arg4}
    elif kind == ZoneCommandType.LOAD_OBJECT:
        extra = {"obj_vnum": cmd.arg1, "max_existing": cmd.arg2, "room_vnum": cmd.arg3, "room_limit": cmd.arg4}
    elif kind == ZoneCommandType.GIVE_OBJECT:
        extra = {"obj_vnum": cmd.arg1, "max_existing": cmd.arg2}
    elif kind == ZoneCommandType.EQUIP_OBJECT:
        extra = {"obj_vnum": cmd.arg1, "max_existing": cmd.arg2, "wear_slot": cmd.arg_str}
    elif kind == ZoneCommandType.PUT_OBJECT:
        extra = {"obj_vnum": cmd.arg1, "max_existing": cmd.arg2, "container_vnum": cmd.arg3}
    elif kind == ZoneCommandType.SET_DOOR_STATE:
        direction = Direction(cmd.arg2).name if cmd.arg2 is not None else None
        extra = {"room_vnum": cmd.arg1, "direction": direction, "state": cmd.arg_str}
    else:  # RANDOMIZE_EXITS
        extra = {"room_vnum": cmd.arg1}
    return {**base, **_clean(extra)}


class ZoneSnapshot:
    """Lo stato di una zona nel DB, nella forma dei file YAML."""

    def __init__(
        self,
        zone: dict[str, Any],
        rooms: list[dict[str, Any]],
        mobs: list[dict[str, Any]],
        objects: list[dict[str, Any]],
        resets: list[dict[str, Any]],
    ) -> None:
        """Memorizza le cinque sezioni."""
        self.zone = zone
        self.rooms = rooms
        self.mobs = mobs
        self.objects = objects
        self.resets = resets

    def texts(self) -> dict[str, str]:
        """I cinque file YAML come testo, nell'ordine di `ZONE_FILES`."""
        return {
            "zone.yaml": dump_yaml(self.zone),
            "rooms.yaml": dump_yaml({"rooms": self.rooms}),
            "mobs.yaml": dump_yaml({"mobs": self.mobs}),
            "objects.yaml": dump_yaml({"objects": self.objects}),
            "resets.yaml": dump_yaml({"resets": self.resets}),
        }


async def snapshot_zone(session: AsyncSession, zone: Any) -> ZoneSnapshot:
    """Legge dal DB tutto il contenuto di `zone`."""
    m = models_of(session)
    rooms = (await session.execute(select(m.Room).where(m.Room.zone_id == zone.id))).scalars().all()
    mobs = (
        (await session.execute(select(m.MobPrototype).where(m.MobPrototype.zone_id == zone.id).order_by(m.MobPrototype.vnum)))
        .scalars()
        .all()
    )
    objects = (
        (await session.execute(select(m.ObjectPrototype).where(m.ObjectPrototype.zone_id == zone.id).order_by(m.ObjectPrototype.vnum)))
        .scalars()
        .all()
    )
    resets = (
        (
            await session.execute(
                select(m.ZoneResetCommand).where(m.ZoneResetCommand.zone_id == zone.id).order_by(m.ZoneResetCommand.order_index)
            )
        )
        .scalars()
        .all()
    )
    return ZoneSnapshot(
        zone=zone_dict(zone),
        rooms=await room_dicts(session, list(rooms)),
        mobs=[mob_dict(x) for x in mobs],
        objects=[object_dict(x) for x in objects],
        resets=[reset_dict(x) for x in resets],
    )


class _Dumper(yaml.SafeDumper):
    """Dumper che scrive le stringhe multilinea come blocchi letterali `|` (come i file scritti a mano)."""


def _represent_str(dumper: yaml.SafeDumper, value: str) -> yaml.ScalarNode:
    """Stringhe con a-capo -> blocco letterale; le altre restano scalari normali."""
    style = "|" if "\n" in value else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


_Dumper.add_representer(str, _represent_str)


def dump_yaml(data: dict[str, Any]) -> str:
    """Serializza `data` in YAML (UTF-8, ordine delle chiavi preservato, righe non spezzate)."""
    return "---\n" + yaml.dump(data, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=10_000, indent=2)
