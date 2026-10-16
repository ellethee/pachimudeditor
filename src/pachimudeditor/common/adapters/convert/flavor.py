"""Architettura dei convertitori reali: un "sapore" per mondo, una coppia = due sapori composti.

Ogni sapore (`Flavor`) sa tradurre le entita' del *proprio* mondo da/verso il **pivot**, cioe' il modello neutro con
la semantica di pachimud/ROM (vedi `tables.py`). Il convertitore della coppia A -> B e' `ComposedConverter(A, B)`:
`B.from_pivot(A.to_pivot(x))`. Cosi' con N mondi servono N sapori, non N*(N-1) convertitori, e ogni decisione di
mappatura sta in un posto solo. Il prezzo: cio' che il pivot non puo' rappresentare (negozi, spec_fun, affect dei mob,
...) si perde passando da qui, anche tra due mondi che lo avrebbero entrambi; la perdita e' sempre riportata.
"""

from pachimudeditor.common.adapters.convert.converter import ConvertContext, Converted, PairConverter, extra_dropped, to_in
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
    ZoneOut,
)


class Flavor:
    """Traduzione delle entita' di un tipo di mondo da/verso il pivot. I default sono l'identita' (nucleo copiato)."""

    kind: str = "*"
    door_state_in_resets: bool = False

    # --- verso il pivot
    def zone_to_pivot(self, z: ZoneOut, ctx: ConvertContext) -> Converted[ZoneIn]:
        """Zona del mondo -> zona pivot."""
        values = to_in(ZoneIn, z, min_level=max(z.min_level, 1), max_level=max(z.max_level, z.min_level, 1))
        return Converted(ZoneIn(**values), extra_dropped("zone", z.extra, "info"))

    def room_to_pivot(self, r: RoomOut, ctx: ConvertContext) -> Converted[RoomIn]:
        """Stanza del mondo -> stanza pivot."""
        return Converted(RoomIn(**to_in(RoomIn, r, zone_id=0)), extra_dropped("room", r.extra, "info"))

    def exit_to_pivot(self, e: ExitOut, ctx: ConvertContext) -> Converted[ExitIn]:
        """Uscita del mondo -> uscita pivot."""
        return Converted(ExitIn(**to_in(ExitIn, e, target_room_id=None)), extra_dropped("exit", e.extra, "info"))

    def mob_to_pivot(self, m: MobOut, ctx: ConvertContext) -> Converted[MobIn]:
        """Mob del mondo -> mob pivot."""
        return Converted(MobIn(**to_in(MobIn, m, zone_id=0)), extra_dropped("mob", m.extra, "dropped"))

    def object_to_pivot(self, o: ObjectOut, ctx: ConvertContext) -> Converted[ObjectIn]:
        """Oggetto del mondo -> oggetto pivot."""
        return Converted(ObjectIn(**to_in(ObjectIn, o, zone_id=0)), extra_dropped("object", o.extra, "dropped"))

    def reset_to_pivot(self, c: ResetCommandOut, ctx: ConvertContext) -> Converted[ResetCommandIn]:
        """Comando di reset del mondo -> comando pivot (`None` = non rappresentabile)."""
        return Converted(ResetCommandIn(**to_in(ResetCommandIn, c, comment=None, if_value=None)))

    # --- dal pivot
    def zone_from_pivot(self, z: ZoneIn, ctx: ConvertContext) -> Converted[ZoneIn]:
        """Zona pivot -> zona del mondo."""
        return Converted(z)

    def room_from_pivot(self, r: RoomIn, ctx: ConvertContext) -> Converted[RoomIn]:
        """Stanza pivot -> stanza del mondo."""
        return Converted(r)

    def exit_from_pivot(self, e: ExitIn, ctx: ConvertContext) -> Converted[ExitIn]:
        """Uscita pivot -> uscita del mondo."""
        return Converted(e)

    def mob_from_pivot(self, m: MobIn, ctx: ConvertContext) -> Converted[MobIn]:
        """Mob pivot -> mob del mondo."""
        return Converted(m)

    def object_from_pivot(self, o: ObjectIn, ctx: ConvertContext) -> Converted[ObjectIn]:
        """Oggetto pivot -> oggetto del mondo."""
        return Converted(o)

    def reset_from_pivot(self, c: ResetCommandIn, ctx: ConvertContext) -> Converted[ResetCommandIn]:
        """Comando pivot -> comando del mondo (`None` = non rappresentabile)."""
        return Converted(c)


def _then(first: Converted, step) -> Converted:  # type: ignore[no-untyped-def, type-arg]
    """Applica `step` al valore di `first` (se c'e') sommando le perdite."""
    if first.value is None:
        return first
    second = step(first.value)
    return Converted(second.value, [*first.losses, *second.losses])


class ComposedConverter(PairConverter):
    """`target.from_pivot(source.to_pivot(x))` per ogni tipo di entita'."""

    def __init__(self, source: Flavor, target: Flavor) -> None:
        """Compone i due sapori."""
        self.source_kind = source.kind
        self.target_kind = target.kind
        self.door_state_in_resets = target.door_state_in_resets
        self._s, self._t = source, target

    def zone(self, zone: ZoneOut, ctx: ConvertContext) -> Converted[ZoneIn]:
        """Zona via pivot."""
        return _then(self._s.zone_to_pivot(zone, ctx), lambda v: self._t.zone_from_pivot(v, ctx))

    def room(self, room: RoomOut, ctx: ConvertContext) -> Converted[RoomIn]:
        """Stanza via pivot."""
        return _then(self._s.room_to_pivot(room, ctx), lambda v: self._t.room_from_pivot(v, ctx))

    def exit(self, ex: ExitOut, ctx: ConvertContext) -> Converted[ExitIn]:
        """Uscita via pivot."""
        return _then(self._s.exit_to_pivot(ex, ctx), lambda v: self._t.exit_from_pivot(v, ctx))

    def mob(self, mob: MobOut, ctx: ConvertContext) -> Converted[MobIn]:
        """Mob via pivot."""
        return _then(self._s.mob_to_pivot(mob, ctx), lambda v: self._t.mob_from_pivot(v, ctx))

    def object(self, obj: ObjectOut, ctx: ConvertContext) -> Converted[ObjectIn]:
        """Oggetto via pivot."""
        return _then(self._s.object_to_pivot(obj, ctx), lambda v: self._t.object_from_pivot(v, ctx))

    def reset(self, command: ResetCommandOut, ctx: ConvertContext) -> Converted[ResetCommandIn]:
        """Comando di reset via pivot."""
        return _then(self._s.reset_to_pivot(command, ctx), lambda v: self._t.reset_from_pivot(v, ctx))
