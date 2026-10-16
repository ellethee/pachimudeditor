"""Regole di validazione e integrita' indipendenti dal backend dati (DB o file).

Tutto qui e' riusabile da qualsiasi `WorldAdapter`: funzioni pure oppure async che ricevono un
piccolo "lookup" (callable) al posto di una sessione SQLAlchemy.

- script di reset (comandi ROM M/O/G/E/P/D/R): `structural_problems`, `validate_script`, `to_issues`;
- coerenza di un'uscita: `check_exit`;
- range di zone (vnum e livelli): `check_zone_ranges`, `suggest_zone_range`, `range_clash`;
- vnum liberi: `first_free_vnum`;
- uso nei reset: `USAGE_FIELDS`, `raise_if_used`;
- grafo delle stanze: `build_room_graph`.

Semantica degli argomenti dei reset (vedi `pachimud.zone.importer._reset_args`):

- `LOAD_MOB`: arg1 vnum mob, arg2 massimo nel mondo, arg3 vnum stanza, arg4 massimo nella stanza (opzionale)
- `LOAD_OBJECT`: arg1 vnum oggetto, arg2 massimo, arg3 vnum stanza, arg4 massimo nella stanza (opzionale)
- `GIVE_OBJECT`: arg1 vnum oggetto, arg2 massimo (opzionale); va all'ultimo mob caricato
- `EQUIP_OBJECT`: arg1 vnum oggetto, arg2 massimo (opzionale), `argStr` slot di vestizione
- `PUT_OBJECT`: arg1 vnum oggetto, arg2 massimo (opzionale), arg3 vnum del contenitore
- `SET_DOOR_STATE`: arg1 vnum stanza, arg2 direzione 0-5, `argStr` stato (OPEN/CLOSED/LOCKED)
- `RANDOMIZE_EXITS`: arg1 vnum stanza
"""

from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from pachifast.i18n import api_error, translate
from pachimudeditor.common.enums import ZoneCommandType
from pachimudeditor.common.enums import Direction, DoorFlag, SectorType

from pachimudeditor.common.adapters.layout import LayoutEdge, LayoutNode, compute_layout
from pachimudeditor.common.adapters.models import (
    EXTENDED_COMMAND_TYPES,
    EntityKind,
    GraphEdge,
    GraphNode,
    ResetCommandDraft,
    ResetIssue,
    ResetUsage,
    RoomGraph,
)
from pachimudeditor.common.editor.errors import conflict

# --------------------------------------------------------------------------- script di reset

DOOR_STATES: frozenset[str] = frozenset({"OPEN", "CLOSED", "LOCKED"})
"""Valori ammessi di `argStr` per `SET_DOOR_STATE`."""

CHARM_MOB = 7
"""Comando Diku Modificato `C`: mob seguace incantato (arg1 mob, arg2 massimo, arg3 bit act)."""
SET_HATE = 8
"""Comando Diku Modificato `H`: odio del mob corrente (arg1 tipo, arg2 valore; tipo 7 = vnum di un mob)."""
SET_FEAR = 9
"""Comando Diku Modificato `F`: paura del mob corrente (come `H`)."""
SET_MOB_ZONE = 10
"""Comando Diku Modificato `Z`: zona (indice) del mob corrente (arg1 zona, arg2 flag)."""
EXTENDED_TYPES = EXTENDED_COMMAND_TYPES
"""Tipi di comando oltre `ZoneCommandType`: solo alcuni mondi (Diku Modificato) li usano; pachimud li rifiuta."""
HATE_FEAR_MOB_TYPE = 7
"""Per `H`/`F`: `arg1 == 7` significa che `arg2` e' un vnum di mob."""

_REQUIRED: dict[Any, tuple[str, ...]] = {
    CHARM_MOB: ("arg1", "arg2", "arg3"),
    SET_HATE: ("arg1", "arg2"),
    SET_FEAR: ("arg1", "arg2"),
    SET_MOB_ZONE: ("arg1", "arg2"),
    ZoneCommandType.LOAD_MOB: ("arg1", "arg2", "arg3"),
    ZoneCommandType.LOAD_OBJECT: ("arg1", "arg2", "arg3"),
    ZoneCommandType.GIVE_OBJECT: ("arg1",),
    ZoneCommandType.EQUIP_OBJECT: ("arg1",),
    ZoneCommandType.PUT_OBJECT: ("arg1", "arg3"),
    ZoneCommandType.SET_DOOR_STATE: ("arg1", "arg2"),
    ZoneCommandType.RANDOMIZE_EXITS: ("arg1",),
}
"""Argomenti numerici obbligatori per tipo di comando."""

