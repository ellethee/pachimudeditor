"""Mondo: panoramica, grafo tra zone, ricerca globale e primo range di vnum libero. Prefisso `/api/world`.

Tutte le route sono in sola lettura. I "warning" di qualita' dei dati sono identificati da un `kind`
stabile (tradotto dal frontend), non da un codice di errore HTTP.
"""

from typing import Annotated, Literal

from fastapi import Depends, Query
from pachifast.database import AliasedBaseModel
from pachifast.i18n import api_error
from pachifast.router_factory import get_router

from pachimudeditor.sdk import require_capability
from sqlalchemy import String, cast, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from pachimudeditor_adapter_pachimud.schema import models_of
from pachimudeditor_adapter_pachimud.editor.db import SessionDep
from pachimudeditor.common.enums import ZoneCommandType

router = get_router(deps=[Depends(require_capability("supports_world_overview"))])

WARNINGS_PER_KIND = 100
"""Massimo numero di warning elencati per ciascun `kind` (i totali reali stanno in `warningTotals`)."""

SearchType = Literal["zone", "room", "mob", "object"]
SEARCH_TYPES: tuple[SearchType, ...] = ("zone", "room", "mob", "object")

WarningKind = Literal[
    "room_empty_description",
    "exit_without_target",
    "zone_empty_reset_script",
    "vnum_out_of_range",
    "mob_never_loaded",
    "object_never_loaded",
]
EntityType = Literal["zone", "room", "mob", "object"]


# --------------------------------------------------------------------------- overview


class WorldCounts(AliasedBaseModel):
    """Conteggi globali del mondo."""

    zones: int
    zones_enabled: int
    zones_disabled: int
    rooms: int
    mobs: int
    objects: int
    mob_instances: int
    object_instances: int
    accounts: int
    characters: int


class ZoneOverview(AliasedBaseModel):
    """Riga della tabella riepilogativa per zona.

    `rangeUsagePct`: percentuale di vnum del range `[bottomVnum, topVnum]` occupati da contenuto della
    zona (vnum distinti di stanze, mob e oggetti dentro il range); `null` se il range e' 0-0 (da assegnare).
    """

    id: int
    vnum: int
    name: str
    enabled: bool
    bottom_vnum: int
    top_vnum: int
    rooms: int
    mobs: int
    objects: int
    range_usage_pct: float | None
    reset_commands: int


class QualityWarning(AliasedBaseModel):
    """Un problema di qualita' dei dati, con l'entita' da aprire nell'editor.

    `params` dipende dal `kind`: `exit_without_target` -> `direction` (int), `vnum_out_of_range` ->
    `bottom`, `top`. `zoneId`/`zoneName` sono la zona proprietaria dell'entita' (per `zone_*` la zona stessa).
    """

    kind: WarningKind
    entity_type: EntityType
    entity_id: int
    vnum: int
    name: str
    zone_id: int
    zone_name: str
    params: dict[str, int] = {}


class WorldOverview(AliasedBaseModel):
    """Risposta di `GET /world/overview`."""

    counts: WorldCounts
    zones: list[ZoneOverview]
    warnings: list[QualityWarning]
    warning_totals: dict[str, int]


async def _count(session: AsyncSession, model: type | None) -> int:
    """Numero di righe della tabella di `model` (0 se la tabella non esiste nel DB)."""
    if model is None:
        return 0
    return (await session.execute(select(func.count()).select_from(model))).scalar_one()


def _push(warnings: list[QualityWarning], totals: dict[str, int], warning: QualityWarning) -> None:
    """Conta il warning nei totali e lo elenca solo finche' non si supera `WARNINGS_PER_KIND`."""
    totals[warning.kind] = totals.get(warning.kind, 0) + 1
    if totals[warning.kind] <= WARNINGS_PER_KIND:
        warnings.append(warning)


