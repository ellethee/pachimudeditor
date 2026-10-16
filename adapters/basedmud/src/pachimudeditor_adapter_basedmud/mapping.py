"""Conversioni pure tra il modello della libreria `.are` (ROM/basedmud) e i DTO neutri dell'editor.

Nessun I/O e nessuno stato: ogni funzione riceve gli oggetti della libreria e restituisce DTO (o applica un
patch ai soli campi toccati). Regole generali:

- cio' che ha un campo nel DTO neutro (nome, descrizioni, livello, flag come `list[str]`, ...) va li';
- tutto il resto (flag act/affect/off/imm/res/vuln, razza-form-parti, valori v0-v4 grezzi, trigger di mobprog,
  negozio, spec_fun, ...) va in `extra`, in entrambe le direzioni;
- un patch applica solo i campi **diversi** dal valore corrente: riscrivere un `extra` invariato non cambia
  nemmeno un byte del file (la libreria riemette il testo originale degli elementi non modificati).
"""

import copy
import re
from typing import Any

from pachimudeditor_adapter_basedmud.rom_lib import (
    Dice,
    Exit,
    ExtraDescription,
    FlagRemoval,
    Mobile,
    MobProgTrigger,
    Object,
    ObjectAffect,
    Reset,
    Room,
    Shop,
    Special,
    flag_names,
    names_to_flags,
    parse_flags,
)
from pachimudeditor_adapter_basedmud.rom_lib.model import AreaHeader
from pachimudeditor_adapter_basedmud.rom_lib.tables import FLAG_TABLES, TYPE_TABLES
from pachifast.i18n import api_error
from pachimudeditor.common.enums import Sex
from pachimudeditor.common.enums import ObjectType
from pachimudeditor.common.enums import ZoneCommandType
from pachimudeditor.common.enums import Direction, DoorFlag, SectorType

from pachimudeditor.common.adapters.models import (
    ExitOut,
    ExtraDescriptionOut,
    MobOut,
    ObjectOut,
    ResetCommandDraft,
    ResetCommandOut,
    RoomOut,
)

MAX_LEVEL = 60
"""`MAX_LEVEL` di basedmud (`defs.h`): estremo alto quando la zona non dichiara un range di livelli."""

LIFESPAN_MINUTES = 15
"""ROM resetta un'area ogni ~15 tick (31 se non e' vuota): valore costante esposto come `lifespanMinutes`."""

EXTRA_DESC_STRIDE = 1000
"""`id` di un'extra description di stanza = `vnum * 1000 + posizione`."""

EXIT_STRIDE = 10
"""`id` di un'uscita = `vnum_stanza * 10 + direzione`."""

# --------------------------------------------------------------------------- errori


def unknown_flag(table: str, name: str) -> Any:
    """422 `basedmud.unknown_flag`: il nome non e' in `table`."""
    return api_error(422, "basedmud.unknown_flag", table=table, name=name)


def flags_from_names(table: str, names: list[str]) -> int:
    """Valore intero dei flag `names` (nomi simbolici o `[X]`); 422 `basedmud.unknown_flag` se un nome non esiste."""
    try:
        return names_to_flags(table, names)
    except (KeyError, ValueError) as error:
        raise unknown_flag(table, str(error.args[0] if error.args else error)) from error


def apply_extra(extra: dict[str, Any], handlers: dict[str, Any]) -> None:
    """Chiama `handlers[chiave](valore)` per ogni chiave di `extra`; 422 `basedmud.extra_unknown` se non e' nota."""
    for key, value in extra.items():
        handler = handlers.get(key)
        if handler is None:
            raise api_error(422, "basedmud.extra_unknown", key=key, known=", ".join(sorted(handlers)))
        handler(value)


# --------------------------------------------------------------------------- settori, tipi, sesso

SECTOR_TO_DTO: dict[int, SectorType] = {
    0: SectorType.INSIDE,
    1: SectorType.CITY,
    2: SectorType.FIELD,
    3: SectorType.FOREST,
    4: SectorType.HILLS,
    5: SectorType.MOUNTAIN,
    6: SectorType.WATER_SWIM,
    7: SectorType.WATER_NOSWIM,
    8: SectorType.UNDERWATER,  # SECT_UNUSED
    9: SectorType.FLYING,  # SECT_AIR
    10: SectorType.FIELD,  # SECT_DESERT: nessun equivalente, il valore vero e' in extra["sector"]
}
"""Settore ROM -> `SectorType` di pachimud (approssimato dove non c'e' equivalente)."""

