"""Pianificazione: dove finisce ogni zona (vnum, range), e cosa ne e' (crea, sostituisci, salta, bloccata).

Parte dalle zone sorgente lette e dall'indice del mondo di arrivo; non scrive nulla. Politiche di vnum:

- `keep`: nessun cambiamento (vnum di zona e range invariati);
- `offset N`: contenuto, range e vnum di zona di ogni zona sommano `N`;
- `shift_to`: le zone vanno nel primo intervallo libero dell'arrivo (`next_zone_vnum`), una dopo l'altra.

Un contenuto sorgente fuori dal range dichiarato dalla zona (o una zona senza range, `0 0`) allarga il range
effettivo: il mondo di arrivo accetta solo vnum dentro il range della sua zona.
"""

from dataclasses import dataclass, field

from pachifast.i18n import api_error

from pachimudeditor.common.adapters.base import WorldAdapter
from pachimudeditor.common.adapters.convert.models import ConvertConflict, ConvertPlan
from pachimudeditor.common.adapters.convert.reader import SourceZone, TargetIndex
from pachimudeditor.common.adapters.models import ZoneOut


@dataclass
class ZonePlan:
    """Il destino di una zona sorgente."""

    src: SourceZone
    target_vnum: int
    bottom: int
    top: int
    offset: int
    action: str = "create"
    existing: ZoneOut | None = None
    """La zona gia' presente nel mondo di arrivo che questa corrisponde (per `replace`/`skip`)."""
    conflicts: list[ConvertConflict] = field(default_factory=list)

    @property
    def written(self) -> bool:
        """`True` se la zona viene scritta (create/replace)."""
        return self.action in ("create", "replace")


def effective_range(src: SourceZone) -> tuple[int, int]:
    """Range effettivo della zona sorgente: quello dichiarato, allargato al contenuto (o al contenuto, se `0 0`)."""
    vnums = src.vnums
    low, high = src.zone.bottom_vnum, src.zone.top_vnum
    if not vnums:
        return low, high
    if (low, high) == (0, 0):
        return min(vnums), max(vnums)
    return min(low, min(vnums)), max(high, max(vnums))


async def allocate(target: WorldAdapter, sources: list[SourceZone], plan: ConvertPlan) -> list[ZonePlan]:
    """Assegna a ogni zona vnum di zona, range e scostamento secondo la politica."""
    policy = plan.vnum_policy
    plans: list[ZonePlan] = []
    first = None
    cursor = 0
    for index, src in enumerate(sources):
        low, high = effective_range(src)
        if policy.mode == "keep":
            new = ZonePlan(src, src.zone.vnum, low, high, 0)
        elif policy.mode == "offset":
            if low + policy.offset < 0 or src.zone.vnum + policy.offset < 0:
                raise api_error(422, "convert.offset_negative", zone=src.zone.vnum, offset=policy.offset)
            new = ZonePlan(src, src.zone.vnum + policy.offset, low + policy.offset, high + policy.offset, policy.offset)
        else:
            span = high - low
            if first is None:
                first = await target.next_zone_vnum(span)
                bottom = first.bottom_vnum
            else:
                bottom = cursor
            vnum = bottom if first.vnum == first.bottom_vnum else first.vnum + index
            new = ZonePlan(src, vnum, bottom, bottom + span, bottom - low)
            cursor = bottom + span + 1
        plans.append(new)
    return plans


def _overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    """I due range (non `0 0`) si sovrappongono?"""
    return a != (0, 0) and b != (0, 0) and a[0] <= b[1] and b[0] <= a[1]


def detect_conflicts(plans: list[ZonePlan], index: TargetIndex, plan: ConvertPlan) -> None:
    """Imposta `action`, `existing` e `conflicts` di ogni piano (modifica sul posto).

    Corrispondenza con una zona dell'arrivo: stesso vnum di zona, altrimenti stesso range (non `0 0`) e stesso nome. Un vnum di
    contenuto gia' usato da un'altra zona, o un range che ne tocca un'altra, **blocca** la zona; una zona gia'
    presente e' `skip` oppure, con `onConflict=replace`, `replace`.
    """
    accepted: list[ZonePlan] = []
    for zp in plans:
        rng = (zp.bottom, zp.top)
        match = next((z for z in index.zones if z.vnum == zp.target_vnum), None) or next(
            (z for z in index.zones if rng != (0, 0) and (z.bottom_vnum, z.top_vnum) == rng and z.name == zp.src.zone.name), None
        )
        zp.existing = match
        blockers: list[ConvertConflict] = []
        for other in index.zones:
            if other is not match and _overlaps(rng, (other.bottom_vnum, other.top_vnum)):
                blockers.append(ConvertConflict(zone_vnum=zp.src.zone.vnum, kind="range_overlap", other_zone=other.name))
        for earlier in accepted:
            if _overlaps(rng, (earlier.bottom, earlier.top)):
                blockers.append(ConvertConflict(zone_vnum=zp.src.zone.vnum, kind="range_overlap", other_zone=earlier.src.zone.name))
        mine = match.id if match is not None else None
        for kind, table in (("room", index.rooms), ("mob", index.mobs), ("object", index.objects)):
            for vnum in _new_vnums(zp, kind):
                owner = table.get(vnum)
                owner_zone = owner[1] if isinstance(owner, tuple) else owner
                if owner_zone is not None and owner_zone != mine:
                    other = next((z.name for z in index.zones if z.id == owner_zone), None)
                    blockers.append(
                        ConvertConflict(zone_vnum=zp.src.zone.vnum, kind="vnum_taken", entity=kind, vnum=vnum, other_zone=other)
                    )
        zp.conflicts = blockers
        if blockers:
            zp.action = "blocked"
        elif match is not None:
            resolved = plan.on_conflict == "replace"
            zp.conflicts.append(ConvertConflict(zone_vnum=zp.src.zone.vnum, kind="zone_exists", other_zone=match.name, resolved=resolved))
            zp.action = "replace" if resolved else "skip"
        else:
            zp.action = "create"
        if zp.written:
            accepted.append(zp)


def _new_vnums(zp: ZonePlan, kind: str) -> list[int]:
    """I vnum di arrivo dei contenuti di tipo `kind` della zona."""
    items = {"room": zp.src.rooms, "mob": zp.src.mobs, "object": zp.src.objects}[kind]
    return [i.vnum + zp.offset for i in items]