async def build_overview(session: AsyncSession) -> WorldOverview:
    """Calcola conteggi, riepilogo per zona e warning di qualita' dei dati."""
    m = models_of(session)
    Zone, Room, Exit, MobPrototype, ObjectPrototype, ZoneResetCommand = (  # noqa: N806
        m.Zone,
        m.Room,
        m.Exit,
        m.MobPrototype,
        m.ObjectPrototype,
        m.ZoneResetCommand,
    )
    zones = (await session.execute(select(Zone).order_by(Zone.vnum))).scalars().all()
    zone_by_id = {z.id: z for z in zones}
    rooms = (await session.execute(select(Room.id, Room.vnum, Room.name, Room.description, Room.zone_id).order_by(Room.vnum))).all()
    mobs = (
        await session.execute(
            select(MobPrototype.id, MobPrototype.vnum, MobPrototype.short_description, MobPrototype.zone_id).order_by(MobPrototype.vnum)
        )
    ).all()
    objects = (
        await session.execute(
            select(ObjectPrototype.id, ObjectPrototype.vnum, ObjectPrototype.short_description, ObjectPrototype.zone_id).order_by(
                ObjectPrototype.vnum
            )
        )
    ).all()
    commands = (
        await session.execute(
            select(
                ZoneResetCommand.zone_id,
                ZoneResetCommand.command_type,
                ZoneResetCommand.arg1,
                ZoneResetCommand.arg3,
            )
        )
    ).all()
    dangling = (
        await session.execute(
            select(Exit.direction, Room.id, Room.vnum, Room.name, Room.zone_id)
            .join(Room, Room.id == Exit.room_id)
            .where(Exit.target_room_id.is_(None))
            .order_by(Room.vnum, Exit.direction)
        )
    ).all()

    counts = WorldCounts(
        zones=len(zones),
        zones_enabled=sum(1 for z in zones if z.enabled),
        zones_disabled=sum(1 for z in zones if not z.enabled),
        rooms=len(rooms),
        mobs=len(mobs),
        objects=len(objects),
        mob_instances=await _count(session, m.MobInstance),
        object_instances=await _count(session, m.ObjectInstance),
        accounts=await _count(session, m.Account),
        characters=await _count(session, m.PlayerCharacter),
    )

    # riepilogo per zona
    per_zone: dict[int, dict[str, set[int] | int]] = {
        z.id: {"rooms": 0, "mobs": 0, "objects": 0, "used": set(), "commands": 0} for z in zones
    }
    for kind, rows in (("rooms", rooms), ("mobs", mobs), ("objects", objects)):
        for row in rows:
            stats = per_zone[row.zone_id]
            stats[kind] = int(stats[kind]) + 1  # type: ignore[arg-type]
            zone = zone_by_id[row.zone_id]
            if zone.bottom_vnum <= row.vnum <= zone.top_vnum:
                stats["used"].add(row.vnum)  # type: ignore[union-attr]
    for command in commands:
        if command.zone_id in per_zone:
            per_zone[command.zone_id]["commands"] = int(per_zone[command.zone_id]["commands"]) + 1  # type: ignore[arg-type]

    zone_rows: list[ZoneOverview] = []
    for z in zones:
        stats = per_zone[z.id]
        size = z.top_vnum - z.bottom_vnum + 1
        assigned = (z.bottom_vnum, z.top_vnum) != (0, 0) and size > 0
        zone_rows.append(
            ZoneOverview(
                id=z.id,
                vnum=z.vnum,
                name=z.name,
                enabled=z.enabled,
                bottom_vnum=z.bottom_vnum,
                top_vnum=z.top_vnum,
                rooms=int(stats["rooms"]),  # type: ignore[arg-type]
                mobs=int(stats["mobs"]),  # type: ignore[arg-type]
                objects=int(stats["objects"]),  # type: ignore[arg-type]
                range_usage_pct=round(100 * len(stats["used"]) / size, 1) if assigned else None,  # type: ignore[arg-type]
                reset_commands=int(stats["commands"]),  # type: ignore[arg-type]
            )
        )

    # warning di qualita'
    warnings: list[QualityWarning] = []
    totals: dict[str, int] = {}

    def make(
        kind: WarningKind,
        entity_type: EntityType,
        entity_id: int,
        vnum: int,
        name: str,
        zone_id: int,
        params: dict[str, int] | None = None,
    ) -> QualityWarning:
        """Costruisce un warning risolvendo il nome della zona."""
        return QualityWarning(
            kind=kind,
            entity_type=entity_type,
            entity_id=entity_id,
            vnum=vnum,
            name=name,
            zone_id=zone_id,
            zone_name=zone_by_id[zone_id].name,
            params=params or {},
        )

    for row in rooms:
        if not (row.description or "").strip():
            _push(warnings, totals, make("room_empty_description", "room", row.id, row.vnum, row.name, row.zone_id))
    for row in dangling:
        _push(
            warnings,
            totals,
            make("exit_without_target", "room", row.id, row.vnum, row.name, row.zone_id, {"direction": int(row.direction)}),
        )
    for z in zones:
        stats = per_zone[z.id]
        if stats["commands"] == 0 and (stats["mobs"] or stats["objects"]):
            _push(warnings, totals, make("zone_empty_reset_script", "zone", z.id, z.vnum, z.name, z.id))
    for entity_type, rows in (("room", rooms), ("mob", mobs), ("object", objects)):
        for row in rows:
            zone = zone_by_id[row.zone_id]
            if (zone.bottom_vnum, zone.top_vnum) == (0, 0) or zone.bottom_vnum <= row.vnum <= zone.top_vnum:
                continue
            name = row.name if entity_type == "room" else row.short_description
            _push(
                warnings,
                totals,
                make(
                    "vnum_out_of_range",
                    entity_type,
                    row.id,
                    row.vnum,
                    name,
                    row.zone_id,
                    {"bottom": zone.bottom_vnum, "top": zone.top_vnum},
                ),
            )
    loaded_mobs = {c.arg1 for c in commands if c.command_type == ZoneCommandType.LOAD_MOB}
    loaded_objects = {
        c.arg1
        for c in commands
        if c.command_type
        in (ZoneCommandType.LOAD_OBJECT, ZoneCommandType.GIVE_OBJECT, ZoneCommandType.EQUIP_OBJECT, ZoneCommandType.PUT_OBJECT)
    } | {c.arg3 for c in commands if c.command_type == ZoneCommandType.PUT_OBJECT}
    for row in mobs:
        if row.vnum not in loaded_mobs:
            _push(warnings, totals, make("mob_never_loaded", "mob", row.id, row.vnum, row.short_description, row.zone_id))
    for row in objects:
        if row.vnum not in loaded_objects:
            _push(warnings, totals, make("object_never_loaded", "object", row.id, row.vnum, row.short_description, row.zone_id))

    return WorldOverview(counts=counts, zones=zone_rows, warnings=warnings, warning_totals=totals)