SECTOR_FROM_DTO: dict[SectorType, int] = {
    SectorType.INSIDE: 0,
    SectorType.CITY: 1,
    SectorType.FIELD: 2,
    SectorType.FOREST: 3,
    SectorType.HILLS: 4,
    SectorType.MOUNTAIN: 5,
    SectorType.WATER_SWIM: 6,
    SectorType.WATER_NOSWIM: 7,
    SectorType.UNDERWATER: 8,
    SectorType.FLYING: 9,
}

ITEM_TO_DTO: dict[str, ObjectType] = {
    "light": ObjectType.LIGHT,
    "weapon": ObjectType.WEAPON,
    "armor": ObjectType.ARMOR,
    "container": ObjectType.CONTAINER,
    "drink": ObjectType.LIQUID_CONTAINER,
    "treasure": ObjectType.TREASURE,
    "trash": ObjectType.TRASH,
    "key": ObjectType.KEY,
    "food": ObjectType.FOOD,
    "money": ObjectType.MONEY,
    "potion": ObjectType.POTION,
    "scroll": ObjectType.SCROLL,
    "wand": ObjectType.WAND,
    "staff": ObjectType.STAFF,
    "fountain": ObjectType.FOUNTAIN,
}
"""Tipo oggetto ROM -> `ObjectType` (gli altri tipi ROM diventano `OTHER`; il nome vero e' in extra["itemType"])."""

ITEM_FROM_DTO: dict[ObjectType, str] = {v: k for k, v in ITEM_TO_DTO.items()} | {ObjectType.OTHER: "none"}

SEX_TO_DTO: dict[str, Sex] = {
    "none": Sex.NEUTRAL,
    "neutral": Sex.NEUTRAL,
    "male": Sex.MALE,
    "female": Sex.FEMALE,
    "either": Sex.BOTH,
    "random": Sex.BOTH,
}
SEX_FROM_DTO: dict[Sex, str] = {Sex.NEUTRAL: "none", Sex.MALE: "male", Sex.FEMALE: "female", Sex.BOTH: "either"}


def sector_out(raw: int) -> SectorType:
    """`SectorType` per il settore ROM `raw` (sconosciuto: `INSIDE`)."""
    return SECTOR_TO_DTO.get(raw, SectorType.INSIDE)


# --------------------------------------------------------------------------- zona (intestazione)

_LEVELS = re.compile(r"^\s*\{\s*(\d+)\s+(\d+)\s*\}")
_BRACES = re.compile(r"^\s*\{[^}]*\}")


def parse_credits(credits: str) -> tuple[int, int, str]:
    """`(livello_min, livello_max, autore)` dai credits `{ 5 35 } Autore  Titolo` (`{ All }` o assente: 1..60)."""
    match = _LEVELS.match(credits)
    low, high = (int(match.group(1)), int(match.group(2))) if match else (1, MAX_LEVEL)
    rest = _BRACES.sub("", credits, count=1).strip()
    return low, high, rest.split()[0] if rest else ""


def build_credits(credits: str, low: int, high: int, author: str | None = None) -> str:
    """I credits con il blocco `{ low high }` sostituito/aggiunto e, se dato, l'autore (prima parola) cambiato."""
    rest = _BRACES.sub("", credits, count=1).strip()
    if author is not None:
        words = rest.split(None, 1)
        rest = " ".join([author, *words[1:]]) if words else author
    return f"{{ {low} {high} }} {rest}".rstrip()


def header_builder(header: AreaHeader) -> str:
    """Il builder della zona: `Builders` di `#AREADATA`, altrimenti l'autore nei credits."""
    return header.builders.strip() or parse_credits(header.credits)[2]


# --------------------------------------------------------------------------- stanze, uscite


def exit_id(room_vnum: int, door: int) -> int:
    """`id` di un'uscita."""
    return room_vnum * EXIT_STRIDE + door


def door_flag_out(exit_: Exit) -> DoorFlag:
    """`DoorFlag` di un'uscita (nopass non e' rappresentabile: resta nel codice `locks`)."""
    if exit_.locks in (2, 4):
        return DoorFlag.PICKPROOF
    return DoorFlag.CLOSABLE if exit_.locks in (1, 3) else DoorFlag.NONE


