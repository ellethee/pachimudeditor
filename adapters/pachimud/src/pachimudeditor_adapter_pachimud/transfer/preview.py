"""Anteprima (dry-run) di un import di zona: confronto dei file validati con lo stato del DB, elemento per vnum.

Non scrive nulla. I file sono validati con gli schemi `Loader*` di questo pacchetto (copie di quelli del gioco);
l'applicazione dell'import e' in `importer.py`.
"""

from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pachimudeditor_adapter_pachimud.schema import models_of
from pachimudeditor_adapter_pachimud.transfer.files import chunks, mob_dict, object_dict, reset_dict, room_dicts, zone_dict
from pachimudeditor_adapter_pachimud.transfer.importer import ParsedZone
from pachimudeditor_adapter_pachimud.transfer.schemas import LoaderMob, LoaderObject, LoaderResetsFile, LoaderRoom, LoaderZone
from pachimudeditor.common.adapters.models import (
    Conflict,
    ImportPreview,
    ImportWarning,
    KindDiff,
    ResetDiff,
    VnumChange,
)

UNSUPPORTED_FILE_FIELDS: dict[str, tuple[str, str, str]] = {
    "mobs.race_id": ("mob_prototype", "race_id", "mobs"),
    "mobs.class_id": ("mob_prototype", "class_id", "mobs"),
    "rooms.heal_rate": ("room", "heal_rate", "rooms"),
    "rooms.mana_rate": ("room", "mana_rate", "rooms"),
    "rooms.clan_id": ("room", "clan_id", "rooms"),
    "rooms.owner": ("room", "owner", "rooms"),
    "zone.min_level": ("zone", "min_level", "zone"),
    "zone.max_level": ("zone", "max_level", "zone"),
}
"""Campi dei file senza colonna in uno schema piu' vecchio: se il file li valorizza, l'import li ignorerebbe (avviso)."""


def _norm(model: type[BaseModel], data: dict[str, Any]) -> dict[str, Any]:
    """Normalizza un dict con lo schema (default espliciti, enum in maiuscolo) per confrontare file e DB."""
    return model.model_validate(data).model_dump(mode="json")


def _classify(entries: list[BaseModel], existing: dict[int, dict[str, Any]], zone_vnums_in_db: set[int], name_of: str) -> KindDiff:
    """Confronta gli elementi del file (`entries`) con quelli del DB (`existing`, gia' normalizzati)."""
    diff = KindDiff()
    seen: set[int] = set()
    for entry in entries:
        vnum: int = getattr(entry, "vnum")
        seen.add(vnum)
        name = str(getattr(entry, name_of))
        if vnum not in existing:
            action = "create"
            diff.create += 1
        elif existing[vnum] == entry.model_dump(mode="json"):
            action = "unchanged"
            diff.unchanged += 1
        else:
            action = "update"
            diff.update += 1
        diff.items.append(VnumChange(vnum=vnum, name=name, action=action))
    diff.kept_not_in_file = sorted(zone_vnums_in_db - seen)
    return diff


def _norm_reset(data: dict[str, Any]) -> dict[str, Any]:
    """Un reset del DB normalizzato con lo schema del file."""
    return LoaderResetsFile.model_validate({"resets": [data]}).resets[0].model_dump(mode="json")


