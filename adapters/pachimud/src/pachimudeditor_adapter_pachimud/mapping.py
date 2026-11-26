"""Conversioni tra le voci YAML del gioco pachimud e i DTO neutri dell'editor (e scrittura sulle voci ruamel).

Convenzioni degli `id`: zona = `vnum` di `zone.yaml`; stanza/mob/oggetto = `vnum`; uscita = `vnum * 10 + direzione`;
extra description = `vnum * 1000 + posizione` nella lista della stanza; comando di reset = posizione nello script.

Cio' che non ha un campo neutro sta in `extra` (vedi `fields.py`): `area` (testo vuoto = nessuna) e `enabled` delle stanze, le sei statistiche dei
mob, i campi specifici del tipo di un oggetto (`typeFields`, con i nomi snake_case del file) ecc. Dei `value_0..3` degli
oggetti si leggono e scrivono solo quelli numerici (`VALUE_SLOTS`, indici di LeU).
"""

import re
from typing import Any

from pachifast.i18n import api_error
from pydantic import ValidationError

from pachimudeditor.common.adapters.models import (
    ExitOut,
    ExtraDescriptionOut,
    MobOut,
    ObjectOut,
    RoomOut,
    ZoneOut,
)
from pachimudeditor.common.enums import Direction, DoorFlag, ObjectType, SectorType, Sex, ZoneResetMode
from pachimudeditor_adapter_pachimud.apps.content.yaml_store import _as_scalar, _same
from pachimudeditor_adapter_pachimud.loaders import (
    COMMON_OBJECT_FIELDS,
    TYPE_MODELS,
    OBJECT_ADAPTER,
    join_dice,
    split_dice,
    type_fields,
)
from pachimudeditor_adapter_pachimud import simple_extra
from pachimudeditor_adapter_pachimud.store import Item, ZoneEntry, plain

EXIT_STRIDE = 10
EXTRA_DESC_STRIDE = 1000
STATS = ("strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma")

VALUE_SLOTS: dict[str, dict[str, int]] = {
    "LIGHT": {"hours": 2},
    "SCROLL": {"level": 0},
    "POTION": {"level": 0},
    "WAND": {"level": 0, "max_charges": 1, "charges": 2},
    "STAFF": {"level": 0, "max_charges": 1, "charges": 2},
    "WEAPON": {"dice_count": 1, "die_size": 2, "weapon_type": 3},
    "FIREWEAPON": {"strength": 0, "range_bonus": 2, "ammo_type": 3},
    "MISSILE": {"break_chance": 0, "dice_count": 1, "die_size": 2, "ammo_type": 3},
    "ARMOR": {"armor_class": 0},
    "CONTAINER": {"max_weight": 0, "key_vnum": 2, "corpse": 3},
    "TRAP": {"level": 2, "charges": 3},
    "DRINKCON": {"capacity": 0, "units": 1, "poisoned": 3},
    "FOOD": {"hours": 0, "poisoned": 3},
    "MONEY": {"gold": 0},
    "KEY": {"key_type": 0},
    "AUDIO": {"frequency": 0},
}
"""Tipo -> campo numerico del file -> indice del `value` di LeU (i campi con stringhe, come incantesimi e liquido, non hanno slot)."""


# --------------------------------------------------------------------------- tipi oggetto


BOOL_FIELDS = frozenset({"poisoned", "corpse"})
"""Campi booleani con uno slot numerico (0/1)."""


def type_name(object_type: ObjectType) -> str:
    """Il nome `object_type` del file per un `ObjectType` (`LIQUID_CONTAINER` e' `DRINKCON` nel gioco)."""
    return "DRINKCON" if object_type == ObjectType.LIQUID_CONTAINER else object_type.name


def type_enum(name: str) -> ObjectType:
    """L'`ObjectType` per il nome del file."""
    return ObjectType.LIQUID_CONTAINER if name == "DRINKCON" else ObjectType[name]


# --------------------------------------------------------------------------- scrittura generica


def to_commented(value: Any) -> Any:
    """Copia di `value` (dict/liste annidati) con i dict come `CommentedMap`, pronta per essere scritta nel file."""
    from ruamel.yaml.comments import CommentedMap

    if isinstance(value, dict):
        out = CommentedMap()
        for key, item in value.items():
            out[key] = to_commented(item)
        return out
    if isinstance(value, list):
        return [to_commented(item) for item in value]
    return value


