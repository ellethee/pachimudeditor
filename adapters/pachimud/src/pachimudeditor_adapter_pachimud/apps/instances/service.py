"""Query, validazione ed eliminazione dietro `/api/instances`.

Invariante applicativo di un `ObjectInstance` (non imposto dal DB): esattamente uno tra `room_id`,
`container_instance_id`, `mob_instance_id`, `character_id` e' valorizzato; `equipped_slot` solo con
mob/personaggio. Il DB ha FK vere ma **nessun cascade**: chi elimina un mob o un contenitore deve
dire cosa ne e' del contenuto (`ContentsPolicy`).
"""

import random
from collections.abc import Sequence
from typing import Any, Literal

from pachifast.i18n import api_error
from pachifast.schemas.responses import PageParams, PaginatedResponse
from sqlalchemy import Select, String, cast, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from pachimudeditor_adapter_pachimud.schema import GameModels, models_of
from pachimudeditor_adapter_pachimud.apps.instances.schemas import LOCATION_KINDS, LocationIn, MobOut, ObjectOut
from pachimudeditor.common.enums import ObjectType

ContentsPolicy = Literal["destroy", "drop"]

_CONTAINER = int(ObjectType.CONTAINER)
_LIQUID = int(ObjectType.LIQUID_CONTAINER)
_CHARGE_TYPES = (int(ObjectType.WAND), int(ObjectType.STAFF))


