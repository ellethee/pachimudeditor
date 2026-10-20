"""Scrittura sul mondo di arrivo (solo tramite `WorldAdapter`) con tracciamento di cio' che e' stato creato.

Ordine: zona, stanze (con extra description), oggetti, mob per **tutte** le zone; poi le uscite (due passate: le
destinazioni possono stare in un'altra zona); infine gli script di reset. Con `replace` la zona esistente viene
prima svuotata (reset, stanze, mob, oggetti) dopo averne fatto un'istantanea.

Rollback: se un passo fallisce si annullano, in ordine inverso, le creazioni di questa esecuzione; le zone
`replace` vengono riportate allo stato dell'istantanea (stanze, mob, oggetti e reset ricreati, uscite verso
l'esterno comprese; le uscite *entranti* da altre zone, azzerate dalla cancellazione, non sono ripristinabili).
"""

from collections.abc import Awaitable
from dataclasses import dataclass, field

from fastapi import HTTPException

from pachimudeditor.common.adapters.base import WorldAdapter
from pachimudeditor.common.adapters.convert.build import ExitW, RoomW, ZoneW
from pachimudeditor.common.adapters.convert.models import ReportError
from pachimudeditor.common.adapters.convert.reader import SourceZone, TargetIndex, read_zone
from pachimudeditor.common.adapters.models import (
    ExitIn,
    ExtraDescriptionIn,
    MobIn,
    ObjectIn,
    ResetCommandIn,
    ResetScriptIn,
    RoomIn,
    ZoneIn,
    ZoneOut,
    ZonePatch,
)


@dataclass
class Created:
    """Cio' che questa esecuzione ha creato (per il rollback) e gli id di arrivo."""

    zones: list[int] = field(default_factory=list)
    rooms: list[int] = field(default_factory=list)
    mobs: list[int] = field(default_factory=list)
    objects: list[int] = field(default_factory=list)
    touched: list[tuple[int, SourceZone | None]] = field(default_factory=list)
    """`(id zona di arrivo, istantanea)` per ogni zona toccata, in ordine; istantanea `None` = zona creata."""
    room_ids: dict[int, int] = field(default_factory=dict)
    """vnum di arrivo -> id stanza (create ora)."""
    zone_ids: dict[int, int] = field(default_factory=dict)
    """vnum zona sorgente -> id zona di arrivo."""


def _patch_for(old: ZoneOut, new: ZoneIn) -> ZonePatch:
    """Il patch che porta `old` a `new` con i soli campi diversi (alcuni mondi ne vietano la modifica)."""
    names = ("name", "builder", "bottom_vnum", "top_vnum", "min_level", "max_level", "lifespan_minutes", "reset_mode", "enabled")
    return ZonePatch(**{n: getattr(new, n) for n in names if getattr(new, n) != getattr(old, n)})


def _room_id(vnum: int, created: Created, index: TargetIndex) -> int | None:
    """Id (nel mondo di arrivo) della stanza con quel vnum: creata ora oppure gia' esistente."""
    if vnum in created.room_ids:
        return created.room_ids[vnum]
    found = index.rooms.get(vnum)
    return found[0] if found else None


async def clear_zone(target: WorldAdapter, snap: SourceZone) -> None:
    """Svuota una zona: reset, stanze (con le uscite), mob, oggetti."""
    zid = snap.zone.id
    await target.replace_reset_commands(zid, ResetScriptIn(commands=[]))
    for room in snap.rooms:
        await target.delete_room(room.id)
    for mob in snap.mobs:
        await target.delete_mob(mob.id)
    for obj in snap.objects:
        await target.delete_object(obj.id)


async def write_content(target: WorldAdapter, zw: ZoneW, zone_id: int, created: Created) -> None:
    """Fase A di una zona: stanze (con extra description), oggetti e mob."""
    for room in zw.rooms:
        made = await target.create_room(room.data.model_copy(update={"zone_id": zone_id}))
        created.rooms.append(made.id)
        created.room_ids[made.vnum] = made.id
        for extra in room.extras:
            await target.create_extra_description(made.id, extra)
    for obj in zw.objects:
        made_obj = await target.create_object(obj.model_copy(update={"zone_id": zone_id}))
        created.objects.append(made_obj.id)
    for mob in zw.mobs:
        made_mob = await target.create_mob(mob.model_copy(update={"zone_id": zone_id}))
        created.mobs.append(made_mob.id)


async def write_exits(target: WorldAdapter, zw: ZoneW, created: Created, index: TargetIndex) -> None:
    """Fase B: le uscite (tutte le stanze di arrivo esistono gia')."""
    for ex in zw.exits:
        room_id = created.room_ids[ex.room_vnum]
        dest = _room_id(ex.target_vnum, created, index) if ex.target_vnum is not None else None
        await target.create_exit(room_id, ex.data.model_copy(update={"target_room_id": dest}))