def shop_value(raw_shop: Any) -> Any:
    """Il campo `extra.shop` come va scritto nel file: validato con `LoaderShop` (422 `pachimud.invalid_entry` se non valido) e
    ridotto ai soli campi diversi dal default (`None`/vuoto: il mob non e' un negoziante)."""
    from pachimudeditor_adapter_pachimud.loaders import LoaderShop

    if raw_shop in (None, {}):
        return None
    if not isinstance(raw_shop, dict):
        raise api_error(422, "pachimud.invalid_entry", detail="shop: atteso un oggetto")
    try:
        shop = LoaderShop.model_validate(raw_shop)
    except ValidationError as error:
        raise invalid(error) from error
    return to_commented(shop.model_dump(exclude_defaults=True))


def trigger_out(item: Any) -> dict[str, Any]:
    """Un trigger letto dal file come lo vede il client: `block` compare solo se vero (e' falso quasi sempre)."""
    return item.model_dump(by_alias=True, exclude_none=True, exclude=None if item.block else {"block"})


def _trigger_dump(item: Any) -> dict[str, Any]:
    """Un trigger validato come dizionario del file: solo i campi diversi dal default (`type` e `actions` restano), `if`/`else`/`class` con il nome del file."""
    return item.model_dump(exclude_defaults=True, by_alias=True)


def _mp_verb(actions: list[Any]) -> str | None:
    """Il primo comando che oggetti e stanze non possono usare (mpgoto, mpkill, mpforce, mppurge self) tra le azioni, anche dentro gli `if`/`else`."""
    from pachimudeditor_adapter_pachimud.loaders import MOB_ONLY_MP, LoaderIfBlock

    for a in actions:
        if isinstance(a, LoaderIfBlock):
            if verb := _mp_verb([*a.then, *a.else_]):
                return verb
        elif (word := a.split()[0]) in MOB_ONLY_MP or a.split()[:2] == ["mppurge", "self"]:
            return word
    return None


def triggers_value(raw_triggers: Any, current: Any = None, owner: str = "mob", field: str = "triggers") -> Any:
    """Il campo `triggers` di un mob/stanza (o `scripts` di un oggetto) come va scritto nel file: lista validata con `LoaderTrigger`
    (422 `pachimud.invalid_choice|range|length` sul campo, es. `triggers[0].chance`; `invalid_choice` anche per un tipo che `owner`
    non ammette), ridotta ai soli campi diversi dal default. Ogni trigger equivalente a quello gia' nel file (`current`, anche con i
    default scritti a mano) resta quello (commenti e formato intatti); se sono tutti uguali restituisce `current`: nessun diff."""
    from pydantic import TypeAdapter

    from pachimudeditor_adapter_pachimud.loaders import OWNER_TYPES, LoaderTrigger

    adapter = TypeAdapter(list[LoaderTrigger])
    if raw_triggers is None:
        raw_triggers = []
    if not isinstance(raw_triggers, list):
        raise api_error(422, "pachimud.invalid_entry", detail=f"{field}: attesa una lista")
    try:
        items = adapter.validate_python(raw_triggers)
    except ValidationError as error:
        raise invalid(error, field) from error
    old: list[Any] = []
    try:
        old = adapter.validate_python(plain(current)) if current is not None else []
    except ValidationError:  # il file ha gia' un valore non valido: si riscrive
        pass
    same = [n < len(old) and i.model_dump() == old[n].model_dump() for n, i in enumerate(items)]
    if all(same) and len(items) == len(old) and current is not None:
        return current
    for n, i in enumerate(items):
        if not same[n] and i.type not in OWNER_TYPES[owner]:
            raise api_error(422, "pachimud.invalid_choice", field=f"{field}[{n}].type", limit=", ".join(OWNER_TYPES[owner]))
        if not same[n] and owner != "mob" and (verb := _mp_verb(i.actions)):
            raise api_error(
                422,
                "pachimud.invalid_entry",
                detail=f"{field}[{n}]: il comando '{verb}' non e' ammesso a oggetti e stanze (solo i mob usano mpgoto, mpkill, mpforce e mppurge self)",
            )
    return [current[n] if same[n] else to_commented(_trigger_dump(i)) for n, i in enumerate(items)]


