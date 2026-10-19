"""`DikumodAdapter`: il mondo "Diku Modificato" (Diku molto modificato) sui file dati di `lib/` (libreria `dikumod_lib`).

Configurazione (`webeditor_worlds`)::

    - {id: dikumod, kind: dikumod, name: "Diku Modificato", path: /percorso/a/dikumod2/lib, params: {variant: dikumod2, data_prefix: miomondo}}
    - {id: dikumod-rw, kind: dikumod, path: /percorso/a/dikumod2, read_only: false}   # scrittura abilitata esplicitamente

`path` e' la cartella `lib/` (quella con `dikumoddata.wld`) oppure la sua radice. **`read_only` vale `true` se non e'
specificato** (i file monolitici sono fragili: il gioco legge mob/oggetti per offset; scrivere con il gioco acceso lo
rompe). `params.variant` (`dikumod`|`dikumod2`) e' facoltativo e solo informativo. `params.data_prefix` (facoltativo, default
`dikumoddata`; solo `[A-Za-z0-9_-]`) e' il prefisso dei file dati: `<prefisso>.wld`, `.mob`, `.obj`, `.zon`, `.shp`, `.gui`.

Convenzioni (dettagli in `docs/adapters/index.md`):

- **zona**: `id == vnum ==` posizione nel `dikumoddata.zon` (il `#N` non e' univoco, e' in `extra.numRaw`); `topVnum` e' il
  `top` del file, `bottomVnum` e' derivato (`top` della precedente + 1; `0-0` se la zona non possiede vnum);
- stanza/mob/oggetto: `id == vnum`, `zoneId` derivato dal vnum; uscita `vnum*10 + direzione`; extra description di
  stanza `vnum*1000 + posizione`; comando di reset = posizione tra i comandi;
- i file `rooms/<vnum>`, `objects/<vnum>`, `zones/<n>.zon` prevalgono sui file principali, in lettura e in scrittura;
- record corrotti (33 mob): visibili con `extra.corrupted`, non modificabili.
"""

from __future__ import annotations

from pachimudeditor_adapter_dikumod.meta import MetaMixin
from pachimudeditor_adapter_dikumod.prototypes import PrototypesMixin
from pachimudeditor_adapter_dikumod.rooms import RoomsMixin
from pachimudeditor_adapter_dikumod.zones import ZonesMixin
from pachimudeditor.sdk import AdapterCapabilities, AdapterInfo, ResourceInfo, WorldAdapter
from pachimudeditor_adapter_dikumod.fields import EXTRA, FLAG_LISTS, UNSUPPORTED
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
    """Completa la risorsa con tabelle dei flag, campi non supportati, `bottomVnum` derivato e chiavi di `extra`."""
    enums = {name: key for (res, name), key in FLAG_LISTS.items() if res == info.type}
    zone = info.type == "zone"
    return finish_resource(
        info,
        EXTRA.get(info.type, []),
        enums=enums,
        unsupported=UNSUPPORTED.get(info.type, frozenset()),
        read_only=frozenset({"bottomVnum"}) if zone else frozenset(),
        create_at_end=zone,
    )


class DikumodAdapter(ZonesMixin, RoomsMixin, PrototypesMixin, MetaMixin, WorldAdapter):
    """Adapter dei file dati di Diku Modificato (vedi docstring del modulo)."""

    def capabilities(self) -> AdapterCapabilities:
        """Nucleo + script di reset + extra description; niente panoramica, istanze, giocatori, trasferimento, contenuti."""
        return AdapterCapabilities(read_only=self.read_only, supports_reset_scripts=True, supports_extra_descriptions=True)

    def describe(self) -> AdapterInfo:
        """Descrittori dei campi (dai DTO) con i flag collegati alle tabelle Diku Modificato e il campo `extra`."""
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
            name=self.config.name or f"Diku Modificato ({self.variant})",
            capabilities=self.capabilities(),
            params={"variant": self.variant, "data_prefix": self.store.prefix},
            resources=[_finish(r) for r in resources],
        )