async def write_all(target: WorldAdapter, writes: list[ZoneW], created: Created, index: TargetIndex) -> None:
    """Esegue le tre fasi su tutte le zone (solleva al primo errore: il chiamante fa il rollback)."""
    for zw in writes:
        zp = zw.plan
        if zp.action == "replace" and zp.existing is not None:
            snap = await read_zone(target, zp.existing.id)
            created.touched.append((zp.existing.id, snap))
            await clear_zone(target, snap)
            patch = _patch_for(zp.existing, zw.zone_in)
            zone_id = zp.existing.id
            if patch.model_fields_set:
                await target.update_zone(zone_id, patch)
        else:
            made = await target.create_zone(zw.zone_in)
            created.zones.append(made.id)
            created.touched.append((made.id, None))
            zone_id = made.id
        created.zone_ids[zp.src.zone.vnum] = zone_id
        await write_content(target, zw, zone_id, created)
    for zw in writes:
        await write_exits(target, zw, created, index)
    for zw in writes:
        if zw.resets is not None:
            await target.replace_reset_commands(created.zone_ids[zw.plan.src.zone.vnum], ResetScriptIn(commands=zw.resets))


def error_of(error: Exception, what: str) -> ReportError:
    """Un `ReportError` da un'eccezione (codice stabile se e' un `HTTPException` dell'editor)."""
    if isinstance(error, HTTPException) and isinstance(error.detail, list) and error.detail:
        first = error.detail[0]
        return ReportError(code=str(first.get("code") or "http.error"), params={"step": what, "msg": str(first.get("msg", ""))[:200]})
    return ReportError(code="convert.write_failed", params={"step": what, "msg": str(error)[:200]})


async def rollback(target: WorldAdapter, created: Created, index: TargetIndex) -> list[ReportError]:
    """Annulla le creazioni (ordine inverso) e ripristina le zone `replace`; restituisce gli errori incontrati."""
    errors: list[ReportError] = []

    async def attempt(what: str, call: Awaitable[object]) -> None:
        """Esegue un passo di rollback registrando l'errore senza interrompersi."""
        try:
            await call
        except Exception as error:  # noqa: BLE001  (best effort: si prosegue)
            errors.append(error_of(error, what))

    for zone_id, _ in reversed(created.touched):
        await attempt("clear_resets", target.replace_reset_commands(zone_id, ResetScriptIn(commands=[])))
    for room_id in reversed(created.rooms):
        await attempt("delete_room", target.delete_room(room_id))
    for mob_id in reversed(created.mobs):
        await attempt("delete_mob", target.delete_mob(mob_id))
    for obj_id in reversed(created.objects):
        await attempt("delete_object", target.delete_object(obj_id))
    for zone_id in reversed(created.zones):
        await attempt("delete_zone", target.delete_zone(zone_id))
    for zone_id, snap in reversed(created.touched):
        if snap is not None:
            await attempt("restore_zone", _restore(target, zone_id, snap, index))
    return errors


async def _restore(target: WorldAdapter, zone_id: int, snap: SourceZone, index: TargetIndex) -> None:
    """Ricrea il contenuto dell'istantanea di una zona `replace` (stessi vnum, `extra` compreso)."""
    old = snap.zone
    current = await target.get_zone(zone_id)
    zone_in = ZoneIn(
        vnum=old.vnum, name=old.name, builder=old.builder, bottom_vnum=old.bottom_vnum, top_vnum=old.top_vnum,
        min_level=old.min_level, max_level=old.max_level, lifespan_minutes=old.lifespan_minutes,
        reset_mode=old.reset_mode, enabled=old.enabled,
    )  # fmt: skip
    patch = _patch_for(current, zone_in)
    if patch.model_fields_set:
        await target.update_zone(zone_id, patch)
    created = Created()
    zw = ZoneW(plan=None, zone_in=zone_in)  # type: ignore[arg-type]
    for r in snap.rooms:
        data = RoomIn(
            vnum=r.vnum, zone_id=zone_id, name=r.name, description=r.description, sector_type=r.sector_type,
            flags=r.flags, heal_rate=r.heal_rate, mana_rate=r.mana_rate, clan_id=r.clan_id, owner=r.owner, extra=r.extra,
        )  # fmt: skip
        zw.rooms.append(RoomW(data, [ExtraDescriptionIn(keywords=e.keywords, text=e.text) for e in r.extra_descriptions]))
        for e in r.exits:
            zw.exits.append(
                ExitW(
                    r.vnum,
                    ExitIn(direction=e.direction, description=e.description, keywords=e.keywords, door_flag=e.door_flag,
                           is_open=e.is_open, is_locked=e.is_locked, key_vnum=e.key_vnum),
                    e.target_room_vnum,
                )
            )  # fmt: skip
    zw.objects = [ObjectIn(**{**o.model_dump(by_alias=False, exclude={"id"}), "zone_id": zone_id}) for o in snap.objects]
    zw.mobs = [MobIn(**{**m.model_dump(by_alias=False, exclude={"id"}), "zone_id": zone_id}) for m in snap.mobs]
    await write_content(target, zw, zone_id, created)
    for ex in zw.exits:
        dest = _room_id(ex.target_vnum, created, index) if ex.target_vnum is not None else None
        await target.create_exit(created.room_ids[ex.room_vnum], ex.data.model_copy(update={"target_room_id": dest}))
    cmds = [
        ResetCommandIn(
            command_type=c.command_type, if_flag=c.if_flag, arg1=c.arg1, arg2=c.arg2, arg3=c.arg3, arg4=c.arg4,
            arg_str=c.arg_str, if_value=c.if_value, comment=c.comment, extra=c.extra,
        )
        for c in snap.resets
    ]  # fmt: skip
    if cmds:
        await target.replace_reset_commands(zone_id, ResetScriptIn(commands=cmds))