@router.get("/overview", response_model=WorldOverview)
async def world_overview(session: SessionDep) -> WorldOverview:
    """Conteggi del mondo, tabella per zona e warning di qualita' dei dati (max 100 per tipo)."""
    return await build_overview(session)


# --------------------------------------------------------------------------- zone graph


class ZoneGraphNode(AliasedBaseModel):
    """Una zona del grafo; `isolated` = nessuna uscita attraversa il suo confine (ne' in ne' out)."""

    id: int
    vnum: int
    name: str
    enabled: bool
    rooms: int
    isolated: bool


class ZoneGraphEdge(AliasedBaseModel):
    """Arco orientato: `count` uscite di stanze di `fromZoneId` che portano in stanze di `toZoneId`."""

    from_zone_id: int
    to_zone_id: int
    count: int


class ZoneGraph(AliasedBaseModel):
    """Risposta di `GET /world/zone-graph`."""

    nodes: list[ZoneGraphNode]
    edges: list[ZoneGraphEdge]


@router.get("/zone-graph", response_model=ZoneGraph)
async def zone_graph(session: SessionDep) -> ZoneGraph:
    """Zone come nodi, archi dove un'uscita attraversa il confine di zona (con conteggio)."""
    Zone, Room, Exit = (models_of(session).Zone, models_of(session).Room, models_of(session).Exit)  # noqa: N806
    zones = (await session.execute(select(Zone).order_by(Zone.vnum))).scalars().all()
    room_counts = dict((await session.execute(select(Room.zone_id, func.count()).group_by(Room.zone_id))).all())
    target = Room.__table__.alias("target_room")
    rows = (
        await session.execute(
            select(Room.zone_id, target.c.zone_id, func.count())
            .select_from(Exit)
            .join(Room, Room.id == Exit.room_id)
            .join(target, target.c.id == Exit.target_room_id)
            .where(Room.zone_id != target.c.zone_id)
            .group_by(Room.zone_id, target.c.zone_id)
            .order_by(Room.zone_id, target.c.zone_id)
        )
    ).all()
    edges = [ZoneGraphEdge(from_zone_id=a, to_zone_id=b, count=n) for a, b, n in rows]
    connected = {e.from_zone_id for e in edges} | {e.to_zone_id for e in edges}
    nodes = [
        ZoneGraphNode(
            id=z.id,
            vnum=z.vnum,
            name=z.name,
            enabled=z.enabled,
            rooms=room_counts.get(z.id, 0),
            isolated=z.id not in connected,
        )
        for z in zones
    ]
    return ZoneGraph(nodes=nodes, edges=edges)


# --------------------------------------------------------------------------- search


class SearchHit(AliasedBaseModel):
    """Un risultato di ricerca. `name` = nome zona/stanza o descrizione breve di mob/oggetto;
    `keywords` solo per mob e oggetti. Per le zone `zoneId` e' l'id della zona stessa."""

    id: int
    vnum: int
    name: str
    keywords: str | None = None
    zone_id: int
    zone_name: str


class SearchGroup(AliasedBaseModel):
    """Risultati di un tipo: `items` limitati a `limit`, `total` = corrispondenze reali."""

    items: list[SearchHit] = []
    total: int = 0


class SearchResults(AliasedBaseModel):
    """Risposta di `GET /world/search`."""

    q: str
    zones: SearchGroup
    rooms: SearchGroup
    mobs: SearchGroup
    objects: SearchGroup


