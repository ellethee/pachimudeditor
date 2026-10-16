"""Conversioni pure tra il modello di `dikumod_lib` e i DTO neutri dell'editor.

Regole (come per BasedMud): cio' che ha un campo neutro va li', il resto in `extra`; un patch applica solo i campi
**diversi** dal valore corrente, quindi rimandare un DTO letto (con `extra`) non cambia nemmeno un byte del file.
`thac0` e' il valore del file (nel gioco `hitroll = 20 - thac0`), `armorClass` il valore `ac` del file (`armor = 10 * ac`).
"""

from __future__ import annotations

from typing import Any

from pachimudeditor_adapter_dikumod.dikumod_lib import Dice, Exit, ExtraDesc, Mob, Obj, ObjAffect, Room, Shop, Tele, ZoneCmd
from pachimudeditor_adapter_dikumod.dikumod_lib import tables as T
from pachifast.i18n import api_error
from pachimudeditor.common.enums import Sex
from pachimudeditor.common.enums import ObjectType
from pachimudeditor.common.enums import ZoneCommandType, ZoneResetMode
from pachimudeditor.common.enums import Direction, DoorFlag, SectorType

from pachimudeditor.sdk import rules
from pachimudeditor.common.adapters.models import (
    ExitOut,
    ExtraDescriptionOut,
    MobOut,
    ObjectOut,
    ResetCommandDraft,
    ResetCommandOut,
    RoomOut,
)

EXTRA_DESC_STRIDE = 1000
"""`id` di un'extra description di stanza = `vnum * 1000 + posizione`."""
EXIT_STRIDE = 10
"""`id` di un'uscita = `vnum_stanza * 10 + direzione`."""

EX_ISDOOR, EX_CLOSED, EX_LOCKED, EX_PICKPROOF = 1, 2, 4, 32

# --------------------------------------------------------------------------- errori e testi


def bad(code: str, **params: Any) -> Any:
    """422 con codice `dikumod.*`."""
    return api_error(422, code, **params)


def clean_text(value: str, *, newline: bool = False, lstrip: bool = False) -> str:
    """Testo per un campo `~`: niente `\\r`, niente `~` (422 `dikumod.unsafe_text`); `newline` forza il `\\n` finale."""
    text = value.replace("\r", "")
    if "~" in text:
        raise bad("dikumod.unsafe_text", reason="il carattere ~ non e' ammesso")
    if lstrip:
        text = text.lstrip()
    if newline and text and not text.endswith("\n"):
        text += "\n"
    return text


def view(text: str) -> str:
    """Il testo come lo vede l'API: senza il `\\n` finale che il gioco richiede (lo riaggiunge `clean_text(newline=True)`)."""
    return text[:-1] if text.endswith("\n") else text


def flags_from_names(table: str, names: list[str]) -> int:
    """Valore dei flag per nome; 422 `dikumod.unknown_flag` se un nome non esiste."""
    try:
        return T.names_to_flags(T.FLAG_TABLES[table], names)
    except KeyError as error:
        raise bad("dikumod.unknown_flag", table=table, name=str(error.args[0])) from error


def apply_extra(extra: dict[str, Any], handlers: dict[str, Any]) -> None:
    """Chiama `handlers[chiave](valore)` per ogni chiave; 422 `dikumod.extra_unknown` se non e' nota."""
    for key, value in extra.items():
        handler = handlers.get(key)
        if handler is None:
            raise bad("dikumod.extra_unknown", key=key, known=", ".join(sorted(handlers)))
        handler(value)


def _int(key: str, value: Any, lo: int | None = None, hi: int | None = None) -> int:
    """Intero (non bool) nei limiti, altrimenti 422 `dikumod.extra_invalid`."""
    if isinstance(value, bool) or not isinstance(value, int) or (lo is not None and value < lo) or (hi is not None and value > hi):
        raise bad("dikumod.extra_invalid", key=key)
    return value


def reject_unsupported(values: dict[str, Any], neutral: dict[str, Any]) -> None:
    """422 `dikumod.field_unsupported` se un campo che Diku Modificato non ha e' diverso dal valore neutro."""
    for key, base in neutral.items():
        if key in values and values[key] != base and not (base == [] and not values[key]):
            raise bad("dikumod.field_unsupported", field=key)


# --------------------------------------------------------------------------- stanze

SECTOR_TO_DTO: dict[int, SectorType] = {
    0: SectorType.INSIDE, 1: SectorType.CITY, 2: SectorType.FIELD, 3: SectorType.FOREST, 4: SectorType.HILLS,
    5: SectorType.MOUNTAIN, 6: SectorType.WATER_SWIM, 7: SectorType.WATER_NOSWIM, 8: SectorType.FLYING,
    9: SectorType.UNDERWATER, 10: SectorType.FIELD, 11: SectorType.FOREST, 12: SectorType.CITY,
}  # fmt: skip
"""Settore Diku Modificato -> `SectorType` (deserto/albero/citta' scura approssimati: il valore vero e' in `extra.sector`)."""
SECTOR_FROM_DTO: dict[SectorType, int] = {
    SectorType.INSIDE: 0, SectorType.CITY: 1, SectorType.FIELD: 2, SectorType.FOREST: 3, SectorType.HILLS: 4,
    SectorType.MOUNTAIN: 5, SectorType.WATER_SWIM: 6, SectorType.WATER_NOSWIM: 7, SectorType.FLYING: 8,
    SectorType.UNDERWATER: 9,
}  # fmt: skip