def apply_triggers(raw: Any, value: Any, owner: str, key: str) -> None:
    """Scrive i trigger (`key` e' `triggers`, o `scripts` per gli oggetti) nella voce: un valore uguale lascia il file com'e', svuotati
    la chiave sparisce."""
    new = triggers_value(value, raw.get(key), owner, key)
    if not new and raw.get(key):
        del raw[key]
    else:
        put(raw, key, new, default=[])


def put(raw: Any, key: str, value: Any, *, default: Any = None, required: bool = False) -> None:
    """Scrive `raw[key] = value` toccando solo cio' che cambia: `None` toglie la chiave, un valore uguale al default non
    aggiunge rumore (salvo `required`), un valore invariato lascia intatti commenti e formato."""
    if value is None and not required:
        raw.pop(key, None)
    elif key in raw:
        if not _same(raw[key], value):
            raw[key] = _as_scalar(value) if not isinstance(value, list) else list(value)
    elif required or default is None or not _same(default, value):
        raw[key] = _as_scalar(value) if not isinstance(value, list) else list(value)


def new_map(pairs: dict[str, Any]) -> Any:
    """Un `CommentedMap` con le chiavi in ordine, i testi multilinea come blocchi letterali."""
    from ruamel.yaml.comments import CommentedMap

    out = CommentedMap()
    for key, value in pairs.items():
        out[key] = _as_scalar(value) if not isinstance(value, list) else list(value)
    return out


_INVALID_LIMITS = {
    "gt": ">",
    "ge": "≥",
    "lt": "<",
    "le": "≤",
    "min_length": "lunghezza ≥",
    "max_length": "lunghezza ≤",
    "multiple_of": "multiplo di",
}
"""Chiavi di `ctx` (pydantic) che descrivono un limite numerico o di lunghezza, col simbolo con cui si mostrano (uguale in it/en)."""


def _where(loc: tuple[Any, ...]) -> str:
    """Il percorso di un errore pydantic come `triggers[0].chance` (indice di lista tra parentesi, base 0)."""
    loc = tuple(p for p in loc if p not in ("str", "block"))  # etichette dell'unione delle azioni
    return "".join(f"[{p}]" if isinstance(p, int) else f"{'.' if i else ''}{p}" for i, p in enumerate(loc))


def invalid(error: ValidationError, prefix: str = "") -> Exception:
    """422 sul primo errore del loader, con testo it/en per i casi comuni di pydantic (campo mancante, tipo, intervallo, lunghezza, scelta,
    campo non ammesso): `pachimud.invalid_missing|type|range|length|choice|unknown` con `field` (e `limit`). Altrimenti
    `pachimud.invalid_entry` con `detail` (i messaggi dei validatori del gioco sono gia' in italiano, senza il prefisso «Value error, »)."""
    first = error.errors()[0]
    where = prefix + _where(first["loc"])
    kind, ctx = str(first["type"]), first.get("ctx") or {}
    limit = ", ".join(f"{sym} {ctx[k]}" for k, sym in _INVALID_LIMITS.items() if k in ctx)
    if kind == "missing":
        return api_error(422, "pachimud.invalid_missing", field=where)
    if kind == "extra_forbidden":
        return api_error(422, "pachimud.invalid_unknown", field=where)
    if kind in ("literal_error", "enum"):
        return api_error(
            422, "pachimud.invalid_choice", field=where, limit=re.sub(r"\s+or\s+", ", ", str(ctx.get("expected", "")).replace("'", ""))
        )
    if limit and kind.split("_")[0] in ("greater", "less", "multiple"):
        return api_error(422, "pachimud.invalid_range", field=where, limit=limit)
    if limit and kind in ("string_too_short", "string_too_long", "too_short", "too_long"):
        return api_error(422, "pachimud.invalid_length", field=where, limit=limit)
    if kind.endswith(("_type", "_parsing")) or kind in ("int_from_float", "bool_parsing"):
        return api_error(422, "pachimud.invalid_type", field=where)
    msg = str(first["msg"]).removeprefix("Value error, ")
    return api_error(422, "pachimud.invalid_entry", detail=f"{where}: {msg}" if where else msg)


# --------------------------------------------------------------------------- zona