class Queries:
    """Entita', alias e colonne di ordinamento dello schema riflesso di un mondo (una istanza per `GameModels`).

    L'istanza sta "in" un contenitore / mob / personaggio e la stanza effettiva viene da quello dei tre (o
    dall'istanza stessa) che ne ha una: da qui gli alias per la lista oggetti.
    """

    def __init__(self, m: GameModels) -> None:
        """Costruisce alias, espressione della stanza effettiva e colonne ammesse in `orderBy`."""
        assert m.MobInstance is not None and m.ObjectInstance is not None and m.PlayerCharacter is not None
        self.m = m
        MobInstance, ObjectInstance, PlayerCharacter = m.MobInstance, m.ObjectInstance, m.PlayerCharacter  # noqa: N806
        self.MobInstance, self.ObjectInstance, self.PlayerCharacter = MobInstance, ObjectInstance, PlayerCharacter  # noqa: N815
        self.Container = aliased(ObjectInstance, name="container")
        self.ContainerProto = aliased(m.ObjectPrototype, name="container_proto")
        self.Mob = aliased(MobInstance, name="holder_mob")
        self.MobProto = aliased(m.MobPrototype, name="holder_mob_proto")
        self.Holder = aliased(PlayerCharacter, name="holder_char")
        self.ContainerMob = aliased(MobInstance, name="container_mob")
        self.ContainerHolder = aliased(PlayerCharacter, name="container_char")
        self.effective_room = func.coalesce(
            ObjectInstance.room_id,
            self.Mob.room_id,
            self.Holder.current_room_id,
            self.Container.room_id,
            self.ContainerMob.room_id,
            self.ContainerHolder.current_room_id,
        )
        self.mob_order_columns: dict[str, Any] = {
            "id": MobInstance.id,
            "prototypeVnum": m.MobPrototype.vnum,
            "prototypeName": m.MobPrototype.short_description,
            "roomVnum": m.Room.vnum,
            "roomName": m.Room.name,
            "zoneName": m.Zone.name,
            "hitPointsCurrent": MobInstance.hit_points_current,
            "hitPointsMax": MobInstance.hit_points_max,
            "gold": MobInstance.gold,
        }
        """Colonne ammesse in `orderBy` per i mob."""
        self.object_order_columns: dict[str, Any] = {
            "id": ObjectInstance.id,
            "prototypeVnum": m.ObjectPrototype.vnum,
            "prototypeName": m.ObjectPrototype.short_description,
            "objectType": m.ObjectPrototype.object_type,
            "roomVnum": m.Room.vnum,
            "zoneName": m.Zone.name,
            "charges": ObjectInstance.charges,
            "liquidAmount": ObjectInstance.liquid_amount,
        }
        """Colonne ammesse in `orderBy` per gli oggetti."""
        self.kind_columns: dict[str, Any] = {
            "room": ObjectInstance.room_id,
            "container": ObjectInstance.container_instance_id,
            "mob": ObjectInstance.mob_instance_id,
            "character": ObjectInstance.character_id,
        }

    def mob_statement(self) -> Select[Any]:
        """`SELECT MobInstance, MobPrototype, Room, Zone` con i join sulle chiavi naturali."""
        m = self.m
        return (
            select(self.MobInstance, m.MobPrototype, m.Room, m.Zone)
            .join(m.MobPrototype, m.MobPrototype.id == self.MobInstance.prototype_id)
            .join(m.Room, m.Room.id == self.MobInstance.room_id)
            .join(m.Zone, m.Zone.id == m.Room.zone_id)
        )

    def mob_search_filter(self, term: str) -> Any:
        """Id istanza (con o senza `#`), keywords/descrizione/vnum del prototipo o nome della stanza."""
        m, like = self.m, _like(term)
        return or_(
            cast(self.MobInstance.id, String) == term.lstrip("#"),
            func.lower(m.MobPrototype.keywords).like(like),
            func.lower(m.MobPrototype.short_description).like(like),
            cast(m.MobPrototype.vnum, String).like(like),
            func.lower(m.Room.name).like(like),
        )

    def object_statement(self) -> Select[Any]:
        """Istanze oggetto con prototipo, possessore (contenitore/mob/personaggio) e stanza/zona effettive."""
        m = self.m
        return (
            select(
                self.ObjectInstance,
                m.ObjectPrototype,
                self.Container,
                self.ContainerProto,
                self.Mob,
                self.MobProto,
                self.Holder,
                m.Room,
                m.Zone,
            )
            .join(m.ObjectPrototype, m.ObjectPrototype.id == self.ObjectInstance.prototype_id)
            .outerjoin(self.Container, self.Container.id == self.ObjectInstance.container_instance_id)
            .outerjoin(self.ContainerProto, self.ContainerProto.id == self.Container.prototype_id)
            .outerjoin(self.Mob, self.Mob.id == self.ObjectInstance.mob_instance_id)
            .outerjoin(self.MobProto, self.MobProto.id == self.Mob.prototype_id)
            .outerjoin(self.Holder, self.Holder.id == self.ObjectInstance.character_id)
            .outerjoin(self.ContainerMob, self.ContainerMob.id == self.Container.mob_instance_id)
            .outerjoin(self.ContainerHolder, self.ContainerHolder.id == self.Container.character_id)
            .outerjoin(m.Room, m.Room.id == self.effective_room)
            .outerjoin(m.Zone, m.Zone.id == m.Room.zone_id)
        )

    def object_search_filter(self, term: str) -> Any:
        """Id istanza (con o senza `#`) o keywords/descrizione/vnum del prototipo."""
        m, like = self.m, _like(term)
        return or_(
            cast(self.ObjectInstance.id, String) == term.lstrip("#"),
            func.lower(m.ObjectPrototype.keywords).like(like),
            func.lower(m.ObjectPrototype.short_description).like(like),
            cast(m.ObjectPrototype.vnum, String).like(like),
        )

    def kind_column(self, kind: str) -> Any:
        """La colonna-possessore di `kind` (422 `instances.invalid_location_kind` se sconosciuto)."""
        if kind not in self.kind_columns:
            raise api_error(422, "instances.invalid_location_kind", kind=kind)
        return self.kind_columns[kind]


def queries(session: AsyncSession) -> Queries:
    """Le `Queries` del mondo della sessione (costruite una volta per schema riflesso)."""
    m = models_of(session)
    cached = m.__dict__.get("_instance_queries")
    if cached is None:
        cached = m.__dict__["_instance_queries"] = Queries(m)
    return cached  # type: ignore[no-any-return]


def _like(term: str) -> str:
    """`%term%` minuscolo, per un confronto case-insensitive per sottostringa."""
    return f"%{term.lower()}%"


def _enum_int(value: Any) -> int:
    """Il valore intero di una colonna enum (o gia' intera)."""
    return int(getattr(value, "value", value))


def roll_dice(count: int, size: int, bonus: int) -> int:
    """Tira `count`d`size` + `bonus`."""
    return sum(random.randint(1, max(1, size)) for _ in range(max(0, count))) + bonus