def sector_out(raw: int) -> SectorType:
    """`SectorType` per il settore Diku Modificato (fuori tabella: `INSIDE`)."""
    return SECTOR_TO_DTO.get(raw, SectorType.INSIDE)


def room_out(room: Room, zone_id: int, *, override: bool = False, duplicate: bool = False) -> RoomOut:
    """DTO neutro di una stanza."""
    extra: dict[str, Any] = {
        "sector": room.sector,
        "tele": None if room.tele is None else {
            "time": room.tele.time, "target": room.tele.target, "mask": room.tele.mask, "count": room.tele.count,
        },
        "river": None if room.river is None else {"speed": room.river[0], "dir": room.river[1]},
        "moblim": room.moblim,
        "light": None if room.light is None else {"night": view(room.light[0]), "day": view(room.light[1])},
        "zoneIgnored": room.zone_ignored,
        "source": "override" if override else "main",
    }  # fmt: skip
    if duplicate:
        extra["warning"] = "vnum doppio nel file: il gioco usa l'ultimo"
    if not -1 <= room.sector <= 12:
        extra["warning"] = f"settore fuori tabella ({room.sector})"
    return RoomOut(
        id=room.vnum, vnum=room.vnum, zone_id=zone_id, name=room.name, description=view(room.description),
        sector_type=sector_out(room.sector), flags=T.flag_names(T.ROOM_FLAGS, room.flags), heal_rate=100,
        mana_rate=100, clan_id=None, owner=None, extra=extra,
    )  # fmt: skip


def apply_room_fields(room: Room, values: dict[str, Any]) -> None:
    """Applica ai campi della stanza i soli valori (nomi Python del DTO) diversi dall'attuale."""
    reject_unsupported(values, {"heal_rate": 100, "mana_rate": 100, "clan_id": None, "owner": None})
    if "name" in values and values["name"] != room.name:
        room.name = clean_text(values["name"], lstrip=True)
    if "description" in values and values["description"] != view(room.description):
        room.description = clean_text(values["description"], newline=True)
    if "flags" in values and values["flags"] != T.flag_names(T.ROOM_FLAGS, room.flags):
        room.flags = flags_from_names("room_flags", values["flags"])
        if room.flags & 256 and room.moblim is None:
            room.moblim = 0
    if "sector_type" in values and SECTOR_TO_DTO.get(room.sector) != values["sector_type"]:
        set_sector(room, SECTOR_FROM_DTO[SectorType(values["sector_type"])])


def set_sector(room: Room, sector: int) -> None:
    """Imposta il settore vero (un fiume nasce con velocita'/direzione 0)."""
    room.sector = sector
    if sector in (7, 9) and room.river is None:
        room.river = (0, 0)


def room_extra_handlers(room: Room) -> dict[str, Any]:
    """Handler delle chiavi di `extra` di una stanza."""

    def sector(value: Any) -> None:
        """Settore Diku Modificato 0-12."""
        new = _int("sector", value, 0, len(T.SECTORS) - 1)
        if new != room.sector:
            set_sector(room, new)

    def tele(value: Any) -> None:
        """Blocco teleport `{time, target, mask, count}` o null."""
        if value is None:
            room.tele = None
            return
        if not isinstance(value, dict):
            raise bad("dikumod.extra_invalid", key="tele")
        mask = _int("tele.mask", value.get("mask", 0), 0)
        count = value.get("count")
        new = Tele(_int("tele.time", value.get("time", 0)), _int("tele.target", value.get("target", 0)), mask,
                   _int("tele.count", count, 0) if mask & 2 else None)  # fmt: skip
        if new != room.tele:
            room.tele = new

    def river(value: Any) -> None:
        """Fiume `{speed, dir}` o null (scritto solo con settore 7 o 9)."""
        if value is None:
            room.river = None
            return
        if not isinstance(value, dict):
            raise bad("dikumod.extra_invalid", key="river")
        new = (_int("river.speed", value.get("speed", 0)), _int("river.dir", value.get("dir", 0), 0, 5))
        if new != room.river:
            room.river = new

    def moblim(value: Any) -> None:
        """Limite di mob del tunnel (scritto solo con il flag `tunnel`)."""
        new = None if value is None else _int("moblim", value, 0)
        if new != room.moblim:
            room.moblim = new

    def light(value: Any) -> None:
        """Blocco `L` `{night, day}` o null."""
        if value is None:
            room.light = None
            return
        if not isinstance(value, dict):
            raise bad("dikumod.extra_invalid", key="light")
        new = (clean_text(str(value.get("night", "")), newline=True), clean_text(str(value.get("day", "")), newline=True))
        if room.light is None or tuple(view(t) for t in new) != tuple(view(t) for t in room.light):
            room.light = new

    def zone_ignored(value: Any) -> None:
        """Il numero di zona scritto nel file (il gioco lo scarta)."""
        new = _int("zoneIgnored", value)
        if new != room.zone_ignored:
            room.zone_ignored = new

    return {
        "sector": sector, "tele": tele, "river": river, "moblim": moblim, "light": light, "zoneIgnored": zone_ignored,
        "source": lambda v: None, "warning": lambda v: None,
    }  # fmt: skip