_ARG_STR_TYPES = (ZoneCommandType.EQUIP_OBJECT, ZoneCommandType.SET_DOOR_STATE)
"""Gli unici comandi in cui `argStr` ha significato."""

MAX_SANE = 100
"""Oltre questo `max esistenti` si segnala un avvertimento (probabile refuso)."""


@dataclass(frozen=True)
class Problem:
    """Un problema trovato in un comando: codice di catalogo, parametri, gravita'."""

    code: str
    params: dict[str, Any] = field(default_factory=dict)
    severity: Literal["error", "warning"] = "error"


class ResetLookup(Protocol):
    """Cio' che `validate_script` chiede al backend dati (implementato da ogni adapter)."""

    async def existing_vnums(self, kind: EntityKind, vnums: set[int]) -> set[int]:
        """Quali tra `vnums` esistono come stanza/mob/oggetto."""
        ...

    async def exit_has_door(self, room_vnum: int, direction: int) -> bool | None:
        """`None` se la stanza non ha un'uscita in quella direzione, altrimenti se ha una porta."""
        ...


def structural_problems(
    command_type: ZoneCommandType,
    *,
    arg1: int | None = None,
    arg2: int | None = None,
    arg3: int | None = None,
    arg4: int | None = None,
    arg_str: str | None = None,
) -> list[Problem]:
    """Problemi di un singolo comando, indipendenti dal resto del mondo e dallo script."""
    args = {"arg1": arg1, "arg2": arg2, "arg3": arg3, "arg4": arg4}
    problems: list[Problem] = []
    for name, value in args.items():
        if value is not None and value < 0:
            problems.append(Problem("zones.reset_negative_arg", {"arg": name, "value": value}))
    for name in _REQUIRED.get(command_type, ()):
        if args[name] is None:
            problems.append(Problem("zones.reset_missing_arg", {"arg": name}))
    if command_type is ZoneCommandType.SET_DOOR_STATE and arg2 is not None and not 0 <= arg2 <= 5:
        problems.append(Problem("zones.reset_invalid_direction", {"value": arg2}))
    if command_type is ZoneCommandType.EQUIP_OBJECT and not (arg_str or "").strip():
        problems.append(Problem("zones.reset_slot_required"))
    if command_type is ZoneCommandType.SET_DOOR_STATE and (arg_str or "").upper() not in DOOR_STATES:
        problems.append(Problem("zones.reset_invalid_door_state", {"value": arg_str or ""}))
    if arg_str is not None and command_type not in _ARG_STR_TYPES:
        problems.append(Problem("zones.reset_arg_str_not_allowed"))
    return problems


def first_structural_message(command_type: ZoneCommandType, **args: Any) -> str | None:
    """Il messaggio tradotto del primo problema strutturale, o None se il comando e' ben formato."""
    problems = structural_problems(command_type, **args)
    return translate(problems[0].code, problems[0].params) if problems else None


