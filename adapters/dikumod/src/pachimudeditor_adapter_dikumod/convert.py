"""Sapore Diku Modificato (Diku molto modificato): da/verso il pivot.

Decisioni (vedi `docs/conversion.md`):

- **AC / THAC0**: come il pivot (scala piccola, `thac0` del file): nessuna trasformazione.
- **flag**: `act` (mob), flag di stanza, `extra` e vestibilita' (oggetti) passano da `tables.py`: nomi Diku Modificato senza
  corrispondenza ROM (es. `nochase`, `no_summon`, `anti_mage`, `throw`) si perdono con un avviso; `isnpc` e' implicito.
- **settore**: gia' approssimato dall'adapter (Diku Modificato 8 aria -> FLYING, 9 -> UNDERWATER, 10-12 -> FIELD/FOREST/CITY).
- **mob**: negozio (`.shp`), script (`scripts.dat`), `affectedBy`, immunita', suoni, posizioni e attacchi multipli non
  esistono nel pivot; il record corrotto (`extra.corrupted`) non si converte. Sesso: Diku Modificato non ha `BOTH`.
- **oggetti**: valori per tipo (`helpers.dikumod_values_to_pivot`: l'arma Diku ha dadi in v1/v2 e colpo in v3); gli apply
  passano da `APPLY_DIKUMOD_TO_ROM`; `extraDescs`, `forbiddenWear`, `typeRaw` senza equivalente si perdono.
- **reset**: `max` 0 = "nessun limite": in pachimud `M`/`O` richiedono un massimo (99), `G`/`E`/`P` lo lasciano vuoto;
  `O` `arg4` (massimo per stanza) passa; `C H F Z` (charm, odio, paura, zona) non esistono e si scartano (con i comandi
  che dipendono da loro); gli slot di `E` passano dai nomi `wear_positions` ai nomi di flag.
"""

from pachimudeditor.common.enums import Sex
from pachimudeditor.common.enums import ZoneCommandType

