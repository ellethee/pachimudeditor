"""Controlli di integrita' del mondo (il gioco non segnala nulla: uscite verso stanze inesistenti, reset con vnum morti,
vnum duplicate...). Usati dalla panoramica (`/api/world/overview`, warning con `kind` stabile) e da `worlds check`."""

from dataclasses import dataclass, field

from pachimudeditor.common.enums import Direction, ZoneCommandType
from pachimudeditor_adapter_pachimud import resets
from pachimudeditor_adapter_pachimud.store import Item, Kind, YamlStore, ZoneEntry

LOAD_TYPES = (ZoneCommandType.LOAD_OBJECT, ZoneCommandType.GIVE_OBJECT, ZoneCommandType.EQUIP_OBJECT, ZoneCommandType.PUT_OBJECT)


@dataclass(eq=False)
class Warn:
    """Un problema: `kind` stabile, entita' da aprire (`vnum` = id), zona proprietaria e parametri interi."""

    kind: str
    entity_type: str
    vnum: int
    name: str
    zone: ZoneEntry
    params: dict[str, int] = field(default_factory=dict)


def _name(item: Item) -> str:
    """Il nome mostrato di una voce."""
    return item.model.name if item.kind == "room" else item.model.short_description


def collect(store: YamlStore) -> list[Warn]:
    """Tutti i problemi di qualita' dei dati (ordine: zona, tipo, vnum)."""
    out: list[Warn] = []
    rooms, mobs, objects = store.vnums("room"), store.vnums("mob"), store.vnums("object")
    scripts = {z.vnum: resets.flatten(z) for z in store.zones}
    loaded_mobs = {c[1] for cs in scripts.values() for c in cs if c[0] is ZoneCommandType.LOAD_MOB}
    loaded_objects = {c[1] for cs in scripts.values() for c in cs if c[0] in LOAD_TYPES} | {
        c[3] for cs in scripts.values() for c in cs if c[0] is ZoneCommandType.PUT_OBJECT
    }
    for zone in store.zones:
        m = zone.model
        commands = scripts[zone.vnum]
        if not commands and (zone.items["mob"] or zone.items["object"]):
            out.append(Warn("zone_empty_reset_script", "zone", m.vnum, m.name, zone))
        for index, (t, a1, a2, a3, _a4, _s) in enumerate(commands):
            refs: list[tuple[str, int | None]] = []
            if t is ZoneCommandType.LOAD_MOB:
                refs = [("mob", a1), ("room", a3)]
            elif t is ZoneCommandType.LOAD_OBJECT:
                refs = [("object", a1), ("room", a3)]
            elif t in (ZoneCommandType.GIVE_OBJECT, ZoneCommandType.EQUIP_OBJECT):
                refs = [("object", a1)]
            elif t is ZoneCommandType.PUT_OBJECT:
                refs = [("object", a1), ("object", a3)]
            elif t is ZoneCommandType.SET_DOOR_STATE:
                refs = [("room", a1)]
            known = {"room": rooms, "mob": mobs, "object": objects}
            out += [
                Warn(f"reset_unknown_{kind}", "zone", m.vnum, m.name, zone, {"vnum": vnum, "index": index})
                for kind, vnum in refs
                if vnum is not None and vnum not in known[kind]
            ]
        for item in zone.items["room"]:
            if not item.model.description.strip():
                out.append(Warn("room_empty_description", "room", item.vnum, _name(item), zone))
            for key, x in item.model.exits.items():
                direction = int(Direction[key.upper()])
                if x.target_vnum is None or x.target_vnum not in rooms:
                    out.append(Warn("exit_without_target", "room", item.vnum, _name(item), zone, {"direction": direction}))
                if x.key_vnum is not None and x.key_vnum not in objects:
                    out.append(Warn("exit_key_missing", "room", item.vnum, _name(item), zone, {"direction": direction, "vnum": x.key_vnum}))
        for item in zone.items["object"]:
            key = getattr(item.model, "key_vnum", None)
            if key is not None and key not in objects:
                out.append(Warn("container_key_missing", "object", item.vnum, _name(item), zone, {"vnum": key}))
            if item.vnum not in loaded_objects:
                out.append(Warn("object_never_loaded", "object", item.vnum, _name(item), zone))
        for item in zone.items["mob"]:
            if item.vnum not in loaded_mobs:
                out.append(Warn("mob_never_loaded", "mob", item.vnum, _name(item), zone))
        if (m.bottom_vnum, m.top_vnum) != (0, 0):
            for kind in ("room", "mob", "object"):
                for item in zone.items[kind]:  # type: ignore[index]
                    if not m.bottom_vnum <= item.vnum <= m.top_vnum:
                        out.append(
                            Warn("vnum_out_of_range", kind, item.vnum, _name(item), zone, {"bottom": m.bottom_vnum, "top": m.top_vnum})
                        )
    for kind, vnum, zone in store.duplicates:
        first = store.find(kind, vnum)
        out.append(Warn("duplicate_vnum", kind, vnum, _name(first) if first else "", zone))
    return out


def kinds_total(warnings: list[Warn]) -> dict[str, int]:
    """Conteggio per `kind`."""
    totals: dict[str, int] = {}
    for w in warnings:
        totals[w.kind] = totals.get(w.kind, 0) + 1
    return totals


Kinds = Kind