# --------------------------------------------------------------------------- uscite


def exit_id(room_vnum: int, door: int) -> int:
    """`id` di un'uscita."""
    return room_vnum * EXIT_STRIDE + door


def door_flag_out(info: int) -> DoorFlag:
    """`DoorFlag` dai bit di `exit_info` (senza `ISDOOR` nessuna porta)."""
    if not info & EX_ISDOOR:
        return DoorFlag.NONE
    return DoorFlag.PICKPROOF if info & EX_PICKPROOF else DoorFlag.CLOSABLE


def info_from(flag: DoorFlag, is_open: bool, is_locked: bool, old: int) -> int:
    """Nuovo `exit_info` per porta/stato, conservando gli altri bit (secret, notbash, ...)."""
    info = old & ~(EX_ISDOOR | EX_CLOSED | EX_LOCKED | EX_PICKPROOF)
    if flag is DoorFlag.NONE:
        return info
    info |= EX_ISDOOR | (EX_PICKPROOF if flag is DoorFlag.PICKPROOF else 0)
    if is_locked:
        info |= EX_CLOSED | EX_LOCKED
    elif not is_open:
        info |= EX_CLOSED
    return info


def door_state(info: int, d_state: int | None) -> tuple[bool, bool]:
    """`(is_open, is_locked)`: il comando `D` della zona, se c'e', prevale sui bit del file."""
    if d_state is not None:
        return d_state == 0, d_state == 2
    return not info & EX_CLOSED, bool(info & EX_LOCKED)


def exit_out(room_vnum: int, ex: Exit, names: dict[int, str], d_state: int | None) -> ExitOut:
    """DTO di un'uscita; `names` mappa vnum stanza -> nome."""
    is_open, is_locked = door_state(ex.info, d_state)
    target = ex.to_room if ex.to_room in names else None
    return ExitOut(
        id=exit_id(room_vnum, ex.door), room_id=room_vnum, direction=Direction(ex.door),
        description=view(ex.description) or None, keywords=ex.keyword or None, door_flag=door_flag_out(ex.info),
        is_open=is_open, is_locked=is_locked, key_vnum=ex.key if ex.key > 0 else None, target_room_id=target,
        target_room_vnum=ex.to_room if ex.to_room >= 0 else None, target_room_name=names.get(ex.to_room),
        extra={"exitInfo": ex.info, "openCmd": ex.open_cmd, "dState": d_state},
    )  # fmt: skip


def extra_desc_out(room_vnum: int, index: int, e: ExtraDesc) -> ExtraDescriptionOut:
    """DTO di un'extra description di stanza."""
    return ExtraDescriptionOut(id=room_vnum * EXTRA_DESC_STRIDE + index, room_id=room_vnum, keywords=e.keyword, text=view(e.description))


# --------------------------------------------------------------------------- mob

SEX_TO_DTO = {0: Sex.NEUTRAL, 1: Sex.MALE, 2: Sex.FEMALE}
SEX_FROM_DTO = {v: k for k, v in SEX_TO_DTO.items()}


def race_name(index: int | None) -> str | None:
    """Nome della razza (`None` se il mob non ha il campo razza)."""
    return None if index is None else T.type_name(T.RACES, index)


def race_index(name: str | None) -> int | None:
    """Indice di razza dal nome; 422 `dikumod.unknown_race` se non esiste."""
    if not name:
        return None
    key = name.strip().lower()
    if key in T.RACES:
        return T.RACES.index(key)
    if key.isdigit():
        return int(key)
    raise bad("dikumod.unknown_race", name=name)


def shop_out(shop: Shop | None) -> dict[str, Any] | None:
    """Il negozio del mob come dict."""
    if shop is None:
        return None
    return {
        "tag": shop.tag, "producing": list(shop.producing), "profitBuy": float(shop.profit_buy),
        "profitSell": float(shop.profit_sell), "types": list(shop.types),
        "messages": dict(zip(("noSuchItem1", "noSuchItem2", "doNotBuy", "missingCash1", "missingCash2", "messageBuy", "messageSell"), shop.messages)),
        "temper1": shop.temper1, "temper2": shop.temper2, "withWho": shop.with_who, "room": shop.room,
        "open1": shop.open1, "close1": shop.close1, "open2": shop.open2, "close2": shop.close2,
    }  # fmt: skip


_MSG_KEYS = ("noSuchItem1", "noSuchItem2", "doNotBuy", "missingCash1", "missingCash2", "messageBuy", "messageSell")