def locks_from(flag: DoorFlag, old_locks: int = 0) -> int:
    """Codice `locks` per `flag`, conservando il bit nopass dell'uscita precedente."""
    nopass = old_locks in (3, 4)
    if flag is DoorFlag.NONE:
        return 0
    return (2 if flag is DoorFlag.PICKPROOF else 1) + (2 if nopass else 0)


def door_state_out(locks_reset: int | None) -> tuple[bool, bool]:
    """`(is_open, is_locked)` dal valore del reset `D` (0 aperta, 1 chiusa, 2 chiusa e serrata; assente = aperta)."""
    return locks_reset in (None, 0), locks_reset == 2


def exit_out(room_vnum: int, exit_: Exit, targets: dict[int, str], door_reset: int | None) -> ExitOut:
    """DTO di un'uscita. `targets` mappa vnum stanza -> nome; `door_reset` e' il `D` della zona per questa porta."""
    is_open, is_locked = door_state_out(door_reset)
    target = exit_.to_vnum if exit_.to_vnum in targets else None
    return ExitOut(
        id=exit_id(room_vnum, exit_.door),
        room_id=room_vnum,
        direction=Direction(exit_.door),
        description=exit_.description or None,
        keywords=exit_.keyword or None,
        door_flag=door_flag_out(exit_),
        is_open=is_open,
        is_locked=is_locked,
        key_vnum=exit_.key if exit_.key > 0 else None,
        target_room_id=target,
        target_room_vnum=exit_.to_vnum if exit_.to_vnum > 0 else None,
        target_room_name=targets.get(exit_.to_vnum),
    )


def extra_desc_out(room_vnum: int, index: int, extra: ExtraDescription) -> ExtraDescriptionOut:
    """DTO di un'extra description di stanza (`id` = `vnum * 1000 + posizione`)."""
    return ExtraDescriptionOut(id=room_vnum * EXTRA_DESC_STRIDE + index, room_id=room_vnum, keywords=extra.keyword, text=extra.description)


def room_out(room: Room, zone_id: int) -> RoomOut:
    """DTO neutro di una stanza (uscite ed extra description sono in `RoomDetail`)."""
    return RoomOut(
        id=room.vnum,
        vnum=room.vnum,
        zone_id=zone_id,
        name=room.name,
        description=room.description,
        sector_type=sector_out(room.sector),
        flags=room.flag_names,
        heal_rate=room.heal_rate,
        mana_rate=room.mana_rate,
        clan_id=room.clan or None,
        owner=room.owner or None,
        extra={"sector": room.sector},
    )


def apply_room_fields(room: Room, values: dict[str, Any]) -> None:
    """Applica ai campi della stanza i soli valori del dict (nomi Python del DTO) che differiscono dall'attuale."""
    simple = {"name": "name", "description": "description", "heal_rate": "heal_rate", "mana_rate": "mana_rate"}
    for key, attr in simple.items():
        if key in values and getattr(room, attr) != values[key]:
            setattr(room, attr, values[key])
    for key, attr in (("clan_id", "clan"), ("owner", "owner")):
        if key in values and (values[key] or "") != getattr(room, attr):
            setattr(room, attr, values[key] or "")
    if "flags" in values and values["flags"] != room.flag_names:
        room.room_flags = flags_from_names("room_flags", values["flags"])
    if "sector_type" in values and SECTOR_TO_DTO.get(room.sector) != values["sector_type"]:
        room.sector = SECTOR_FROM_DTO[SectorType(values["sector_type"])]


def apply_room_extra(room: Room, extra: dict[str, Any]) -> None:
    """Applica `extra` di una stanza (chiave nota: `sector`, il settore ROM grezzo)."""

    def sector(value: Any) -> None:
        """Il settore ROM grezzo (0-10)."""
        if not isinstance(value, int) or not 0 <= value < len(TYPE_TABLES["sector_types"]):
            raise api_error(422, "basedmud.extra_invalid", key="sector")
        room.sector = value

    apply_extra(extra, {"sector": sector})


# --------------------------------------------------------------------------- mob

MOB_EXTRA_KEYS = (
    "affectedBy", "offFlags", "immFlags", "resFlags", "vulnFlags", "form", "parts", "size", "material",
    "startPos", "defaultPos", "group", "damType", "mana", "ac", "flagRemovals", "mprogs", "shop", "special",
)  # fmt: skip


