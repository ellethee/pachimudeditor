"""Funzioni condivise dai sapori: flag, razze, valori degli oggetti per tipo, argomenti dei reset."""

from collections.abc import Iterable

from pachimudeditor.common.enums import ObjectType

from pachimudeditor.common.adapters.convert import tables
from pachimudeditor.common.adapters.convert.converter import ConvertContext, loss
from pachimudeditor.common.adapters.convert.models import LossEntity, LossItem
from pachimudeditor.common.adapters.models import ObjectIn, ObjectOut

UNLIMITED = 99
"""Valore di pachimud per "nessun limite" nei campi `max` di `M`/`O` (che li richiedono): Diku Modificato usa 0."""


def map_flags(
    entity: LossEntity,
    field_name: str,
    flags: Iterable[str],
    table: dict[str, str],
    silent: frozenset[str] = frozenset(),
) -> tuple[list[str], list[LossItem]]:
    """Traduce i nomi di flag con `table` (senza maiuscole); quelli senza corrispondenza si scartano con una perdita."""
    out: list[str] = []
    dropped: list[str] = []
    for flag in flags:
        key = flag.strip().lower()
        if key in silent or key.startswith("unused"):
            continue
        mapped = table.get(key)
        if mapped is None:
            dropped.append(flag)
        elif mapped not in out:
            out.append(mapped)
    losses = [loss(entity, field_name, "flags_dropped", "warning", flags=", ".join(dropped))] if dropped else []
    return out, losses


def norm_race(race: str | None) -> str | None:
    """Nome di razza normalizzato (`Song Bird` -> `song_bird`); vuoto -> None."""
    return race.strip().lower().replace(" ", "_").replace("-", "_") if race and race.strip() else None


def pick_race(race: str | None, candidates: list[str], ctx: ConvertContext) -> tuple[str | None, list[LossItem]]:
    """La razza di arrivo: la prima di `candidates` presente tra quelle del mondo (se note), altrimenti `None` + avviso."""
    if not race:
        return None, []
    if not ctx.target_races:
        return candidates[0], []
    for name in candidates:
        if name in ctx.target_races:
            return name, []
    return None, [loss("mob", "raceId", "race_unknown", "warning", race=race)]


def neutral_mob_fields() -> dict[str, object]:
    """Valori neutri dei campi del mob che ROM/Diku Modificato non hanno."""
    return {
        "class_id": None, "debuff_skill_id": None, "shop_id": None, "quest_ids": [], "is_banker": False,
        "teaches_class_ids": None, "teaches_skill_ids": None,
    }  # fmt: skip


def unsupported_mob_losses(m: object) -> list[LossItem]:
    """Perdite per i campi del mob pachimud che il mondo di arrivo non ha (valori non neutri)."""
    out: list[LossItem] = []
    for name, neutral in neutral_mob_fields().items():
        value = getattr(m, name)
        if value != neutral and not (neutral == [] and not value):
            out.append(loss("mob", name, "field_dropped", "dropped", name=name, value=str(value)[:60]))
    return out


# --------------------------------------------------------------------------- valori degli oggetti per tipo

T = ObjectType


def _vals(o: ObjectOut | ObjectIn) -> list[int | None]:
    """I quattro `value_N`."""
    return [o.value_0, o.value_1, o.value_2, o.value_3]


def _nz(*values: int | None) -> bool:
    """Almeno un valore non nullo e diverso da zero."""
    return any(v not in (None, 0) for v in values)


def rom_values_to_pivot(o: ObjectOut) -> tuple[list[int | None], list[LossItem]]:
    """`value_0..3` di pachimud da un oggetto ROM (i nomi di classe, colpo, liquido e incantesimo stanno in `extra.values`)."""
    v, raw = _vals(o), [str(x) for x in (o.extra.get("values") or [])] + [""] * 5
    t, L = o.object_type, []
    if t == T.WEAPON:
        offset = tables.ATTACK_ROM_TO_OFFSET.get(raw[3].strip("'\" ").lower(), 0)
        if raw[3].strip("'\" ").lower() not in tables.ATTACK_ROM_TO_OFFSET:
            L.append(loss("object", "value_3", "attack_type_approximated", "info", attack=raw[3]))
        return [v[1], v[2], 0, offset], L
    if t == T.ARMOR:
        if _nz(*v[1:3]):
            L.append(loss("object", "values", "armor_ac_dropped", "info"))
        return [v[0], None, None, None], L
    if t == T.CONTAINER:
        L.append(loss("object", "value_0", "container_capacity_dropped", "info", capacity=v[0]))
        if _nz(v[2]):
            L.append(loss("object", "value_2", "container_key_dropped", "warning", vnum=v[2]))
        return [None, None, None, None], L
    if t in (T.LIQUID_CONTAINER, T.FOUNTAIN):
        L.append(loss("object", "values", "liquid_dropped", "info"))
        return [v[0], None, None, None], L
    if t in (T.POTION, T.SCROLL):
        if any(x.strip("'\" ") for x in raw[1:4]):
            L.append(loss("object", "values", "spells_dropped", "warning"))
        return [v[0], None, None, None], L
    if t in (T.WAND, T.STAFF):
        if raw[3].strip("'\" "):
            L.append(loss("object", "value_3", "spells_dropped", "warning"))
        return [v[0], v[1], v[2], None], L
    return v, L