async def validate_script(lookup: ResetLookup, commands: Sequence[ResetCommandDraft]) -> list[tuple[int, Problem]]:
    """Tutti i problemi dello script (ordine di esecuzione = ordine lista) come coppie (indice, problema).

    Errori: problemi strutturali e vnum inesistenti. Avvertimenti: `ifFlag` sul primo comando,
    G/E senza un `LOAD_MOB` prima, P il cui contenitore non e' stato caricato prima, massimi
    sospetti (zero, oltre `MAX_SANE`, limite per stanza sopra il globale), porta su un'uscita
    inesistente o senza porta. Non scrive nulla.
    """
    mob_vnums: set[int] = set()
    object_vnums: set[int] = set()
    room_vnums: set[int] = set()
    for c in commands:
        t = c.command_type
        if t == CHARM_MOB:
            mob_vnums |= {c.arg1} - {None}  # type: ignore[arg-type]
        elif t in (SET_HATE, SET_FEAR):
            if c.arg1 == HATE_FEAR_MOB_TYPE:
                mob_vnums |= {c.arg2} - {None}  # type: ignore[arg-type]
        elif t == SET_MOB_ZONE:
            pass
        elif t is ZoneCommandType.LOAD_MOB:
            mob_vnums |= {c.arg1} - {None}  # type: ignore[arg-type]
            room_vnums |= {c.arg3} - {None}  # type: ignore[arg-type]
        elif t is ZoneCommandType.LOAD_OBJECT:
            object_vnums |= {c.arg1} - {None}  # type: ignore[arg-type]
            room_vnums |= {c.arg3} - {None}  # type: ignore[arg-type]
        elif t in (ZoneCommandType.GIVE_OBJECT, ZoneCommandType.EQUIP_OBJECT):
            object_vnums |= {c.arg1} - {None}  # type: ignore[arg-type]
        elif t is ZoneCommandType.PUT_OBJECT:
            object_vnums |= {c.arg1, c.arg3} - {None}  # type: ignore[arg-type]
        else:
            room_vnums |= {c.arg1} - {None}  # type: ignore[arg-type]
    mobs = await lookup.existing_vnums("mob", mob_vnums) if mob_vnums else set()
    objects = await lookup.existing_vnums("object", object_vnums) if object_vnums else set()
    rooms = await lookup.existing_vnums("room", room_vnums) if room_vnums else set()

    out: list[tuple[int, Problem]] = []
    loaded_mob = False
    loaded_objects: set[int] = set()

    def unknown(index: int, kind: str, vnum: int | None, known: set[int]) -> None:
        """Errore se `vnum` e' valorizzato ma non esiste."""
        if vnum is not None and vnum >= 0 and vnum not in known:
            out.append((index, Problem(f"zones.reset_unknown_{kind}", {"index": index, "vnum": vnum})))

    for index, c in enumerate(commands):
        t = c.command_type
        out.extend((index, p) for p in structural_problems(t, arg1=c.arg1, arg2=c.arg2, arg3=c.arg3, arg4=c.arg4, arg_str=c.arg_str))
        if c.if_flag and index == 0:
            out.append((index, Problem("zones.reset_if_flag_first", {"index": index}, "warning")))

        if t == CHARM_MOB:
            unknown(index, "mob", c.arg1, mobs)
            if not loaded_mob:
                out.append((index, Problem("zones.reset_no_mob_before", {"index": index}, "warning")))
        elif t in (SET_HATE, SET_FEAR):
            if c.arg1 == HATE_FEAR_MOB_TYPE:
                unknown(index, "mob", c.arg2, mobs)
            if not loaded_mob:
                out.append((index, Problem("zones.reset_no_mob_before", {"index": index}, "warning")))
        elif t == SET_MOB_ZONE:
            if not loaded_mob:
                out.append((index, Problem("zones.reset_no_mob_before", {"index": index}, "warning")))
        elif t is ZoneCommandType.LOAD_MOB:
            unknown(index, "mob", c.arg1, mobs)
            unknown(index, "room", c.arg3, rooms)
            loaded_mob = True
        elif t is ZoneCommandType.LOAD_OBJECT:
            unknown(index, "object", c.arg1, objects)
            unknown(index, "room", c.arg3, rooms)
            if c.arg1 is not None:
                loaded_objects.add(c.arg1)
        elif t in (ZoneCommandType.GIVE_OBJECT, ZoneCommandType.EQUIP_OBJECT):
            unknown(index, "object", c.arg1, objects)
            if not loaded_mob:
                out.append((index, Problem("zones.reset_no_mob_before", {"index": index}, "warning")))
        elif t is ZoneCommandType.PUT_OBJECT:
            unknown(index, "object", c.arg1, objects)
            unknown(index, "object", c.arg3, objects)
            if c.arg3 is not None and c.arg3 not in loaded_objects:
                out.append((index, Problem("zones.reset_container_not_loaded", {"index": index, "vnum": c.arg3}, "warning")))
            if c.arg1 is not None:
                loaded_objects.add(c.arg1)
        else:
            unknown(index, "room", c.arg1, rooms)
            if t is ZoneCommandType.SET_DOOR_STATE and c.arg1 in rooms and c.arg2 is not None and 0 <= c.arg2 <= 5:
                has_door = await lookup.exit_has_door(c.arg1, c.arg2)  # type: ignore[arg-type]
                direction = Direction(c.arg2).name
                params = {"index": index, "vnum": c.arg1, "direction": direction}
                if has_door is None:
                    out.append((index, Problem("zones.reset_no_such_exit", params, "warning")))
                elif not has_door:
                    out.append((index, Problem("zones.reset_exit_without_door", params, "warning")))

        if t in (ZoneCommandType.LOAD_MOB, ZoneCommandType.LOAD_OBJECT) and c.arg2 is not None and c.arg2 >= 0:
            if c.arg2 == 0:
                out.append((index, Problem("zones.reset_max_zero", {"index": index}, "warning")))
            elif c.arg2 > MAX_SANE:
                out.append((index, Problem("zones.reset_max_high", {"index": index, "max": c.arg2}, "warning")))
            if c.arg4 is not None and c.arg4 > c.arg2:
                out.append(
                    (
                        index,
                        Problem(
                            "zones.reset_room_cap_above_max",
                            {"index": index, "room_cap": c.arg4, "max": c.arg2},
                            "warning",
                        ),
                    )
                )
    return out


