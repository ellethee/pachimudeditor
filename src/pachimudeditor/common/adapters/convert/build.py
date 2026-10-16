"""Costruzione del contenuto da scrivere: conversione di ogni entita', controllo dei riferimenti, nuovi vnum.

Fasi (nessuna scrittura):

1. ogni entita' passa dal `PairConverter` (le entita' che non passano la validazione dei DTO di arrivo vengono
   scartate con una perdita `entity_invalid`);
2. tabella di rimappatura `vnum sorgente -> vnum di arrivo` delle entita' sopravvissute;
3. riferimenti (destinazione e chiave delle uscite, argomenti dei reset) risolti con la tabella, oppure -- fuori dalla
   conversione -- verso entita' che esistono gia' nell'arrivo; se non si risolvono l'uscita/il comando e' scartato;
4. un comando che dipende da uno scartato (G/E/H/F/Z dopo un mob scartato, `ifFlag` dopo un comando scartato) cade a
   sua volta.
"""

from dataclasses import dataclass, field

from pachimudeditor.common.enums import ZoneCommandType
from pachimudeditor.common.enums import DoorFlag
from pydantic import ValidationError

from pachimudeditor.common.adapters.convert.converter import ConvertContext, Converted, PairConverter, loss
from pachimudeditor.common.adapters.convert.models import ConvertPlan, LossItem
from pachimudeditor.common.adapters.convert.planner import ZonePlan
from pachimudeditor.common.adapters.convert.reader import TargetIndex
from pachimudeditor.common.adapters.convert.remap import ACTS_ON_LAST_MOB, LOADS_MOB, remap_reset
from pachimudeditor.common.adapters.models import (
    EntityKind,
    ExitIn,
    ExtraDescriptionIn,
    MobIn,
    ObjectIn,
    ResetCommandIn,
    RoomIn,
    ZoneIn,
)

ENTITIES = ("zones", "rooms", "mobs", "objects", "exits", "extraDescriptions", "resets")


@dataclass
class ExitW:
    """Un'uscita da creare: `room_vnum` e `target_vnum` sono vnum **di arrivo**."""

    room_vnum: int
    data: ExitIn
    target_vnum: int | None


@dataclass
class RoomW:
    """Una stanza da creare con le sue extra description."""

    data: RoomIn
    extras: list[ExtraDescriptionIn] = field(default_factory=list)


@dataclass
class ZoneW:
    """Tutto cio' che va scritto per una zona."""

    plan: ZonePlan
    zone_in: ZoneIn
    rooms: list[RoomW] = field(default_factory=list)
    exits: list[ExitW] = field(default_factory=list)
    mobs: list[MobIn] = field(default_factory=list)
    objects: list[ObjectIn] = field(default_factory=list)
    resets: list[ResetCommandIn] | None = None
    """`None` = non toccare lo script (`convertResets` falso)."""
    counts: dict[str, int] = field(default_factory=dict)


@dataclass
class BuildResult:
    """Esito della costruzione."""

    writes: list[ZoneW] = field(default_factory=list)
    remap: dict[str, dict[int, int]] = field(default_factory=lambda: {"rooms": {}, "mobs": {}, "objects": {}})
    losses: list[LossItem] = field(default_factory=list)
    dropped: dict[str, int] = field(default_factory=dict)
    """Entita' sorgente scartate, per tipo (`rooms`, `mobs`, ...)."""


def _tag(items: list[LossItem], zone_vnum: int, vnum: int | None = None, index: int | None = None) -> list[LossItem]:
    """Le perdite con zona sorgente, vnum e posizione impostati."""
    return [i.model_copy(update={"zone_vnum": zone_vnum, "vnum": vnum, "index": index}) for i in items]


def _safe(fn, *args):  # type: ignore[no-untyped-def]
    """Esegue un metodo del convertitore: una `ValidationError` diventa `Converted(None, [entity_invalid])`."""
    try:
        return fn(*args)
    except (ValidationError, ValueError) as error:
        detail = error.errors()[0] if isinstance(error, ValidationError) else {"loc": (), "msg": str(error)}
        where = ".".join(str(p) for p in detail["loc"])
        return Converted(None, [loss("zone", where or "-", "entity_invalid", "dropped", detail=f"{where}: {detail['msg']}"[:200])])