def shop_apply(shop: Shop, data: dict[str, Any]) -> None:
    """Imposta i campi di `shop` dal dict di `shop_out`."""
    if "producing" in data or "types" in data:
        for key, attr in (("producing", "producing"), ("types", "types")):
            if key in data:
                vals = data[key]
                if not isinstance(vals, list) or len(vals) > 5 or not all(isinstance(v, int) for v in vals):
                    raise bad("dikumod.extra_invalid", key=f"shop.{key}")
                setattr(shop, attr, (list(vals) + ([-1] if key == "producing" else [0]) * 5)[:5])
    for key, attr in (("profitBuy", "profit_buy"), ("profitSell", "profit_sell")):
        if key in data:
            try:
                new = float(data[key])
            except (TypeError, ValueError) as error:
                raise bad("dikumod.extra_invalid", key=f"shop.{key}") from error
            if new != float(getattr(shop, attr)):
                setattr(shop, attr, f"{new:g}")
    if "messages" in data:
        msgs = list(shop.messages)
        for i, key in enumerate(_MSG_KEYS):
            if key in data["messages"]:
                msgs[i] = clean_text(str(data["messages"][key]))
        shop.messages = msgs
    for key, attr in (("temper1", "temper1"), ("temper2", "temper2"), ("withWho", "with_who"), ("room", "room"),
                      ("open1", "open1"), ("close1", "close1"), ("open2", "open2"), ("close2", "close2")):  # fmt: skip
        if key in data:
            setattr(shop, attr, _int(f"shop.{key}", data[key]))


def mob_out(mob: Mob, zone_id: int, shop: Shop | None, script: dict[str, Any] | None, *, duplicate: bool = False) -> MobOut:
    """DTO neutro di un mob. hp: `S` = dado del file; `A/N/B/L` = `level d8 + bonus`."""
    if mob.hp_dice is not None:
        hp = (mob.hp_dice.n, mob.hp_dice.m, mob.hp_dice.k)
    else:
        hp = (mob.level, 8, mob.hp_bonus)
    extra: dict[str, Any] = {
        "kind": mob.kind, "multiAttack": mob.multi, "affectedBy": T.flag_names(T.AFFECT_FLAGS, mob.affected),
        "position": mob.position, "defaultPos": mob.default_pos, "sexCode": mob.sex_code,
        "immune": T.flag_names(T.IMMUNE_FLAGS, mob.immune), "mImmune": T.flag_names(T.IMMUNE_FLAGS, mob.m_immune),
        "susc": T.flag_names(T.IMMUNE_FLAGS, mob.susc), "sound": mob.sound, "distantSound": mob.distant_sound,
        "expRaw": mob.exp, "shop": shop_out(shop), "script": script, "trailing": mob.trailing,
    }  # fmt: skip
    if duplicate:
        extra["warning"] = "vnum doppio nel file"
    return MobOut(
        id=mob.vnum, vnum=mob.vnum, zone_id=zone_id, keywords=mob.name, short_description=mob.short,
        long_description=view(mob.long), detailed_description=view(mob.description), level=mob.level, thac0=mob.thac0,
        armor_class=mob.ac, hp_dice_count=hp[0], hp_die_size=hp[1], hp_bonus=hp[2], damage_dice_count=mob.damage.n,
        damage_die_size=mob.damage.m, damage_bonus=mob.damage.k, gold=mob.gold, experience=max(mob.exp, 0),
        sex=SEX_TO_DTO.get(mob.sex, Sex.NEUTRAL), flags=T.flag_names(T.ACT_FLAGS, mob.act), race_id=race_name(mob.race),
        class_id=None, alignment=mob.alignment, debuff_skill_id=None, shop_id=None, quest_ids=[], is_banker=False,
        teaches_class_ids=None, teaches_skill_ids=None, extra=extra,
    )  # fmt: skip


def corrupted_mob_out(vnum: int, src: str, error: str, line: int, zone_id: int) -> MobOut:
    """Segnaposto per un record corrotto (visibile ma non modificabile): nomi dal testo grezzo, dati neutri."""
    parts = src.split("~")
    name = parts[0].split("\n", 1)[1].strip() if "\n" in parts[0] else ""
    short = parts[1].strip() if len(parts) > 1 else ""
    return MobOut(
        id=vnum, vnum=vnum, zone_id=zone_id, keywords=name or f"#{vnum}", short_description=short or f"#{vnum} (corrotto)",
        long_description="", detailed_description="", level=0, thac0=0, armor_class=0, hp_dice_count=0, hp_die_size=0,
        hp_bonus=0, damage_dice_count=0, damage_die_size=0, damage_bonus=0, gold=0, experience=0, sex=Sex.NEUTRAL,
        flags=[], race_id=None, class_id=None, alignment=0, debuff_skill_id=None, shop_id=None, quest_ids=[],
        is_banker=False, teaches_class_ids=None, teaches_skill_ids=None,
        extra={"corrupted": True, "warning": error, "line": line, "raw": src},
    )  # fmt: skip


MOB_UNSUPPORTED: dict[str, Any] = {
    "class_id": None, "debuff_skill_id": None, "shop_id": None, "quest_ids": [], "is_banker": False,
    "teaches_class_ids": None, "teaches_skill_ids": None,
}  # fmt: skip