def zone_out(zone: ZoneEntry) -> ZoneOut:
    """DTO di una zona (`id == vnum`); `description`, `zoneId` e cartella stanno in `extra`."""
    m = zone.model
    return ZoneOut(
        id=m.vnum,
        vnum=m.vnum,
        name=m.name,
        builder=m.builder,
        bottom_vnum=m.bottom_vnum,
        top_vnum=m.top_vnum,
        min_level=1,  # il gioco non ha il livello minimo di zona: valore neutro (campo `unsupported`)
        max_level=m.max_level,
        lifespan_minutes=m.lifespan_minutes,
        reset_mode=ZoneResetMode[m.reset_mode],
        enabled=m.enabled,
        extra={
            "zoneId": m.zone_id,
            "description": m.description,
            "folder": zone.dir.name,
            "climate": m.climate,
            "prototypesOnly": m.prototypes_only,
            "extendsZone": m.extends_zone,
            **simple_extra.out("zone", m),
        },
    )


def zone_apply(raw: Any, changes: dict[str, Any]) -> None:
    """Applica i campi del DTO (nomi Python) a `zone.yaml`."""
    for key, value in changes.items():
        if key == "reset_mode":
            value = ZoneResetMode(value).name
        put(raw, key, value, default=50 if key == "max_level" else None, required=key != "max_level")  # il gioco omette il default


# --------------------------------------------------------------------------- stanza


def room_out(item: Item, zone_vnum: int) -> RoomOut:
    """DTO di una stanza; `enabled`, `area`, `climate` e `triggers` del file stanno in `extra`."""
    m = item.model
    return RoomOut(
        id=m.vnum,
        vnum=m.vnum,
        zone_id=zone_vnum,
        name=m.name,
        description=m.description,
        sector_type=SectorType[m.sector_type],
        flags=list(m.flags),
        heal_rate=m.heal_rate,
        mana_rate=m.mana_rate,
        clan_id=m.clan_id,
        owner=m.owner,
        extra={
            "enabled": m.enabled,
            "area": item.area or "",
            "climate": m.climate,
            "triggers": [trigger_out(t) for t in m.triggers],
            **simple_extra.out("room", m),
        },
    )


ROOM_DEFAULTS = {"enabled": True, "sector_type": "INSIDE", "flags": [], "heal_rate": 100, "mana_rate": 100}


def room_apply(raw: Any, changes: dict[str, Any]) -> None:
    """Applica i campi del DTO a una voce di stanza (`zone_id`/`extra` sono gestiti dal chiamante)."""
    for key, value in changes.items():
        if key == "sector_type":
            value = SectorType(value).name
        put(raw, key, value, default=ROOM_DEFAULTS.get(key), required=key in ("vnum", "name", "description"))


def direction_key(raw_exits: dict[str, Any], direction: int) -> str | None:
    """La chiave (con la maiuscola del file) dell'uscita in quella direzione, o `None`."""
    name = Direction(direction).name
    return next((k for k in raw_exits if str(k).upper() == name), None)


def exit_out(room: Item, key: str, names: dict[int, str]) -> ExitOut:
    """DTO di un'uscita; `target_room_id` e' `None` se la destinazione non esiste (resta il vnum in `target_room_vnum`)."""
    x = room.model.exits[key]
    direction = Direction[key.upper()]
    exists = x.target_vnum in names
    return ExitOut(
        id=room.vnum * EXIT_STRIDE + int(direction),
        room_id=room.vnum,
        direction=direction,
        description=x.description,
        keywords=x.keywords,
        door_flag=DoorFlag[x.door_flag],
        is_open=x.is_open,
        is_locked=x.is_locked,
        key_vnum=x.key_vnum,
        target_room_id=x.target_vnum if exists else None,
        target_room_vnum=x.target_vnum,
        target_room_name=names.get(x.target_vnum) if x.target_vnum is not None else None,
        extra={"isMale": x.is_male, "openCmd": x.open_cmd, "climb": x.climb},
    )


def extra_desc_out(room_vnum: int, index: int, extra: Any) -> ExtraDescriptionOut:
    """DTO di una extra description (`id = vnum * 1000 + posizione`)."""
    return ExtraDescriptionOut(id=room_vnum * EXTRA_DESC_STRIDE + index, room_id=room_vnum, keywords=extra.keywords, text=extra.text)


# --------------------------------------------------------------------------- mob

