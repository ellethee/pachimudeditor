"""Sapore BasedMud (ROM, file `.are`): da/verso il pivot.

Decisioni (vedi `docs/conversion.md`):

- **AC**: ROM tiene l'AC x10 (`armorClass` = `ac[0]`, pierce); il pivot e' in scala piccola (come Diku Modificato e i dati di
  pachimud): `armorClass / 10` verso il pivot, `* 10` (su tutti e quattro i tipi) dal pivot.
- **flag**: i nomi ROM sono il vocabolario del pivot; quelli non ROM (da pachimud) si scartano; `npc` e `unused_*` sono impliciti.
- **settore**: gia' approssimato dall'adapter sulla enum di pachimud (`extra.sector` 8/10 segnalato).
- **mob**: negozio (`#SHOPS`), `spec_fun` (`#SPECIALS`), mobprog, affect/off/imm/res/vuln, form/parti, taglia, materiale,
  posizioni, gruppo e tipo di danno non esistono nel pivot: perdite `dropped`; `mana` e `ac[1..3]` si perdono.
- **oggetti**: i valori dipendono dal tipo (`helpers.rom_values_to_pivot`); `flagAffects`, `extraDescs`, `level`,
  `material`, `condition` si perdono; i tipi ROM senza equivalente sono gia' `OTHER` (con avviso).
- **reset**: gli argomenti sono gli stessi di pachimud (l'adapter li espone cosi'); `O` ha `max` 0 in ROM (ignorato dal
  gioco) e diventa "99 nel mondo, 1 per stanza"; gli slot di `E` passano dai nomi `wear_loc` ai nomi di flag.
"""

from pachimudeditor_adapter_basedmud.rom_lib.tables import FLAG_TABLES, TYPE_TABLES
from pachimudeditor.common.enums import ZoneCommandType, ZoneResetMode

from pachimudeditor_adapter_basedmud import convert_tables as local_tables
from pachimudeditor.sdk import convert_tables as tables
from pachimudeditor.sdk import Flavor
from pachimudeditor.common.adapters.convert.helpers import (
    UNLIMITED,
    map_affects,
    map_flags,
    neutral_mob_fields,
    norm_race,
    pick_race,
    pivot_values_to_rom,
    rom_values_to_pivot,
    unsupported_mob_losses,
)
from pachimudeditor.sdk import ConvertContext, Converted, loss, to_in
from pachimudeditor.common.adapters.models import (
    MobIn,
    MobOut,
    ObjectIn,
    ObjectOut,
    ResetCommandIn,
    ResetCommandOut,
    RoomIn,
    RoomOut,
    ZoneIn,
)


def rom_names(table: str) -> dict[str, str]:
    """I nomi di flag di una tabella ROM (senza i segnaposto `unused_*`) come tabella identita'."""
    return {name: name for name in FLAG_TABLES[table] if not name.startswith("unused")}


_ROOM = rom_names("room_flags")
_MOB = rom_names("mob_flags")
_EXTRA = rom_names("extra_flags")
_WEAR = rom_names("wear_flags")
_APPLY = {name: name for name in TYPE_TABLES["affect_apply_types"] if name != "none"}
_MOB_DROPPED_KEYS = {  # chiave di `extra` -> gravita' della perdita
    "shop": "dropped", "special": "dropped", "mprogs": "dropped", "affectedBy": "dropped", "offFlags": "dropped",
    "immFlags": "dropped", "resFlags": "dropped", "vulnFlags": "dropped", "flagRemovals": "info", "form": "info",
    "parts": "info", "size": "info", "material": "info", "startPos": "info", "defaultPos": "info", "group": "info",
    "damType": "info", "mana": "info", "ac": "info",
}  # fmt: skip


def _div10(value: int) -> int:
    """`value / 10` arrotondato al piu' vicino (mezzi lontano da zero)."""
    return int(value / 10 + (0.5 if value >= 0 else -0.5))