async def build_preview(session: AsyncSession, parsed: ParsedZone, race_ids: set[str] | None, class_ids: set[str] | None) -> ImportPreview:
    """Confronta i file validati con il DB, senza scrivere. Vedi `ImportPreview`."""
    m = models_of(session)
    zdata = parsed.zone
    db_zone = (await session.execute(select(m.Zone).where(m.Zone.vnum == zdata.vnum))).scalar_one_or_none()
    warnings: list[ImportWarning] = []
    conflicts: list[Conflict] = []

    if db_zone is None:
        zone_change = VnumChange(vnum=zdata.vnum, name=zdata.name, action="create")
    else:
        same = _norm(LoaderZone, zone_dict(db_zone) | {"zone_id": zdata.zone_id}) == zdata.model_dump(mode="json")
        zone_change = VnumChange(vnum=zdata.vnum, name=zdata.name, action="unchanged" if same else "update")
    db_zone_id = db_zone.id if db_zone is not None else None

    async def conflicts_for(model: Any, kind: str, vnums: list[int]) -> dict[int, Any]:
        """Righe esistenti con quei vnum; registra i conflitti con altre zone."""
        if not vnums:
            return {}
        rows = [r for part in chunks(vnums) for r in (await session.execute(select(model).where(model.vnum.in_(part)))).scalars()]
        by_vnum = {row.vnum: row for row in rows}
        other_ids = {row.zone_id for row in rows if row.zone_id != db_zone_id}
        zones = {}
        if other_ids:
            zones = {z.id: z for z in (await session.execute(select(m.Zone).where(m.Zone.id.in_(other_ids)))).scalars()}
        for row in rows:
            if row.zone_id != db_zone_id:
                other = zones[row.zone_id]
                conflicts.append(Conflict(kind=kind, vnum=row.vnum, zone_vnum=other.vnum, zone_name=other.name))
        return by_vnum

    async def zone_vnums(model: Any) -> set[int]:
        """I vnum della zona nel DB."""
        if db_zone_id is None:
            return set()
        return set((await session.execute(select(model.vnum).where(model.zone_id == db_zone_id))).scalars())

    rooms = parsed.rooms.rooms
    room_rows = await conflicts_for(m.Room, "room", [r.vnum for r in rooms])
    room_existing = {d["vnum"]: _norm(LoaderRoom, d) for d in await room_dicts(session, list(room_rows.values()))}
    rooms_diff = _classify(list(rooms), room_existing, await zone_vnums(m.Room), "name")

    mob_rows = await conflicts_for(m.MobPrototype, "mob", [x.vnum for x in parsed.mobs.mobs])
    mob_existing = {v: _norm(LoaderMob, mob_dict(x)) for v, x in mob_rows.items()}
    mobs_diff = _classify(list(parsed.mobs.mobs), mob_existing, await zone_vnums(m.MobPrototype), "short_description")

    obj_rows = await conflicts_for(m.ObjectPrototype, "object", [o.vnum for o in parsed.objects.objects])
    obj_existing = {v: _norm(LoaderObject, object_dict(o)) for v, o in obj_rows.items()}
    objs_diff = _classify(list(parsed.objects.objects), obj_existing, await zone_vnums(m.ObjectPrototype), "short_description")

    # reset: sostituiti per intero
    db_resets: list[dict[str, Any]] = []
    if db_zone_id is not None:
        cmds = (
            (
                await session.execute(
                    select(m.ZoneResetCommand).where(m.ZoneResetCommand.zone_id == db_zone_id).order_by(m.ZoneResetCommand.order_index)
                )
            )
            .scalars()
            .all()
        )
        db_resets = [_norm_reset(reset_dict(c)) for c in cmds]
    file_resets = [r.model_dump(mode="json") for r in parsed.resets.resets]
    resets_diff = ResetDiff(in_file=len(file_resets), in_db=len(db_resets), changed=file_resets != db_resets)

    await _collect_warnings(session, parsed, race_ids, class_ids, warnings)
    return ImportPreview(
        zone=zone_change,
        rooms=rooms_diff,
        mobs=mobs_diff,
        objects=objs_diff,
        resets=resets_diff,
        warnings=warnings,
        conflicts=conflicts,
    )


def _unsupported_warnings(session: AsyncSession, parsed: ParsedZone) -> list[ImportWarning]:
    """Avvisi per i campi dei file senza colonna nel DB (schema piu' vecchio) che il file valorizza: verrebbero ignorati."""
    m = models_of(session)
    defaults = {"rooms.heal_rate": 100, "rooms.mana_rate": 100, "zone.min_level": 1, "zone.max_level": 1}
    sources: dict[str, list[Any]] = {
        "mobs": list(parsed.mobs.mobs),
        "rooms": list(parsed.rooms.rooms),
        "zone": [parsed.zone],
    }
    out: list[ImportWarning] = []
    for key, (table, column, source) in UNSUPPORTED_FILE_FIELDS.items():
        if m.column(table, column) or not m.has(table):
            continue
        neutral = defaults.get(key)
        if any(getattr(item, column) != neutral for item in sources[source]):
            out.append(ImportWarning(code="unsupported_column", params={"table": table, "column": column}))
    return out