async def paginate(
    session: AsyncSession,
    statement: Select[Any],
    params: PageParams,
    order_columns: dict[str, Any],
    default_order: Sequence[Any],
) -> tuple[list[Any], int, PaginatedResponse[Any]]:
    """Esegue `statement` per una pagina: `(righe, totale, finestra)`.

    I nomi di `orderBy` (camelCase, `-` = decrescente) sono cercati in `order_columns`; uno sconosciuto
    da' 422 `api.invalid_order_by`. Si pagina solo con `page` e `pageSize` entrambi presenti.
    """
    clauses = []
    for token in (params.orderBy or "").split(","):
        token = token.strip()
        if not token:
            continue
        column = order_columns.get(token.lstrip("-+"))
        if column is None:
            raise api_error(422, "api.invalid_order_by", loc=("query", "orderBy"), field=token.lstrip("-+"))
        clauses.append(column.desc() if token.startswith("-") else column.asc())
    total = (await session.execute(select(func.count()).select_from(statement.order_by(None).subquery()))).scalar_one()
    page = statement.order_by(*(clauses or default_order))
    if params.page and params.pageSize:
        page = page.offset((params.page - 1) * params.pageSize).limit(params.pageSize)
    rows = list((await session.execute(page)).all())
    return rows, total, PaginatedResponse(items=[], total=total, page=params.page, pageSize=params.pageSize)


# ------------------------------------------------------------------------------------- mobs


async def build_mobs(session: AsyncSession, rows: Sequence[Any]) -> list[MobOut]:
    """`MobOut` per ogni riga `(MobInstance, MobPrototype, Room, Zone)`; conteggio oggetti in una query."""
    ObjectInstance = queries(session).ObjectInstance  # noqa: N806
    counts: dict[int, int] = {}
    if rows:
        found = await session.execute(
            select(ObjectInstance.mob_instance_id, func.count())
            .where(ObjectInstance.mob_instance_id.in_([row[0].id for row in rows]))
            .group_by(ObjectInstance.mob_instance_id)
        )
        counts = {mob_id: int(count) for mob_id, count in found.all()}
    return [
        MobOut(
            id=mob.id,
            prototype_id=prototype.id,
            prototype_vnum=prototype.vnum,
            prototype_name=prototype.short_description,
            prototype_zone_id=prototype.zone_id,
            shop_id=prototype.shop_id,
            room_id=room.id,
            room_vnum=room.vnum,
            room_name=room.name,
            zone_id=zone.id,
            zone_name=zone.name,
            hit_points_current=mob.hit_points_current,
            hit_points_max=mob.hit_points_max,
            gold=mob.gold,
            item_count=counts.get(mob.id, 0),
        )
        for mob, prototype, room, zone in rows
    ]


# --------------------------------------------------------------------------------- objects


def _location_of(
    instance: Any,
    container_proto: Any | None,
    mob_proto: Any | None,
    holder: Any | None,
    room: Any | None,
) -> tuple[str, int, str]:
    """`(kind, id bersaglio, etichetta)` di dove si trova `instance` (etichette in italiano di cortesia)."""
    if instance.container_instance_id is not None:
        name = container_proto.short_description if container_proto is not None else "?"
        return "container", instance.container_instance_id, f"Dentro #{instance.container_instance_id} {name}"
    if instance.mob_instance_id is not None:
        name = mob_proto.short_description if mob_proto is not None else "?"
        return "mob", instance.mob_instance_id, f"Mob #{instance.mob_instance_id} {name}"
    if instance.character_id is not None:
        name = holder.name if holder is not None else "?"
        return "character", instance.character_id, f"Personaggio {name}"
    label = f"Stanza {room.vnum} - {room.name}" if room is not None else f"Stanza #{instance.room_id}"
    return "room", instance.room_id or 0, label