class BasedMudFlavor(Flavor):
    """Mondo BasedMud/ROM (`kind: basedmud`)."""

    kind = "basedmud"
    door_state_in_resets = True

    # ------------------------------------------------------------------ verso il pivot

    def room_to_pivot(self, r: RoomOut, ctx: ConvertContext) -> Converted[RoomIn]:
        """Stanza ROM -> pivot: flag filtrati sui nomi ROM, settore ROM 8/10 segnalato."""
        losses = []
        flags, fl = map_flags("room", "flags", r.flags, _ROOM)
        if r.extra.get("sector") in (8, 10):
            losses.append(loss("room", "sectorType", "sector_approximated", "info", sector=r.extra["sector"]))
        values = to_in(RoomIn, r, zone_id=0, flags=flags)
        return Converted(RoomIn(**values), [*fl, *losses])

    def mob_to_pivot(self, m: MobOut, ctx: ConvertContext) -> Converted[MobIn]:
        """Mob ROM -> pivot (vedi docstring del modulo)."""
        flags, losses = map_flags("mob", "flags", m.flags, _MOB, silent=tables.ACT_ROM_SILENT)
        race = norm_race(m.race_id)
        for key, severity in _MOB_DROPPED_KEYS.items():
            value = m.extra.get(key)
            if value not in (None, [], {}, "", 0, "none"):
                if key in ("shop", "special"):
                    losses.append(loss("mob", key, f"{key}_unsupported", severity, value=str(value)[:120]))
                elif severity == "dropped":
                    losses.append(loss("mob", key, "mob_flagset_dropped", severity, name=key, value=str(value)[:120]))
        minor = sorted(k for k, s in _MOB_DROPPED_KEYS.items() if s == "info" and m.extra.get(k) not in (None, [], {}, ""))
        if minor:
            losses.append(loss("mob", "extra", "extra_dropped", "info", keys=", ".join(minor)))
        values = to_in(MobIn, m, zone_id=0, flags=flags, race_id=race, armor_class=_div10(m.armor_class))
        return Converted(MobIn(**values), losses)

    def object_to_pivot(self, o: ObjectOut, ctx: ConvertContext) -> Converted[ObjectIn]:
        """Oggetto ROM -> pivot."""
        losses = []
        if o.extra.get("itemType") not in tables_item_known() and o.object_type.name == "OTHER":
            losses.append(loss("object", "objectType", "object_type_approximated", "warning", type=o.extra.get("itemType")))
        extra_flags, fl1 = map_flags("object", "extraFlags", o.extra_flags, _EXTRA)
        wear, fl2 = map_flags("object", "wearFlags", o.wear_flags, _WEAR)
        affects, fl3 = map_affects(o.affects, _APPLY)
        values, vl = rom_values_to_pivot(o)
        if o.extra.get("flagAffects"):
            losses.append(loss("object", "flagAffects", "object_flag_affects_dropped", "warning"))
        if o.extra.get("extraDescs"):
            losses.append(loss("object", "extraDescs", "object_extra_descs_dropped", "warning"))
        minor = [k for k in ("level", "material", "condition") if o.extra.get(k) not in (None, "", 0)]
        if minor:
            losses.append(loss("object", "extra", "extra_dropped", "info", keys=", ".join(minor)))
        v = dict(zip(("value_0", "value_1", "value_2", "value_3"), values))
        new = to_in(ObjectIn, o, zone_id=0, extra_flags=extra_flags, wear_flags=wear, affects=affects, **v)
        return Converted(ObjectIn(**new), [*losses, *fl1, *fl2, *fl3, *vl])

    def reset_to_pivot(self, c: ResetCommandOut, ctx: ConvertContext) -> Converted[ResetCommandIn]:
        """Reset ROM -> pivot: `O` come "99 nel mondo, 1 per stanza"; slot di `E` con i nomi dei flag."""
        losses = []
        v = to_in(ResetCommandIn, c, comment=None, if_value=None)
        t = c.command_type
        if t == ZoneCommandType.LOAD_OBJECT:
            v.update(arg2=UNLIMITED, arg4=1)
        elif t == ZoneCommandType.PUT_OBJECT and c.arg4 not in (None, 0, 1):
            losses.append(loss("reset", "arg4", "reset_arg_dropped", "warning", arg="arg4", value=c.arg4))
            v["arg4"] = None
        elif t == ZoneCommandType.EQUIP_OBJECT:
            slot = local_tables.SLOT_ROM_TO_PIVOT.get((c.arg_str or "").lower())
            if slot is None:
                return Converted(None, [loss("reset", "argStr", "reset_slot_unknown", "dropped", slot=c.arg_str)])
            v["arg_str"] = slot
        elif t == ZoneCommandType.RANDOMIZE_EXITS:
            v["arg2"] = None
        return Converted(ResetCommandIn(**v), losses)

    # ------------------------------------------------------------------ dal pivot

    def zone_from_pivot(self, z: ZoneIn, ctx: ConvertContext) -> Converted[ZoneIn]:
        """ROM non ha durata ne' modo di reset: segnalati se diversi dalle costanti dell'adapter."""
        losses = []
        if z.lifespan_minutes != 15 or z.reset_mode != ZoneResetMode.EMPTY:
            losses.append(loss("zone", "lifespanMinutes", "zone_reset_not_representable", "info"))
        return Converted(z, losses)

    def room_from_pivot(self, r: RoomIn, ctx: ConvertContext) -> Converted[RoomIn]:
        """Stanza pivot -> ROM: flag filtrati sulla tabella `room_flags`."""
        flags, losses = map_flags("room", "flags", r.flags, _ROOM)
        return Converted(r.model_copy(update={"flags": flags, "extra": {}}), losses)

    def mob_from_pivot(self, m: MobIn, ctx: ConvertContext) -> Converted[MobIn]:
        """Mob pivot -> ROM: AC x10 su tutti i tipi, campi senza equivalente azzerati con perdita."""
        flags, losses = map_flags("mob", "flags", m.flags, _MOB)
        losses += unsupported_mob_losses(m)
        if m.experience:
            losses.append(loss("mob", "experience", "field_dropped", "info", name="experience", value=m.experience))
        race = norm_race(m.race_id)
        picked, rl = pick_race(race, [race.replace("_", " ")] if race else [], ctx)
        if ctx.target_races and race in ctx.target_races:
            picked, rl = race, []
        losses += rl
        ac = m.armor_class * 10
        update = {
            "flags": flags, "race_id": picked, "experience": 0, "armor_class": ac, "extra": {"ac": [ac] * 4},
            **neutral_mob_fields(),
        }  # fmt: skip
        return Converted(m.model_copy(update=update), losses)

    def object_from_pivot(self, o: ObjectIn, ctx: ConvertContext) -> Converted[ObjectIn]:
        """Oggetto pivot -> ROM: valori per tipo (`extra.values` con i nomi), flag e apply sulle tabelle ROM."""
        extra_flags, fl1 = map_flags("object", "extraFlags", o.extra_flags, _EXTRA)
        wear, fl2 = map_flags("object", "wearFlags", o.wear_flags, _WEAR)
        affects, fl3 = map_affects(o.affects, _APPLY)
        values, raw, vl = pivot_values_to_rom(o)
        losses = [*fl1, *fl2, *fl3, *vl]
        if o.rent:
            losses.append(loss("object", "rent", "field_dropped", "info", name="rent", value=o.rent))
        if o.action_description:
            losses.append(loss("object", "actionDescription", "field_dropped", "info", name="actionDescription", value=""))
        update = {
            "extra_flags": extra_flags, "wear_flags": wear, "affects": affects, "rent": 0, "action_description": None,
            "value_0": values[0], "value_1": values[1], "value_2": values[2], "value_3": values[3],
            "extra": {"values": raw} if raw else {},
        }  # fmt: skip
        return Converted(o.model_copy(update=update), losses)

    def reset_from_pivot(self, c: ResetCommandIn, ctx: ConvertContext) -> Converted[ResetCommandIn]:
        """Reset pivot -> ROM: slot `E` con i nomi `wear_loc`; `O` con max 0 (ROM lo ignora)."""
        losses = []
        t = c.command_type
        update: dict = {}
        if t == ZoneCommandType.LOAD_OBJECT:
            update = {"arg2": 0, "arg4": None}
            if c.arg4 not in (None, 1):
                losses.append(loss("reset", "arg4", "reset_arg_dropped", "info", arg="arg4", value=c.arg4))
        elif t == ZoneCommandType.EQUIP_OBJECT:
            slot = local_tables.SLOT_PIVOT_TO_ROM.get((c.arg_str or "").strip().lower())
            if slot is None:
                return Converted(None, [loss("reset", "argStr", "reset_slot_unknown", "dropped", slot=c.arg_str)])
            update = {"arg_str": slot}
        return Converted(c.model_copy(update=update), losses)


def tables_item_known() -> set[str]:
    """Tipi oggetto ROM che hanno un equivalente in `ObjectType` (gli altri sono approssimati a `OTHER`)."""
    from pachimudeditor_adapter_basedmud.mapping import ITEM_TO_DTO

    return set(ITEM_TO_DTO) | {"none"}