def build(
    plans: list[ZonePlan],
    converter: PairConverter,
    ctx: ConvertContext,
    index: TargetIndex,
    plan: ConvertPlan,
) -> BuildResult:
    """Converte le zone `create`/`replace` di `plans` (vedi docstring del modulo)."""
    result = BuildResult()
    written = [p for p in plans if p.written]
    skipped_vnums = {  # vnum sorgente (tipo, vnum) delle zone non scritte: i riferimenti verso di loro non si risolvono
        (kind, v.vnum): p for p in plans if p.action == "blocked" for kind, items in _contents(p) for v in items
    }
    pre: list[_Pre] = []
    for zp in written:
        pre.append(_convert_zone(zp, converter, ctx, plan, result))
    for item in pre:
        for kind, vnums in item.kept.items():
            result.remap[kind].update({v: v + item.zp.offset for v in vnums})

    replaced = {p.existing.id for p in written if p.action == "replace" and p.existing is not None}

    def resolve(kind: EntityKind, vnum: int) -> int | None:
        """Vnum di arrivo di un riferimento sorgente (None = non esiste ne' verra' creato)."""
        table = result.remap[{"room": "rooms", "mob": "mobs", "object": "objects"}[kind]]
        if vnum in table:
            return table[vnum]
        if (kind, vnum) in skipped_vnums:
            return None
        owner = {"room": lambda: (index.rooms.get(vnum) or (None, None))[1], "mob": lambda: index.mobs.get(vnum),
                 "object": lambda: index.objects.get(vnum)}[kind]()  # fmt: skip
        return vnum if owner is not None and owner not in replaced else None

    for item in pre:
        _finalize_zone(item, resolve, plan, converter, result, index)
    return result


def _contents(zp: ZonePlan) -> list[tuple[str, list]]:  # type: ignore[type-arg]
    """`(tipo, elementi)` del contenuto sorgente di una zona."""
    return [("room", zp.src.rooms), ("mob", zp.src.mobs), ("object", zp.src.objects)]


@dataclass
class _Pre:
    """Una zona dopo la conversione, prima dei riferimenti."""

    zp: ZonePlan
    zone_in: ZoneIn
    rooms: list[tuple[int, RoomIn, list[tuple[int, ExitIn, int | None]], list[ExtraDescriptionIn]]]
    mobs: list[MobIn]
    objects: list[ObjectIn]
    resets: list[tuple[int, int, ResetCommandIn | None]]
    """`(indice sorgente, tipo di comando sorgente, comando convertito o None)`."""
    kept: dict[str, list[int]]