MOB_DEFAULTS = {
    "gold": 0, "experience": 0, "sex": "NEUTRAL", "flags": [], "alignment": 0, "quest_ids": [], "is_banker": False,
    **{s: 0 for s in STATS},
}  # fmt: skip
MOB_REQUIRED = frozenset(
    {
        "vnum",
        "keywords",
        "short_description",
        "long_description",
        "detailed_description",
        "level",
        "thac0",
        "armor_class",
        "hp_dice",
        "damage_dice",
    }
)


def mob_out(item: Item, zone_vnum: int) -> MobOut:
    """DTO di un mob: i dadi `XdY+Z` sono spezzati nei tre campi; area e statistiche stanno in `extra`."""
    m = item.model
    hp, dmg = split_dice(m.hp_dice), split_dice(m.damage_dice)
    return MobOut(
        id=m.vnum,
        vnum=m.vnum,
        zone_id=zone_vnum,
        keywords=m.keywords,
        short_description=m.short_description,
        long_description=m.long_description,
        detailed_description=m.detailed_description,
        level=m.level,
        thac0=m.thac0,
        armor_class=m.armor_class,
        hp_dice_count=hp[0],
        hp_die_size=hp[1],
        hp_bonus=hp[2],
        damage_dice_count=dmg[0],
        damage_die_size=dmg[1],
        damage_bonus=dmg[2],
        gold=m.gold,
        experience=m.experience,
        sex=Sex[m.sex],
        flags=list(m.flags),
        race_id=m.race_id,
        class_id=m.class_id,
        alignment=m.alignment,
        debuff_skill_id=m.debuff_skill_id,
        shop_id=m.shop_id,
        quest_ids=list(m.quest_ids),
        is_banker=m.is_banker,
        teaches_class_ids=None if m.teaches_class_ids is None else list(m.teaches_class_ids),
        teaches_skill_ids=None if m.teaches_skill_ids is None else list(m.teaches_skill_ids),
        extra={
            "area": item.area or "",
            "name": m.name or "",
            "attacks": m.attacks,
            "persona": m.persona,
            "postmaster": m.postmaster,
            "receptionist": m.receptionist,
            "weaponImmunity": m.weapon_immunity,
            "breath": list(m.breath),
            "breathCost": m.breath_cost,
            "shop": None if m.shop is None else m.shop.model_dump(),
            "triggers": [trigger_out(t) for t in m.triggers],
            **{s: getattr(m, s) for s in STATS},
            **simple_extra.out("mob", m),
        },
    )


MOB_ORDER = (
    "vnum", "keywords", "name", "short_description", "long_description", "detailed_description", "level", "thac0", "attacks", "armor_class",
    "hp_dice", "damage_dice", "strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma", "gold", "experience",
    "sex", "flags", "alignment", "race_id", "class_id", "debuff_skill_id", "persona", "shop_id", "shop", "quest_ids", "is_banker",
    "postmaster", "receptionist", "weapon_immunity", "breath", "breath_cost", "teaches_class_ids", "teaches_skill_ids", "triggers",
    "position", "clan_id", "noise", "affects", "immunity", "resistance", "vulnerability", "spec",
)  # fmt: skip
"""Ordine dei campi di un mob nuovo (quello dei file del gioco)."""


def mob_apply(raw: Any, changes: dict[str, Any], current: Any = None) -> None:
    """Applica i campi del DTO a una voce di mob (`current` e' il modello attuale: serve a ricomporre i dadi)."""
    final = dict(changes)
    for prefix, key in (("hp", "hp_dice"), ("damage", "damage_dice")):
        names = (f"{prefix}_dice_count", f"{prefix}_die_size", f"{prefix}_bonus")
        if any(n in final for n in names):
            base = split_dice(getattr(current, key)) if current is not None else (1, 8, 0) if prefix == "hp" else (1, 4, 0)
            parts = [final.pop(n, base[i]) for i, n in enumerate(names)]
            final[key] = join_dice(*parts)
    for key in MOB_ORDER:
        if key not in final:
            continue
        value = final[key]
        if key == "sex":
            value = Sex(value).name
        put(raw, key, value, default=MOB_DEFAULTS.get(key), required=key in MOB_REQUIRED)


# --------------------------------------------------------------------------- oggetto

OBJECT_DEFAULTS = {"weight": 0, "cost": 0, "rent": 0, "extra_flags": [], "wear_flags": [], "affects": {}}