def apply_mob_fields(mob: Mob, values: dict[str, Any]) -> None:
    """Applica al mob i soli valori (nomi Python del DTO) diversi dall'attuale."""
    reject_unsupported(values, MOB_UNSUPPORTED)
    for key, attr, kwargs in (
        ("keywords", "name", {}), ("short_description", "short", {}), ("long_description", "long", {"newline": True}),
        ("detailed_description", "description", {"newline": True}),
    ):  # fmt: skip
        current = view(getattr(mob, attr)) if kwargs else getattr(mob, attr)
        if key in values and current != values[key]:
            setattr(mob, attr, clean_text(values[key], **kwargs))
    for key, attr in (("level", "level"), ("thac0", "thac0"), ("armor_class", "ac"), ("gold", "gold"), ("alignment", "alignment")):
        if key in values and getattr(mob, attr) != values[key]:
            setattr(mob, attr, values[key])
    if "experience" in values and max(mob.exp, 0) != values["experience"]:
        mob.exp = values["experience"]
    # hp: `S` = dado del file; `A/N/B/L` = level d8 + bonus (dado derivato: deve restare coerente)
    hp = {k: values[k] for k in ("hp_dice_count", "hp_die_size", "hp_bonus") if k in values}
    if hp:
        if mob.hp_dice is not None:
            d = mob.hp_dice
            new = Dice(hp.get("hp_dice_count", d.n), hp.get("hp_die_size", d.m), hp.get("hp_bonus", d.k))
            if new != d:
                mob.hp_dice = new
        else:
            if hp.get("hp_dice_count", mob.level) != mob.level or hp.get("hp_die_size", 8) != 8:
                raise bad("dikumod.hp_not_dice", level=mob.level)
            if "hp_bonus" in hp:
                mob.hp_bonus = hp["hp_bonus"]
    dmg = mob.damage
    new_dmg = Dice(values.get("damage_dice_count", dmg.n), values.get("damage_die_size", dmg.m), values.get("damage_bonus", dmg.k))
    if new_dmg != dmg:
        mob.damage = new_dmg
    if "sex" in values and SEX_TO_DTO.get(mob.sex) != values["sex"]:
        if values["sex"] not in SEX_FROM_DTO:
            raise bad("dikumod.field_unsupported", field="sex")
        new_sex = SEX_FROM_DTO[Sex(values["sex"])]
        mob.sex_code = new_sex + 3 if 3 <= mob.sex_code < 6 else new_sex
    if "flags" in values and values["flags"] != T.flag_names(T.ACT_FLAGS, mob.act):
        mob.act = flags_from_names("act_flags", values["flags"])
    if "race_id" in values and race_name(mob.race) != (values["race_id"] or None):
        mob.race = race_index(values["race_id"])


def _mask_setter(mob: Mob, attr: str):  # type: ignore[no-untyped-def]
    """Handler di `extra` per una maschera di immunita' (promuove il codice sesso a 3..5 se serve)."""

    def apply(value: Any) -> None:
        """Imposta la maschera dai nomi."""
        if not isinstance(value, list):
            raise bad("dikumod.extra_invalid", key=attr)
        new = flags_from_names("immune_flags", value)
        if new != getattr(mob, attr):
            setattr(mob, attr, new)
            if new and mob.sex_code < 3:
                mob.sex_code += 3  # solo con codice 3..5 il gioco legge le maschere

    return apply


def mob_extra_handlers(mob: Mob, shop_cb: Any, script_cb: Any) -> dict[str, Any]:
    """Handler delle chiavi di `extra` di un mob (`shop_cb`/`script_cb` toccano gli altri file)."""

    def kind(value: Any) -> None:
        """Tipo di record; non si passa da/verso `S` (cambierebbe il significato degli hp)."""
        if value not in ("S", "A", "N", "B", "L") or (value == "S") != (mob.kind == "S"):
            raise bad("dikumod.kind_change", kind=str(value))
        if value != mob.kind:
            mob.kind = value
            if value in ("A", "B", "L") and mob.multi is None:
                mob.multi = 1
            if value == "L":
                mob.sound = mob.sound or "\n"
                mob.distant_sound = mob.distant_sound or ""

    def simple(attr: str, key: str, lo: int | None = None):  # type: ignore[no-untyped-def]
        """Handler per un intero."""

        def apply(value: Any) -> None:
            """Assegna l'intero se cambia."""
            new = _int(key, value, lo)
            if getattr(mob, attr) != new:
                setattr(mob, attr, new)

        return apply

    def multi(value: Any) -> None:
        """Numero di attacchi (solo `A/B/L`)."""
        if value is None:
            return
        new = _int("multiAttack", value, 0)
        if mob.kind in ("A", "B", "L") and mob.multi != new:
            mob.multi = new

    def affected(value: Any) -> None:
        """Affect flag dai nomi."""
        if not isinstance(value, list):
            raise bad("dikumod.extra_invalid", key="affectedBy")
        new = flags_from_names("affect_flags", value)
        if new != mob.affected:
            mob.affected = new

    def text(attr: str, key: str):  # type: ignore[no-untyped-def]
        """Handler per un suono (solo `L`)."""

        def apply(value: Any) -> None:
            """Assegna il testo (il suono principale conserva il `\\n` iniziale che il gioco vi legge)."""
            if value is None:
                return
            new = clean_text(str(value))
            if key == "sound" and new and not new.startswith("\n"):
                new = "\n" + new
            if getattr(mob, attr) != new and mob.kind == "L":
                setattr(mob, attr, new)

        return apply

    def exp_raw(value: Any) -> None:
        """Esperienza grezza del file (negativa = fissa)."""
        new = _int("expRaw", value)
        if new != mob.exp:
            mob.exp = new

    def readonly(key: str, current: Any):  # type: ignore[no-untyped-def]
        """Accetta solo il valore corrente."""

        def check(value: Any) -> None:
            """422 se diverso."""
            if value != current:
                raise bad("dikumod.extra_readonly", key=key)

        return check

    return {
        "kind": kind, "multiAttack": multi, "affectedBy": affected, "position": simple("position", "position", 0),
        "defaultPos": simple("default_pos", "defaultPos", 0), "sexCode": readonly("sexCode", mob.sex_code),
        "immune": _mask_setter(mob, "immune"), "mImmune": _mask_setter(mob, "m_immune"), "susc": _mask_setter(mob, "susc"),
        "sound": text("sound", "sound"), "distantSound": text("distant_sound", "distantSound"), "expRaw": exp_raw,
        "shop": shop_cb, "script": script_cb, "trailing": readonly("trailing", mob.trailing),
        "warning": lambda v: None, "corrupted": lambda v: None, "raw": lambda v: None, "line": lambda v: None,
    }  # fmt: skip


