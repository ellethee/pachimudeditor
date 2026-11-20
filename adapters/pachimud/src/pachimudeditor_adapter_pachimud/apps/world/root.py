"""Mondo: panoramica, grafo tra zone, ricerca globale e primo range di vnum libero. Prefisso `/api/world`.

Tutte le route sono in sola lettura. I "warning" di qualita' dei dati sono identificati da un `kind`
stabile (tradotto dal frontend), non da un codice di errore HTTP.
"""

from typing import Annotated, Literal

from fastapi import Depends, Query
from pachifast.database import AliasedBaseModel
from pachifast.i18n import api_error
from pachifast.router_factory import get_router
from sqlalchemy import func, select

from pachimudeditor.sdk import require_capability
from pachimudeditor_adapter_pachimud import integrity, resets
from pachimudeditor_adapter_pachimud.editor.db import PachimudDep
from pachimudeditor_adapter_pachimud.store import YamlStore

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
    "duplicate_vnum",
    "reset_unknown_room",
    "reset_unknown_mob",
    "reset_unknown_object",
    "exit_key_missing",
    "container_key_missing",
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


class FileProblem(AliasedBaseModel):
    """Un file YAML (o una sua voce) che non si e' potuto leggere: percorso relativo a `definitions/`, riga, messaggio."""

    path: str
    line: int | None = None
    message: str
    severity: Literal["error", "warning"] = "error"


class WorldOverview(AliasedBaseModel):
    """Risposta di `GET /world/overview`."""

    counts: WorldCounts
    zones: list[ZoneOverview]
    warnings: list[QualityWarning]
    warning_totals: dict[str, int]
    file_problems: list[FileProblem] = []
    """File YAML illeggibili o voci non valide (saltati, il resto del mondo si legge comunque)."""


async def _db_counts(adapter: PachimudDep) -> tuple[int, int]:
    """`(account, personaggi)` dal DB dei giocatori, `(0, 0)` se non c'e' o non si legge."""
    if adapter.connection is None:
        return 0, 0
    try:
        async with adapter.connection.session() as session:
            models = session.info["models"]
            counts = []
            for model in (models.Account, models.PlayerCharacter):
                counts.append(0 if model is None else int((await session.execute(select(func.count()).select_from(model))).scalar_one()))
            return counts[0], counts[1]
    except Exception:  # noqa: BLE001 - la panoramica dei contenuti non dipende dal DB dei giocatori
        return 0, 0


def build_overview(adapter: PachimudDep, accounts: int, characters: int) -> WorldOverview:
    """Calcola conteggi, riepilogo per zona e warning di qualita' dei dati."""
    store = adapter.sync()
    zones = store.zones
    rows: list[ZoneOverview] = []
    for z in zones:
        m = z.model
        size = m.top_vnum - m.bottom_vnum + 1
        assigned = (m.bottom_vnum, m.top_vnum) != (0, 0) and size > 0
        used = {i.vnum for kind in ("room", "mob", "object") for i in z.items[kind] if m.bottom_vnum <= i.vnum <= m.top_vnum}  # type: ignore[index]
        rows.append(
            ZoneOverview(
                id=m.vnum,
                vnum=m.vnum,
                name=m.name,
                enabled=m.enabled,
                bottom_vnum=m.bottom_vnum,
                top_vnum=m.top_vnum,
                rooms=len(z.items["room"]),
                mobs=len(z.items["mob"]),
                objects=len(z.items["object"]),
                range_usage_pct=round(100 * len(used) / size, 1) if assigned else None,
                reset_commands=len(resets.flatten(z)),
            )
        )
    found = integrity.collect(store)
    totals = integrity.kinds_total(found)
    listed: dict[str, int] = {}
    warnings: list[QualityWarning] = []
    for w in found:
        listed[w.kind] = listed.get(w.kind, 0) + 1
        if listed[w.kind] <= WARNINGS_PER_KIND:
            warnings.append(
                QualityWarning(
                    kind=w.kind,  # type: ignore[arg-type]
                    entity_type=w.entity_type,  # type: ignore[arg-type]
                    entity_id=w.vnum,
                    vnum=w.vnum,
                    name=w.name,
                    zone_id=w.zone.vnum,
                    zone_name=w.zone.model.name,
                    params=w.params,
                )
            )
    counts = WorldCounts(
        zones=len(zones),
        zones_enabled=sum(1 for z in zones if z.model.enabled),
        zones_disabled=sum(1 for z in zones if not z.model.enabled),
        rooms=len(store.vnums("room")),
        mobs=len(store.vnums("mob")),
        objects=len(store.vnums("object")),
        mob_instances=0,
        object_instances=0,
        accounts=accounts,
        characters=characters,
    )
    problems = [FileProblem(path=i.path, line=i.line, message=i.message, severity=i.severity) for i in store.issues]
    return WorldOverview(counts=counts, zones=rows, warnings=warnings, warning_totals=totals, file_problems=problems)