from pachimudeditor_adapter_dikumod import convert_tables as local_tables
from pachimudeditor.sdk import convert_tables as tables
from pachimudeditor.sdk import Flavor
from pachimudeditor.common.adapters.convert.helpers import (
    UNLIMITED,
    dikumod_values_to_pivot,
    map_affects,
    map_flags,
    neutral_mob_fields,
    norm_race,
    pick_race,
    pivot_values_to_dikumod,
    unsupported_mob_losses,
)
from pachimudeditor.sdk import rules
from pachimudeditor.sdk import ConvertContext, Converted, loss, to_in
from pachimudeditor.common.adapters.models import (
    ExitIn,
    ExitOut,
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

_ACT_TO_DIKUMOD = tables.invert(local_tables.ACT_DIKUMOD_TO_ROM)
_ROOM_TO_DIKUMOD = tables.invert(local_tables.ROOM_DIKUMOD_TO_ROM)
_EXTRA_TO_DIKUMOD = tables.invert(local_tables.EXTRA_DIKUMOD_TO_ROM)
_WEAR_TO_DIKUMOD = tables.invert(local_tables.WEAR_DIKUMOD_TO_ROM)
_APPLY_TO_DIKUMOD = tables.invert(local_tables.APPLY_DIKUMOD_TO_ROM)
_EXIT_DOOR_BITS = 1 | 2 | 4 | 32
"""`exitInfo`: ISDOOR, CLOSED, LOCKED, PICKPROOF -- gia' rappresentati dai campi neutri."""
_MOB_DROPPED = ("shop", "script", "affectedBy", "immune", "mImmune", "susc")
_MOB_MINOR = ("multiAttack", "position", "defaultPos", "sound", "distantSound")
_LETTER = {rules.CHARM_MOB: "C", rules.SET_HATE: "H", rules.SET_FEAR: "F", rules.SET_MOB_ZONE: "Z"}


def race_candidates_dikumod(race: str) -> list[str]:
    """Razze Diku Modificato da provare per un id pivot: stesso nome, alias, famiglia (`dragon_*` -> `dragon`)."""
    return [race, local_tables.RACE_PIVOT_TO_DIKUMOD.get(race, race)]


class DikumodFlavor(Flavor):
    """Mondo Diku Modificato (`kind: dikumod`)."""

    kind = "dikumod"
    door_state_in_resets = True

    # ------------------------------------------------------------------ verso il pivot

    def room_to_pivot(self, r: RoomOut, ctx: ConvertContext) -> Converted[RoomIn]:
        """Stanza Diku Modificato -> pivot: flag via tabella; teletrasporto, fiume, tunnel e luce si perdono."""
        flags, losses = map_flags("room", "flags", r.flags, local_tables.ROOM_DIKUMOD_TO_ROM)
        for key in ("tele", "river", "moblim", "light"):
            if r.extra.get(key) not in (None, 0):
                losses.append(loss("room", key, "room_special_dropped", "warning", name=key))
        if r.extra.get("sector") in (10, 11, 12):
            losses.append(loss("room", "sectorType", "sector_approximated", "info", sector=r.extra["sector"]))
        return Converted(RoomIn(**to_in(RoomIn, r, zone_id=0, flags=flags)), losses)

    def exit_to_pivot(self, e: ExitOut, ctx: ConvertContext) -> Converted[ExitIn]:
        """Uscita Diku Modificato -> pivot: i bit oltre porta/chiusa/serrata/a prova di scasso (secret, climb, ...) si perdono."""
        losses = []
        info = int(e.extra.get("exitInfo") or 0)
        if info & ~_EXIT_DOOR_BITS:
            names = [n for n, bit in exit_bit_names().items() if info & bit and not bit & _EXIT_DOOR_BITS]
            losses.append(loss("exit", "exitInfo", "exit_flags_dropped", "warning", flags=", ".join(names) or str(info)))
        if (e.extra.get("openCmd") or 0) > 0:
            losses.append(loss("exit", "openCmd", "field_dropped", "info", name="openCmd", value=str(e.extra["openCmd"])[:60]))
        return Converted(ExitIn(**to_in(ExitIn, e, target_room_id=None)), losses)

    def mob_to_pivot(self, m: MobOut, ctx: ConvertContext) -> Converted[MobIn]:
        """Mob Diku Modificato -> pivot."""
        if m.extra.get("corrupted"):
            return Converted(None, [loss("mob", "-", "mob_corrupted", "dropped", reason=str(m.extra.get("warning", ""))[:120])])
        flags, losses = map_flags("mob", "flags", m.flags, local_tables.ACT_DIKUMOD_TO_ROM, silent=local_tables.ACT_DIKUMOD_SILENT)
        for key in _MOB_DROPPED:
            if m.extra.get(key) not in (None, [], {}, "", 0):
                code = f"{key}_unsupported" if key in ("shop", "script") else "mob_flagset_dropped"
                losses.append(loss("mob", key, code, "dropped", name=key, value=str(m.extra[key])[:120]))
        minor = [k for k in _MOB_MINOR if m.extra.get(k) not in (None, "", 0, 8)]
        if minor:
            losses.append(loss("mob", "extra", "extra_dropped", "info", keys=", ".join(minor)))
        race = local_tables.RACE_DIKUMOD_TO_PIVOT.get(m.race_id or "", m.race_id)
        if race and race.startswith(("dragon_", "undead_")):
            race = race.split("_", 1)[0]
        values = to_in(MobIn, m, zone_id=0, flags=flags, race_id=norm_race(race))
        return Converted(MobIn(**values), losses)

    def object_to_pivot(self, o: ObjectOut, ctx: ConvertContext) -> Converted[ObjectIn]:
        """Oggetto Diku Modificato -> pivot."""
        losses = []
        if o.object_type.name == "OTHER" and o.extra.get("typeRaw") not in (None, 12):
            losses.append(loss("object", "objectType", "object_type_approximated", "warning", type=o.extra["typeRaw"]))
        extra_flags, fl1 = map_flags("object", "extraFlags", o.extra_flags, local_tables.EXTRA_DIKUMOD_TO_ROM)
        wear, fl2 = map_flags("object", "wearFlags", o.wear_flags, local_tables.WEAR_DIKUMOD_TO_ROM)
        affects, fl3 = map_affects(o.affects, local_tables.APPLY_DIKUMOD_TO_ROM)
        values, vl = dikumod_values_to_pivot(o)
        if o.extra.get("extraDescs"):
            losses.append(loss("object", "extraDescs", "object_extra_descs_dropped", "warning"))
        if o.extra.get("forbiddenWear"):
            losses.append(loss("object", "forbiddenWear", "field_dropped", "info", name="forbiddenWear", value=""))
        v = dict(zip(("value_0", "value_1", "value_2", "value_3"), values))
        new = to_in(ObjectIn, o, zone_id=0, extra_flags=extra_flags, wear_flags=wear, affects=affects, **v)
        return Converted(ObjectIn(**new), [*losses, *fl1, *fl2, *fl3, *vl])

    def reset_to_pivot(self, c: ResetCommandOut, ctx: ConvertContext) -> Converted[ResetCommandIn]:
        """Comando Diku Modificato -> pivot (vedi docstring del modulo)."""
        t = int(c.command_type)
        if t in _LETTER:
            return Converted(None, [loss("reset", "command", "reset_unsupported_command", "dropped", letter=_LETTER[t])])
        v = to_in(ResetCommandIn, c, comment=None, if_value=None)
        losses = []
        if t in (ZoneCommandType.LOAD_MOB, ZoneCommandType.LOAD_OBJECT):
            if not c.arg2:
                v["arg2"] = UNLIMITED
                losses.append(loss("reset", "arg2", "reset_unlimited_max", "info", value=UNLIMITED))
            v["arg4"] = c.arg4 or None if t == ZoneCommandType.LOAD_OBJECT else None
        elif t in (ZoneCommandType.GIVE_OBJECT, ZoneCommandType.EQUIP_OBJECT, ZoneCommandType.PUT_OBJECT):
            v["arg2"] = c.arg2 or None
            if t == ZoneCommandType.EQUIP_OBJECT:
                slot = local_tables.SLOT_DIKUMOD_TO_PIVOT.get((c.arg_str or "").lower())
                if slot is None:
                    return Converted(None, [loss("reset", "argStr", "reset_slot_unknown", "dropped", slot=c.arg_str)])
                v["arg_str"] = slot
        return Converted(ResetCommandIn(**v), losses)

    # ------------------------------------------------------------------ dal pivot

    def zone_from_pivot(self, z: ZoneIn, ctx: ConvertContext) -> Converted[ZoneIn]:
        """Diku Modificato ignora costruttore, livelli e `enabled`."""
        lost = [n for n, v, d in (("builder", z.builder, ""), ("minLevel", z.min_level, 1), ("maxLevel", z.max_level, 1)) if v != d]
        if not z.enabled:
            lost.append("enabled")
        losses = [loss("zone", "-", "zone_fields_dropped", "info", names=", ".join(lost))] if lost else []
        return Converted(z, losses)

    def room_from_pivot(self, r: RoomIn, ctx: ConvertContext) -> Converted[RoomIn]:
        """Stanza pivot -> Diku Modificato: flag via tabella inversa; rigenerazione e proprieta' non esistono (valori neutri)."""
        flags, losses = map_flags("room", "flags", r.flags, _ROOM_TO_DIKUMOD)
        for name, value, neutral in (
            ("healRate", r.heal_rate, 100),
            ("manaRate", r.mana_rate, 100),
            ("clanId", r.clan_id, None),
            ("owner", r.owner, None),
        ):
            if value != neutral:
                losses.append(loss("room", name, "field_dropped", "info", name=name, value=value))
        update = {"flags": flags, "heal_rate": 100, "mana_rate": 100, "clan_id": None, "owner": None, "extra": {}}
        return Converted(r.model_copy(update=update), losses)

    def mob_from_pivot(self, m: MobIn, ctx: ConvertContext) -> Converted[MobIn]:
        """Mob pivot -> Diku Modificato."""
        flags, losses = map_flags("mob", "flags", m.flags, _ACT_TO_DIKUMOD, silent=tables.ACT_ROM_SILENT)
        flags = ["isnpc", *flags]  # il bit ISNPC e' sempre presente nei mob Diku Modificato
        losses += unsupported_mob_losses(m)
        race = norm_race(m.race_id)
        picked, rl = pick_race(race, race_candidates_dikumod(race) if race else [], ctx)
        update = {"flags": flags, "race_id": picked, "extra": {}, **neutral_mob_fields()}
        if m.sex == Sex.BOTH:
            losses.append(loss("mob", "sex", "sex_approximated", "warning"))
            update["sex"] = Sex.NEUTRAL
        return Converted(m.model_copy(update=update), [*losses, *rl])

    def object_from_pivot(self, o: ObjectIn, ctx: ConvertContext) -> Converted[ObjectIn]:
        """Oggetto pivot -> Diku Modificato."""
        extra_flags, fl1 = map_flags("object", "extraFlags", o.extra_flags, _EXTRA_TO_DIKUMOD)
        wear, fl2 = map_flags("object", "wearFlags", o.wear_flags, _WEAR_TO_DIKUMOD)
        affects, fl3 = map_affects(o.affects, _APPLY_TO_DIKUMOD)
        values, vl = pivot_values_to_dikumod(o)
        losses = [*fl1, *fl2, *fl3, *vl]
        if len(affects) > 5:
            losses.append(loss("object", "affects", "affects_dropped", "warning", names=", ".join(list(affects)[5:])))
            affects = dict(list(affects.items())[:5])
        update = {
            "extra_flags": extra_flags, "wear_flags": wear, "affects": affects, "extra": {},
            "value_0": values[0], "value_1": values[1], "value_2": values[2], "value_3": values[3],
        }  # fmt: skip
        return Converted(o.model_copy(update=update), losses)

    def reset_from_pivot(self, c: ResetCommandIn, ctx: ConvertContext) -> Converted[ResetCommandIn]:
        """Comando pivot -> Diku Modificato: `R` (non implementato dal loader Diku Modificato) si scarta; `M` non ha il massimo per stanza."""
        t = c.command_type
        losses = []
        update: dict = {}
        if t == ZoneCommandType.RANDOMIZE_EXITS:
            return Converted(None, [loss("reset", "command", "reset_unsupported_command", "dropped", letter="R")])
        if t == ZoneCommandType.LOAD_MOB and c.arg4 is not None:
            losses.append(loss("reset", "arg4", "reset_arg_dropped", "info", arg="arg4", value=c.arg4))
            update["arg4"] = None
        if t == ZoneCommandType.EQUIP_OBJECT:
            slot = local_tables.SLOT_PIVOT_TO_DIKUMOD.get((c.arg_str or "").strip().lower())
            if slot is None:
                return Converted(None, [loss("reset", "argStr", "reset_slot_unknown", "dropped", slot=c.arg_str)])
            update["arg_str"] = slot
        return Converted(c.model_copy(update=update), losses)


def exit_bit_names() -> dict[str, int]:
    """I nomi dei bit di `exitInfo` (tabella `EXIT_FLAGS` della libreria Diku Modificato)."""
    from pachimudeditor_adapter_dikumod.dikumod_lib import tables as dikumod_tables

    return dict(dikumod_tables.EXIT_FLAGS)