def to_issues(problems: Sequence[tuple[int, Problem]]) -> list[ResetIssue]:
    """Converte i problemi in `ResetIssue` con messaggio tradotto nella lingua della richiesta."""
    return [
        ResetIssue(index=i, severity=p.severity, code=p.code, params=p.params, message=translate(p.code, p.params)) for i, p in problems
    ]


def raise_script_errors(problems: Sequence[tuple[int, Problem]]) -> None:
    """422 sul primo problema di gravita' `error` (nulla va salvato), con `loc` = comando in errore."""
    for index, problem in problems:
        if problem.severity == "error":
            raise api_error(422, problem.code, loc=("body", "commands", index), **problem.params)


# --------------------------------------------------------------------------- uso nei reset

USAGE_FIELDS: dict[EntityKind, tuple[tuple[ZoneCommandType, str], ...]] = {
    "room": (
        (ZoneCommandType.LOAD_MOB, "arg3"),
        (ZoneCommandType.LOAD_OBJECT, "arg3"),
        (ZoneCommandType.SET_DOOR_STATE, "arg1"),
        (ZoneCommandType.RANDOMIZE_EXITS, "arg1"),
    ),
    "mob": ((ZoneCommandType.LOAD_MOB, "arg1"),),
    "object": (
        (ZoneCommandType.LOAD_OBJECT, "arg1"),
        (ZoneCommandType.GIVE_OBJECT, "arg1"),
        (ZoneCommandType.EQUIP_OBJECT, "arg1"),
        (ZoneCommandType.PUT_OBJECT, "arg1"),
        (ZoneCommandType.PUT_OBJECT, "arg3"),  # container_vnum: anche un contenitore e' un oggetto
    ),
}
"""Per ogni tipo di contenuto, quali (command_type, campo arg) del reset contengono quel vnum."""


def raise_if_used(usage: Sequence[ResetUsage], code: str) -> None:
    """409 `code` (parametri `count`, `zones`) se `usage` non e' vuoto."""
    if usage:
        zone_names = sorted({item.zone_name for item in usage})
        raise conflict(code, count=len(usage), zones=", ".join(zone_names))


# --------------------------------------------------------------------------- zone e vnum


def check_zone_ranges(bottom: int, top: int, min_level: int, max_level: int) -> None:
    """422 `zones.invalid_vnum_range` / `zones.invalid_level_range` se i range finali sono incoerenti."""
    if bottom > top:
        raise api_error(422, "zones.invalid_vnum_range", bottom=bottom, top=top)
    if min_level > max_level:
        raise api_error(422, "zones.invalid_level_range", min=min_level, max=max_level)


def suggest_zone_range(rows: Iterable[tuple[int, int, int]], span: int) -> tuple[int, int, int]:
    """`(vnum, bottom, top)` liberi dato l'elenco `(vnum, bottom_vnum, top_vnum)` delle zone esistenti.

    Il vnum e' uno oltre il piu' alto in uso; il range e' `vnum * 100` (convenzione DikuMUD) se non tocca
    altre zone, altrimenti subito dopo il range piu' alto. I range 0-0 ("da assegnare") sono ignorati.
    """
    rows = list(rows)
    vnum = max((r[0] for r in rows), default=0) + 1
    bottom = vnum * 100
    if any(bottom <= top and bottom + span >= low for _, low, top in rows if (low, top) != (0, 0)):
        bottom = max((top for _, _, top in rows), default=0) + 1
    return vnum, bottom, bottom + span


def range_clash(zones: Iterable[tuple[str, int, int, int]], bottom: int, top: int) -> tuple[str, int] | None:
    """`(nome, vnum)` della prima zona `(nome, vnum, bottom, top)` il cui range si sovrappone a `bottom..top`."""
    for name, vnum, low, high in zones:
        if (low, high) != (0, 0) and low <= top and high >= bottom:
            return name, vnum
    return None


def first_free_vnum(candidate: int, taken: set[int]) -> int:
    """Il primo vnum >= `candidate` non presente in `taken`."""
    while candidate in taken:
        candidate += 1
    return candidate


# --------------------------------------------------------------------------- uscite