def new_mob(vnum: int, values: dict[str, Any]) -> Mob:
    """Un mob nuovo (`N`, o `S` se i dadi hp non sono `level d8`) con i campi di `MobIn`."""
    mob = Mob(vnum=vnum, kind="N", level=values.get("level", 1), position=8, default_pos=8)
    if values.get("hp_dice_count", mob.level) != mob.level or values.get("hp_die_size", 8) != 8:
        mob.kind = "S"
        mob.hp_dice = Dice(values["hp_dice_count"], values["hp_die_size"], values.get("hp_bonus", 0))
        values = {k: v for k, v in values.items() if not k.startswith("hp_")}
    mob.damage = Dice(1, 4, 0)
    apply_mob_fields(mob, values)
    return mob


# --------------------------------------------------------------------------- oggetti

ITEM_TO_DTO: dict[int, ObjectType] = {
    1: ObjectType.LIGHT, 2: ObjectType.SCROLL, 3: ObjectType.WAND, 4: ObjectType.STAFF, 5: ObjectType.WEAPON,
    8: ObjectType.TREASURE, 9: ObjectType.ARMOR, 10: ObjectType.POTION, 12: ObjectType.OTHER, 13: ObjectType.TRASH,
    15: ObjectType.CONTAINER, 17: ObjectType.LIQUID_CONTAINER, 18: ObjectType.KEY, 19: ObjectType.FOOD,
    20: ObjectType.MONEY,
}  # fmt: skip
ITEM_FROM_DTO: dict[ObjectType, int] = {v: k for k, v in ITEM_TO_DTO.items()} | {ObjectType.FOUNTAIN: 17}
"""Tipo oggetto Diku Modificato <-> `ObjectType`. I tipi senza equivalente (6, 7, 11, 14, 16, 21-26, 0) sono `OTHER`; il vero e' in `extra.typeRaw`."""


def object_affects(obj: Obj) -> dict[str, int]:
    """Gli affect come `{nome_apply: somma}` (l'elenco completo e ordinato e' in `extra.affects`)."""
    out: dict[str, int] = {}
    for a in obj.affects:
        key = T.type_name(T.APPLY_TYPES, a.location)
        out[key] = out.get(key, 0) + a.modifier
    return out


def _apply_location(key: str) -> int:
    """Numero di apply da un nome della tabella (o un intero scritto come stringa)."""
    if key in T.APPLY_TYPES:
        return T.APPLY_TYPES.index(key)
    if key.lstrip("-").isdigit():
        return int(key)
    raise bad("dikumod.extra_invalid", key=f"affects.{key}")


def object_out(obj: Obj, zone_id: int, *, override: bool = False, duplicate: bool = False) -> ObjectOut:
    """DTO neutro di un oggetto."""
    extra: dict[str, Any] = {
        "typeRaw": obj.type,
        "affects": [
            {"location": a.location, "name": T.type_name(T.APPLY_TYPES, a.location), "modifier": a.modifier} for a in obj.affects
        ],
        "extraDescs": [{"keyword": e.keyword, "description": view(e.description)} for e in obj.extra_descs],
        "forbiddenWear": None if obj.forbidden is None else {"toChar": view(obj.forbidden[0]), "toRoom": view(obj.forbidden[1])},
        "source": "override" if override else "main",
    }  # fmt: skip
    if duplicate:
        extra["warning"] = "vnum doppio nel file"
    v = (list(obj.values) + [0] * 4)[:4]
    return ObjectOut(
        id=obj.vnum, vnum=obj.vnum, zone_id=zone_id, keywords=obj.name, short_description=obj.short,
        long_description=view(obj.description), action_description=view(obj.action) or None,
        object_type=ITEM_TO_DTO.get(obj.type, ObjectType.OTHER), weight=obj.weight, cost=obj.cost, rent=obj.rent,
        value_0=v[0], value_1=v[1], value_2=v[2], value_3=v[3],
        extra_flags=T.flag_names(T.EXTRA_FLAGS, obj.extra_flags), wear_flags=T.flag_names(T.WEAR_FLAGS, obj.wear_flags),
        affects=object_affects(obj), extra=extra,
    )  # fmt: skip