def object_out(item: Item, zone_vnum: int) -> ObjectOut:
    """DTO di un oggetto: `value_0..3` dai soli campi numerici (indici di LeU), il resto in `extra.typeFields`."""
    m = item.model
    values: list[int | None] = [None] * 4
    for field, slot in VALUE_SLOTS.get(m.object_type, {}).items():
        value = getattr(m, field)
        values[slot] = -1 if value is None else int(value)
    return ObjectOut(
        id=m.vnum,
        vnum=m.vnum,
        zone_id=zone_vnum,
        keywords=m.keywords,
        short_description=m.short_description,
        long_description=m.long_description,
        action_description=m.action_description,
        object_type=type_enum(m.object_type),
        weight=m.weight,
        cost=m.cost,
        rent=m.rent,
        value_0=values[0],
        value_1=values[1],
        value_2=values[2],
        value_3=values[3],
        extra_flags=list(m.extra_flags),
        wear_flags=list(m.wear_flags),
        affects=dict(m.affects),
        extra={
            "area": item.area or "",
            "extraDescriptions": [{"keywords": e.keywords, "text": e.text} for e in m.extra_descriptions],
            "typeFields": {n: _plain(getattr(m, n)) for n in type_fields(m.object_type)},
            "scripts": [trigger_out(t) for t in m.scripts],
            **simple_extra.out("object", m),
        },
    )


def _plain(value: Any) -> Any:
    """Valore JSON-izzabile di un campo (liste copiate)."""
    return list(value) if isinstance(value, list) else value


def values_to_fields(object_type: str, values: dict[int, int | None]) -> dict[str, Any]:
    """I campi del file corrispondenti ai `value_N` dati (solo gli slot numerici del tipo; `poisoned` e' booleano)."""
    out: dict[str, Any] = {}
    for field, slot in VALUE_SLOTS.get(object_type, {}).items():
        value = values.get(slot)
        if value is None:
            continue
        out[field] = bool(value) if field in BOOL_FIELDS else (None if field == "key_vnum" and value < 0 else value)
    return out


def check_object(raw: Any) -> Any:
    """Valida la voce con il modello del suo tipo (422 `pachimud.invalid_entry` se non valida); restituisce il modello."""
    try:
        return OBJECT_ADAPTER.validate_python(plain(raw))
    except ValidationError as error:
        raise invalid(error) from error


def object_apply(raw: Any, changes: dict[str, Any], fields: dict[str, Any] | None = None) -> None:
    """Applica ai campi dell'oggetto i `changes` del DTO e i campi del tipo `fields` (`extra.typeFields` e `value_N`).

    Cambiando `object_type` i campi del vecchio tipo che il nuovo non ha vengono tolti dal file.
    """
    new_type = type_name(ObjectType(changes["object_type"])) if "object_type" in changes else raw["object_type"]
    allowed = set(type_fields(new_type)) | COMMON_OBJECT_FIELDS | {"object_type"}
    for key in [k for k in raw if k not in allowed]:
        del raw[key]
    for key, value in changes.items():
        if key == "object_type":
            put(raw, "object_type", new_type, required=True)
        elif key not in ("value_0", "value_1", "value_2", "value_3"):
            put(
                raw,
                key,
                value,
                default=OBJECT_DEFAULTS.get(key),
                required=key in ("vnum", "keywords", "short_description", "long_description"),
            )
    unknown = set(fields or {}) - set(type_fields(new_type))
    if unknown:
        raise api_error(422, "pachimud.invalid_entry", detail=f"campi non ammessi per {new_type}: {', '.join(sorted(unknown))}")
    model_fields = TYPE_MODELS[new_type].model_fields
    for key, value in (fields or {}).items():
        default = model_fields[key].get_default(call_default_factory=True)
        put(raw, key, value, default=default)


def apply_object_extra_descriptions(raw: Any, extra: dict[str, Any]) -> None:
    """Scrive `extra.extraDescriptions` (lista di `{keywords, text}`) nella voce di un oggetto."""
    if "extraDescriptions" not in extra:
        return
    items = extra["extraDescriptions"] or []
    if not isinstance(items, list) or any(not isinstance(i, dict) or set(i) != {"keywords", "text"} for i in items):
        raise api_error(422, "pachimud.invalid_entry", detail="extraDescriptions: attesa una lista di {keywords, text}")
    put(raw, "extra_descriptions", [new_map({"keywords": i["keywords"], "text": i["text"]}) for i in items], default=[])