async def check_exit(
    room_id: int,
    final: dict[str, Any],
    touched: set[str],
    key_exists: Callable[[int], Awaitable[bool]],
) -> None:
    """Coerenza di un'uscita (422), limitata ai campi `touched` cosi' dati preesistenti incoerenti
    restano modificabili: porta assente (`door_flag` NONE) non puo' essere chiusa/serrata, serrata
    richiede `key_vnum`, la chiave deve esistere come oggetto (`key_exists`), niente uscita verso la
    stessa stanza. `final` ha i nomi Python dei campi dell'uscita risultante."""
    if touched & {"door_flag", "is_open", "is_locked"} and final["door_flag"] == DoorFlag.NONE:
        if not final["is_open"] or final["is_locked"]:
            raise api_error(422, "rooms.exit_door_state_invalid")
    if touched & {"is_locked", "key_vnum"} and final["is_locked"] and final["key_vnum"] is None:
        raise api_error(422, "rooms.exit_locked_needs_key")
    key_vnum = final["key_vnum"]
    if "key_vnum" in touched and key_vnum is not None and not await key_exists(key_vnum):
        raise api_error(422, "rooms.exit_key_unknown", vnum=key_vnum)
    if "target_room_id" in touched and final["target_room_id"] == room_id:
        raise api_error(422, "rooms.exit_self_loop")


# --------------------------------------------------------------------------- grafo

OPPOSITE: dict[Direction, Direction] = {
    Direction.NORTH: Direction.SOUTH,
    Direction.SOUTH: Direction.NORTH,
    Direction.EAST: Direction.WEST,
    Direction.WEST: Direction.EAST,
    Direction.UP: Direction.DOWN,
    Direction.DOWN: Direction.UP,
}
"""La direzione dell'uscita che riporta indietro."""


@dataclass(frozen=True)
class GraphRoom:
    """Una stanza in ingresso a `build_room_graph`."""

    id: int
    vnum: int
    name: str
    sector_type: SectorType
    flags: list[str]


@dataclass(frozen=True)
class GraphExit:
    """Un'uscita in ingresso a `build_room_graph` (`target_room_id` puo' essere None o fuori zona)."""

    id: int
    room_id: int
    direction: Direction
    door_flag: DoorFlag
    target_room_id: int | None


def build_room_graph(rooms: Sequence[GraphRoom], exits: Sequence[GraphExit]) -> RoomGraph:
    """Nodi (con layout a bussola) e archi delle stanze di una zona.

    Gli archi collegano solo stanze della zona; due uscite opposte reciproche diventano un solo arco
    `twoWay`. Le uscite senza destinazione sono contate in `danglingExits` del nodo.
    """
    room_ids = {room.id for room in rooms}
    dangling: dict[int, int] = {}
    for e in exits:
        if e.target_room_id is None:
            dangling[e.room_id] = dangling.get(e.room_id, 0) + 1

    graph_exits = sorted((e for e in exits if e.target_room_id is not None and e.target_room_id in room_ids), key=lambda e: e.id)
    by_key = {(e.room_id, e.direction): e for e in graph_exits}
    merged: set[int] = set()
    edges: list[GraphEdge] = []
    for e in graph_exits:
        if e.id in merged:
            continue
        back = by_key.get((e.target_room_id, OPPOSITE[e.direction]))  # type: ignore[arg-type]
        two_way = back is not None and back.target_room_id == e.room_id
        if two_way:
            merged.add(back.id)  # type: ignore[union-attr]
        edges.append(
            GraphEdge(
                id=e.id,
                from_room_id=e.room_id,
                to_room_id=e.target_room_id,  # type: ignore[arg-type]
                direction=e.direction,
                door_flag=e.door_flag,
                two_way=two_way,
                reverse_exit_id=back.id if two_way else None,  # type: ignore[union-attr]
            )
        )

    layout = compute_layout(
        [LayoutNode(id=room.id, vnum=room.vnum) for room in rooms],
        [LayoutEdge(from_id=e.from_room_id, to_id=e.to_room_id, direction=e.direction) for e in edges],
    )
    nodes = [
        GraphNode(
            id=room.id,
            vnum=room.vnum,
            name=room.name,
            sector_type=room.sector_type,
            flags=list(room.flags),
            x=layout[room.id][0],
            y=layout[room.id][1],
            dangling_exits=dangling.get(room.id, 0),
        )
        for room in sorted(rooms, key=lambda r: r.vnum)
    ]
    return RoomGraph(nodes=nodes, edges=edges)