def shop_out(shop: Shop | None) -> dict[str, Any] | None:
    """Il negozio del mob come dict (`None` se non ne ha)."""
    if shop is None:
        return None
    return {
        "buyTypes": [TYPE_TABLES["item_types"][t] if 0 <= t < len(TYPE_TABLES["item_types"]) else t for t in shop.buy_types],
        "profitBuy": shop.profit_buy,
        "profitSell": shop.profit_sell,
        "openHour": shop.open_hour,
        "closeHour": shop.close_hour,
    }


def _item_type_number(value: Any) -> int:
    """Numero di tipo oggetto da un nome della tabella `item_types` o da un intero."""
    if isinstance(value, int):
        return value
    try:
        return TYPE_TABLES["item_types"].index(str(value))
    except ValueError as error:
        raise api_error(422, "basedmud.extra_invalid", key="shop.buyTypes") from error


def shop_apply(shop: Shop, data: dict[str, Any]) -> None:
    """Imposta i campi di `shop` dal dict (formato di `shop_out`)."""
    if "buyTypes" in data:
        types = [_item_type_number(t) for t in data["buyTypes"]][:5]
        shop.buy_types = types + [0] * (5 - len(types))
    for key, attr in (("profitBuy", "profit_buy"), ("profitSell", "profit_sell"), ("openHour", "open_hour"), ("closeHour", "close_hour")):
        if key in data:
            setattr(shop, attr, int(data[key]))


def mob_out(mob: Mobile, zone_id: int, shop: Shop | None, special: Special | None) -> MobOut:
    """DTO neutro di un mob. `shop`/`special` sono le voci di `#SHOPS`/`#SPECIALS` del suo keeper."""
    extra: dict[str, Any] = {
        "affectedBy": mob.affect_names,
        "offFlags": mob.off_names,
        "immFlags": flag_names("res_flags", mob.imm_flags),
        "resFlags": flag_names("res_flags", mob.res_flags),
        "vulnFlags": flag_names("res_flags", mob.vuln_flags),
        "form": flag_names("form_flags", mob.form),
        "parts": flag_names("part_flags", mob.parts),
        "size": mob.size,
        "material": mob.material,
        "startPos": mob.start_pos,
        "defaultPos": mob.default_pos,
        "group": mob.group,
        "damType": mob.dam_type,
        "mana": str(mob.mana),
        "ac": list(mob.ac),
        "flagRemovals": [{"word": f.word, "value": f.value} for f in mob.flag_removals],
        "mprogs": [{"trigger": p.trigger, "vnum": p.vnum, "phrase": p.phrase} for p in mob.mprogs],
        "shop": shop_out(shop),
        "special": special.function if special else None,
    }
    return MobOut(
        id=mob.vnum,
        vnum=mob.vnum,
        zone_id=zone_id,
        keywords=mob.name,
        short_description=mob.short_descr,
        long_description=mob.long_descr,
        detailed_description=mob.description,
        level=mob.level,
        thac0=20 - mob.hitroll,
        armor_class=mob.ac[0],
        hp_dice_count=mob.hit.number,
        hp_die_size=mob.hit.type,
        hp_bonus=mob.hit.bonus,
        damage_dice_count=mob.damage.number,
        damage_die_size=mob.damage.type,
        damage_bonus=mob.damage.bonus,
        gold=mob.wealth,
        experience=0,
        sex=SEX_TO_DTO.get(mob.sex, Sex.NEUTRAL),
        flags=mob.act_names,
        race_id=mob.race or None,
        class_id=None,
        alignment=mob.alignment,
        debuff_skill_id=None,
        shop_id=None,
        quest_ids=[],
        is_banker=False,
        teaches_class_ids=None,
        teaches_skill_ids=None,
        extra=extra,
    )


MOB_UNSUPPORTED: dict[str, Any] = {
    "experience": 0,
    "class_id": None,
    "debuff_skill_id": None,
    "shop_id": None,
    "quest_ids": [],
    "is_banker": False,
    "teaches_class_ids": None,
    "teaches_skill_ids": None,
}
"""Campi di `MobOut` che ROM non ha: accettati solo col valore neutro (altrimenti 422 `basedmud.field_unsupported`)."""


def reject_unsupported(values: dict[str, Any], defaults: dict[str, Any]) -> None:
    """422 `basedmud.field_unsupported` se un campo di `values` e' diverso dal valore neutro in `defaults`."""
    for key, neutral in defaults.items():
        if key in values and values[key] != neutral and not (neutral == [] and not values[key]):
            raise api_error(422, "basedmud.field_unsupported", field=key)