def apply_object_fields(obj: Obj, values: dict[str, Any]) -> None:
    """Applica all'oggetto i soli valori (nomi Python del DTO) diversi dall'attuale."""
    for key, attr, kw in (
        ("keywords", "name", {}), ("short_description", "short", {}), ("long_description", "description", {"newline": True}),
    ):  # fmt: skip
        current = view(getattr(obj, attr)) if kw else getattr(obj, attr)
        if key in values and current != values[key]:
            setattr(obj, attr, clean_text(values[key], **kw))
    if "action_description" in values and (values["action_description"] or "") != view(obj.action):
        obj.action = clean_text(values["action_description"] or "", newline=True)
    for key, attr in (("weight", "weight"), ("cost", "cost"), ("rent", "rent")):
        if key in values and getattr(obj, attr) != values[key]:
            setattr(obj, attr, values[key])
    if "object_type" in values and ITEM_TO_DTO.get(obj.type, ObjectType.OTHER) != values["object_type"]:
        obj.type = ITEM_FROM_DTO[ObjectType(values["object_type"])]
    for i in range(4):
        key = f"value_{i}"
        if key in values:
            new = 0 if values[key] is None else values[key]
            if obj.values[i] != new:
                obj.values[i] = new
    for key, attr, table in (("extra_flags", "extra_flags", "extra_flags"), ("wear_flags", "wear_flags", "wear_flags")):
        if key in values and values[key] != T.flag_names(T.FLAG_TABLES[table], getattr(obj, attr)):
            setattr(obj, attr, flags_from_names(table, values[key]))
    if "affects" in values and values["affects"] != object_affects(obj):
        affects = [ObjAffect(_apply_location(k), int(v)) for k, v in values["affects"].items()]
        if len(affects) > 5:
            raise bad("dikumod.too_many_affects")
        obj.affects = affects


def object_extra_handlers(obj: Obj) -> dict[str, Any]:
    """Handler delle chiavi di `extra` di un oggetto."""

    def type_raw(value: Any) -> None:
        """Tipo Diku Modificato grezzo (0-26)."""
        new = _int("typeRaw", value, 0)
        if new != obj.type:
            obj.type = new

    def affects(value: Any) -> None:
        """Elenco ordinato di affect `{location, modifier}` (max 5)."""
        if not isinstance(value, list) or len(value) > 5:
            raise bad("dikumod.too_many_affects" if isinstance(value, list) else "dikumod.extra_invalid", key="affects")
        try:
            new = [ObjAffect(_int("affects.location", v["location"]), _int("affects.modifier", v["modifier"])) for v in value]
        except (KeyError, TypeError) as error:
            raise bad("dikumod.extra_invalid", key="affects") from error
        if new != obj.affects:
            obj.affects = new

    def extra_descs(value: Any) -> None:
        """Extra description dell'oggetto."""
        if not isinstance(value, list):
            raise bad("dikumod.extra_invalid", key="extraDescs")
        try:
            new = [ExtraDesc(clean_text(str(v["keyword"])), clean_text(str(v["description"]), newline=True)) for v in value]
        except (KeyError, TypeError) as error:
            raise bad("dikumod.extra_invalid", key="extraDescs") from error
        if [(e.keyword, view(e.description)) for e in new] != [(e.keyword, view(e.description)) for e in obj.extra_descs]:
            obj.extra_descs = new

    def forbidden(value: Any) -> None:
        """Messaggi `P` `{toChar, toRoom}` o null."""
        if value is None:
            obj.forbidden = None
            return
        try:
            new = (clean_text(str(value["toChar"]), newline=True), clean_text(str(value["toRoom"]), newline=True))
        except (KeyError, TypeError) as error:
            raise bad("dikumod.extra_invalid", key="forbiddenWear") from error
        if obj.forbidden is None or tuple(view(t) for t in new) != tuple(view(t) for t in obj.forbidden):
            obj.forbidden = new

    return {
        "typeRaw": type_raw, "affects": affects, "extraDescs": extra_descs, "forbiddenWear": forbidden,
        "source": lambda v: None, "warning": lambda v: None,
    }  # fmt: skip


def new_object(vnum: int, values: dict[str, Any]) -> Obj:
    """Un oggetto nuovo (tipo OTHER) con i campi di `ObjectIn`."""
    obj = Obj(vnum=vnum, type=12)
    apply_object_fields(obj, values)
    return obj


# --------------------------------------------------------------------------- reset