def dikumod_values_to_pivot(o: ObjectOut) -> tuple[list[int | None], list[LossItem]]:
    """`value_0..3` di pachimud da un oggetto Diku Modificato (Diku: l'arma ha dadi in v1/v2 e tipo di colpo in v3)."""
    v, t, L = _vals(o), o.object_type, []
    if t == T.WEAPON:
        return [v[1], v[2], 0, v[3]], L
    if t == T.ARMOR:
        return [v[0], None, None, None], L
    if t == T.CONTAINER:
        L.append(loss("object", "value_0", "container_capacity_dropped", "info", capacity=v[0]))
        if _nz(v[2]):
            L.append(loss("object", "value_2", "container_key_dropped", "warning", vnum=v[2]))
        return [None, None, None, None], L
    if t in (T.LIQUID_CONTAINER, T.FOUNTAIN):
        L.append(loss("object", "values", "liquid_dropped", "info"))
        return [v[0], None, None, None], L
    if t in (T.POTION, T.SCROLL):
        if _nz(*v[1:4]):
            L.append(loss("object", "values", "spells_dropped", "warning"))
        return [v[0], None, None, None], L
    if t in (T.WAND, T.STAFF):
        if _nz(v[3]):
            L.append(loss("object", "value_3", "spells_dropped", "warning"))
        return [v[0], v[1], v[2], None], L
    return v, L


def pivot_values_to_rom(o: ObjectIn) -> tuple[list[int | None], list[str] | None, list[LossItem]]:
    """`(value_0..3, extra.values)` ROM da un oggetto pivot; `extra.values` (5 token) solo per i tipi con nomi."""
    v, t, L = _vals(o), o.object_type, []
    n = lambda x, d=0: d if x is None else x  # noqa: E731
    if t == T.WEAPON:
        if _nz(v[2]):
            L.append(loss("object", "value_2", "weapon_bonus_dropped", "warning", bonus=v[2]))
        attack = tables.ATTACK_OFFSET_TO_ROM.get(n(v[3]), "punch")
        return [None] * 4, ["exotic", str(n(v[0], 1)), str(n(v[1], 4)), attack, "0"], L
    if t == T.ARMOR:
        a = str(n(v[0]))
        return [None] * 4, [a, a, a, a, "0"], L
    if t == T.CONTAINER:
        L.append(loss("object", "values", "container_defaults", "info"))
        return [None] * 4, ["100", "0", "0", "100", "100"], L
    if t in (T.LIQUID_CONTAINER, T.FOUNTAIN):
        cap = str(n(v[0], 10))
        return [None] * 4, [cap, cap, "water", "0", "0"], L
    if t in (T.POTION, T.SCROLL):
        return [None] * 4, [str(n(v[0], 1)), "", "", "", ""], L
    if t in (T.WAND, T.STAFF):
        return [None] * 4, [str(n(v[0], 1)), str(n(v[1])), str(n(v[2])), "", "0"], L
    return v, None, L


def pivot_values_to_dikumod(o: ObjectIn) -> tuple[list[int | None], list[LossItem]]:
    """`value_0..3` Diku Modificato da un oggetto pivot."""
    v, t, L = _vals(o), o.object_type, []
    n = lambda x, d=0: d if x is None else x  # noqa: E731
    if t == T.WEAPON:
        if _nz(v[2]):
            L.append(loss("object", "value_2", "weapon_bonus_dropped", "warning", bonus=v[2]))
        return [0, n(v[0], 1), n(v[1], 4), n(v[3])], L
    if t == T.ARMOR:
        return [n(v[0]), 0, 0, 0], L
    if t == T.CONTAINER:
        L.append(loss("object", "values", "container_defaults", "info"))
        return [100, 0, 0, 0], L
    if t in (T.LIQUID_CONTAINER, T.FOUNTAIN):
        return [n(v[0], 10), n(v[0], 10), 0, 0], L
    if t in (T.POTION, T.SCROLL):
        return [n(v[0], 1), 0, 0, 0], L
    if t in (T.WAND, T.STAFF):
        return [n(v[0], 1), n(v[1]), n(v[2]), 0], L
    return [n(x) for x in v], L


def map_affects(affects: dict[str, int], table: dict[str, str]) -> tuple[dict[str, int], list[LossItem]]:
    """Traduce i nomi di `apply` degli oggetti con `table` (somma i duplicati); gli altri si scartano con una perdita."""
    out: dict[str, int] = {}
    dropped: list[str] = []
    for name, modifier in affects.items():
        mapped = table.get(name)
        if mapped is None:
            dropped.append(name)
        else:
            out[mapped] = out.get(mapped, 0) + modifier
    return out, ([loss("object", "affects", "affects_dropped", "warning", names=", ".join(dropped))] if dropped else [])