def apply_mob_fields(mob: Mobile, values: dict[str, Any]) -> None:
    """Applica ai campi del mob i soli valori del dict (nomi Python del DTO) che differiscono dall'attuale."""
    reject_unsupported(values, MOB_UNSUPPORTED)
    for key, attr in (
        ("keywords", "name"), ("short_description", "short_descr"), ("long_description", "long_descr"),
        ("detailed_description", "description"), ("level", "level"), ("gold", "wealth"), ("alignment", "alignment"),
    ):  # fmt: skip
        if key in values and getattr(mob, attr) != values[key]:
            setattr(mob, attr, values[key])
    if "thac0" in values and 20 - mob.hitroll != values["thac0"]:
        mob.hitroll = 20 - values["thac0"]
    if "armor_class" in values and mob.ac[0] != values["armor_class"]:
        mob.ac = [values["armor_class"], *mob.ac[1:]]
    for prefix, dice in (("hp", mob.hit), ("damage", mob.damage)):
        for key, attr in (("dice_count", "number"), ("die_size", "type"), ("bonus", "bonus")):
            name = f"{prefix}_{key}"
            if name in values and getattr(dice, attr) != values[name]:
                setattr(dice, attr, values[name])
    if "sex" in values and SEX_TO_DTO.get(mob.sex) != values["sex"]:
        mob.sex = SEX_FROM_DTO[Sex(values["sex"])]
    if "flags" in values and values["flags"] != mob.act_names:
        mob.act = flags_from_names("mob_flags", values["flags"])
    if "race_id" in values and (values["race_id"] or "") != mob.race:
        mob.race = values["race_id"] or ""


def _flag_setter(mob: Mobile, attr: str, table: str):  # type: ignore[no-untyped-def]
    """Handler di `extra` che imposta il campo flag `attr` dai nomi della tabella `table`."""

    def apply(value: Any) -> None:
        """Imposta i flag dai nomi."""
        if not isinstance(value, list):
            raise api_error(422, "basedmud.extra_invalid", key=attr)
        new = flags_from_names(table, value)
        if new != getattr(mob, attr):
            setattr(mob, attr, new)

    return apply


def _attr_setter(obj: Any, attr: str, kind: type = str):  # type: ignore[no-untyped-def]
    """Handler di `extra` che assegna `attr` (convertito con `kind`) solo se cambia."""

    def apply(value: Any) -> None:
        """Assegna il valore."""
        try:
            new = kind(value)
        except (TypeError, ValueError) as error:
            raise api_error(422, "basedmud.extra_invalid", key=attr) from error
        if getattr(obj, attr) != new:
            setattr(obj, attr, new)

    return apply


def mob_extra_handlers(mob: Mobile, shop_cb: Any, special_cb: Any) -> dict[str, Any]:
    """Handler per ogni chiave di `extra` di un mob; `shop_cb(dict|None)`/`special_cb(str|None)` toccano le altre sezioni."""

    def mana(value: Any) -> None:
        """Dado mana `NdT+B`."""
        try:
            new = Dice.parse(str(value))
        except ValueError as error:
            raise api_error(422, "basedmud.extra_invalid", key="mana") from error
        if new != mob.mana:
            mob.mana = new

    def ac(value: Any) -> None:
        """I 4 valori di AC."""
        if not isinstance(value, list) or len(value) != 4 or not all(isinstance(v, int) for v in value):
            raise api_error(422, "basedmud.extra_invalid", key="ac")
        if mob.ac != value:
            mob.ac = list(value)

    def removals(value: Any) -> None:
        """Righe `F`."""
        new = [FlagRemoval(str(v["word"]), int(v["value"])) for v in value]
        if new != mob.flag_removals:
            mob.flag_removals = new

    def mprogs(value: Any) -> None:
        """Righe `M`."""
        new = [MobProgTrigger(str(v["trigger"]), int(v["vnum"]), str(v.get("phrase", ""))) for v in value]
        if new != mob.mprogs:
            mob.mprogs = new

    return {
        "affectedBy": _flag_setter(mob, "affected_by", "affect_flags"),
        "offFlags": _flag_setter(mob, "off_flags", "off_flags"),
        "immFlags": _flag_setter(mob, "imm_flags", "res_flags"),
        "resFlags": _flag_setter(mob, "res_flags", "res_flags"),
        "vulnFlags": _flag_setter(mob, "vuln_flags", "res_flags"),
        "form": _flag_setter(mob, "form", "form_flags"),
        "parts": _flag_setter(mob, "parts", "part_flags"),
        "size": _attr_setter(mob, "size"),
        "material": _attr_setter(mob, "material"),
        "startPos": _attr_setter(mob, "start_pos"),
        "defaultPos": _attr_setter(mob, "default_pos"),
        "group": _attr_setter(mob, "group", int),
        "damType": _attr_setter(mob, "dam_type"),
        "mana": mana,
        "ac": ac,
        "flagRemovals": removals,
        "mprogs": mprogs,
        "shop": shop_cb,
        "special": special_cb,
    }