async def _collect_warnings(
    session: AsyncSession,
    parsed: ParsedZone,
    race_ids: set[str] | None,
    class_ids: set[str] | None,
    warnings: list[ImportWarning],
) -> None:
    """Riempie `warnings` con le incongruenze non bloccanti (range, riferimenti, razze/classi)."""
    m = models_of(session)
    zdata = parsed.zone
    file_rooms = {r.vnum for r in parsed.rooms.rooms}
    file_mobs = {x.vnum for x in parsed.mobs.mobs}
    file_objs = {o.vnum for o in parsed.objects.objects}

    async def known(model: Any, wanted: set[int], in_file: set[int]) -> set[int]:
        """I vnum di `wanted` che esistono nel file o nel DB."""
        missing = wanted - in_file
        if not missing:
            return in_file
        rows = {
            v for part in chunks(list(missing)) for v in (await session.execute(select(model.vnum).where(model.vnum.in_(part)))).scalars()
        }
        return in_file | rows

    for kind, vnums in (("room", file_rooms), ("mob", file_mobs), ("object", file_objs)):
        for vnum in sorted(vnums):
            if not zdata.bottom_vnum <= vnum <= zdata.top_vnum:
                warnings.append(ImportWarning(code="out_of_range", params={"kind": kind, "vnum": vnum}))
    if zdata.bottom_vnum > zdata.top_vnum:
        warnings.append(ImportWarning(code="invalid_range", params={"bottom": zdata.bottom_vnum, "top": zdata.top_vnum}))

    exit_targets = {e.target_vnum for r in parsed.rooms.rooms for e in r.exits.values() if e.target_vnum is not None}
    reset_rooms = {r.room_vnum for r in parsed.resets.resets if hasattr(r, "room_vnum")}
    exit_keys = {e.key_vnum for r in parsed.rooms.rooms for e in r.exits.values() if e.key_vnum is not None}
    all_rooms = await known(m.Room, exit_targets | reset_rooms, file_rooms)
    for room in parsed.rooms.rooms:
        for direction, ex in room.exits.items():
            if ex.target_vnum is not None and ex.target_vnum not in all_rooms:
                warnings.append(
                    ImportWarning(
                        code="dangling_exit", params={"room": room.vnum, "direction": direction.lower(), "target": ex.target_vnum}
                    )
                )

    ref_mobs = {getattr(r, "mob_vnum") for r in parsed.resets.resets if hasattr(r, "mob_vnum")}
    ref_objs = {getattr(r, "obj_vnum") for r in parsed.resets.resets if hasattr(r, "obj_vnum")}
    ref_objs |= {getattr(r, "container_vnum") for r in parsed.resets.resets if hasattr(r, "container_vnum")}
    all_mobs = await known(m.MobPrototype, ref_mobs, file_mobs)
    all_objs = await known(m.ObjectPrototype, ref_objs | exit_keys, file_objs)
    for index, reset in enumerate(parsed.resets.resets):
        for attr, pool, label in (
            ("room_vnum", all_rooms, "room"),
            ("mob_vnum", all_mobs, "mob"),
            ("obj_vnum", all_objs, "object"),
            ("container_vnum", all_objs, "object"),
        ):
            value = getattr(reset, attr, None)
            if value is not None and value not in pool:
                warnings.append(ImportWarning(code="unknown_reset_ref", params={"index": index, "kind": label, "vnum": value}))
    for room in parsed.rooms.rooms:
        for direction, ex in room.exits.items():
            if ex.key_vnum is not None and ex.key_vnum not in all_objs:
                warnings.append(
                    ImportWarning(code="unknown_key", params={"room": room.vnum, "direction": direction.lower(), "vnum": ex.key_vnum})
                )

    for mob in parsed.mobs.mobs:
        if race_ids is not None and mob.race_id is not None and mob.race_id not in race_ids:
            warnings.append(ImportWarning(code="unknown_race", params={"mob": mob.vnum, "id": mob.race_id}))
        if class_ids is not None and mob.class_id is not None and mob.class_id not in class_ids:
            warnings.append(ImportWarning(code="unknown_class", params={"mob": mob.vnum, "id": mob.class_id}))

    # sovrapposizione del range con un'altra zona
    others = (await session.execute(select(m.Zone).where(m.Zone.vnum != zdata.vnum))).scalars().all()
    for other in others:
        if zdata.bottom_vnum <= other.top_vnum and other.bottom_vnum <= zdata.top_vnum:
            warnings.append(ImportWarning(code="range_overlap", params={"zone": other.name, "zone_vnum": other.vnum}))
    warnings.extend(_unsupported_warnings(session, parsed))