def escape_like(text: str) -> str:
    """Rende letterali `%`, `_` e `\\` in un pattern LIKE (da usare con `escape="\\\\"`)."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def parse_types(raw: str | None) -> list[SearchType]:
    """Elenco di tipi da `types` (separati da virgola); vuoto/assente = tutti. 422 `world.invalid_types` se ignoti."""
    if raw is None or not raw.strip():
        return list(SEARCH_TYPES)
    wanted = [part.strip().lower() for part in raw.split(",") if part.strip()]
    unknown = [part for part in wanted if part not in SEARCH_TYPES]
    if unknown:
        raise api_error(422, "world.invalid_types", types=", ".join(unknown))
    return [t for t in SEARCH_TYPES if t in wanted]


async def _search_group(session: AsyncSession, kind: SearchType, term: str, limit: int) -> SearchGroup:
    """Cerca per prefisso di vnum o per sottostringa nei campi testuali del tipo `kind`."""
    m = models_of(session)
    Zone, Room, MobPrototype, ObjectPrototype = m.Zone, m.Room, m.MobPrototype, m.ObjectPrototype  # noqa: N806
    esc = "\\"
    escaped = escape_like(term)
    if kind == "zone":
        model, text_cols, kw_col = Zone, (Zone.name, Zone.builder), None
        name_col = Zone.name
    elif kind == "room":
        model, text_cols, kw_col = Room, (Room.name,), None
        name_col = Room.name
    elif kind == "mob":
        model = MobPrototype
        text_cols = (MobPrototype.keywords, MobPrototype.short_description)
        name_col, kw_col = MobPrototype.short_description, MobPrototype.keywords
    else:
        model = ObjectPrototype
        text_cols = (ObjectPrototype.keywords, ObjectPrototype.short_description)
        name_col, kw_col = ObjectPrototype.short_description, ObjectPrototype.keywords
    cond = or_(
        cast(model.vnum, String).like(f"{escaped}%", escape=esc),
        *[col.ilike(f"%{escaped}%", escape=esc) for col in text_cols],
    )
    total = (await session.execute(select(func.count()).select_from(model).where(cond))).scalar_one()
    keywords = kw_col if kw_col is not None else literal(None)
    if kind == "zone":
        stmt = select(Zone.id, Zone.vnum, name_col, keywords, Zone.id, Zone.name)
    else:
        stmt = select(model.id, model.vnum, name_col, keywords, model.zone_id, Zone.name).join(Zone, Zone.id == model.zone_id)
    rows = (await session.execute(stmt.where(cond).order_by(model.vnum).limit(limit))).all()
    items = [SearchHit(id=r[0], vnum=r[1], name=r[2], keywords=r[3], zone_id=r[4], zone_name=r[5]) for r in rows]
    return SearchGroup(items=items, total=total)


@router.get("/search", response_model=SearchResults)
async def world_search(
    session: SessionDep,
    q: Annotated[str, Query(min_length=1, max_length=100)],
    types: Annotated[str | None, Query(description="zone,room,mob,object separati da virgola; default tutti")] = None,
    limit: Annotated[int, Query(ge=1, le=100, description="Massimo risultati per tipo")] = 20,
) -> SearchResults:
    """Ricerca globale su zone, stanze, mob e oggetti: prefisso del vnum oppure sottostringa (ILIKE,
    caratteri jolly `%`/`_` letterali) su nome/keywords. Al massimo `limit` risultati per tipo, ordinati per vnum."""
    wanted = parse_types(types)
    term = q.strip()
    if not term:
        raise api_error(422, "world.empty_query")
    groups = {kind: SearchGroup() for kind in SEARCH_TYPES}
    for kind in wanted:
        groups[kind] = await _search_group(session, kind, term, limit)
    return SearchResults(q=term, zones=groups["zone"], rooms=groups["room"], mobs=groups["mob"], objects=groups["object"])


# --------------------------------------------------------------------------- next-zone-range


class ZoneRange(AliasedBaseModel):
    """Range di vnum libero: `[bottomVnum, topVnum]` di `span` vnum."""

    bottom_vnum: int
    top_vnum: int


@router.get("/next-zone-range", response_model=ZoneRange)
async def next_zone_range(session: SessionDep, span: Annotated[int, Query(ge=1, le=100000)] = 100) -> ZoneRange:
    """Il primo range di `span` vnum consecutivi (a partire da 1) che non tocca il range di nessuna zona
    (i range 0-0, "da assegnare", sono ignorati). Riempie anche i buchi tra una zona e l'altra."""
    Zone = models_of(session).Zone  # noqa: N806
    taken = sorted((await session.execute(select(Zone.bottom_vnum, Zone.top_vnum))).all(), key=lambda row: row.bottom_vnum)
    bottom = 1
    for low, high in taken:
        if (low, high) == (0, 0):
            continue
        if bottom + span - 1 < low:
            break
        bottom = max(bottom, high + 1)
    return ZoneRange(bottom_vnum=bottom, top_vnum=bottom + span - 1)