def new_mobile(vnum: int, values: dict[str, Any]) -> Mobile:
    """Un mob nuovo (default ROM sensati) con i campi di `MobIn`."""
    mob = Mobile(vnum=vnum, race="", act=1, mana=Dice(1, 1, 100), dam_type="none")
    apply_mob_fields(mob, values)
    if not mob.act & 1:  # il loader ROM aggiunge ACT_IS_NPC; l'OLC lo scrive sempre
        mob.act |= 1
    return mob


# --------------------------------------------------------------------------- oggetti


def _value_int(raw: str, quoted: bool = False) -> int | None:
    """Il valore v0-v4 come intero: decimale, oppure bit string a lettere (`AB`) se lo slot non e' un nome.
    `None` per i nomi (skill, liquidi: `quoted`)."""
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    if quoted:
        return None
    try:
        return parse_flags(raw)
    except ValueError:
        return None


def _slot_int(obj: Object, index: int) -> int | None:
    """`_value_int` del valore `index` di `obj` tenendo conto degli slot che contengono nomi."""
    return _value_int(obj.values[index], index in Object.QUOTED_SLOTS.get(obj.item_type, ()))


def object_affects(obj: Object) -> dict[str, int]:
    """Gli affect semplici (`A`) come `{nome_apply: somma_modificatori}`."""
    names = TYPE_TABLES["affect_apply_types"]
    out: dict[str, int] = {}
    for a in obj.affects:
        if not a.is_flag_affect:
            key = names[a.location] if 0 <= a.location < len(names) else str(a.location)
            out[key] = out.get(key, 0) + a.modifier
    return out


def _apply_location(key: str) -> int:
    """Numero di apply per un nome della tabella (o un intero scritto come stringa)."""
    names = TYPE_TABLES["affect_apply_types"]
    if key in names:
        return names.index(key)
    if key.lstrip("-").isdigit():
        return int(key)
    raise api_error(422, "basedmud.extra_invalid", key=f"affects.{key}")


def object_out(obj: Object, zone_id: int) -> ObjectOut:
    """DTO neutro di un oggetto."""
    ints = [_slot_int(obj, i) for i in range(4)]
    return ObjectOut(
        id=obj.vnum,
        vnum=obj.vnum,
        zone_id=zone_id,
        keywords=obj.name,
        short_description=obj.short_descr,
        long_description=obj.description,
        action_description=None,
        object_type=ITEM_TO_DTO.get(obj.item_type, ObjectType.OTHER),
        weight=obj.weight,
        cost=obj.cost,
        rent=0,
        value_0=ints[0],
        value_1=ints[1],
        value_2=ints[2],
        value_3=ints[3],
        extra_flags=obj.extra_names,
        wear_flags=obj.wear_names,
        affects=object_affects(obj),
        extra={
            "itemType": obj.item_type,
            "values": list(obj.values),
            "level": obj.level,
            "material": obj.material,
            "condition": obj.condition,
            "flagAffects": [
                {"where": a.where, "location": a.location, "modifier": a.modifier, "bits": a.bits} for a in obj.affects if a.is_flag_affect
            ],
            "extraDescs": [{"keyword": e.keyword, "description": e.description} for e in obj.extra_descs],
        },
    )


OBJECT_UNSUPPORTED: dict[str, Any] = {"rent": 0, "action_description": None}
"""Campi di `ObjectOut` che ROM non ha (accettati solo col valore neutro)."""