async def build_objects(session: AsyncSession, rows: Sequence[Any]) -> list[ObjectOut]:
    """`ObjectOut` per ogni riga di `object_statement()`; conteggio contenuti in una query."""
    ObjectInstance = queries(session).ObjectInstance  # noqa: N806
    counts: dict[int, int] = {}
    if rows:
        found = await session.execute(
            select(ObjectInstance.container_instance_id, func.count())
            .where(ObjectInstance.container_instance_id.in_([row[0].id for row in rows]))
            .group_by(ObjectInstance.container_instance_id)
        )
        counts = {container_id: int(count) for container_id, count in found.all()}
    items: list[ObjectOut] = []
    for instance, prototype, _container, container_proto, _mob, mob_proto, holder, room, zone in rows:
        kind, target_id, label = _location_of(instance, container_proto, mob_proto, holder, room)
        items.append(
            ObjectOut(
                id=instance.id,
                prototype_id=prototype.id,
                prototype_vnum=prototype.vnum,
                prototype_name=prototype.short_description,
                prototype_zone_id=prototype.zone_id,
                object_type=_enum_int(prototype.object_type),
                wear_slots=[flag for flag in prototype.wear_flags if flag != "take"],
                location_kind=kind,
                location_id=target_id,
                location_label=label,
                equipped_slot=instance.equipped_slot,
                room_id=room.id if room is not None else None,
                room_vnum=room.vnum if room is not None else None,
                room_name=room.name if room is not None else None,
                zone_id=zone.id if zone is not None else None,
                zone_name=zone.name if zone is not None else None,
                charges=instance.charges,
                liquid_amount=instance.liquid_amount,
                liquid_type=instance.liquid_type,
                liquid_poisoned=instance.liquid_poisoned,
                content_count=counts.get(instance.id, 0),
            )
        )
    return items


# ----------------------------------------------------------------------------- validazione


def check_non_negative(field: str, value: int | None) -> None:
    """422 `instances.negative_value` se `value` e' negativo (`None` passa: significa "come il prototipo")."""
    if value is not None and value < 0:
        raise api_error(422, "instances.negative_value", field=field)


def check_hit_points(current: int, maximum: int) -> None:
    """422 se i PF sono < 1 (`instances.hp_min`) o se gli attuali superano i massimi (`instances.hp_exceeds_max`)."""
    if current < 1 or maximum < 1:
        raise api_error(422, "instances.hp_min")
    if current > maximum:
        raise api_error(422, "instances.hp_exceeds_max")


async def ensure_room(session: AsyncSession, room_id: int) -> None:
    """422 `instances.room_not_found` se la stanza non esiste."""
    if await session.get(models_of(session).Room, room_id) is None:
        raise api_error(422, "instances.room_not_found", id=room_id)


def check_object_state(
    prototype: Any,
    *,
    charges: int | None = None,
    liquid_amount: int | None = None,
    liquid_type: int | None = None,
    liquid_poisoned: bool | None = None,
) -> None:
    """422 per un valore per-istanza senza senso per l'`ObjectType` del prototipo.

    Le cariche valgono per bacchette/bastoni, i campi liquido per i contenitori di liquido; `None` passa sempre.
    """
    kind = _enum_int(prototype.object_type)
    check_non_negative("charges", charges)
    check_non_negative("liquidAmount", liquid_amount)
    check_non_negative("liquidType", liquid_type)
    if charges is not None and kind not in _CHARGE_TYPES:
        raise api_error(422, "instances.charges_not_allowed")
    if (liquid_amount is not None or liquid_type is not None or liquid_poisoned is not None) and kind != _LIQUID:
        raise api_error(422, "instances.liquid_not_allowed")


async def resolve_location(
    session: AsyncSession,
    prototype: Any,
    location: LocationIn,
    *,
    instance: Any | None = None,
) -> dict[str, Any]:
    """Valida `location` per un oggetto di `prototype` e restituisce le quattro colonne-possessore + slot.

    `instance` e' l'oggetto che si sposta (None alla creazione). 422 per bersaglio inesistente, non-contenitore,
    contenitore annidato o pieno, slot inutilizzabile od occupato.
    """
    q = queries(session)
    values: dict[str, Any] = {
        "room_id": None,
        "container_instance_id": None,
        "mob_instance_id": None,
        "character_id": None,
        "equipped_slot": None,
    }
    kind = location.kind
    if kind not in LOCATION_KINDS:
        raise api_error(422, "instances.invalid_location_kind", kind=kind)
    if kind == "room":
        await ensure_room(session, location.target_id)
        values["room_id"] = location.target_id
    elif kind == "character":
        if await session.get(q.PlayerCharacter, location.target_id) is None:
            raise api_error(422, "instances.holder_not_found", kind=kind, id=location.target_id)
        values["character_id"] = location.target_id
    elif kind == "mob":
        if await session.get(q.MobInstance, location.target_id) is None:
            raise api_error(422, "instances.holder_not_found", kind=kind, id=location.target_id)
        values["mob_instance_id"] = location.target_id
    else:
        await _check_container_target(session, prototype, location.target_id, instance)
        values["container_instance_id"] = location.target_id

    slot = (location.equipped_slot or "").strip() or None
    if slot is not None:
        if kind not in ("mob", "character"):
            raise api_error(422, "instances.slot_not_allowed")
        if slot == "take" or slot not in prototype.wear_flags:
            allowed = ", ".join(flag for flag in prototype.wear_flags if flag != "take") or "-"
            raise api_error(422, "instances.slot_invalid", slot=slot, allowed=allowed)
        ObjectInstance = q.ObjectInstance  # noqa: N806
        owner = ObjectInstance.mob_instance_id == location.target_id if kind == "mob" else ObjectInstance.character_id == location.target_id
        clash = select(ObjectInstance.id).where(owner, ObjectInstance.equipped_slot == slot)
        if instance is not None and instance.id is not None:
            clash = clash.where(ObjectInstance.id != instance.id)
        if (await session.execute(clash.limit(1))).first() is not None:
            raise api_error(422, "instances.slot_taken", slot=slot)
        values["equipped_slot"] = slot
    return values


