"""`BasedMudAdapter`: il mondo BasedMud/ROM/QuickMUD su file `.are` (libreria `rom_lib`).

Configurazione (`webeditor_worlds`)::

    - {id: basedmud, kind: basedmud, name: BasedMud, path: /percorso/a/basedmud, read_only: false}

`path` e' la radice di basedmud oppure la sua cartella `area/` (quella con `area.lst`). Convenzioni:

- **zona** = un file `.are` con intestazione; `id == vnum ==` vnum minimo dell'area (negativo `-(posizione)` se l'area
  non ha un range numerico univoco); `enabled` = il file e' in `area.lst`;
- stanza/mob/oggetto: `id == vnum` (globalmente univoco); uscita `vnum*10 + direzione`; extra description di stanza
  `vnum*1000 + posizione`; reset = posizione nello script (commenti esclusi);
- cio' che non ha un campo neutro e' in `extra` (vedi `mapping.py` e `docs/adapters/index.md`).

Le scritture riscrivono solo il file toccato con `preserve=True`: gli elementi non modificati restano byte per byte.
"""

from pachimudeditor_adapter_basedmud.meta import MetaMixin
from pachimudeditor_adapter_basedmud.prototypes import PrototypesMixin
from pachimudeditor_adapter_basedmud.rooms import RoomsMixin
from pachimudeditor_adapter_basedmud.zones import ZonesMixin
from pachimudeditor.sdk import AdapterCapabilities, AdapterInfo, ResourceInfo, WorldAdapter
from pachimudeditor_adapter_basedmud.fields import EXTRA, FLAG_LISTS, UNSUPPORTED
from pachimudeditor.sdk import describe_resource, finish_resource
from pachimudeditor.common.adapters.models import (
    ExitIn,
    ExitOut,
    ExtraDescriptionIn,
    ExtraDescriptionOut,
    MobIn,
    MobOut,
    ObjectIn,
    ObjectOut,
    ResetCommandIn,
    ResetCommandOut,
    RoomDetail,
    RoomIn,
    ZoneIn,
    ZoneOut,
)


def _finish(info: ResourceInfo) -> ResourceInfo:
    """Completa la risorsa con tabelle dei flag ROM, campi non supportati e chiavi di `extra`."""
    enums = {name: key for (res, name), key in FLAG_LISTS.items() if res == info.type}
    return finish_resource(info, EXTRA.get(info.type, []), enums=enums, unsupported=UNSUPPORTED.get(info.type, frozenset()))


class BasedMudAdapter(ZonesMixin, RoomsMixin, PrototypesMixin, MetaMixin, WorldAdapter):
    """Adapter dei file `.are` di BasedMud (vedi docstring del modulo)."""

    def capabilities(self) -> AdapterCapabilities:
        """Nucleo + script di reset + extra description; niente panoramica, istanze, giocatori, trasferimento, contenuti."""
        return AdapterCapabilities(
            read_only=self.config.read_only,
            supports_reset_scripts=True,
            supports_extra_descriptions=True,
        )

    def describe(self) -> AdapterInfo:
        """Descrittori dei campi (dai DTO) con i flag collegati alle tabelle ROM e il campo `extra`."""
        resources = [
            describe_resource("zone", ZoneOut, ZoneIn),
            describe_resource("room", RoomDetail, RoomIn, skip=frozenset({"extra", "exits", "extra_descriptions"})),
            describe_resource("exit", ExitOut, ExitIn, read_only=frozenset({"id", "room_id"})),
            describe_resource("extra_description", ExtraDescriptionOut, ExtraDescriptionIn),
            describe_resource("mob", MobOut, MobIn),
            describe_resource("object", ObjectOut, ObjectIn),
            describe_resource("reset_command", ResetCommandOut, ResetCommandIn),
        ]
        return AdapterInfo(
            id=self.config.id,
            kind=self.config.kind,
            name=self.config.name or "BasedMud",
            capabilities=self.capabilities(),
            resources=[_finish(r) for r in resources],
        )