def apply_object_fields(obj: Object, values: dict[str, Any]) -> None:
    """Applica ai campi dell'oggetto i soli valori del dict (nomi Python del DTO) che differiscono dall'attuale."""
    reject_unsupported(values, OBJECT_UNSUPPORTED)
    for key, attr in (
        ("keywords", "name"), ("short_description", "short_descr"), ("long_description", "description"),
        ("weight", "weight"), ("cost", "cost"),
    ):  # fmt: skip
        if key in values and getattr(obj, attr) != values[key]:
            setattr(obj, attr, values[key])
    if "object_type" in values and ITEM_TO_DTO.get(obj.item_type, ObjectType.OTHER) != values["object_type"]:
        obj.item_type = ITEM_FROM_DTO[ObjectType(values["object_type"])]
    for index in range(4):
        key = f"value_{index}"
        if key in values:
            new = "0" if values[key] is None else str(values[key])
            if _slot_int(obj, index) != values[key] and obj.values[index] != new:
                obj.values[index] = new
    for key, attr, table in (("extra_flags", "extra_flags", "extra_flags"), ("wear_flags", "wear_flags", "wear_flags")):
        names = flag_names(table, getattr(obj, attr))
        if key in values and values[key] != names:
            setattr(obj, attr, flags_from_names(table, values[key]))
    if "affects" in values and values["affects"] != object_affects(obj):
        flag_affects = [a for a in obj.affects if a.is_flag_affect]
        simple = [ObjectAffect(_apply_location(k), int(v)) for k, v in values["affects"].items()]
        obj.affects = simple + flag_affects


def object_extra_handlers(obj: Object) -> dict[str, Any]:
    """Handler per ogni chiave di `extra` di un oggetto."""

    def values(value: Any) -> None:
        """I 5 valori grezzi v0-v4."""
        if not isinstance(value, list) or len(value) != 5:
            raise api_error(422, "basedmud.extra_invalid", key="values")
        new = [str(v) for v in value]
        if obj.values != new:
            obj.values = new

    def flag_affects(value: Any) -> None:
        """Gli affect `F` (sostituiscono quelli esistenti, gli `A` restano)."""
        new = [ObjectAffect(int(v["location"]), int(v["modifier"]), str(v["where"]), int(v["bits"])) for v in value]
        old = [a for a in obj.affects if a.is_flag_affect]
        if new != old:
            obj.affects = [a for a in obj.affects if not a.is_flag_affect] + new

    def extra_descs(value: Any) -> None:
        """Le extra description dell'oggetto."""
        new = [ExtraDescription(str(v["keyword"]), str(v["description"])) for v in value]
        if new != obj.extra_descs:
            obj.extra_descs = new

    return {
        "itemType": _attr_setter(obj, "item_type"),
        "values": values,
        "level": _attr_setter(obj, "level", int),
        "material": _attr_setter(obj, "material"),
        "condition": _attr_setter(obj, "condition"),
        "flagAffects": flag_affects,
        "extraDescs": extra_descs,
    }


def new_object(vnum: int, values: dict[str, Any]) -> Object:
    """Un oggetto nuovo con i campi di `ObjectIn`."""
    obj = Object(vnum=vnum, material="unknown", item_type="trash")
    apply_object_fields(obj, values)
    return obj


# --------------------------------------------------------------------------- reset

_WEAR_LOC = TYPE_TABLES["wear_loc_types"]
_DOOR_STATE = {0: "OPEN", 1: "CLOSED", 2: "LOCKED"}
_DOOR_STATE_REV = {v: k for k, v in _DOOR_STATE.items()}
_TYPE_BY_LETTER = {
    "M": ZoneCommandType.LOAD_MOB,
    "O": ZoneCommandType.LOAD_OBJECT,
    "G": ZoneCommandType.GIVE_OBJECT,
    "E": ZoneCommandType.EQUIP_OBJECT,
    "P": ZoneCommandType.PUT_OBJECT,
    "D": ZoneCommandType.SET_DOOR_STATE,
    "R": ZoneCommandType.RANDOMIZE_EXITS,
}
_LETTER_BY_TYPE = {v: k for k, v in _TYPE_BY_LETTER.items()}