@router.get("/overview", response_model=WorldOverview)
async def world_overview(adapter: PachimudDep) -> WorldOverview:
    """Conteggi del mondo, tabella per zona e warning di qualita' dei dati (max 100 per tipo)."""
    accounts, characters = await _db_counts(adapter)
    return build_overview(adapter, accounts, characters)


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
async def zone_graph(adapter: PachimudDep) -> ZoneGraph:
    """Zone come nodi, archi dove un'uscita attraversa il confine di zona (con conteggio)."""
    store = adapter.sync()
    counts: dict[tuple[int, int], int] = {}
    for room in store.all_items("room"):
        for x in room.model.exits.values():
            target = store.find("room", x.target_vnum) if x.target_vnum is not None else None
            if target is not None and target.zone is not room.zone:
                key = (room.zone.vnum, target.zone.vnum)
                counts[key] = counts.get(key, 0) + 1
    edges = [ZoneGraphEdge(from_zone_id=a, to_zone_id=b, count=n) for (a, b), n in sorted(counts.items())]
    connected = {e.from_zone_id for e in edges} | {e.to_zone_id for e in edges}
    nodes = [
        ZoneGraphNode(
            id=z.vnum,
            vnum=z.vnum,
            name=z.model.name,
            enabled=z.model.enabled,
            rooms=len(z.items["room"]),
            isolated=z.vnum not in connected,
        )
        for z in store.zones
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


def parse_types(raw: str | None) -> list[SearchType]:
    """Elenco di tipi da `types` (separati da virgola); vuoto/assente = tutti. 422 `world.invalid_types` se ignoti."""
    if raw is None or not raw.strip():
        return list(SEARCH_TYPES)
    wanted = [part.strip().lower() for part in raw.split(",") if part.strip()]
    unknown = [part for part in wanted if part not in SEARCH_TYPES]
    if unknown:
        raise api_error(422, "world.invalid_types", types=", ".join(unknown))
    return [t for t in SEARCH_TYPES if t in wanted]


def _search_group(store: YamlStore, kind: SearchType, term: str, limit: int) -> SearchGroup:
    """Cerca per prefisso di vnum o per sottostringa nei campi testuali del tipo `kind` (ordine per vnum)."""
    needle = term.lower()
    hits: list[SearchHit] = []
    if kind == "zone":
        entries = [(z.vnum, z.model.name, None, z, (z.model.name, z.model.builder)) for z in store.zones]
    else:
        entries = []
        for item in store.all_items(kind):
            m = item.model
            name = m.name if kind == "room" else m.short_description
            keywords = None if kind == "room" else m.keywords
            entries.append((item.vnum, name, keywords, item.zone, (name, keywords or "")))
    for vnum, name, keywords, zone, texts in entries:
        if str(vnum).startswith(term) or any(needle in text.lower() for text in texts):
            hits.append(SearchHit(id=vnum, vnum=vnum, name=name, keywords=keywords, zone_id=zone.vnum, zone_name=zone.model.name))
    return SearchGroup(items=hits[:limit], total=len(hits))


@router.get("/search", response_model=SearchResults)
async def world_search(
    adapter: PachimudDep,
    q: Annotated[str, Query(min_length=1, max_length=100)],
    types: Annotated[str | None, Query(description="zone,room,mob,object separati da virgola; default tutti")] = None,
    limit: Annotated[int, Query(ge=1, le=100, description="Massimo risultati per tipo")] = 20,
) -> SearchResults:
    """Ricerca globale su zone, stanze, mob e oggetti: prefisso del vnum oppure sottostringa (senza maiuscole,
    senza maiuscole) su nome/keywords. Al massimo `limit` risultati per tipo, ordinati per vnum."""
    wanted = parse_types(types)
    term = q.strip()
    if not term:
        raise api_error(422, "world.empty_query")
    groups = {kind: SearchGroup() for kind in SEARCH_TYPES}
    for kind in wanted:
        groups[kind] = _search_group(adapter.sync(), kind, term, limit)
    return SearchResults(q=term, zones=groups["zone"], rooms=groups["room"], mobs=groups["mob"], objects=groups["object"])


# --------------------------------------------------------------------------- next-zone-range


class ZoneRange(AliasedBaseModel):
    """Range di vnum libero: `[bottomVnum, topVnum]` di `span` vnum."""

    bottom_vnum: int
    top_vnum: int


@router.get("/next-zone-range", response_model=ZoneRange)
async def next_zone_range(adapter: PachimudDep, span: Annotated[int, Query(ge=1, le=100000)] = 100) -> ZoneRange:
    """Il primo range di `span` vnum consecutivi (a partire da 1) che non tocca il range di nessuna zona
    (i range 0-0, "da assegnare", sono ignorati). Riempie anche i buchi tra una zona e l'altra."""
    taken = sorted((z.model.bottom_vnum, z.model.top_vnum) for z in adapter.sync().zones)
    bottom = 1
    for low, high in taken:
        if (low, high) == (0, 0):
            continue
        if bottom + span - 1 < low:
            break
        bottom = max(bottom, high + 1)
    return ZoneRange(bottom_vnum=bottom, top_vnum=bottom + span - 1)