_TYPE_BY_LETTER: dict[str, Any] = {
    "M": ZoneCommandType.LOAD_MOB, "O": ZoneCommandType.LOAD_OBJECT, "G": ZoneCommandType.GIVE_OBJECT,
    "E": ZoneCommandType.EQUIP_OBJECT, "P": ZoneCommandType.PUT_OBJECT, "D": ZoneCommandType.SET_DOOR_STATE,
    "C": rules.CHARM_MOB, "H": rules.SET_HATE, "F": rules.SET_FEAR, "Z": rules.SET_MOB_ZONE,
}  # fmt: skip
_LETTER_BY_TYPE: dict[Any, str] = {v: k for k, v in _TYPE_BY_LETTER.items()}
_SLOTS: dict[str, tuple[int | None, int | None, int | None, int | None]] = {
    "M": (0, 1, 2, None), "O": (0, 1, 2, 3), "G": (0, 1, None, None), "E": (0, 1, None, None), "P": (0, 1, 2, None),
    "D": (0, 1, None, None), "C": (0, 1, 2, None), "H": (0, 1, None, None), "F": (0, 1, None, None), "Z": (0, 1, None, None),
}  # fmt: skip
"""Per ogni comando: indici in `ZoneCmd.args` di arg1..arg4 del DTO (`None` = non presente nel file)."""


def reset_out(zone_id: int, index: int, cmd: ZoneCmd) -> ResetCommandOut:
    """DTO di un comando (`id` = `orderIndex` = posizione tra i soli comandi).

    M mob/max/stanza; O oggetto/max/stanza/max in stanza; G oggetto/max; E oggetto/max + `argStr` slot (`wear_positions`);
    P oggetto/max/contenitore; D stanza/direzione + `argStr` OPEN/CLOSED/LOCKED; C mob/max/bit act; H, F tipo/valore;
    Z zona/flag. `max` 0 = nessun limite (come nel gioco)."""
    a = list(cmd.args) + [0] * 5
    slots = _SLOTS[cmd.letter]
    args = [a[i] if i is not None else None for i in slots]
    arg_str: str | None = None
    if cmd.letter == "E":
        arg_str = T.type_name(T.WEAR_POSITIONS, a[2])
    elif cmd.letter == "D":
        arg_str = T.DOOR_STATES[a[2]] if 0 <= a[2] < 3 else str(a[2])
    return ResetCommandOut(
        id=index, zone_id=zone_id, order_index=index, command_type=_TYPE_BY_LETTER[cmd.letter], if_flag=cmd.if_flag > 0,
        arg1=args[0], arg2=args[1], arg3=args[2], arg4=args[3], arg_str=arg_str, if_value=cmd.if_flag,
        comment=cmd.comment_text or None,
        extra={"letter": cmd.letter, **({"missingArg4": True} if cmd.letter == "O" and len(cmd.args) < 4 else {})},
    )  # fmt: skip


def reset_from(command: ResetCommandDraft | Any, index: int, old_comment: ZoneCmd | None = None) -> ZoneCmd:
    """Un `ZoneCmd` da un comando del DTO (stessa semantica di `reset_out`); 422 se lo slot di `E` non esiste."""
    letter = _LETTER_BY_TYPE[command.command_type]
    one = lambda v, d=0: d if v is None else v  # noqa: E731
    flag = command.if_value if command.if_value is not None else int(bool(command.if_flag))
    if letter == "M":
        args = [command.arg1, one(command.arg2, 1), command.arg3]
    elif letter == "O":
        args = [command.arg1, one(command.arg2, 1), command.arg3, one(command.arg4, 0)]
    elif letter == "P":
        args = [command.arg1, one(command.arg2), command.arg3]
    elif letter == "G":
        args = [command.arg1, one(command.arg2)]
    elif letter == "E":
        slot = (command.arg_str or "").strip().lower()
        if slot in T.WEAR_POSITIONS:
            wear = T.WEAR_POSITIONS.index(slot)
        elif slot.isdigit():
            wear = int(slot)
        else:
            raise bad("dikumod.reset_invalid_slot", loc=("body", "commands", index), slot=slot)
        args = [command.arg1, one(command.arg2), wear]
    elif letter == "D":
        state = {"OPEN": 0, "CLOSED": 1, "LOCKED": 2}.get((command.arg_str or "").upper(), 0)
        args = [command.arg1, command.arg2, state]
    elif letter == "C":
        args = [command.arg1, one(command.arg2, 1), one(command.arg3)]
    else:  # H, F, Z
        args = [command.arg1, one(command.arg2)]
    text = (command.comment or "").strip().replace("\n", " ").replace("\r", "")
    comment = f"   ; {text}" if text else ""
    if old_comment is not None and old_comment.comment_text == text:
        comment = old_comment.comment
    return ZoneCmd(letter, flag, [int(x) for x in args], comment)


def reset_key(out: ResetCommandOut) -> tuple[Any, ...]:
    """Identita' di un comando come lo vede il DTO (per riconoscere quelli invariati in una sostituzione dello script)."""
    return out.command_type, out.if_value, out.arg1, out.arg2, out.arg3, out.arg4, out.arg_str, out.comment


def reset_mode_out(raw: int) -> ZoneResetMode:
    """`ZoneResetMode` dai bit di `reset_mode` (2 sempre, 1 solo se vuota, altrimenti mai)."""
    if raw & 2:
        return ZoneResetMode.ALWAYS
    return ZoneResetMode.EMPTY if raw & 1 else ZoneResetMode.NEVER


def reset_mode_in(raw: int, mode: ZoneResetMode) -> int:
    """Nuovi bit di `reset_mode` per `mode`, conservando i bit 4/8/16/32."""
    if reset_mode_out(raw) == mode:
        return raw
    return (raw & ~3) | int(mode)