def reset_out(zone_id: int, index: int, reset: Reset) -> ResetCommandOut:
    """DTO di un reset (`id` e `orderIndex` = posizione tra i soli reset, commenti esclusi).

    Argomenti come in pachimud: M `arg1` mob, `arg2` massimo globale, `arg3` stanza, `arg4` massimo in stanza;
    O `arg1` oggetto, `arg2` massimo, `arg3` stanza; P `arg1` oggetto, `arg2` massimo, `arg3` contenitore, `arg4`
    quantita'; G `arg1`, `arg2`; E come G con `argStr` = slot (`wear_loc_types`); D `arg1` stanza, `arg2` direzione,
    `argStr` OPEN/CLOSED/LOCKED; R `arg1` stanza, `arg2` numero di direzioni.
    """
    a = reset.args
    arg_str: str | None = None
    if reset.command == "E":
        arg_str = _WEAR_LOC[a[3]] if 0 <= a[3] < len(_WEAR_LOC) else str(a[3])
    elif reset.command == "D":
        arg_str = _DOOR_STATE.get(a[3], str(a[3]))
    slots = {"M": (1, 2, 3, 4), "O": (1, 2, 3, None), "P": (1, 2, 3, 4), "G": (1, 2, None, None),
             "E": (1, 2, None, None), "D": (1, 2, None, None), "R": (1, 2, None, None)}[reset.command]  # fmt: skip
    args = [max(a[i], 0) if i is not None else None for i in slots]
    if reset.command in "GEP" and a[2] < 0:
        args[1] = None  # limite negativo (-1) = nessun limite: nel DTO l'argomento opzionale assente
    return ResetCommandOut(
        id=index,
        zone_id=zone_id,
        order_index=index,
        command_type=_TYPE_BY_LETTER[reset.command],
        if_flag=bool(a[0]),
        arg1=args[0],
        arg2=args[1],
        arg3=args[2],
        arg4=args[3],
        arg_str=arg_str,
    )


def reset_from(command: ResetCommandDraft | Any, index: int, comment: str = "") -> Reset:
    """Un `Reset` ROM da un comando del DTO (stessa semantica di `reset_out`); 422 se lo slot di `E` non esiste."""
    letter = _LETTER_BY_TYPE[command.command_type]
    one = lambda v, d=1: d if v is None else v  # noqa: E731
    flag = 1 if command.if_flag else 0
    if letter == "M":
        args = [flag, command.arg1, one(command.arg2), command.arg3, one(command.arg4)]
    elif letter == "O":
        args = [flag, command.arg1, one(command.arg2), command.arg3]
    elif letter == "P":
        args = [flag, command.arg1, one(command.arg2, -1), command.arg3, one(command.arg4)]
    elif letter == "G":
        args = [flag, command.arg1, one(command.arg2, -1)]
    elif letter == "E":
        slot = (command.arg_str or "").strip()
        if slot in _WEAR_LOC:
            wear = _WEAR_LOC.index(slot)
        elif slot.isdigit():
            wear = int(slot)
        else:
            raise api_error(422, "basedmud.reset_invalid_slot", loc=("body", "commands", index), slot=slot)
        args = [flag, command.arg1, one(command.arg2, -1), wear]
    elif letter == "D":
        args = [flag, command.arg1, command.arg2, _DOOR_STATE_REV.get((command.arg_str or "").upper(), 0)]
    else:
        args = [flag, command.arg1, one(command.arg2, 0)]
    return Reset(letter, [int(x) for x in args], comment)


def reset_key(reset: Reset) -> tuple[Any, ...]:
    """Identita' di un reset come lo vede il DTO (comando, argomenti, slot): per riconoscere quelli invariati in una
    sostituzione dello script anche quando ROM usa valori che il DTO normalizza (limite -1)."""
    out = reset_out(0, 0, reset)
    return out.command_type, out.if_flag, out.arg1, out.arg2, out.arg3, out.arg4, out.arg_str


def copy_reset(reset: Reset) -> Reset:
    """Copia indipendente di un reset (mantiene il testo sorgente: invariato = stessi byte)."""
    return copy.deepcopy(reset)


__all__ = [
    "EXIT_STRIDE", "EXTRA_DESC_STRIDE", "FLAG_TABLES", "ITEM_FROM_DTO", "ITEM_TO_DTO", "LIFESPAN_MINUTES",
    "MAX_LEVEL", "MOB_EXTRA_KEYS", "SECTOR_FROM_DTO", "SECTOR_TO_DTO", "SEX_FROM_DTO", "SEX_TO_DTO",
    "apply_extra", "apply_mob_fields", "apply_object_fields", "apply_room_extra", "apply_room_fields",
    "build_credits", "door_flag_out", "door_state_out", "exit_id", "exit_out", "extra_desc_out",
    "flags_from_names", "header_builder", "locks_from", "mob_extra_handlers", "mob_out", "new_mobile",
    "new_object", "object_extra_handlers", "object_out", "parse_credits", "reject_unsupported", "reset_from",
    "reset_key", "reset_out", "room_out", "sector_out", "shop_apply", "shop_out",
]  # fmt: skip