async def _check_container_target(session: AsyncSession, prototype: Any, target_id: int, instance: Any | None) -> None:
    """422 salvo che `target_id` sia un contenitore che puo' ospitare un oggetto di `prototype`.

    Niente annidamento (un contenitore non va in un contenitore, ne' dentro un oggetto gia' contenuto) e
    rispetto della capacita' (`value_0` del prototipo del contenitore, `None` = illimitata).
    """
    ObjectInstance = queries(session).ObjectInstance  # noqa: N806
    target = await session.get(ObjectInstance, target_id)
    if target is None:
        raise api_error(422, "instances.container_not_found", id=target_id)
    if instance is not None and target.id == instance.id:
        raise api_error(422, "instances.container_self")
    target_proto = await session.get(models_of(session).ObjectPrototype, target.prototype_id)
    if target_proto is None or _enum_int(target_proto.object_type) != _CONTAINER:
        raise api_error(422, "instances.not_a_container", id=target_id)
    if target.container_instance_id is not None:
        raise api_error(422, "instances.container_nested", id=target_id)
    if _enum_int(prototype.object_type) == _CONTAINER:
        raise api_error(422, "instances.container_in_container")
    capacity = target_proto.value_0
    if capacity is not None and not (instance is not None and instance.container_instance_id == target_id):
        inside = (
            await session.execute(select(func.count()).select_from(ObjectInstance).where(ObjectInstance.container_instance_id == target_id))
        ).scalar_one()
        if inside >= capacity:
            raise api_error(422, "instances.container_full", id=target_id, capacity=capacity)


# -------------------------------------------------------------------------- eliminazione


async def destroy_mob(session: AsyncSession, mob: Any, contents: ContentsPolicy) -> None:
    """Elimina un mob e sistema cio' che porta/indossa (nessun commit).

    `drop`: gli oggetti cadono, senza slot, nella stanza del mob (i contenitori tengono il contenuto).
    `destroy`: gli oggetti (e il contenuto dei contenitori tra loro) vengono eliminati.
    """
    ObjectInstance = queries(session).ObjectInstance  # noqa: N806
    held = ObjectInstance.mob_instance_id == mob.id
    if contents == "drop":
        await session.execute(update(ObjectInstance).where(held).values(mob_instance_id=None, equipped_slot=None, room_id=mob.room_id))
    else:
        held_ids = select(ObjectInstance.id).where(held)
        await session.execute(delete(ObjectInstance).where(ObjectInstance.container_instance_id.in_(held_ids)))
        await session.execute(delete(ObjectInstance).where(held))
    await session.delete(mob)


async def destroy_object(session: AsyncSession, instance: Any, contents: ContentsPolicy) -> None:
    """Elimina un oggetto e sistema il suo contenuto (nessun commit).

    `drop`: il contenuto va dove stava il contenitore (stessa stanza, o inventario dello stesso mob/personaggio,
    senza slot). `destroy`: viene eliminato con lui. Un contenitore non sta dentro un altro: un solo livello.
    """
    ObjectInstance = queries(session).ObjectInstance  # noqa: N806
    inside = ObjectInstance.container_instance_id == instance.id
    if contents == "drop":
        await session.execute(
            update(ObjectInstance)
            .where(inside)
            .values(
                container_instance_id=None,
                room_id=instance.room_id,
                mob_instance_id=instance.mob_instance_id,
                character_id=instance.character_id,
                equipped_slot=None,
            )
        )
    else:
        await session.execute(delete(ObjectInstance).where(inside))
    await session.delete(instance)