def _convert_zone(zp: ZonePlan, converter: PairConverter, ctx: ConvertContext, plan: ConvertPlan, out: BuildResult) -> _Pre:
    """Fase 1: conversione per entita' (vnum ancora sorgente)."""
    src, zv = zp.src, zp.src.zone.vnum

    def drop(kind: str) -> None:
        """Conta un'entita' scartata."""
        out.dropped[kind] = out.dropped.get(kind, 0) + 1

    zone = _safe(converter.zone, src.zone, ctx)
    out.losses += _tag(zone.losses, zv)
    zone_in = zone.value or ZoneIn(vnum=0, name=src.zone.name)
    zone_in = zone_in.model_copy(update={"vnum": zp.target_vnum, "bottom_vnum": zp.bottom, "top_vnum": zp.top})

    rooms: list = []
    for room in src.rooms:
        conv = _safe(converter.room, room, ctx)
        out.losses += _tag(_retarget(conv.losses, "room"), zv, room.vnum)
        if conv.value is None:
            drop("rooms")
            continue
        exits = []
        if plan.convert_exits:
            for ex in room.exits:
                ec = _safe(converter.exit, ex, ctx)
                out.losses += _tag(_retarget(ec.losses, "exit"), zv, room.vnum)
                if ec.value is None:
                    drop("exits")
                else:
                    exits.append((ex.direction, ec.value, ex.target_room_vnum))
        extras = []
        if plan.convert_extra_descriptions:
            for ed in room.extra_descriptions:
                try:
                    extras.append(ExtraDescriptionIn(keywords=ed.keywords, text=ed.text))
                except ValidationError:
                    out.losses += _tag(
                        [loss("extra_description", "text", "entity_invalid", "dropped", detail="testo vuoto")], zv, room.vnum
                    )
                    drop("extraDescriptions")
        rooms.append((room.vnum, conv.value, exits, extras))

    mobs: list[MobIn] = []
    for mob in src.mobs:
        conv = _safe(converter.mob, mob, ctx)
        out.losses += _tag(_retarget(conv.losses, "mob"), zv, mob.vnum)
        if conv.value is None:
            drop("mobs")
        else:
            mobs.append(conv.value)
    objects: list[ObjectIn] = []
    for obj in src.objects:
        conv = _safe(converter.object, obj, ctx)
        out.losses += _tag(_retarget(conv.losses, "object"), zv, obj.vnum)
        if conv.value is None:
            drop("objects")
        else:
            objects.append(conv.value)

    resets: list = []
    if plan.convert_resets:
        for i, cmd in enumerate(src.resets):
            conv = _safe(converter.reset, cmd, ctx)
            out.losses += _tag(_retarget(conv.losses, "reset"), zv, None, i)
            resets.append((i, int(cmd.command_type), conv.value))
    kept = {"rooms": [r[0] for r in rooms], "mobs": [m.vnum for m in mobs], "objects": [o.vnum for o in objects]}
    return _Pre(zp, zone_in, rooms, mobs, objects, resets, kept)


def _retarget(items: list[LossItem], entity: str) -> list[LossItem]:
    """Le perdite di `_safe` nascono con entita' `zone`: le attribuisce all'entita' che si stava convertendo."""
    return [i.model_copy(update={"entity": entity}) if i.code == "entity_invalid" else i for i in items]


def _finalize_zone(item: _Pre, resolve, plan: ConvertPlan, converter: PairConverter, out: BuildResult, index: TargetIndex) -> None:  # type: ignore[no-untyped-def]
    """Fasi 3-4: riferimenti, nuovi vnum, dipendenze dei reset."""
    zp = item.zp
    zv = zp.src.zone.vnum
    offset = zp.offset
    zw = ZoneW(plan=zp, zone_in=item.zone_in)

    for old_vnum, room_in, exits, extras in item.rooms:
        new_vnum = old_vnum + offset
        zw.rooms.append(RoomW(room_in.model_copy(update={"vnum": new_vnum}), extras))
        for direction, ex_in, target in exits:
            ex = _resolve_exit(ex_in, target, old_vnum, new_vnum, resolve, zv, out)
            if ex is not None:
                zw.exits.append(ExitW(new_vnum, ex[0], ex[1]))
    zw.mobs = [m.model_copy(update={"vnum": m.vnum + offset}) for m in item.mobs]
    zw.objects = [o.model_copy(update={"vnum": o.vnum + offset}) for o in item.objects]

    if plan.convert_resets:
        zw.resets = _finalize_resets(item.resets, resolve, zv, out)
        if converter.door_state_in_resets:
            zw.resets += _door_resets(zw, out, zv)
    zw.counts = {
        "rooms": len(zw.rooms),
        "mobs": len(zw.mobs),
        "objects": len(zw.objects),
        "exits": len(zw.exits),
        "extraDescriptions": sum(len(r.extras) for r in zw.rooms),
        "resets": len(zw.resets or []),
    }
    out.writes.append(zw)


