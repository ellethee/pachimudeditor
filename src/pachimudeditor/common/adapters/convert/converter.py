"""Convertitori di coppia: come un'entita' di un mondo diventa l'entita' equivalente di un altro.

Un `PairConverter` e' **puro** (nessun I/O, nessuna scrittura): riceve i DTO `*Out` letti dall'adapter sorgente e
restituisce i DTO `*In` da scrivere sull'adapter di arrivo, piu' le `LossItem` di tutto cio' che non e' passato
tale e quale. I vnum restano quelli **sorgente**: li riscrive il motore (`engine`) con la tabella di rimappatura.

Registro: `register_converter(c)` associa `(source_kind, target_kind)`; `get_converter` restituisce quello
specifico oppure `GenericConverter` (campi del nucleo copiati cosi' come sono, `extra` scartato con un rapporto).
I convertitori reali non sono nel core: ogni adapter porta il "sapore" (`AdapterPlugin.flavor`) che traduce il proprio
mondo da/verso il pivot, e `get_converter` compone la coppia con i sapori degli adapter installati
(`common.adapters.convert.flavor`).
"""

from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

from pachimudeditor.common.adapters.convert.models import LossEntity, LossItem, Severity
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

T = TypeVar("T")


@dataclass
class Converted(Generic[T]):
    """Esito della conversione di un elemento: il valore (`None` = elemento scartato) e le perdite."""

    value: T | None
    losses: list[LossItem] = field(default_factory=list)


@dataclass
class ConvertContext:
    """Cio' che il convertitore sa del mondo di arrivo (non della sorgente)."""

    target_races: set[str] | None = None
    """Id di razza del mondo di arrivo (`None` o vuoto = sconosciuti: il valore passa invariato)."""
    target_classes: set[str] | None = None


def loss(entity: LossEntity, field_name: str, code: str, severity: Severity = "info", **params: Any) -> LossItem:
    """Una voce di perdita (vnum/zona/indice li imposta il motore)."""
    return LossItem(entity=entity, field=field_name, code=code, severity=severity, params=params)


def to_in(model: type[BaseModel], source: BaseModel, **overrides: Any) -> dict[str, Any]:
    """I valori per costruire `model` (un DTO `*In`) dai campi omonimi di `source` (un DTO `*Out`); `extra` escluso."""
    names = [n for n in model.model_fields if n != "extra" and hasattr(source, n)]
    return {**{n: getattr(source, n) for n in names}, **overrides}


def extra_dropped(entity: LossEntity, extra: dict[str, Any], severity: Severity, *, keep: frozenset[str] = frozenset()) -> list[LossItem]:
    """Una perdita `extra_dropped` con le chiavi di `extra` che il mondo di arrivo non puo' ricevere."""
    keys = sorted(k for k, v in extra.items() if k not in keep and v not in (None, [], {}, "", False))
    return [loss(entity, "extra", "extra_dropped", severity, keys=", ".join(keys))] if keys else []


class PairConverter:
    """Convertitore da un `kind` di mondo a un altro. Le sottoclassi ridefiniscono i metodi per entita'."""

    source_kind: str = "*"
    target_kind: str = "*"
    generic: bool = False
    """`True` per il convertitore di ripiego (nessuna regola specifica per la coppia)."""
    door_state_in_resets: bool = False
    """Il mondo di arrivo tiene lo stato aperta/chiusa delle porte nei reset `D` (BasedMud, Diku Modificato): il motore ne
    aggiunge uno per ogni uscita chiusa/serrata che lo script convertito non copre."""

    def zone(self, zone: ZoneOut, ctx: ConvertContext) -> Converted[ZoneIn]:
        """La zona di arrivo (`extra` scartato)."""
        values = to_in(ZoneIn, zone, min_level=max(zone.min_level, 1), max_level=max(zone.max_level, zone.min_level, 1))
        return Converted(ZoneIn(**values), extra_dropped("zone", zone.extra, "info"))

    def room(self, room: RoomOut, ctx: ConvertContext) -> Converted[RoomIn]:
        """La stanza di arrivo (`zoneId` provvisorio 0: lo imposta il motore)."""
        return Converted(RoomIn(**to_in(RoomIn, room, zone_id=0)), extra_dropped("room", room.extra, "info"))

    def exit(self, ex: ExitOut, ctx: ConvertContext) -> Converted[ExitIn]:
        """L'uscita di arrivo (la destinazione la imposta il motore dal vnum)."""
        return Converted(ExitIn(**to_in(ExitIn, ex, target_room_id=None)), extra_dropped("exit", ex.extra, "info"))

    def mob(self, mob: MobOut, ctx: ConvertContext) -> Converted[MobIn]:
        """Il mob di arrivo."""
        return Converted(MobIn(**to_in(MobIn, mob, zone_id=0)), extra_dropped("mob", mob.extra, "dropped"))

    def object(self, obj: ObjectOut, ctx: ConvertContext) -> Converted[ObjectIn]:
        """L'oggetto di arrivo."""
        return Converted(ObjectIn(**to_in(ObjectIn, obj, zone_id=0)), extra_dropped("object", obj.extra, "dropped"))

    def reset(self, command: ResetCommandOut, ctx: ConvertContext) -> Converted[ResetCommandIn]:
        """Il comando di reset di arrivo (`ifValue`/commento/`extra` scartati)."""
        losses: list[LossItem] = []
        if command.comment:
            losses.append(loss("reset", "comment", "field_dropped", "info", name="comment"))
        if command.if_value not in (None, 0, 1):
            losses.append(loss("reset", "if_value", "field_dropped", "info", name="ifValue"))
        losses += extra_dropped("reset", command.extra, "info")
        values = to_in(ResetCommandIn, command, comment=None, if_value=None)
        return Converted(ResetCommandIn(**values), losses)


class GenericConverter(PairConverter):
    """Ripiego per le coppie senza regole proprie: nucleo copiato, `extra` scartato con un rapporto."""

    generic = True

    def __init__(self, source_kind: str, target_kind: str) -> None:
        """Il ripiego per la coppia `(source_kind, target_kind)`."""
        self.source_kind = source_kind
        self.target_kind = target_kind


_CONVERTERS: dict[tuple[str, str], PairConverter] = {}


def register_converter(converter: PairConverter) -> None:
    """Registra il convertitore della coppia `(converter.source_kind, converter.target_kind)` (sovrascrive)."""
    _CONVERTERS[(converter.source_kind, converter.target_kind)] = converter


def get_converter(source_kind: str, target_kind: str) -> PairConverter:
    """Il convertitore specifico della coppia, oppure `GenericConverter`."""
    found = _CONVERTERS.get((source_kind, target_kind))
    if found is None and source_kind != target_kind:
        from pachimudeditor.common.adapters import plugins
        from pachimudeditor.common.adapters.convert.flavor import ComposedConverter

        source, target = plugins.load_flavor(source_kind), plugins.load_flavor(target_kind)
        if source is not None and target is not None:
            found = _CONVERTERS[(source_kind, target_kind)] = ComposedConverter(source, target)
    return found or GenericConverter(source_kind, target_kind)