def _resolve_exit(ex: ExitIn, target: int | None, old_room: int, new_room: int, resolve, zv: int, out: BuildResult):  # type: ignore[no-untyped-def]
    """`(uscita normalizzata, vnum di destinazione di arrivo)` oppure None se l'uscita va scartata."""
    values: dict = {}
    new_target: int | None = None
    if target is not None:
        new_target = resolve("room", target)
        if new_target is None:
            out.losses += _tag(
                [loss("exit", "targetRoom", "exit_target_outside", "dropped", direction=ex.direction.name, vnum=target)], zv, old_room
            )
            out.dropped["exits"] = out.dropped.get("exits", 0) + 1
            return None
        if new_target == new_room:
            out.losses += _tag([loss("exit", "targetRoom", "exit_self_loop", "dropped", direction=ex.direction.name)], zv, old_room)
            out.dropped["exits"] = out.dropped.get("exits", 0) + 1
            return None
    if ex.key_vnum is not None:
        key = resolve("object", ex.key_vnum)
        if key is None:
            out.losses += _tag(
                [loss("exit", "keyVnum", "exit_key_missing", "warning", direction=ex.direction.name, vnum=ex.key_vnum)], zv, old_room
            )
        values["key_vnum"] = key
    final = ex.model_copy(update=values)
    if final.door_flag == DoorFlag.NONE and (not final.is_open or final.is_locked):
        final = final.model_copy(update={"is_open": True, "is_locked": False})
    if final.is_locked and final.key_vnum is None:
        out.losses += _tag([loss("exit", "isLocked", "exit_locked_no_key", "warning", direction=ex.direction.name)], zv, old_room)
        final = final.model_copy(update={"is_locked": False, "is_open": False})
    return final, new_target


def _finalize_resets(items: list, resolve, zv: int, out: BuildResult) -> list[ResetCommandIn]:  # type: ignore[no-untyped-def, type-arg]
    """Riferimenti e dipendenze di uno script (vedi docstring del modulo)."""
    kept: list[ResetCommandIn] = []
    prev_dropped = False
    last_mob_ok = False

    def lose(index: int, code: str, **params: object) -> None:
        """Scarta il comando `index` con una perdita."""
        out.losses.extend(_tag([loss("reset", "command", code, "dropped", **params)], zv, None, index))
        out.dropped["resets"] = out.dropped.get("resets", 0) + 1

    for index, src_type, cmd in items:
        if cmd is None:
            # il convertitore l'ha gia' motivato con una sua perdita
            out.dropped["resets"] = out.dropped.get("resets", 0) + 1
            prev_dropped = True
            if src_type in LOADS_MOB:
                last_mob_ok = False
            continue
        if cmd.if_flag and prev_dropped:
            lose(index, "reset_dependent")
            prev_dropped = True
            continue
        if src_type in ACTS_ON_LAST_MOB and not last_mob_ok:
            lose(index, "reset_orphan")
            prev_dropped = True
            continue
        fixed, missing = remap_reset(cmd, resolve)
        if fixed is None:
            arg, kind, vnum = missing[0]
            lose(index, "reset_unknown_ref", kind=kind, vnum=vnum, arg=arg)
            prev_dropped = True
            if src_type in LOADS_MOB:
                last_mob_ok = False
            continue
        prev_dropped = False
        if src_type in LOADS_MOB:
            last_mob_ok = True
        kept.append(fixed)
    return kept


def _door_resets(zw: ZoneW, out: BuildResult, zv: int) -> list[ResetCommandIn]:
    """Un `D` per ogni porta chiusa/serrata che lo script non copre (per i mondi che tengono lo stato nei reset)."""
    covered = {(c.arg1, c.arg2) for c in zw.resets or [] if c.command_type == ZoneCommandType.SET_DOOR_STATE}
    added: list[ResetCommandIn] = []
    for ex in zw.exits:
        if ex.data.door_flag != DoorFlag.NONE and (not ex.data.is_open or ex.data.is_locked):
            key = (ex.room_vnum, int(ex.data.direction))
            if key not in covered:
                covered.add(key)
                state = "LOCKED" if ex.data.is_locked else "CLOSED"
                added.append(ResetCommandIn(command_type=ZoneCommandType.SET_DOOR_STATE, arg1=key[0], arg2=key[1], arg_str=state))
    if added:
        out.losses += _tag([loss("reset", "script", "door_resets_added", "info", count=len(added))], zv)
    return added
